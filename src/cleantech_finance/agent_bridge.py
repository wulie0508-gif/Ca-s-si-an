"""Loopback-only case workspace and consent-gated Agent bridge."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import secrets
import threading
import time
from collections.abc import Iterator
from datetime import date, datetime, timezone
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .deal_service import (
    DealConflictError,
    DealIntegrityError,
    DealNotFoundError,
    DealPermissionError,
    DealServiceError,
    DealStore,
)
from .enterprise_evidence import NexSidecarClient
from .enterprise_matching import (
    browse_catalog_resources,
    catalog_summary,
    load_catalog,
    match_catalog,
    suggest_policy_references,
)
from .mentor_matching import (
    browse_mentor_catalog,
    load_mentor_catalog,
    match_mentor_candidates,
)
from .policy_update import load_policy_update_feed
from .valuation import ValuationError
from .valuation_workflow import (
    ValuationWorkflowError,
    prepare_screen_inputs,
)
from .workspace_service import (
    MAX_TOTAL_FILE_BYTES,
    CaseWorkspaceStore,
    MaterialValidationError,
)

DEFAULT_CONSENT_TTL_SECONDS = 30 * 60
DEFAULT_AUTHORIZATION_REQUEST_TTL_SECONDS = 5 * 60
MAX_REQUEST_BYTES = 128 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_TOTAL_FILE_BYTES + 1024 * 1024
POLICY_SCOPES = frozenset({"policy:read", "policy:match", "policy:reference"})
RESOURCE_SCOPES = frozenset({"resource:read", "resource:match"})
AGENT_SCOPES = frozenset(
    {
        *POLICY_SCOPES,
        *RESOURCE_SCOPES,
        "case:read",
        "material:read",
        "rag:query",
    }
)
CASE_SCOPES = frozenset({"case:read", "material:read", "rag:query"})
PROFILE_DIMENSIONS = frozenset({"industry", "stage", "need", "technology", "geography", "market"})
WEB_ROOT = Path(__file__).with_name("web")
REPOSITORY_TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates"
PACKAGE_TEMPLATE_ROOT = Path(__file__).with_name("templates")
TEMPLATE_DOWNLOADS = {
    "/templates/course-catalog-template.csv": "course-catalog-template.csv",
    "/templates/mentor-catalog-template.csv": "mentor-catalog-template.csv",
}
LOCAL_FA_ACTOR = {"id": "local-fa-ui", "role": "deal_lead", "type": "human"}
CLIENT_ACTOR_FIELDS = frozenset(
    {
        "actor",
        "actor_id",
        "actor_role",
        "actor_type",
        "role",
        "created_by",
        "entered_by",
        "reviewed_by",
        "approved_by",
        "confirmed_by",
    }
)


def _utc_iso(timestamp: float | None = None) -> str:
    value = datetime.fromtimestamp(
        timestamp if timestamp is not None else time.time(),
        tz=timezone.utc,
    )
    return value.isoformat().replace("+00:00", "Z")


class ConsentRegistry:
    """Keep short-lived consent tokens in memory and audit only fingerprints."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_CONSENT_TTL_SECONDS,
        audit_log: str | Path | None = None,
    ) -> None:
        if ttl_seconds < 60:
            raise ValueError("Consent TTL must be at least 60 seconds")
        self.ttl_seconds = ttl_seconds
        self.audit_log = Path(audit_log) if audit_log else None
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _fingerprint(digest: str) -> str:
        return digest[:12]

    def _audit(self, event: str, record: dict[str, Any]) -> None:
        if self.audit_log is None:
            return
        payload = {
            "event": event,
            "at": _utc_iso(),
            "actor": record["actor"],
            "scopes": sorted(record["scopes"]),
            "case_id": record.get("case_id"),
            "token_fingerprint": self._fingerprint(record["digest"]),
            "expires_at": _utc_iso(record["expires_at"]),
        }
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def issue(
        self,
        *,
        actor: str,
        scopes: set[str],
        acknowledge_human_review: bool,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_actor = actor.strip()
        if not normalized_actor or len(normalized_actor) > 120:
            raise ValueError("actor is required and must be at most 120 characters")
        if not acknowledge_human_review:
            raise ValueError("Human-review boundary must be acknowledged")
        if not scopes:
            raise ValueError("At least one Agent scope must be selected")
        if not scopes.issubset(AGENT_SCOPES):
            raise ValueError("Unknown consent scope")
        normalized_case_id = str(case_id or "").strip() or None
        if scopes & CASE_SCOPES and normalized_case_id is None:
            raise ValueError("Case-scoped consent requires case_id")

        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        issued_at = time.time()
        record = {
            "digest": digest,
            "actor": normalized_actor,
            "scopes": frozenset(scopes),
            "case_id": normalized_case_id,
            "issued_at": issued_at,
            "expires_at": issued_at + self.ttl_seconds,
            "revoked": False,
        }
        with self._lock:
            self._records[digest] = record
            self._audit("consent_granted", record)
        return {
            "token": token,
            "token_type": "Bearer",
            "actor": normalized_actor,
            "scopes": sorted(scopes),
            "case_id": normalized_case_id,
            "expires_at": _utc_iso(record["expires_at"]),
            "human_review_required": True,
        }

    def authorize(
        self,
        token: str,
        required_scope: str,
        *,
        case_id: str | None = None,
    ) -> dict[str, Any] | None:
        if required_scope not in AGENT_SCOPES or not token:
            return None
        digest = self._digest(token)
        with self._lock:
            record = self._records.get(digest)
            if record is None or record["revoked"]:
                return None
            if record["expires_at"] <= time.time():
                record["revoked"] = True
                self._audit("consent_expired", record)
                return None
            if required_scope not in record["scopes"]:
                return None
            if required_scope in CASE_SCOPES:
                bound_case_id = record.get("case_id")
                if not bound_case_id:
                    return None
                if case_id is not None and case_id != bound_case_id:
                    return None
            return {
                "actor": record["actor"],
                "scopes": sorted(record["scopes"]),
                "case_id": record.get("case_id"),
                "expires_at": _utc_iso(record["expires_at"]),
                "token_fingerprint": self._fingerprint(digest),
            }

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        digest = self._digest(token)
        with self._lock:
            record = self._records.get(digest)
            if record is None or record["revoked"]:
                return False
            record["revoked"] = True
            self._audit("consent_revoked", record)
            return True


class AgentAuthorizationRegistry:
    """Broker a user-approved Agent handshake without exposing tokens to the UI."""

    def __init__(
        self,
        consent_registry: ConsentRegistry,
        *,
        ttl_seconds: int = DEFAULT_AUTHORIZATION_REQUEST_TTL_SECONDS,
    ) -> None:
        if ttl_seconds < 60:
            raise ValueError("Authorization request TTL must be at least 60 seconds")
        self.consent_registry = consent_registry
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _secret_digest(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def _expire(self, record: dict[str, Any]) -> None:
        if record["status"] == "pending_user" and record["expires_at"] <= time.time():
            record["status"] = "expired"
            record["updated_at"] = time.time()

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "request_id": record["request_id"],
            "actor": record["actor"],
            "purpose": record["purpose"],
            "case_id": record["case_id"],
            "requested_scopes": sorted(record["requested_scopes"]),
            "approved_scopes": sorted(record["approved_scopes"]),
            "status": record["status"],
            "created_at": _utc_iso(record["created_at"]),
            "updated_at": _utc_iso(record["updated_at"]),
            "expires_at": _utc_iso(record["expires_at"]),
            "human_review_required": True,
        }

    def create(
        self,
        *,
        actor: str,
        purpose: str,
        case_id: str | None,
        scopes: set[str],
    ) -> dict[str, Any]:
        normalized_actor = re.sub(r"\s+", " ", actor).strip()
        normalized_purpose = re.sub(r"\s+", " ", purpose).strip()
        if not normalized_actor or len(normalized_actor) > 120:
            raise ValueError("actor is required and must be at most 120 characters")
        if not normalized_purpose or len(normalized_purpose) > 300:
            raise ValueError("purpose is required and must be at most 300 characters")
        if not scopes or not scopes.issubset(AGENT_SCOPES):
            raise ValueError("requested_scopes must contain only supported Agent scopes")
        if scopes & CASE_SCOPES and case_id is None:
            raise ValueError("Case-scoped authorization requires case_id")
        if {"policy:match", "policy:reference"} & scopes and "policy:read" not in scopes:
            raise ValueError("policy:match and policy:reference require policy:read")
        if "resource:match" in scopes and "resource:read" not in scopes:
            raise ValueError("resource:match requires resource:read")
        if "material:read" in scopes and "case:read" not in scopes:
            raise ValueError("material:read also requires case:read")
        request_id = f"auth-{secrets.token_hex(8)}"
        request_secret = secrets.token_urlsafe(32)
        now = time.time()
        record = {
            "request_id": request_id,
            "secret_digest": self._secret_digest(request_secret),
            "actor": normalized_actor,
            "purpose": normalized_purpose,
            "case_id": case_id,
            "requested_scopes": frozenset(scopes),
            "approved_scopes": frozenset(),
            "status": "pending_user",
            "created_at": now,
            "updated_at": now,
            "expires_at": now + self.ttl_seconds,
        }
        with self._lock:
            self._records[request_id] = record
        return {
            **self._public(record),
            "request_secret": request_secret,
            "approval_path": f"/?authorization_request={request_id}",
        }

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            for record in self._records.values():
                self._expire(record)
            records = [
                self._public(record)
                for record in self._records.values()
                if record["status"] == "pending_user"
            ]
        return sorted(records, key=lambda item: item["created_at"])

    def status(self, request_id: str, request_secret: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(request_id)
            if record is None or not secrets.compare_digest(
                record["secret_digest"],
                self._secret_digest(request_secret),
            ):
                raise PermissionError("Authorization request secret is invalid")
            self._expire(record)
            return self._public(record)

    def decide(
        self,
        request_id: str,
        *,
        approve: bool,
        approved_scopes: set[str],
        acknowledge_human_review: bool,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                raise ValueError("Authorization request was not found")
            self._expire(record)
            if record["status"] != "pending_user":
                raise ValueError(f"Authorization request is already {record['status']}")
            if approve:
                if not acknowledge_human_review:
                    raise ValueError("Human-review boundary must be acknowledged")
                if not approved_scopes:
                    raise ValueError("At least one requested scope must be approved")
                if not approved_scopes.issubset(record["requested_scopes"]):
                    raise ValueError("Approved scopes must be a subset of requested scopes")
                if {
                    "policy:match",
                    "policy:reference",
                } & approved_scopes and "policy:read" not in approved_scopes:
                    raise ValueError("policy:match and policy:reference require policy:read")
                if "resource:match" in approved_scopes and "resource:read" not in approved_scopes:
                    raise ValueError("resource:match requires resource:read")
                if "material:read" in approved_scopes and "case:read" not in approved_scopes:
                    raise ValueError("material:read also requires case:read")
                record["approved_scopes"] = frozenset(approved_scopes)
                record["status"] = "approved"
            else:
                record["approved_scopes"] = frozenset()
                record["status"] = "denied"
            record["updated_at"] = time.time()
            return self._public(record)

    def exchange(
        self,
        request_id: str,
        *,
        request_secret: str,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(request_id)
            if record is None or not secrets.compare_digest(
                record["secret_digest"],
                self._secret_digest(request_secret),
            ):
                raise PermissionError("Authorization request secret is invalid")
            self._expire(record)
            if record["status"] != "approved":
                raise ValueError(
                    f"Authorization request cannot be exchanged from {record['status']}"
                )
            grant = self.consent_registry.issue(
                actor=record["actor"],
                scopes=set(record["approved_scopes"]),
                acknowledge_human_review=True,
                case_id=record["case_id"],
            )
            record["status"] = "exchanged"
            record["updated_at"] = time.time()
            return {
                **grant,
                "request_id": request_id,
                "case_id": record["case_id"],
                "purpose": record["purpose"],
            }


class AgentBridgeServer(ThreadingHTTPServer):
    """HTTP server state for the local case workspace and policy resource."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        catalog_path: str | Path,
        *,
        registry: ConsentRegistry,
        workspace_root: str | Path,
        rag_url: str,
        policy_attestation: str | Path | None,
        policy_update_feed: str | Path | None,
        course_catalog: str | Path | None,
        mentor_catalog: str | Path | None,
    ) -> None:
        self.catalog_path = Path(catalog_path).resolve()
        self.policy_attestation = Path(policy_attestation).resolve() if policy_attestation else None
        self.policy_update_feed = Path(policy_update_feed).resolve() if policy_update_feed else None
        self.course_catalog = Path(course_catalog).resolve() if course_catalog else None
        self.mentor_catalog = Path(mentor_catalog).resolve() if mentor_catalog else None
        self.registry = registry
        self.authorization_requests = AgentAuthorizationRegistry(registry)
        self.workspace = CaseWorkspaceStore(workspace_root)
        self.deals = DealStore(Path(workspace_root) / "deal-execution")
        self.rag_url = rag_url.rstrip("/")
        self.rag_client = NexSidecarClient(
            self.rag_url,
            timeout_seconds=90,
        )
        self.rag_health_client = NexSidecarClient(
            self.rag_url,
            # The current local index is large enough that its read-only health
            # aggregation can legitimately take several seconds. Keep this
            # bounded, but avoid presenting a healthy sidecar as unavailable.
            timeout_seconds=8,
        )
        super().__init__(server_address, AgentBridgeHandler)


class AgentBridgeHandler(BaseHTTPRequestHandler):
    """Serve the local workbench and a narrow agent contract."""

    server: AgentBridgeServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _send_bytes(
        self,
        payload: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # A browser navigation or a short client timeout can close the local
            # socket after headers are sent. That is not a server failure and
            # should not flood the operator log with request-thread tracebacks.
            return

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self._send_bytes(
            body,
            status=status,
            content_type="application/json; charset=utf-8",
        )

    def _send_error_json(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
    ) -> None:
        self._send_json(
            {"error": code, "message": message},
            status=status,
        )

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            return False
        return parsed.port == self.server.server_port

    def _read_json(self) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            self._send_error_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "json_required",
                "Content-Type must be application/json",
            )
            return None
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_too_large",
                f"Request body must not exceed {MAX_REQUEST_BYTES} bytes",
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body is not valid UTF-8 JSON",
            )
            return None
        if not isinstance(payload, dict):
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "object_required",
                "JSON root must be an object",
            )
            return None
        return payload

    @staticmethod
    def _contains_client_actor(value: Any) -> bool:
        if isinstance(value, dict):
            if CLIENT_ACTOR_FIELDS.intersection(value):
                return True
            return any(AgentBridgeHandler._contains_client_actor(item) for item in value.values())
        if isinstance(value, list):
            return any(AgentBridgeHandler._contains_client_actor(item) for item in value)
        return False

    def _local_fa_actor(self, payload: dict[str, Any]) -> dict[str, str]:
        if self._contains_client_actor(payload):
            raise DealPermissionError(
                "Client-supplied actor or role fields are not accepted; "
                "local UI actions use the server-owned FA identity"
            )
        return dict(LOCAL_FA_ACTOR)

    def _idempotency_key(self, payload: dict[str, Any]) -> str:
        header_value = str(self.headers.get("Idempotency-Key") or "").strip()
        body_value = str(payload.get("idempotency_key") or "").strip()
        if header_value and body_value and header_value != body_value:
            raise DealConflictError(
                "Idempotency-Key header conflicts with idempotency_key body field"
            )
        value = header_value or body_value
        if not value:
            raise DealServiceError("Idempotency-Key header is required")
        return value

    @staticmethod
    def _positive_integer(payload: dict[str, Any], field: str) -> int:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise DealServiceError(f"{field} must be a positive integer")
        return value

    def _send_deal_error(self, error: Exception) -> None:
        if isinstance(error, DealNotFoundError):
            status = HTTPStatus.NOT_FOUND
            code = "deal_resource_not_found"
        elif isinstance(error, DealConflictError):
            status = HTTPStatus.CONFLICT
            code = "deal_conflict"
        elif isinstance(error, DealPermissionError):
            status = HTTPStatus.FORBIDDEN
            code = "deal_permission_denied"
        elif isinstance(error, DealIntegrityError):
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            code = "deal_integrity_failure"
        else:
            status = HTTPStatus.BAD_REQUEST
            code = "invalid_deal_request"
        self._send_error_json(status, code, str(error))

    def _validate_workspace_source(
        self,
        payload: dict[str, Any],
        deal: dict[str, Any],
    ) -> None:
        company_id = str(deal.get("company_id") or "").strip()

        def source_objects(value: Any) -> Iterator[dict[str, Any]]:
            if isinstance(value, dict):
                for key, child in value.items():
                    if isinstance(child, dict) and (
                        key == "source" or str(key).endswith("_source")
                    ):
                        yield child
                    yield from source_objects(child)
            elif isinstance(value, list):
                for child in value:
                    yield from source_objects(child)

        for source in source_objects(payload):
            source_id = str(source.get("source_id") or "").strip()
            case_id = str(
                source.get("workspace_case_id") or source.get("case_id") or ""
            ).strip()
            if (
                not case_id
                and source_id.startswith("artifact-")
                and company_id.startswith("case-")
            ):
                case_id = company_id
            if case_id:
                if company_id.startswith("case-") and case_id != company_id:
                    raise MaterialValidationError(
                        "Workspace material source must belong to the deal company case"
                    )
                self.server.workspace.get_case(case_id)
            if source_id.startswith("artifact-"):
                if not case_id:
                    raise MaterialValidationError(
                        "Workspace artifact source requires workspace_case_id"
                    )
                self.server.workspace.get_artifact_text(case_id, source_id)
            if source_id.startswith("material-") and not any(
                item.get("material_id") == source_id for item in deal.get("materials", [])
            ):
                raise MaterialValidationError(
                    "Deal material source_id is not registered on this deal"
                )

    def _read_multipart_case(
        self,
    ) -> tuple[str, str, str, str, str, list[tuple[str, bytes, str]]] | None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            self._send_error_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "multipart_required",
                "Content-Type must be multipart/form-data",
            )
            return None
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_UPLOAD_REQUEST_BYTES:
            self._send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "upload_too_large",
                f"Upload request must not exceed {MAX_UPLOAD_REQUEST_BYTES} bytes",
            )
            return None
        raw = self.rfile.read(length)
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
            )
        except (TypeError, ValueError):
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "invalid_multipart",
                "Upload body is not valid multipart data",
            )
            return None
        if not message.is_multipart():
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "invalid_multipart",
                "Upload body is not valid multipart data",
            )
            return None

        case_name = ""
        declared_need = ""
        owner = ""
        case_type = "unclassified"
        workflow_type = "company_intake"
        files: list[tuple[str, bytes, str]] = []
        for part in message.iter_parts():
            field_name = part.get_param(
                "name",
                header="content-disposition",
            )
            file_name = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if (
                field_name
                in {
                    "case_name",
                    "declared_need",
                    "owner",
                    "case_type",
                    "workflow_type",
                }
                and file_name is None
            ):
                if len(payload) > 1024:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_case_metadata",
                        "Case metadata field is too large",
                    )
                    return None
                value = payload.decode("utf-8", errors="replace")
                if field_name == "case_name":
                    case_name = value
                elif field_name == "declared_need":
                    declared_need = value
                elif field_name == "owner":
                    owner = value
                elif field_name == "case_type":
                    case_type = value
                else:
                    workflow_type = value
            elif field_name in {"materials", "files"} and file_name:
                files.append((file_name, payload, part.get_content_type()))
        return case_name, declared_need, owner, case_type, workflow_type, files

    def _bearer_token(self) -> str:
        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        return authorization[len(prefix) :].strip() if authorization.startswith(prefix) else ""

    def _require_scope(
        self,
        scope: str,
        *,
        case_id: str | None = None,
    ) -> dict[str, Any] | None:
        grant = self.server.registry.authorize(
            self._bearer_token(),
            scope,
            case_id=case_id,
        )
        if grant is None:
            self._send_error_json(
                HTTPStatus.FORBIDDEN,
                "consent_required",
                f"Active user consent with {scope} is required",
            )
        return grant

    def _rag_health(self) -> dict[str, Any]:
        status = self.server.rag_health_client.health()
        payload = status.get("payload")
        if not status.get("available") or not isinstance(payload, dict):
            return {
                "available": False,
                "ready_for_query": False,
                "status": "unavailable",
                "url": self.server.rag_url,
                "warning": status.get("warning"),
            }
        rag = payload.get("rag") if isinstance(payload.get("rag"), dict) else {}
        external_research = (
            payload.get("external_research")
            if isinstance(payload.get("external_research"), dict)
            else {}
        )
        return {
            "available": True,
            "ready_for_query": payload.get("ready_for_query") is True,
            "status": str(payload.get("status") or "unknown"),
            "url": self.server.rag_url,
            "documents": int(rag.get("documents") or 0),
            "chunks": int(rag.get("chunks") or 0),
            "embedded_chunks": int(rag.get("embedded_chunks") or 0),
            "embedding_coverage": float(payload.get("embedding_coverage") or 0),
            "external_research_status": external_research.get("status", "unknown"),
            "external_llm_enabled": payload.get("external_llm_enabled") is True,
            "warnings": list(payload.get("warnings") or []),
        }

    def _validated_rag_request(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        question = str(payload.get("question") or "").strip()
        if not question or len(question) > 600:
            raise ValueError("question is required and must be at most 600 characters")
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("case_id is required")
        self.server.workspace.get_case(case_id)
        mode = str(payload.get("mode") or "hybrid")
        if mode not in {"internal", "external", "hybrid"}:
            raise ValueError("mode must be internal, external or hybrid")
        purpose = str(payload.get("purpose") or "enterprise_fact")
        if purpose not in {"enterprise_fact", "industry_background"}:
            raise ValueError("purpose must be enterprise_fact or industry_background")
        try:
            top_k = int(payload.get("top_k") or 5)
        except (TypeError, ValueError) as exc:
            raise ValueError("top_k must be an integer") from exc
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        return {
            "question": question,
            "case_id": case_id,
            "mode": mode,
            "purpose": purpose,
            "top_k": top_k,
            "time_sensitive": payload.get("time_sensitive") is True,
        }

    def _run_rag_query(
        self,
        payload: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        request = self._validated_rag_request(payload)
        result = self.server.rag_client.query(**request)
        if not isinstance(result, dict):
            raise ValueError("RAG sidecar response must be an object")

        evidence: list[dict[str, Any]] = []
        raw_evidence = result.get("evidence")
        if isinstance(raw_evidence, list):
            identity_keys = {"case_id", "entity_id", "subject_entity_id"}

            def has_cross_case_binding(value: object) -> bool:
                if isinstance(value, dict):
                    for key, nested in value.items():
                        if key in identity_keys:
                            if not (
                                isinstance(nested, str) and nested.strip() == request["case_id"]
                            ):
                                return True
                        elif has_cross_case_binding(nested):
                            return True
                elif isinstance(value, list):
                    return any(has_cross_case_binding(item) for item in value)
                return False

            for item in raw_evidence[:10]:
                if not isinstance(item, dict):
                    continue
                returned_entity_id = item.get("entity_id")
                if not (
                    isinstance(returned_entity_id, str)
                    and returned_entity_id.strip() == request["case_id"]
                ):
                    continue
                if has_cross_case_binding(item):
                    continue
                metadata = item.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}

                def safe_text(value: object, limit: int) -> str | None:
                    if not isinstance(value, str):
                        return None
                    normalized = re.sub(r"\s+", " ", value).strip()
                    return normalized[:limit] or None

                source_url = safe_text(item.get("source_url"), 2_000)
                if source_url and urlsplit(source_url).scheme not in {"http", "https"}:
                    source_url = None
                source_catalog_status = safe_text(metadata.get("source_status"), 80)
                if source_catalog_status not in {
                    "approved",
                    "active",
                    "reference_only",
                }:
                    source_catalog_status = "unknown"
                safe_metadata = {
                    "adapter": safe_text(metadata.get("adapter"), 80),
                    "chunk_id": safe_text(metadata.get("chunk_id"), 240),
                    "file_id": safe_text(metadata.get("file_id"), 240),
                    "corpus_role": safe_text(metadata.get("corpus_role"), 80),
                    "source_kind": safe_text(metadata.get("source_kind"), 80),
                    "source_catalog_status": source_catalog_status,
                    "requires_live_official_verification": metadata.get(
                        "requires_live_official_verification"
                    )
                    is True,
                    "candidate_only": True,
                }
                for numeric_key in ("adapter_relevance", "retrieval_score"):
                    numeric_value = metadata.get(numeric_key)
                    if isinstance(numeric_value, (int, float)) and not isinstance(
                        numeric_value, bool
                    ):
                        safe_metadata[numeric_key] = float(numeric_value)
                safe_metadata = {
                    key: value for key, value in safe_metadata.items() if value is not None
                }
                evidence.append(
                    {
                        "claim": safe_text(item.get("claim") or item.get("snippet"), 4_000),
                        "source": safe_text(item.get("source") or item.get("title"), 500),
                        "locator": safe_text(item.get("locator"), 500),
                        "date": safe_text(item.get("date"), 40),
                        "source_url": source_url,
                        "source_level": safe_text(item.get("source_level"), 40),
                        "retrieval_confidence": safe_text(item.get("confidence"), 40),
                        "sha256": safe_text(item.get("sha256"), 128),
                        "evidence_key": safe_text(item.get("evidence_key"), 240),
                        "entity_id": request["case_id"],
                        "review_status": "pending",
                        "is_fact": False,
                        "authority": "reference_suggestion_only",
                        "human_review_required": True,
                        "metadata": safe_metadata,
                    }
                )

        warnings = (
            [item[:500] for item in result.get("warnings", [])[:20] if isinstance(item, str)]
            if isinstance(result.get("warnings"), list)
            else []
        )
        freshness = result.get("data_freshness")
        safe_freshness: dict[str, Any] = {}
        if isinstance(freshness, dict):
            for key in ("as_of", "checked_at"):
                value = freshness.get(key)
                if isinstance(value, str):
                    safe_freshness[key] = value[:80]
            source_dates = freshness.get("source_dates")
            if isinstance(source_dates, list):
                safe_freshness["source_dates"] = [
                    value[:40] for value in source_dates[:20] if isinstance(value, str)
                ]

        result_count = len(evidence)
        self.server.workspace.record_reference_activity(
            request["case_id"],
            result_count=result_count,
            query_status=str(result.get("status") or "unknown"),
        )
        return {
            "status": str(result.get("status") or "unknown")[:80],
            "evidence": evidence,
            "discarded_count": len(result.get("discarded") or [])
            if isinstance(result.get("discarded"), list)
            else 0,
            "warnings": warnings,
            "requires_live_official_search": result.get("requires_live_official_search") is True,
            "data_freshness": safe_freshness,
            "retrieval_confidence": str(result.get("sidecar_confidence") or "unknown")[:40],
            "query": {
                "case_id": request["case_id"],
                "mode": request["mode"],
                "purpose": request["purpose"],
                "time_sensitive": request["time_sensitive"],
            },
            "connection": self._rag_health(),
            "authority": "reference_suggestion_only",
            "usage": "reference_suggestions",
            "human_review_required": True,
            "agent_can_verify": False,
            "actor": actor,
        }

    @staticmethod
    def _validated_profile_tags(payload: object) -> dict[str, list[str]]:
        if not isinstance(payload, dict):
            raise ValueError("profile_tags must be an object")
        unknown = set(payload) - PROFILE_DIMENSIONS
        if unknown:
            raise ValueError(f"Unknown profile dimensions: {', '.join(sorted(unknown))}")
        normalized: dict[str, list[str]] = {}
        for dimension in PROFILE_DIMENSIONS:
            raw = payload.get(dimension, [])
            values = [raw] if isinstance(raw, str) else raw
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise ValueError(f"{dimension} tags must be a string or string array")
            tags = [item.strip() for item in values if item.strip()]
            if len(tags) > 20 or any(len(item) > 80 for item in tags):
                raise ValueError(f"{dimension} accepts at most 20 tags of 80 characters each")
            normalized[dimension] = tags
        return normalized

    def _run_policy_references(
        self,
        payload: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        if self.server.policy_attestation is None:
            raise ValueError("Policy reference confirmation is not configured")
        profile_tags = self._validated_profile_tags(payload.get("profile_tags", {}))
        if not any(profile_tags.values()):
            raise ValueError("At least one policy reference tag is required")
        as_of = str(payload.get("as_of") or date.today().isoformat())
        date.fromisoformat(as_of)
        result = suggest_policy_references(
            self.server.catalog_path,
            profile_tags=profile_tags,
            as_of=as_of,
            attestation_path=self.server.policy_attestation,
        )
        return {
            **result,
            "actor": actor,
            "agent_can_approve": False,
            "agent_can_publish": False,
        }

    @staticmethod
    def _not_connected_resource(category: str) -> dict[str, Any]:
        return {
            "category": category,
            "status": "not_connected",
            "items": [],
            "catalog_metadata": None,
            "authority": "no_catalog_connected",
            "boundaries": {
                "examples_generated": False,
                "matching_performed": False,
                "aggregate_score_produced": False,
                "automatic_assignment": False,
            },
        }

    def _resource_directory(self) -> dict[str, Any]:
        as_of = date.today().isoformat()
        policy_resource = browse_catalog_resources(
            self.server.catalog_path,
            category="policy",
            as_of=as_of,
            attestation_path=self.server.policy_attestation,
        )
        policy_updates = (
            load_policy_update_feed(self.server.policy_update_feed)
            if self.server.policy_update_feed is not None
            else self._not_connected_resource("policy_update")
        )
        policy_resource["updates"] = policy_updates
        course_resource = (
            browse_catalog_resources(
                self.server.course_catalog,
                category="course",
                as_of=as_of,
            )
            if self.server.course_catalog is not None
            else self._not_connected_resource("course")
        )
        mentor_resource = (
            browse_mentor_catalog(self.server.mentor_catalog, as_of=as_of)
            if self.server.mentor_catalog is not None
            else self._not_connected_resource("mentor")
        )
        course_resource["template_url"] = "/templates/course-catalog-template.csv"
        mentor_resource["template_url"] = "/templates/mentor-catalog-template.csv"
        synthetic_count = sum(
            item.get("simulation_only") is True
            for resource in (course_resource, mentor_resource)
            for item in resource.get("items", [])
            if isinstance(item, dict)
        )
        return {
            "schema_version": "1.1.0",
            "status": "ready",
            "evaluated_as_of": as_of,
            "resources": {
                "policy": policy_resource,
                "course": course_resource,
                "mentor": mentor_resource,
            },
            "boundaries": {
                "loopback_only": True,
                "read_only": True,
                "real_catalog_rows_only": synthetic_count == 0,
                "synthetic_fixture_count": synthetic_count,
                "synthetic_fixtures_are_people_or_live_courses": False,
                "examples_generated": False,
                "policy_attestation_is_eligibility_determination": False,
                "official_policy_verification_required": True,
                "mentor_matching_performed": False,
                "mentor_aggregate_score_produced": False,
                "mentor_automatic_assignment": False,
            },
        }

    def _case_profile_tags(self, case_payload: dict[str, Any]) -> dict[str, list[str]]:
        profile_hints = case_payload.get("profile_hints")
        if not isinstance(profile_hints, dict):
            profile_hints = {}
        tags = profile_hints.get("tags")
        if not isinstance(tags, dict):
            tags = {}
        validated = self._validated_profile_tags(tags)
        return {dimension: validated[dimension] for dimension in sorted(validated)}

    def _course_recommendations(
        self,
        profile_tags: dict[str, list[str]],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        if self.server.course_catalog is None:
            return {
                "category": "course",
                "status": "not_connected",
                "matches": [],
                "catalog_metadata": None,
                "authority": "no_catalog_connected",
                "template_url": "/templates/course-catalog-template.csv",
                "boundaries": {
                    "candidate_only": True,
                    "profile_hints_human_confirmed_as_fact": False,
                    "automatic_enrollment": False,
                    "company_score_produced": False,
                    "investment_score_produced": False,
                    "risk_score_produced": False,
                },
            }
        raw = match_catalog(
            self.server.course_catalog,
            category="course",
            profile_tags=profile_tags,
            as_of=as_of,
        )
        matches = []
        for match in raw["matches"]:
            matches.append(
                {
                    **match,
                    "authority": "catalog_tag_relevance_candidate_only",
                    "match_score_authority": ("weighted_exact_catalog_tag_overlap_only"),
                    "not_company_score": True,
                    "not_investment_score": True,
                    "not_credit_score": True,
                    "not_risk_score": True,
                }
            )
        record_count = int(raw["catalog_metadata"]["record_count"])
        if record_count == 0:
            status = "empty_catalog"
        elif not any(profile_tags.values()):
            status = "insufficient_profile"
        else:
            status = raw["status"]
        return {
            "category": "course",
            "status": status,
            "message": raw["message"],
            "matches": matches,
            "excluded": raw["excluded"],
            "catalog_metadata": raw["catalog_metadata"],
            "input_authority": "routing_hint_only",
            "profile_hints_human_confirmed_as_fact": False,
            "authority": "catalog_tag_relevance_candidates_only",
            "template_url": "/templates/course-catalog-template.csv",
            "rules": {
                "tag_weights": raw["rules"]["tag_weights"],
                "minimum_match_score": raw["rules"]["minimum_match_score"],
                "match_score_semantics": ("目录标签相关性；不是企业、投资、信用或风险评分。"),
            },
            "boundaries": {
                "candidate_only": True,
                "profile_hints_human_confirmed_as_fact": False,
                "automatic_enrollment": False,
                "company_score_produced": False,
                "investment_score_produced": False,
                "credit_score_produced": False,
                "risk_score_produced": False,
            },
        }

    def _mentor_recommendations(
        self,
        profile_tags: dict[str, list[str]],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        if self.server.mentor_catalog is None:
            return {
                "category": "mentor",
                "status": "not_connected",
                "candidate_matches": [],
                "catalog_reference": None,
                "authority": "no_catalog_connected",
                "template_url": "/templates/mentor-catalog-template.csv",
                "ordering": "not_ranked",
                "boundaries": {
                    "candidate_only": True,
                    "profile_hints_human_confirmed_as_fact": False,
                    "mentor_ranked": False,
                    "automatic_assignment": False,
                    "automatic_contact": False,
                    "aggregate_score_produced": False,
                },
            }
        raw = match_mentor_candidates(
            {"tags": profile_tags},
            self.server.mentor_catalog,
            as_of=as_of,
        )
        exclusion_reason_counts: dict[str, int] = {}
        for excluded in raw["hard_exclusions"]:
            for reason in excluded["reasons"]:
                code = str(reason["code"])
                exclusion_reason_counts[code] = exclusion_reason_counts.get(code, 0) + 1
        safe_raw = {key: value for key, value in raw.items() if key != "hard_exclusions"}
        return {
            **safe_raw,
            "hard_exclusion_count": len(raw["hard_exclusions"]),
            "hard_exclusion_reason_counts": dict(sorted(exclusion_reason_counts.items())),
            "input_authority": "routing_hint_only",
            "profile_hints_human_confirmed_as_fact": False,
            "template_url": "/templates/mentor-catalog-template.csv",
            "ordering": "mentor_id_casefold_ascending_not_ranked",
            "boundaries": {
                **raw["boundaries"],
                "profile_hints_human_confirmed_as_fact": False,
                "mentor_ranked": False,
                "automatic_assignment": False,
                "automatic_contact": False,
                "aggregate_score_produced": False,
            },
        }

    def _run_resource_match(
        self,
        payload: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        category = str(payload.get("category") or "").strip().casefold()
        if category not in {"course", "mentor"}:
            raise ValueError("category must be course or mentor")
        profile_tags = self._validated_profile_tags(payload.get("profile_tags", {}))
        if not any(profile_tags.values()):
            raise ValueError("At least one resource profile tag is required")
        as_of = str(payload.get("as_of") or date.today().isoformat())
        date.fromisoformat(as_of)
        result = (
            self._course_recommendations(profile_tags, as_of=as_of)
            if category == "course"
            else self._mentor_recommendations(profile_tags, as_of=as_of)
        )
        return {
            **result,
            "actor": actor,
            "authority": "catalog_candidate_match_only",
            "human_confirmation_required": True,
            "agent_can_assign": False,
            "agent_can_contact": False,
            "agent_can_enroll": False,
        }

    def _policy_recommendation_status(self) -> dict[str, Any]:
        summary = catalog_summary(
            self.server.catalog_path,
            category="policy",
            attestation_path=self.server.policy_attestation,
        )
        reference_state = summary["reference_state"]
        status = {
            "ready": "available_for_explicit_reference_query",
            "unconfirmed": "attestation_required",
            "no_current_records": "no_current_entries",
        }[reference_state]
        confirmation = summary.get("reference_confirmation")
        attestation = None
        if isinstance(confirmation, dict):
            attestation = {
                "status": "confirmed_for_reference_only",
                "method": confirmation["method"],
                "catalog_sha256": confirmation["catalog_sha256"],
                "attested_by": confirmation["attested_by"],
                "attested_at": confirmation["attested_at"],
                "authority": "catalog_sha256_attestation_reference_only",
                "not_eligibility_determination": True,
                "official_live_verification_required": True,
            }
        return {
            "category": "policy",
            "status": status,
            "catalog_metadata": {
                "file_name": summary["file_name"],
                "sha256": summary["sha256"],
                "record_count": summary["record_count"],
                "reference_state": reference_state,
                "reference_count": summary["reference_count"],
            },
            "attestation": attestation,
            "explicit_reference_query": {
                "ui_endpoint": "/api/ui/policy-references",
                "agent_endpoint": "/api/agent/policy-references",
            },
            "automatic_reference_query_run": False,
            "profile_tags_used": False,
            "authority": "catalog_and_attestation_status_only",
            "boundaries": {
                "not_eligibility_determination": True,
                "official_live_verification_required": True,
                "automatic_match": False,
                "automatic_reference_query": False,
            },
        }

    def _case_with_resource_recommendations(
        self,
        case_payload: dict[str, Any],
    ) -> dict[str, Any]:
        profile_tags = self._case_profile_tags(case_payload)
        as_of = date.today().isoformat()
        return {
            **case_payload,
            "resource_recommendations": {
                "schema_version": "1.0.0",
                "evaluated_as_of": as_of,
                "input": {
                    "profile_tags": profile_tags,
                    "authority": "routing_hint_only",
                    "human_confirmed_as_fact": False,
                },
                "course": self._course_recommendations(
                    profile_tags,
                    as_of=as_of,
                ),
                "mentor": self._mentor_recommendations(
                    profile_tags,
                    as_of=as_of,
                ),
                "policy": self._policy_recommendation_status(),
                "boundaries": {
                    "candidate_only": True,
                    "profile_hints_human_confirmed_as_fact": False,
                    "agent_can_upgrade_fact": False,
                    "mentor_ranked": False,
                    "automatic_mentor_assignment": False,
                    "automatic_mentor_contact": False,
                    "automatic_policy_reference_query": False,
                    "investment_rating_produced": False,
                    "credit_rating_produced": False,
                    "aggregate_risk_rating_produced": False,
                },
            },
        }

    def _serve_template_download(self, path: str) -> bool:
        file_name = TEMPLATE_DOWNLOADS.get(path)
        if file_name is None:
            return False
        payload = None
        for root in (REPOSITORY_TEMPLATE_ROOT, PACKAGE_TEMPLATE_ROOT):
            try:
                candidate = root / file_name
                if candidate.is_file():
                    payload = candidate.read_bytes()
                    break
            except OSError:
                continue
        if payload is None:
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "template_unavailable",
                "Catalog template is unavailable",
            )
            return True
        self._send_bytes(
            payload,
            content_type="text/csv; charset=utf-8",
            extra_headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
            },
        )
        return True

    @staticmethod
    def _ui_deal_post_route(path: str) -> tuple[str, str | None] | None:
        if path == "/api/ui/deals":
            return "create_deal", None
        patterns = (
            ("confirm_stage", r"/api/ui/deals/([^/]+)/stage"),
            ("create_valuation", r"/api/ui/deals/([^/]+)/valuations"),
            ("update_inputs", r"/api/ui/valuations/([^/]+)/inputs"),
            ("calculate", r"/api/ui/valuations/([^/]+)/calculate"),
            ("review", r"/api/ui/valuations/([^/]+)/review"),
            ("approve_internal", r"/api/ui/valuations/([^/]+)/approve"),
            (
                "approve_internal",
                r"/api/ui/valuations/([^/]+)/approve/internal",
            ),
        )
        for operation, pattern in patterns:
            match = re.fullmatch(pattern, path)
            if match is not None:
                return operation, match.group(1)
        return None

    def _handle_ui_deal_post(
        self,
        route: tuple[str, str | None],
        payload: dict[str, Any],
    ) -> None:
        operation, entity_id = route
        try:
            actor = self._local_fa_actor(payload)
            reason = str(payload.get("reason") or "")
            idempotency_key = self._idempotency_key(payload)
            if operation == "create_deal":
                company_id = str(payload.get("company_id") or "").strip()
                if company_id.startswith("case-"):
                    self.server.workspace.get_case(company_id)
                result = self.server.deals.create_deal(
                    company_id=company_id,
                    buyer=str(payload.get("buyer") or ""),
                    target=str(payload.get("target") or ""),
                    transaction_scope=str(payload.get("transaction_scope") or ""),
                    currency=str(payload.get("currency") or ""),
                    valuation_date=str(payload.get("valuation_date") or ""),
                    owner=str(payload.get("owner") or ""),
                    confidentiality_level=str(payload.get("confidentiality_level") or ""),
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                )
            elif operation == "confirm_stage":
                result = self.server.deals.confirm_stage(
                    str(entity_id),
                    stage=str(payload.get("stage") or ""),
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_revision=self._positive_integer(payload, "expected_revision"),
                    expected_record_hash=str(payload.get("expected_record_hash") or ""),
                )
            elif operation == "create_valuation":
                raw_methods = payload.get("methods")
                if not isinstance(raw_methods, list) or any(
                    not isinstance(method, str) for method in raw_methods
                ):
                    raise DealServiceError("methods must be a string array")
                result = self.server.deals.create_valuation_case(
                    str(entity_id),
                    target_legal_entity=str(payload.get("target_legal_entity") or ""),
                    transaction_scope=str(payload.get("transaction_scope") or ""),
                    valuation_date=str(payload.get("valuation_date") or ""),
                    base_currency=str(payload.get("base_currency") or ""),
                    methods=raw_methods,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_deal_revision=self._positive_integer(
                        payload, "expected_deal_revision"
                    ),
                    expected_deal_hash=str(payload.get("expected_deal_hash") or ""),
                )
            elif operation == "update_inputs":
                valuation = self.server.deals.get_valuation(str(entity_id))
                deal = self.server.deals.get_deal(valuation["deal_id"])
                self._validate_workspace_source(payload, deal)
                inputs = prepare_screen_inputs(payload, valuation)
                result = self.server.deals.update_valuation_inputs(
                    str(entity_id),
                    inputs=inputs,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_version_number=self._positive_integer(
                        payload, "expected_version_number"
                    ),
                    expected_version_hash=str(payload.get("expected_version_hash") or ""),
                )
            elif operation == "calculate":
                allowed_fields = {
                    "reason",
                    "idempotency_key",
                    "expected_version_number",
                    "expected_version_hash",
                }
                unexpected = sorted(set(payload) - allowed_fields)
                if unexpected:
                    raise DealPermissionError(
                        "Calculation payload accepts concurrency metadata only; "
                        f"server-rejected fields: {unexpected}"
                    )
                expected_number = self._positive_integer(payload, "expected_version_number")
                expected_hash = str(payload.get("expected_version_hash") or "")
                result = self.server.deals.calculate_valuation(
                    str(entity_id),
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_version_number=expected_number,
                    expected_version_hash=expected_hash,
                )
            elif operation == "review":
                review = payload.get("review")
                if not isinstance(review, dict):
                    raise DealServiceError("review must be an object")
                result = self.server.deals.review_valuation(
                    str(entity_id),
                    review=review,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_version_number=self._positive_integer(
                        payload, "expected_version_number"
                    ),
                    expected_version_hash=str(payload.get("expected_version_hash") or ""),
                )
            else:
                requested_use = str(payload.get("use") or "internal").casefold()
                if requested_use != "internal":
                    raise DealPermissionError(
                        "External valuation approval is disabled in local mode"
                    )
                result = self.server.deals.approve_valuation(
                    str(entity_id),
                    use="internal",
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    expected_version_number=self._positive_integer(
                        payload, "expected_version_number"
                    ),
                    expected_version_hash=str(payload.get("expected_version_hash") or ""),
                )
        except (
            DealServiceError,
            MaterialValidationError,
            ValuationError,
            ValuationWorkflowError,
        ) as exc:
            self._send_deal_error(exc)
            return
        status = (
            HTTPStatus.CREATED
            if operation
            in {
                "create_deal",
                "create_valuation",
                "update_inputs",
                "calculate",
                "review",
                "approve_internal",
            }
            else HTTPStatus.OK
        )
        self._send_json(result, status=status)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if self._serve_template_download(path):
            return
        if path == "/api/health":
            try:
                summary = catalog_summary(
                    self.server.catalog_path,
                    category="policy",
                    attestation_path=self.server.policy_attestation,
                )
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "catalog_unavailable",
                    str(exc),
                )
                return
            self._send_json(
                {
                    "status": "ok",
                    "service": "cleantech-finance-agent-bridge",
                    "loopback_only": True,
                    "catalog": summary,
                    "rag": self._rag_health(),
                    "workspace": {
                        "case_count": len(self.server.workspace.list_cases()),
                        "material_upload_enabled": True,
                        "automatic_rag_ingestion": False,
                    },
                    "deal_execution": {
                        "deal_count": len(self.server.deals.list_deals()),
                        "server_side_valuation_calculation": True,
                        "external_approval_enabled": False,
                    },
                }
            )
            return
        if path == "/api/ui/resources":
            try:
                resources = self._resource_directory()
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "resource_catalog_unavailable",
                    str(exc),
                )
                return
            self._send_json(resources)
            return
        if path == "/api/agent/resources":
            grant = self._require_scope("resource:read")
            if grant is None:
                return
            try:
                resources = self._resource_directory()
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "resource_catalog_unavailable",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **resources,
                    "access": {
                        "actor": grant["actor"],
                        "expires_at": grant["expires_at"],
                        "authority": "read_only",
                    },
                }
            )
            return
        if path == "/api/agent/manifest":
            self._send_json(
                {
                    "name": "cleantech-finance-case-workspace",
                    "version": "1.2.0",
                    "transport": "loopback_http",
                    "model_api_required": False,
                    "model_execution": "agent_host_owned",
                    "consent": {
                        "request_endpoint": "/api/agent/authorization-requests",
                        "approval_surface": "/api/ui/authorization-requests",
                        "exchange_path_template": (
                            "/api/agent/authorization-requests/{request_id}/exchange"
                        ),
                        "ttl_seconds": self.server.registry.ttl_seconds,
                        "request_ttl_seconds": (self.server.authorization_requests.ttl_seconds),
                        "default_selected": False,
                        "revocable": True,
                        "legacy_direct_endpoint": "/api/consent",
                    },
                    "tools": [
                        {
                            "name": "policy_catalog_status",
                            "method": "GET",
                            "path": "/api/health",
                            "scope": None,
                            "returns_policy_content": False,
                        },
                        {
                            "name": "resource_catalog_read",
                            "method": "GET",
                            "path": "/api/agent/resources",
                            "scope": "resource:read",
                            "result_authority": "read_only_catalog_entries",
                        },
                        {
                            "name": "resource_candidate_match",
                            "method": "POST",
                            "path": "/api/agent/resource-match",
                            "scope": "resource:match",
                            "categories": ["course", "mentor"],
                            "result_authority": "candidate_only",
                        },
                        {
                            "name": "authorization_request",
                            "method": "POST",
                            "path": "/api/agent/authorization-requests",
                            "scope": None,
                            "result_authority": "pending_user_approval",
                        },
                        {
                            "name": "case_workspace_read",
                            "method": "GET",
                            "path_template": "/api/agent/cases/{case_id}",
                            "scope": "case:read",
                            "result_authority": "routing_and_review_state",
                        },
                        {
                            "name": "material_text_read",
                            "method": "GET",
                            "path_template": (
                                "/api/agent/cases/{case_id}/artifacts/{artifact_id}/text"
                            ),
                            "scope": "material:read",
                            "result_authority": "source_material_not_verified_fact",
                        },
                        {
                            "name": "rag_candidate_query",
                            "method": "POST",
                            "path": "/api/agent/rag-query",
                            "scope": "rag:query",
                            "result_authority": "candidate_only",
                        },
                        {
                            "name": "policy_candidate_match",
                            "method": "POST",
                            "path": "/api/agent/policy-match",
                            "scope": "policy:match",
                            "result_authority": "candidate_only",
                        },
                        {
                            "name": "policy_reference_suggestions",
                            "method": "POST",
                            "path": "/api/agent/policy-references",
                            "scope": "policy:reference",
                            "result_authority": "reference_suggestion_only",
                        },
                    ],
                    "boundaries": {
                        "human_review_required": True,
                        "agent_can_approve": False,
                        "agent_can_publish": False,
                        "agent_can_change_catalog": False,
                        "uploaded_materials_auto_ingested_to_rag": False,
                        "interview_statements_prove_truth": False,
                        "aggregate_rating_available": False,
                    },
                }
            )
            return

        if path == "/api/ui/authorization-requests":
            self._send_json({"requests": self.server.authorization_requests.pending()})
            return
        authorization_prefix = "/api/agent/authorization-requests/"
        if path.startswith(authorization_prefix):
            request_id = path.removeprefix(authorization_prefix).strip("/")
            if "/" in request_id:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND,
                    "not_found",
                    "Resource not found",
                )
                return
            try:
                result = self.server.authorization_requests.status(
                    request_id,
                    self.headers.get("X-Authorization-Request-Secret", ""),
                )
            except PermissionError as exc:
                self._send_error_json(
                    HTTPStatus.FORBIDDEN,
                    "authorization_request_denied",
                    str(exc),
                )
                return
            self._send_json(result)
            return

        if path == "/api/ui/cases":
            self._send_json({"cases": self.server.workspace.list_cases()})
            return
        if path == "/api/ui/dashboard":
            self._send_json(self.server.workspace.dashboard())
            return
        if path == "/api/ui/deals":
            try:
                self._send_json({"deals": self.server.deals.list_deals()})
            except DealServiceError as exc:
                self._send_deal_error(exc)
            return
        valuation_export_match = re.fullmatch(
            r"/api/ui/valuations/([^/]+)/export\.xlsx",
            path,
        )
        if valuation_export_match is not None:
            try:
                valuation = self.server.deals.get_valuation(valuation_export_match.group(1))
                deal = self.server.deals.get_deal(valuation["deal_id"])
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                raw_versions = query.get("version_number", query.get("version", []))
                if len(raw_versions) > 1:
                    raise DealServiceError("Select at most one valuation version")
                if raw_versions:
                    try:
                        selected_number = int(raw_versions[0])
                    except ValueError as exc:
                        raise DealServiceError("version_number must be a positive integer") from exc
                    if selected_number < 1:
                        raise DealServiceError("version_number must be a positive integer")
                    selected = next(
                        (
                            version
                            for version in valuation["versions"]
                            if version["version_number"] == selected_number
                        ),
                        None,
                    )
                    if selected is None:
                        raise DealNotFoundError("Valuation version was not found")
                else:
                    selected = valuation["versions"][-1]
                try:
                    from .valuation_export import export_valuation_workbook
                except ImportError:
                    self._send_error_json(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "valuation_export_unavailable",
                        "Valuation workbook exporter is not installed",
                    )
                    return
                workbook = export_valuation_workbook(
                    deal=deal,
                    valuation=valuation,
                    version=selected,
                )
                if not isinstance(workbook, bytes):
                    raise TypeError("Valuation exporter must return bytes")
            except DealServiceError as exc:
                self._send_deal_error(exc)
                return
            except (OSError, TypeError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "valuation_export_failed",
                    str(exc),
                )
                return
            self._send_bytes(
                workbook,
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                extra_headers={
                    "Content-Disposition": (
                        "attachment; filename="
                        f'"{valuation["valuation_id"]}-v'
                        f'{selected["version_number"]:04d}.xlsx"'
                    )
                },
            )
            return
        valuation_detail_match = re.fullmatch(
            r"/api/ui/valuations/([^/]+)",
            path,
        )
        if valuation_detail_match is not None:
            try:
                result = self.server.deals.get_valuation(valuation_detail_match.group(1))
            except DealServiceError as exc:
                self._send_deal_error(exc)
                return
            self._send_json(result)
            return
        deal_valuations_match = re.fullmatch(
            r"/api/ui/deals/([^/]+)/valuations",
            path,
        )
        if deal_valuations_match is not None:
            try:
                result = self.server.deals.list_valuations(deal_valuations_match.group(1))
            except DealServiceError as exc:
                self._send_deal_error(exc)
                return
            self._send_json({"valuations": result})
            return
        deal_detail_match = re.fullmatch(r"/api/ui/deals/([^/]+)", path)
        if deal_detail_match is not None:
            try:
                result = self.server.deals.get_deal(deal_detail_match.group(1))
            except DealServiceError as exc:
                self._send_deal_error(exc)
                return
            self._send_json(result)
            return
        if path == "/api/agent/cases":
            grant = self._require_scope("case:read")
            if grant is None:
                return
            bound_case_id = str(grant["case_id"])
            try:
                bound_case = self.server.workspace.get_case(bound_case_id)
            except MaterialValidationError as exc:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND,
                    "case_not_found",
                    str(exc),
                )
                return
            try:
                bound_case = self._case_with_resource_recommendations(bound_case)
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "resource_recommendations_unavailable",
                    str(exc),
                )
                return
            self._send_json(
                {
                    "cases": [bound_case["dashboard"]],
                    "resource_recommendations": bound_case["resource_recommendations"],
                    "access": {
                        "actor": grant["actor"],
                        "case_id": bound_case_id,
                        "expires_at": grant["expires_at"],
                        "authority": "read_only",
                    },
                }
            )
            return
        ui_case_prefix = "/api/ui/cases/"
        if path.startswith(ui_case_prefix):
            case_id = path.removeprefix(ui_case_prefix)
            try:
                result = self.server.workspace.get_case(case_id)
            except MaterialValidationError as exc:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND,
                    "case_not_found",
                    str(exc),
                )
                return
            try:
                result = self._case_with_resource_recommendations(result)
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "resource_recommendations_unavailable",
                    str(exc),
                )
                return
            self._send_json(result)
            return
        agent_case_prefix = "/api/agent/cases/"
        artifact_text_match = re.fullmatch(
            r"/api/agent/cases/([^/]+)/artifacts/([^/]+)/text",
            path,
        )
        if artifact_text_match is not None:
            grant = self._require_scope(
                "material:read",
                case_id=artifact_text_match.group(1),
            )
            if grant is None:
                return
            try:
                result = self.server.workspace.get_artifact_text(
                    artifact_text_match.group(1),
                    artifact_text_match.group(2),
                )
            except MaterialValidationError as exc:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND,
                    "material_text_unavailable",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **result,
                    "access": {
                        "actor": grant["actor"],
                        "expires_at": grant["expires_at"],
                    },
                }
            )
            return
        if path.startswith(agent_case_prefix):
            case_id = path.removeprefix(agent_case_prefix)
            grant = self._require_scope("case:read", case_id=case_id)
            if grant is None:
                return
            try:
                result = self.server.workspace.get_case(case_id)
            except MaterialValidationError as exc:
                self._send_error_json(
                    HTTPStatus.NOT_FOUND,
                    "case_not_found",
                    str(exc),
                )
                return
            try:
                result = self._case_with_resource_recommendations(result)
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "resource_recommendations_unavailable",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **result,
                    "access": {
                        "actor": grant["actor"],
                        "expires_at": grant["expires_at"],
                        "authority": "read_only",
                    },
                }
            )
            return

        assets = {
            "/": ("agent_bridge.html", "text/html; charset=utf-8"),
            "/index.html": ("agent_bridge.html", "text/html; charset=utf-8"),
            "/agent_bridge.css": ("agent_bridge.css", "text/css; charset=utf-8"),
            "/agent_bridge.js": ("agent_bridge.js", "text/javascript; charset=utf-8"),
        }
        asset = assets.get(path)
        if asset is None:
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Resource not found")
            return
        file_name, content_type = asset
        try:
            payload = (WEB_ROOT / file_name).read_bytes()
        except OSError:
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "asset_unavailable",
                "Workbench asset is unavailable",
            )
            return
        self._send_bytes(payload, content_type=content_type)

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._send_error_json(
                HTTPStatus.FORBIDDEN,
                "origin_rejected",
                "Only same-origin loopback requests are accepted",
            )
            return
        path = urlsplit(self.path).path
        if path.startswith("/api/ui/") and not self.headers.get("Origin"):
            self._send_error_json(
                HTTPStatus.FORBIDDEN,
                "ui_origin_required",
                "Human UI mutations require an explicit same-origin request",
            )
            return

        if path == "/api/ui/cases":
            parsed = self._read_multipart_case()
            if parsed is None:
                return
            case_name, declared_need, owner, case_type, workflow_type, files = parsed
            try:
                result = self.server.workspace.create_case(
                    case_name=case_name,
                    files=files,
                    declared_need=declared_need,
                    owner=owner,
                    case_type=case_type.strip() or "unclassified",
                    workflow_type=workflow_type.strip() or "company_intake",
                )
            except (MaterialValidationError, OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_material_upload",
                    str(exc),
                )
                return
            self._send_json(result, status=HTTPStatus.CREATED)
            return

        ui_rag_prefix = "/api/ui/cases/"
        ui_rag_suffix = "/rag-query"
        is_ui_rag_query = path.startswith(ui_rag_prefix) and path.endswith(ui_rag_suffix)
        ui_deal_route = self._ui_deal_post_route(path)
        decision_match = re.fullmatch(
            r"/api/ui/authorization-requests/([^/]+)/decision",
            path,
        )
        exchange_match = re.fullmatch(
            r"/api/agent/authorization-requests/([^/]+)/exchange",
            path,
        )
        known_paths = {
            "/api/consent",
            "/api/revoke",
            "/api/agent/policy-match",
            "/api/agent/policy-references",
            "/api/agent/resource-match",
            "/api/agent/rag-query",
            "/api/agent/authorization-requests",
            "/api/ui/policy-references",
        }
        if (
            path not in known_paths
            and not is_ui_rag_query
            and ui_deal_route is None
            and decision_match is None
            and exchange_match is None
        ):
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Resource not found")
            return

        if path == "/api/revoke":
            if not self.server.registry.revoke(self._bearer_token()):
                self._send_error_json(
                    HTTPStatus.FORBIDDEN,
                    "invalid_consent",
                    "Active consent token is required",
                )
                return
            self._send_json({"revoked": True})
            return

        payload = self._read_json()
        if payload is None:
            return

        if ui_deal_route is not None:
            self._handle_ui_deal_post(ui_deal_route, payload)
            return

        if path == "/api/ui/policy-references":
            try:
                result = self._run_policy_references(
                    payload,
                    actor="human_ui",
                )
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_policy_reference_request",
                    str(exc),
                )
                return
            self._send_json(result)
            return

        if path == "/api/agent/authorization-requests":
            raw_scopes = payload.get("requested_scopes")
            if not isinstance(raw_scopes, list) or any(
                not isinstance(scope, str) for scope in raw_scopes
            ):
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_authorization_request",
                    "requested_scopes must be a string array",
                )
                return
            case_id = str(payload.get("case_id") or "").strip() or None
            try:
                if case_id:
                    self.server.workspace.get_case(case_id)
                result = self.server.authorization_requests.create(
                    actor=str(payload.get("actor") or ""),
                    purpose=str(payload.get("purpose") or ""),
                    case_id=case_id,
                    scopes=set(raw_scopes),
                )
            except (MaterialValidationError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_authorization_request",
                    str(exc),
                )
                return
            self._send_json(result, status=HTTPStatus.CREATED)
            return

        if decision_match is not None:
            raw_scopes = payload.get("approved_scopes") or []
            if not isinstance(raw_scopes, list) or any(
                not isinstance(scope, str) for scope in raw_scopes
            ):
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_authorization_decision",
                    "approved_scopes must be a string array",
                )
                return
            try:
                result = self.server.authorization_requests.decide(
                    decision_match.group(1),
                    approve=payload.get("approve") is True,
                    approved_scopes=set(raw_scopes),
                    acknowledge_human_review=(payload.get("acknowledge_human_review") is True),
                )
            except ValueError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_authorization_decision",
                    str(exc),
                )
                return
            self._send_json(result)
            return

        if exchange_match is not None:
            try:
                result = self.server.authorization_requests.exchange(
                    exchange_match.group(1),
                    request_secret=self.headers.get(
                        "X-Authorization-Request-Secret",
                        "",
                    ),
                )
            except PermissionError as exc:
                self._send_error_json(
                    HTTPStatus.FORBIDDEN,
                    "authorization_request_denied",
                    str(exc),
                )
                return
            except ValueError as exc:
                self._send_error_json(
                    HTTPStatus.CONFLICT,
                    "authorization_request_not_exchangeable",
                    str(exc),
                )
                return
            self._send_json(result, status=HTTPStatus.CREATED)
            return

        if is_ui_rag_query:
            case_id = path[len(ui_rag_prefix) : -len(ui_rag_suffix)].strip("/")
            payload["case_id"] = case_id
            try:
                result = self._run_rag_query(payload, actor="human_ui")
            except (MaterialValidationError, OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_rag_request",
                    str(exc),
                )
                return
            self._send_json(result)
            return

        if path == "/api/consent":
            allow_read = payload.get("allow_policy_read") is True
            allow_match = payload.get("allow_candidate_match") is True
            allow_reference = payload.get("allow_policy_reference") is True
            allow_case_read = payload.get("allow_case_read") is True
            allow_material_read = payload.get("allow_material_read") is True
            allow_rag_query = payload.get("allow_rag_query") is True
            allow_resource_read = payload.get("allow_resource_read") is True
            allow_resource_match = payload.get("allow_resource_match") is True
            if (allow_match or allow_reference) and not allow_read:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_consent",
                    "Policy matching and reference suggestions require "
                    "explicit policy-read consent",
                )
                return
            if allow_resource_match and not allow_resource_read:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_consent",
                    "Resource candidate matching requires resource-read consent",
                )
                return
            if allow_material_read and not allow_case_read:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_consent",
                    "Material reading also requires explicit case-read consent",
                )
                return
            case_id = str(payload.get("case_id") or "").strip() or None
            if allow_case_read or allow_material_read or allow_rag_query:
                if case_id is None:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_consent",
                        "Case, material and RAG consent require case_id",
                    )
                    return
                try:
                    self.server.workspace.get_case(case_id)
                except MaterialValidationError as exc:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_consent",
                        str(exc),
                    )
                    return
            scopes: set[str] = set()
            if allow_read:
                scopes.add("policy:read")
            if allow_match:
                scopes.add("policy:match")
            if allow_reference:
                scopes.add("policy:reference")
            if allow_case_read:
                scopes.add("case:read")
            if allow_material_read:
                scopes.add("material:read")
            if allow_rag_query:
                scopes.add("rag:query")
            if allow_resource_read:
                scopes.add("resource:read")
            if allow_resource_match:
                scopes.add("resource:match")
            try:
                result = self.server.registry.issue(
                    actor=str(payload.get("actor") or ""),
                    scopes=scopes,
                    acknowledge_human_review=(payload.get("acknowledge_human_review") is True),
                    case_id=case_id,
                )
            except ValueError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_consent",
                    str(exc),
                )
                return
            self._send_json(result, status=HTTPStatus.CREATED)
            return

        if path == "/api/agent/resource-match":
            grant = self._require_scope("resource:match")
            if grant is None:
                return
            try:
                result = self._run_resource_match(
                    payload,
                    actor=grant["actor"],
                )
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_resource_match_request",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **result,
                    "consent": {
                        "expires_at": grant["expires_at"],
                        "token_fingerprint": grant["token_fingerprint"],
                    },
                }
            )
            return

        if path == "/api/agent/rag-query":
            case_id = str(payload.get("case_id") or "").strip()
            grant = self._require_scope("rag:query", case_id=case_id)
            if grant is None:
                return
            try:
                result = self._run_rag_query(
                    payload,
                    actor=grant["actor"],
                )
            except (MaterialValidationError, OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_rag_request",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **result,
                    "consent": {
                        "expires_at": grant["expires_at"],
                        "token_fingerprint": grant["token_fingerprint"],
                    },
                }
            )
            return

        if path == "/api/agent/policy-references":
            grant = self._require_scope("policy:reference")
            if grant is None:
                return
            try:
                result = self._run_policy_references(
                    payload,
                    actor=grant["actor"],
                )
            except (OSError, ValueError) as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_policy_reference_request",
                    str(exc),
                )
                return
            self._send_json(
                {
                    **result,
                    "consent": {
                        "actor": grant["actor"],
                        "expires_at": grant["expires_at"],
                        "token_fingerprint": grant["token_fingerprint"],
                    },
                }
            )
            return

        grant = self._require_scope("policy:match")
        if grant is None:
            return
        try:
            profile_tags = self._validated_profile_tags(payload.get("profile_tags", {}))
            as_of = str(payload.get("as_of") or date.today().isoformat())
            date.fromisoformat(as_of)
            result = match_catalog(
                self.server.catalog_path,
                category="policy",
                profile_tags=profile_tags,
                as_of=as_of,
            )
        except (OSError, ValueError) as exc:
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "invalid_match_request",
                str(exc),
            )
            return
        self._send_json(
            {
                **result,
                "authority": "candidate_only",
                "human_review_required": True,
                "agent_can_approve": False,
                "consent": {
                    "actor": grant["actor"],
                    "expires_at": grant["expires_at"],
                    "token_fingerprint": grant["token_fingerprint"],
                },
            }
        )


def _validate_loopback_host(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
        if address.version == 4 and address.is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("Agent bridge host must be IPv4 loopback or localhost")


def _validate_loopback_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.username or parsed.password:
        raise ValueError("RAG URL must be an unauthenticated local HTTP URL")
    host = parsed.hostname or ""
    if host == "localhost":
        pass
    else:
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError
        except ValueError as exc:
            raise ValueError("RAG URL must use a loopback host") from exc
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("RAG URL must contain only scheme, host and optional port")
    return url.rstrip("/")


def create_agent_bridge_server(
    catalog_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    audit_log: str | Path | None = None,
    consent_ttl_seconds: int = DEFAULT_CONSENT_TTL_SECONDS,
    workspace_root: str | Path = "local-data/agent-workspace",
    rag_url: str = "http://127.0.0.1:8000",
    policy_attestation: str | Path | None = None,
    policy_update_feed: str | Path | None = None,
    course_catalog: str | Path | None = None,
    mentor_catalog: str | Path | None = None,
) -> AgentBridgeServer:
    """Create a bridge server without starting its blocking event loop."""

    _validate_loopback_host(host)
    source = Path(catalog_path)
    if not source.is_file():
        raise ValueError(f"Catalog does not exist: {source}")
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    validated_rag_url = _validate_loopback_url(rag_url)
    if policy_attestation is not None:
        catalog_summary(
            source,
            category="policy",
            attestation_path=policy_attestation,
        )
    if policy_update_feed is not None:
        update_source = Path(policy_update_feed)
        if not update_source.is_file():
            raise ValueError(f"Policy update feed does not exist: {update_source}")
        load_policy_update_feed(update_source)
    if course_catalog is not None:
        course_source = Path(course_catalog)
        if not course_source.is_file():
            raise ValueError(f"Course catalog does not exist: {course_source}")
        load_catalog(course_source)
    if mentor_catalog is not None:
        mentor_source = Path(mentor_catalog)
        if not mentor_source.is_file():
            raise ValueError(f"Mentor catalog does not exist: {mentor_source}")
        load_mentor_catalog(mentor_source)
    registry = ConsentRegistry(
        ttl_seconds=consent_ttl_seconds,
        audit_log=audit_log,
    )
    return AgentBridgeServer(
        (host, port),
        source,
        registry=registry,
        workspace_root=workspace_root,
        rag_url=validated_rag_url,
        policy_attestation=policy_attestation,
        policy_update_feed=policy_update_feed,
        course_catalog=course_catalog,
        mentor_catalog=mentor_catalog,
    )


def serve_agent_bridge(
    catalog_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    audit_log: str | Path | None = None,
    workspace_root: str | Path = "local-data/agent-workspace",
    rag_url: str = "http://127.0.0.1:8000",
    policy_attestation: str | Path | None = None,
    policy_update_feed: str | Path | None = None,
    course_catalog: str | Path | None = None,
    mentor_catalog: str | Path | None = None,
) -> None:
    """Run the consent-gated bridge until interrupted."""

    server = create_agent_bridge_server(
        catalog_path,
        host=host,
        port=port,
        audit_log=audit_log,
        workspace_root=workspace_root,
        rag_url=rag_url,
        policy_attestation=policy_attestation,
        policy_update_feed=policy_update_feed,
        course_catalog=course_catalog,
        mentor_catalog=mentor_catalog,
    )
    url = f"http://{host}:{server.server_port}/"
    summary = catalog_summary(
        catalog_path,
        category="policy",
        attestation_path=policy_attestation,
    )
    update_feed = (
        load_policy_update_feed(policy_update_feed) if policy_update_feed is not None else None
    )
    print(
        json.dumps(
            {
                "url": url,
                "catalog_state": summary["state"],
                "record_count": summary["record_count"],
                "eligible_count": summary["eligible_count"],
                "reference_state": summary["reference_state"],
                "reference_count": summary["reference_count"],
                "policy_update_feed_connected": update_feed is not None,
                "policy_update_candidate_count": (
                    update_feed["catalog_metadata"]["record_count"]
                    if update_feed is not None
                    else 0
                ),
                "course_catalog_connected": course_catalog is not None,
                "mentor_catalog_connected": mentor_catalog is not None,
                "human_review_required": True,
                "workspace_root": str(Path(workspace_root).resolve()),
                "rag_url": rag_url,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
