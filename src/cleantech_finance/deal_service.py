"""Local, auditable deal and valuation-version persistence.

This module stores transaction execution facts and valuation snapshots.  It does
not calculate a formal valuation, infer a transaction stage, or grant an Agent
approval authority.  Callers are expected to authenticate actors before passing
their declared role to this storage boundary.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import threading
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

STORAGE_VERSION = "1.0"
DEAL_ID_PATTERN = re.compile(r"^deal-\d{8}-[a-f0-9]{12}$")
VALUATION_ID_PATTERN = re.compile(r"^valuation-[a-f0-9]{16}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

TRANSACTION_STAGES = frozenset(
    {
        "strategy_and_mandate",
        "industry_research_and_longlist",
        "shortlist_and_preliminary_valuation",
        "initial_contact_and_nda",
        "ioi_loi_and_exclusivity",
        "diligence_and_transaction_structure",
        "signing_approval_and_closing",
        "post_merger_integration",
    }
)
VALUATION_STATUSES = (
    "draft",
    "inputs_incomplete",
    "calculated_screen_grade",
    "fa_reviewed",
    "approved_for_internal_use",
    "approved_for_external_use",
    "superseded",
)
P0_VALUATION_METHODS = frozenset({"trading_comps", "dcf_fcff"})
FA_REVIEW_MISSING_WARNING = "FA review has not been recorded."
HUMAN_ROLES = frozenset(
    {"human", "fa", "fa_analyst", "fa_reviewer", "deal_lead", "approver", "admin"}
)
AGENT_ROLES = frozenset({"agent", "ai_agent", "codex_agent"})
CONFIDENTIALITY_LEVELS = frozenset({"public", "internal", "confidential", "highly_confidential"})
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "human": frozenset({"valuation_input"}),
    "fa": frozenset(
        {
            "create_deal",
            "confirm_stage",
            "create_valuation",
            "valuation_input",
        }
    ),
    "fa_analyst": frozenset(
        {
            "create_deal",
            "create_valuation",
            "valuation_input",
        }
    ),
    "fa_reviewer": frozenset(
        {
            "create_deal",
            "confirm_stage",
            "create_valuation",
            "valuation_input",
            "review_valuation",
            "approve_internal",
            "supersede_valuation",
        }
    ),
    "deal_lead": frozenset(
        {
            "create_deal",
            "confirm_stage",
            "create_valuation",
            "valuation_input",
            "review_valuation",
            "approve_internal",
            "record_decision",
            "supersede_valuation",
        }
    ),
    "approver": frozenset(
        {
            "confirm_stage",
            "review_valuation",
            "approve_internal",
            "approve_external",
            "record_decision",
            "supersede_valuation",
        }
    ),
    "admin": frozenset(
        {
            "create_deal",
            "confirm_stage",
            "create_valuation",
            "valuation_input",
            "review_valuation",
            "approve_internal",
            "approve_external",
            "record_decision",
            "supersede_valuation",
        }
    ),
}


def _calculation_for_lifecycle(
    calculation: Mapping[str, Any] | None,
    *,
    lifecycle_status: str,
) -> dict[str, Any]:
    """Derive decision readiness for a human lifecycle event without recalculating value."""

    if not isinstance(calculation, Mapping):
        raise DealConflictError("Valuation lifecycle action requires a calculation")
    derived = copy.deepcopy(dict(calculation))
    integrity = derived.get("calculation_integrity")
    readiness = derived.get("decision_readiness")
    if not isinstance(integrity, Mapping) or not isinstance(readiness, Mapping):
        raise DealConflictError(
            "Valuation calculation must disclose integrity and decision readiness"
        )
    readiness_value = copy.deepcopy(dict(readiness))
    blockers = [str(item) for item in readiness_value.get("blocking_reasons") or []]
    warnings = [
        str(item)
        for item in readiness_value.get("warnings") or []
        if str(item) != FA_REVIEW_MISSING_WARNING
    ]
    hard_failures = [str(item) for item in derived.get("hard_failures") or []]
    placeholders = [str(item) for item in derived.get("placeholders") or []]
    if hard_failures:
        blockers.append("Valuation contains hard failures.")
    if placeholders:
        blockers.append("Valuation contains placeholders.")
    if integrity.get("status") != "passed":
        blockers.append("Calculation integrity is not passed.")
    blockers = sorted(set(blockers))
    if blockers:
        status = "not_ready"
        human_review_required = True
    elif lifecycle_status == "fa_reviewed":
        status = "fa_reviewed_with_caveats" if warnings else "fa_reviewed"
        human_review_required = bool(warnings)
    elif lifecycle_status == "approved_for_internal_use":
        status = "approved_for_internal_use"
        human_review_required = False
    elif lifecycle_status == "approved_for_external_use":
        status = "approved_for_external_use"
        human_review_required = False
    else:
        raise DealServiceError("Unsupported valuation lifecycle status")
    readiness_value.update(
        {
            "status": status,
            "blocking_reasons": blockers,
            "warnings": sorted(set(warnings)),
            "human_review_required": human_review_required,
        }
    )
    derived["decision_readiness"] = readiness_value
    return derived


def _approval_blockers(calculation: Mapping[str, Any] | None) -> list[str]:
    """Return disclosed conditions that prevent an approval-purpose version."""

    if not isinstance(calculation, Mapping):
        return ["calculation is missing"]
    blockers: list[str] = []
    if calculation.get("hard_failures"):
        blockers.append("hard failures")
    if calculation.get("placeholders"):
        blockers.append("placeholders")
    integrity = calculation.get("calculation_integrity")
    if not isinstance(integrity, Mapping) or integrity.get("status") != "passed":
        blockers.append("calculation integrity")
    readiness = calculation.get("decision_readiness")
    if not isinstance(readiness, Mapping) or readiness.get("blocking_reasons"):
        blockers.append("decision-readiness gaps")
    return blockers


class DealServiceError(ValueError):
    """Base error for an invalid deal-service operation."""


class DealNotFoundError(DealServiceError):
    """Raised when a deal or valuation cannot be found."""


class DealConflictError(DealServiceError):
    """Raised for stale revisions, stale hashes, or idempotency conflicts."""


class DealPermissionError(DealServiceError):
    """Raised when the declared actor cannot perform an operation."""


class DealIntegrityError(DealServiceError):
    """Raised when persisted hashes or version chains do not validate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_digest(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DealServiceError("Payload must contain finite JSON values") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _without_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _record_hash(value: Mapping[str, Any]) -> str:
    return _canonical_digest(_without_hash(value, "record_hash"))


def _version_hash(value: Mapping[str, Any]) -> str:
    return _canonical_digest(_without_hash(value, "version_hash"))


def _text(value: Any, field: str, *, limit: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if not normalized:
        raise DealServiceError(f"{field} is required")
    if len(normalized) > limit:
        raise DealServiceError(f"{field} must be at most {limit} characters")
    return normalized


def _optional_text(value: Any, field: str, *, limit: int = 240) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(normalized) > limit:
        raise DealServiceError(f"{field} must be at most {limit} characters")
    return normalized or None


def _iso_date(value: Any, field: str) -> str:
    normalized = _text(value, field, limit=10)
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise DealServiceError(f"{field} must use YYYY-MM-DD") from exc
    return normalized


def _actor(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise DealPermissionError("actor must be an object")
    actor_id = _text(value.get("id") or value.get("actor_id"), "actor.id", limit=120)
    role = _text(value.get("role"), "actor.role", limit=40).casefold()
    if role in HUMAN_ROLES:
        actor_type = "human"
    elif role in AGENT_ROLES:
        actor_type = "agent"
    else:
        raise DealPermissionError(f"Unsupported actor role: {role}")
    declared_type = str(value.get("type") or value.get("actor_type") or "").casefold()
    if declared_type and declared_type != actor_type:
        raise DealPermissionError("actor type conflicts with actor role")
    return {"id": actor_id, "role": role, "type": actor_type}


def _require_human(actor: Mapping[str, str], action: str) -> None:
    if actor["type"] != "human":
        raise DealPermissionError(f"Only a human actor may {action}")


def _require_capability(actor: Mapping[str, str], capability: str) -> None:
    """Apply business-role separation after the caller authenticates the actor."""

    _require_human(actor, capability.replace("_", " "))
    if capability not in ROLE_CAPABILITIES.get(actor["role"], frozenset()):
        raise DealPermissionError(
            f"Actor role {actor['role']} cannot perform capability {capability}"
        )


def _reason(value: Any) -> str:
    return _text(value, "reason", limit=500)


def _idempotency_key(value: Any) -> str:
    return _text(value, "idempotency_key", limit=200)


def _audit(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    field: str,
    old: Any,
    new: Any,
    reason: str,
    actor: Mapping[str, str],
    at: str | None = None,
) -> dict[str, Any]:
    return {
        "audit_id": f"audit-{secrets.token_hex(8)}",
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "old": copy.deepcopy(old),
        "new": copy.deepcopy(new),
        "reason": reason,
        "actor": dict(actor),
        "time": at or _utc_now(),
    }


class DealStore:
    """Persist deal cockpit records as atomically replaced local JSON files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._write_lock = threading.Lock()

    def _deal_path(self, deal_id: str) -> Path:
        if not DEAL_ID_PATTERN.fullmatch(deal_id):
            raise DealServiceError("Invalid deal identifier")
        path = (self.root / deal_id / "deal.json").resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise DealServiceError("Deal path escapes store root") from exc
        return path

    @staticmethod
    def _public(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in record.items()
            if key not in {"storage_version", "_idempotency"}
        }

    @staticmethod
    def _public_valuation(valuation: Mapping[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(dict(valuation))

    def _validate_record(self, record: Mapping[str, Any]) -> None:
        stored_hash = record.get("record_hash")
        if not isinstance(stored_hash, str) or not secrets.compare_digest(
            stored_hash, _record_hash(record)
        ):
            raise DealIntegrityError("Deal record hash mismatch")
        deal_id = record.get("deal_id")
        for valuation in record.get("valuations", []):
            if valuation.get("deal_id") != deal_id:
                raise DealIntegrityError("Valuation points to a different deal")
            versions = valuation.get("versions")
            if not isinstance(versions, list) or not versions:
                raise DealIntegrityError("Valuation has no version history")
            previous_hash: str | None = None
            for expected_number, version in enumerate(versions, start=1):
                if version.get("version_number") != expected_number:
                    raise DealIntegrityError("Valuation version sequence is invalid")
                if version.get("previous_version_hash") != previous_hash:
                    raise DealIntegrityError("Valuation version hash chain is invalid")
                stored_version_hash = version.get("version_hash")
                if not isinstance(stored_version_hash, str) or not secrets.compare_digest(
                    stored_version_hash, _version_hash(version)
                ):
                    raise DealIntegrityError("Valuation version hash mismatch")
                previous_hash = stored_version_hash
            latest = versions[-1]
            if (
                valuation.get("current_version_number") != latest["version_number"]
                or valuation.get("current_version_hash") != latest["version_hash"]
                or valuation.get("status") != latest["status"]
            ):
                raise DealIntegrityError("Valuation current-version pointer is invalid")

    def _read_path(self, path: Path) -> dict[str, Any]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DealNotFoundError("Deal was not found") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DealIntegrityError("Deal record is unreadable") from exc
        if not isinstance(record, dict):
            raise DealIntegrityError("Deal record root must be an object")
        self._validate_record(record)
        return record

    def _write_record(
        self,
        record: dict[str, Any],
        *,
        expected_disk_hash: str | None,
        creating: bool = False,
    ) -> dict[str, Any]:
        path = self._deal_path(record["deal_id"])
        if creating:
            if path.exists():
                raise DealConflictError("Deal identifier already exists")
            path.parent.mkdir(parents=True, exist_ok=False)
        else:
            current = self._read_path(path)
            if current["record_hash"] != expected_disk_hash:
                raise DealConflictError("Deal changed before it could be written")
        final = copy.deepcopy(record)
        final["record_hash"] = _record_hash(final)
        temporary = path.with_name(f".deal-{secrets.token_hex(6)}.tmp")
        try:
            temporary.write_text(
                json.dumps(final, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return final

    @staticmethod
    def _request_hash(
        operation: str,
        payload: Mapping[str, Any],
        *,
        concurrency: Mapping[str, Any] | None = None,
    ) -> str:
        """Bind an idempotent request to its optimistic-concurrency premise."""

        request: dict[str, Any] = {
            "operation": operation,
            "payload": payload,
        }
        if concurrency is not None:
            request["concurrency"] = concurrency
        return _canonical_digest(request)

    @staticmethod
    def _replay_entry(
        record: Mapping[str, Any],
        *,
        key: str,
        operation: str,
        request_hash: str,
    ) -> Mapping[str, Any] | None:
        entry = record.get("_idempotency", {}).get(_canonical_digest(key))
        if entry is None:
            return None
        if entry.get("operation") != operation or entry.get("request_hash") != request_hash:
            raise DealConflictError("Idempotency key was already used for another request")
        return entry

    @staticmethod
    def _remember(
        record: dict[str, Any],
        *,
        key: str,
        operation: str,
        request_hash: str,
        result: Mapping[str, Any],
    ) -> None:
        record.setdefault("_idempotency", {})[_canonical_digest(key)] = {
            "operation": operation,
            "request_hash": request_hash,
            **copy.deepcopy(dict(result)),
        }

    @staticmethod
    def _check_deal_concurrency(
        record: Mapping[str, Any], expected_revision: int, expected_record_hash: str
    ) -> None:
        if (
            record.get("revision") != expected_revision
            or record.get("record_hash") != expected_record_hash
        ):
            raise DealConflictError("Deal revision or hash is stale")

    @staticmethod
    def _find_valuation_in_record(record: Mapping[str, Any], valuation_id: str) -> dict[str, Any]:
        for valuation in record.get("valuations", []):
            if valuation.get("valuation_id") == valuation_id:
                return valuation
        raise DealNotFoundError("Valuation was not found")

    @staticmethod
    def _check_version_concurrency(
        valuation: Mapping[str, Any], expected_version_number: int, expected_version_hash: str
    ) -> None:
        if (
            valuation.get("current_version_number") != expected_version_number
            or valuation.get("current_version_hash") != expected_version_hash
        ):
            raise DealConflictError("Valuation version number or hash is stale")

    @staticmethod
    def _version_replay(valuation: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
        for version in valuation["versions"]:
            if version["version_number"] == entry.get("version_number") and version[
                "version_hash"
            ] == entry.get("version_hash"):
                return copy.deepcopy(version)
        raise DealIntegrityError("Idempotency result points to a missing version")

    @staticmethod
    def _audit_version_projection(version: Mapping[str, Any]) -> dict[str, Any]:
        """Retain the changed snapshot, not only a pointer to that snapshot."""

        return {
            field: copy.deepcopy(version.get(field))
            for field in (
                "version_number",
                "version_hash",
                "status",
                "inputs",
                "calculation",
                "review",
                "approvals",
            )
        }

    def _find_valuation(self, valuation_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not VALUATION_ID_PATTERN.fullmatch(valuation_id):
            raise DealServiceError("Invalid valuation identifier")
        if not self.root.is_dir():
            raise DealNotFoundError("Valuation was not found")
        for path in sorted(self.root.glob("deal-*/deal.json")):
            record = self._read_path(path)
            for valuation in record.get("valuations", []):
                if valuation.get("valuation_id") == valuation_id:
                    return record, valuation
        raise DealNotFoundError("Valuation was not found")

    def create_deal(
        self,
        *,
        company_id: str,
        buyer: str,
        target: str,
        transaction_scope: str,
        currency: str,
        valuation_date: str,
        owner: str,
        confidentiality_level: str,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "create_deal")
        normalized_reason = _reason(reason)
        key = _idempotency_key(idempotency_key)
        confidentiality = _text(confidentiality_level, "confidentiality_level", limit=40).casefold()
        if confidentiality not in CONFIDENTIALITY_LEVELS:
            raise DealServiceError("Unsupported confidentiality_level")
        normalized_currency = _text(currency, "currency", limit=3).upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
            raise DealServiceError("currency must be a three-letter code")
        payload = {
            "company_id": _text(company_id, "company_id", limit=120),
            "header": {
                "buyer": _text(buyer, "buyer", limit=160),
                "target": _text(target, "target", limit=160),
                "transaction_scope": _text(transaction_scope, "transaction_scope", limit=500),
                "currency": normalized_currency,
                "valuation_date": _iso_date(valuation_date, "valuation_date"),
                "owner": _text(owner, "owner", limit=120),
                "confidentiality_level": confidentiality,
            },
            "actor": normalized_actor,
            "reason": normalized_reason,
        }
        request_hash = self._request_hash("create_deal", payload)
        with self._write_lock:
            if self.root.is_dir():
                for path in self.root.glob("deal-*/deal.json"):
                    existing = self._read_path(path)
                    replay = self._replay_entry(
                        existing,
                        key=key,
                        operation="create_deal",
                        request_hash=request_hash,
                    )
                    if replay is not None:
                        return self._public(existing)
            deal_id = f"deal-{datetime.now():%Y%m%d}-{secrets.token_hex(6)}"
            now = _utc_now()
            event = _audit(
                action="create_deal",
                entity_type="deal",
                entity_id=deal_id,
                field="deal_header",
                old=None,
                new=payload["header"],
                reason=normalized_reason,
                actor=normalized_actor,
                at=now,
            )
            record: dict[str, Any] = {
                "storage_version": STORAGE_VERSION,
                "deal_id": deal_id,
                "company_id": payload["company_id"],
                "revision": 1,
                "deal_header": payload["header"],
                "human_confirmed_stage": None,
                "workplan": [],
                "materials": [],
                "issues": [],
                "decisions": [],
                "valuations": [],
                "audit_trail": [event],
                "created_at": now,
                "updated_at": now,
                "boundaries": {
                    "stage_is_human_confirmed_only": True,
                    "agent_inputs_are_candidates_only": True,
                    "agent_may_approve": False,
                    "formal_valuation_opinion": False,
                },
                "_idempotency": {},
            }
            self._remember(
                record,
                key=key,
                operation="create_deal",
                request_hash=request_hash,
                result={"deal_id": deal_id},
            )
            saved = self._write_record(record, expected_disk_hash=None, creating=True)
            return self._public(saved)

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        return self._public(self._read_path(self._deal_path(deal_id)))

    def list_deals(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        return sorted(
            (self._public(self._read_path(path)) for path in self.root.glob("deal-*/deal.json")),
            key=lambda item: item["updated_at"],
            reverse=True,
        )

    def _mutate_deal(
        self,
        *,
        deal_id: str,
        operation: str,
        request_payload: Mapping[str, Any],
        actor: Mapping[str, str],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
        apply: Any,
    ) -> dict[str, Any]:
        key = _idempotency_key(idempotency_key)
        request_hash = self._request_hash(
            operation,
            request_payload,
            concurrency={
                "expected_revision": expected_revision,
                "expected_record_hash": expected_record_hash,
            },
        )
        with self._write_lock:
            record = self._read_path(self._deal_path(deal_id))
            replay = self._replay_entry(
                record,
                key=key,
                operation=operation,
                request_hash=request_hash,
            )
            if replay is not None:
                return self._public(record)
            self._check_deal_concurrency(record, expected_revision, expected_record_hash)
            prior_hash = record["record_hash"]
            event = apply(record)
            record["audit_trail"].append(event)
            record["revision"] += 1
            record["updated_at"] = event["time"]
            self._remember(
                record,
                key=key,
                operation=operation,
                request_hash=request_hash,
                result={"deal_id": deal_id, "revision": record["revision"]},
            )
            saved = self._write_record(record, expected_disk_hash=prior_hash)
            return self._public(saved)

    def confirm_stage(
        self,
        deal_id: str,
        *,
        stage: str,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "confirm_stage")
        normalized_stage = _text(stage, "stage", limit=80)
        if normalized_stage not in TRANSACTION_STAGES:
            raise DealServiceError("Unsupported transaction stage")
        normalized_reason = _reason(reason)
        request = {
            "stage": normalized_stage,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(record: dict[str, Any]) -> dict[str, Any]:
            old = copy.deepcopy(record["human_confirmed_stage"])
            now = _utc_now()
            new = {
                "stage": normalized_stage,
                "confirmed_by": normalized_actor,
                "confirmed_at": now,
            }
            record["human_confirmed_stage"] = new
            return _audit(
                action="confirm_stage",
                entity_type="deal",
                entity_id=deal_id,
                field="human_confirmed_stage",
                old=old,
                new=new,
                reason=normalized_reason,
                actor=normalized_actor,
                at=now,
            )

        return self._mutate_deal(
            deal_id=deal_id,
            operation="confirm_stage",
            request_payload=request,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
            apply=apply,
        )

    def _add_collection_item(
        self,
        deal_id: str,
        *,
        collection: str,
        prefix: str,
        item: Mapping[str, Any],
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
        human_only: bool = False,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        if human_only:
            _require_human(normalized_actor, f"record a {collection} item")
        normalized_reason = _reason(reason)
        normalized_item = copy.deepcopy(dict(item))
        normalized_item[f"{prefix}_id"] = f"{prefix}-{secrets.token_hex(8)}"
        normalized_item["created_by"] = normalized_actor
        request_item = {
            key: value for key, value in normalized_item.items() if key != f"{prefix}_id"
        }
        request = {
            "item": request_item,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(record: dict[str, Any]) -> dict[str, Any]:
            now = _utc_now()
            normalized_item["created_at"] = now
            record[collection].append(copy.deepcopy(normalized_item))
            return _audit(
                action=f"add_{prefix}",
                entity_type=prefix,
                entity_id=normalized_item[f"{prefix}_id"],
                field=collection,
                old=None,
                new=normalized_item,
                reason=normalized_reason,
                actor=normalized_actor,
                at=now,
            )

        return self._mutate_deal(
            deal_id=deal_id,
            operation=f"add_{prefix}",
            request_payload=request,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
            apply=apply,
        )

    def add_task(
        self,
        deal_id: str,
        *,
        title: str,
        owner: str,
        due_date: str | None,
        dependencies: Sequence[str] = (),
        status: str = "not_started",
        evidence_ids: Sequence[str] = (),
        escalation: str | None = None,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
    ) -> dict[str, Any]:
        if status not in {"not_started", "in_progress", "blocked", "complete", "waived"}:
            raise DealServiceError("Unsupported task status")
        item = {
            "title": _text(title, "title"),
            "owner": _text(owner, "owner", limit=120),
            "due_date": _iso_date(due_date, "due_date") if due_date else None,
            "dependencies": sorted({_text(value, "dependency") for value in dependencies}),
            "status": status,
            "evidence_ids": sorted({_text(value, "evidence_id") for value in evidence_ids}),
            "escalation": _optional_text(escalation, "escalation", limit=500),
        }
        return self._add_collection_item(
            deal_id,
            collection="workplan",
            prefix="task",
            item=item,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
        )

    def add_material(
        self,
        deal_id: str,
        *,
        file_name: str,
        version: int,
        sha256: str,
        source: str,
        disclosure_level: str,
        parse_status: str,
        review_status: str,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
    ) -> dict[str, Any]:
        digest = _text(sha256, "sha256", limit=64).casefold()
        if not SHA256_PATTERN.fullmatch(digest):
            raise DealServiceError("sha256 must be a lowercase SHA-256 digest")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise DealServiceError("material version must be a positive integer")
        item = {
            "file_name": _text(file_name, "file_name", limit=180),
            "version": version,
            "sha256": digest,
            "source": _text(source, "source"),
            "disclosure_level": _text(disclosure_level, "disclosure_level", limit=60),
            "parse_status": _text(parse_status, "parse_status", limit=60),
            "review_status": _text(review_status, "review_status", limit=60),
        }
        return self._add_collection_item(
            deal_id,
            collection="materials",
            prefix="material",
            item=item,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
        )

    def add_issue(
        self,
        deal_id: str,
        *,
        kind: str,
        title: str,
        owner: str,
        due_date: str | None,
        status: str = "open",
        response_versions: Sequence[str] = (),
        disposition: str | None = None,
        waiver_reason: str | None = None,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
    ) -> dict[str, Any]:
        if status not in {"open", "answered", "accepted", "rejected", "waived"}:
            raise DealServiceError("Unsupported issue status")
        if status == "waived" and not waiver_reason:
            raise DealServiceError("waiver_reason is required for a waived issue")
        item = {
            "kind": _text(kind, "kind", limit=60),
            "title": _text(title, "title"),
            "owner": _text(owner, "owner", limit=120),
            "due_date": _iso_date(due_date, "due_date") if due_date else None,
            "status": status,
            "response_versions": [_text(value, "response_version") for value in response_versions],
            "disposition": _optional_text(disposition, "disposition", limit=500),
            "waiver_reason": _optional_text(waiver_reason, "waiver_reason", limit=500),
        }
        return self._add_collection_item(
            deal_id,
            collection="issues",
            prefix="issue",
            item=item,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
        )

    def record_decision(
        self,
        deal_id: str,
        *,
        decision: str,
        quote_range: Mapping[str, Any] | None,
        valuation_id: str | None,
        valuation_version_number: int | None,
        valuation_version_hash: str | None,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_revision: int,
        expected_record_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "record_decision")
        normalized_decision = _text(decision, "decision", limit=20).casefold()
        if normalized_decision not in {"go", "hold", "no_go"}:
            raise DealServiceError("decision must be go, hold, or no_go")
        if valuation_id is None:
            if any(
                value is not None for value in (valuation_version_number, valuation_version_hash)
            ):
                raise DealServiceError("valuation version fields require valuation_id")
        else:
            record = self._read_path(self._deal_path(deal_id))
            valuation = self._find_valuation_in_record(record, valuation_id)
            matching_version = next(
                (
                    version
                    for version in valuation["versions"]
                    if version["version_number"] == valuation_version_number
                    and version["version_hash"] == valuation_version_hash
                ),
                None,
            )
            if matching_version is None:
                raise DealServiceError("Decision valuation version does not belong to this deal")
        item = {
            "decision": normalized_decision,
            "quote_range": copy.deepcopy(dict(quote_range)) if quote_range else None,
            "valuation_id": valuation_id,
            "valuation_version_number": valuation_version_number,
            "valuation_version_hash": valuation_version_hash,
        }
        return self._add_collection_item(
            deal_id,
            collection="decisions",
            prefix="decision",
            item=item,
            actor=normalized_actor,
            reason=reason,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_record_hash=expected_record_hash,
            human_only=True,
        )

    @staticmethod
    def _initial_version(
        valuation_id: str, actor: Mapping[str, str], reason: str, at: str
    ) -> dict[str, Any]:
        version: dict[str, Any] = {
            "version_id": f"{valuation_id}-v0001",
            "version_number": 1,
            "status": "draft",
            "operation": "create_valuation_case",
            "inputs": [],
            "inputs_hash": _canonical_digest([]),
            "calculation": None,
            "calculation_hash": None,
            "review": None,
            "approvals": [],
            "previous_version_hash": None,
            "created_by": dict(actor),
            "created_at": at,
            "reason": reason,
        }
        version["version_hash"] = _version_hash(version)
        return version

    def create_valuation_case(
        self,
        deal_id: str,
        *,
        target_legal_entity: str,
        transaction_scope: str,
        valuation_date: str,
        base_currency: str,
        methods: Sequence[str],
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_deal_revision: int,
        expected_deal_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "create_valuation")
        normalized_reason = _reason(reason)
        key = _idempotency_key(idempotency_key)
        currency = _text(base_currency, "base_currency", limit=3).upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise DealServiceError("base_currency must be a three-letter code")
        normalized_methods = sorted({_text(value, "method", limit=80) for value in methods})
        if not normalized_methods:
            raise DealServiceError("At least one valuation method is required")
        unsupported_methods = sorted(set(normalized_methods) - P0_VALUATION_METHODS)
        if unsupported_methods:
            raise DealServiceError(
                "Unsupported P0 valuation methods: " + ", ".join(unsupported_methods)
            )
        payload = {
            "target_legal_entity": _text(target_legal_entity, "target_legal_entity", limit=200),
            "transaction_scope": _text(transaction_scope, "transaction_scope", limit=500),
            "valuation_date": _iso_date(valuation_date, "valuation_date"),
            "base_currency": currency,
            "methods": normalized_methods,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }
        request_hash = self._request_hash(
            "create_valuation_case",
            payload,
            concurrency={
                "expected_deal_revision": expected_deal_revision,
                "expected_deal_hash": expected_deal_hash,
            },
        )
        with self._write_lock:
            record = self._read_path(self._deal_path(deal_id))
            replay = self._replay_entry(
                record,
                key=key,
                operation="create_valuation_case",
                request_hash=request_hash,
            )
            if replay is not None:
                return self._public_valuation(
                    self._find_valuation_in_record(record, replay["valuation_id"])
                )
            self._check_deal_concurrency(record, expected_deal_revision, expected_deal_hash)
            prior_hash = record["record_hash"]
            valuation_id = f"valuation-{secrets.token_hex(8)}"
            now = _utc_now()
            initial = self._initial_version(valuation_id, normalized_actor, normalized_reason, now)
            valuation: dict[str, Any] = {
                "valuation_id": valuation_id,
                "deal_id": deal_id,
                "target_legal_entity": payload["target_legal_entity"],
                "transaction_scope": payload["transaction_scope"],
                "valuation_date": payload["valuation_date"],
                "base_currency": currency,
                "methods": normalized_methods,
                "status": "draft",
                "current_version_number": 1,
                "current_version_hash": initial["version_hash"],
                "versions": [initial],
                "audit_trail": [],
                "created_at": now,
                "updated_at": now,
                "boundaries": {
                    "screen_grade_until_human_review": True,
                    "agent_inputs_are_candidates_only": True,
                    "agent_may_review_or_approve": False,
                    "formal_valuation_opinion": False,
                },
            }
            event = _audit(
                action="create_valuation_case",
                entity_type="valuation_case",
                entity_id=valuation_id,
                field="valuation_case",
                old=None,
                new={
                    "status": "draft",
                    "version_number": 1,
                    "version_hash": initial["version_hash"],
                },
                reason=normalized_reason,
                actor=normalized_actor,
                at=now,
            )
            valuation["audit_trail"].append(copy.deepcopy(event))
            record["valuations"].append(valuation)
            record["audit_trail"].append(event)
            record["revision"] += 1
            record["updated_at"] = now
            self._remember(
                record,
                key=key,
                operation="create_valuation_case",
                request_hash=request_hash,
                result={"valuation_id": valuation_id},
            )
            saved = self._write_record(record, expected_disk_hash=prior_hash)
            return self._public_valuation(self._find_valuation_in_record(saved, valuation_id))

    def get_valuation(self, valuation_id: str) -> dict[str, Any]:
        _, valuation = self._find_valuation(valuation_id)
        return self._public_valuation(valuation)

    def list_valuations(self, deal_id: str) -> list[dict[str, Any]]:
        record = self._read_path(self._deal_path(deal_id))
        return [self._public_valuation(value) for value in record["valuations"]]

    @staticmethod
    def _normalize_inputs(
        inputs: Sequence[Mapping[str, Any]], actor: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in inputs:
            if not isinstance(raw, Mapping):
                raise DealServiceError("Each valuation input must be an object")
            item = copy.deepcopy(dict(raw))
            name = _text(item.get("name"), "input.name", limit=120)
            input_id = _optional_text(item.get("input_id"), "input_id", limit=120)
            if input_id is None:
                input_id = (
                    f"input-{_canonical_digest({'name': name, 'period': item.get('period')})[:16]}"
                )
            if input_id in seen:
                raise DealServiceError("Duplicate input_id in one update")
            seen.add(input_id)
            requested_status = str(item.get("status") or "").casefold()
            if actor["type"] == "agent":
                if (
                    requested_status not in {"", "candidate_input"}
                    or item.get("human_confirmed") is True
                ):
                    raise DealPermissionError("Agent inputs must remain candidate_input records")
                status = "candidate_input"
                authority = "candidate_only"
            else:
                status = requested_status or "candidate_input"
                if status not in {"candidate_input", "confirmed_input"}:
                    raise DealServiceError("Unsupported valuation input status")
                if status == "confirmed_input" and item.get("human_confirmed") is not True:
                    raise DealPermissionError(
                        "confirmed_input requires explicit human_confirmed=true"
                    )
                authority = "human_confirmed" if status == "confirmed_input" else "candidate_only"
            item.update(
                {
                    "input_id": input_id,
                    "name": name,
                    "status": status,
                    "authority": authority,
                    "human_confirmed": status == "confirmed_input",
                    "entered_by": dict(actor),
                }
            )
            if status == "confirmed_input":
                item["reviewed_by"] = dict(actor)
            else:
                item.pop("reviewed_by", None)
            normalized.append(item)
        return normalized

    @staticmethod
    def _append_version(
        valuation: dict[str, Any],
        *,
        status: str,
        operation: str,
        inputs: list[dict[str, Any]],
        calculation: Mapping[str, Any] | None,
        review: Mapping[str, Any] | None,
        approvals: list[dict[str, Any]],
        actor: Mapping[str, str],
        reason: str,
    ) -> dict[str, Any]:
        if status not in VALUATION_STATUSES:
            raise DealServiceError("Unsupported valuation status")
        previous = valuation["versions"][-1]
        number = previous["version_number"] + 1
        now = _utc_now()
        calculation_value = copy.deepcopy(dict(calculation)) if calculation else None
        version: dict[str, Any] = {
            "version_id": f"{valuation['valuation_id']}-v{number:04d}",
            "version_number": number,
            "status": status,
            "operation": operation,
            "inputs": copy.deepcopy(inputs),
            "inputs_hash": _canonical_digest(inputs),
            "calculation": calculation_value,
            "calculation_hash": (
                _canonical_digest(calculation_value) if calculation_value else None
            ),
            "review": copy.deepcopy(dict(review)) if review else None,
            "approvals": copy.deepcopy(approvals),
            "previous_version_hash": previous["version_hash"],
            "created_by": dict(actor),
            "created_at": now,
            "reason": reason,
        }
        version["version_hash"] = _version_hash(version)
        valuation["versions"].append(version)
        valuation["current_version_number"] = number
        valuation["current_version_hash"] = version["version_hash"]
        valuation["status"] = status
        valuation["updated_at"] = now
        return version

    def _mutate_valuation(
        self,
        valuation_id: str,
        *,
        operation: str,
        payload: Mapping[str, Any],
        actor: Mapping[str, str],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
        apply: Any,
    ) -> dict[str, Any]:
        key = _idempotency_key(idempotency_key)
        request_hash = self._request_hash(
            operation,
            payload,
            concurrency={
                "expected_version_number": expected_version_number,
                "expected_version_hash": expected_version_hash,
            },
        )
        with self._write_lock:
            record, valuation = self._find_valuation(valuation_id)
            replay = self._replay_entry(
                record,
                key=key,
                operation=operation,
                request_hash=request_hash,
            )
            if replay is not None:
                return self._version_replay(valuation, replay)
            self._check_version_concurrency(
                valuation, expected_version_number, expected_version_hash
            )
            prior_hash = record["record_hash"]
            old_version = copy.deepcopy(valuation["versions"][-1])
            new_version = apply(valuation)
            event = _audit(
                action=operation,
                entity_type="valuation_version",
                entity_id=new_version["version_id"],
                field=f"valuations.{valuation_id}.current_version",
                old=self._audit_version_projection(old_version),
                new=self._audit_version_projection(new_version),
                reason=reason,
                actor=actor,
                at=new_version["created_at"],
            )
            valuation["audit_trail"].append(copy.deepcopy(event))
            record["audit_trail"].append(event)
            record["revision"] += 1
            record["updated_at"] = new_version["created_at"]
            self._remember(
                record,
                key=key,
                operation=operation,
                request_hash=request_hash,
                result={
                    "valuation_id": valuation_id,
                    "version_number": new_version["version_number"],
                    "version_hash": new_version["version_hash"],
                },
            )
            self._write_record(record, expected_disk_hash=prior_hash)
            return copy.deepcopy(new_version)

    def update_valuation_inputs(
        self,
        valuation_id: str,
        *,
        inputs: Sequence[Mapping[str, Any]],
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        if normalized_actor["type"] == "human":
            _require_capability(normalized_actor, "valuation_input")
        normalized_reason = _reason(reason)
        normalized_inputs = self._normalize_inputs(inputs, normalized_actor)
        payload = {
            "inputs": normalized_inputs,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(valuation: dict[str, Any]) -> dict[str, Any]:
            if valuation["status"] in {"approved_for_external_use", "superseded"}:
                raise DealConflictError(
                    "Externally approved or superseded valuation cannot be edited"
                )
            current = valuation["versions"][-1]
            merged = {item["input_id"]: copy.deepcopy(item) for item in current["inputs"]}
            for item in normalized_inputs:
                existing = merged.get(item["input_id"])
                if (
                    normalized_actor["type"] == "agent"
                    and existing
                    and existing.get("status") == "confirmed_input"
                ):
                    raise DealPermissionError(
                        "Agent cannot overwrite a human-confirmed valuation input"
                    )
                merged[item["input_id"]] = copy.deepcopy(item)
            return self._append_version(
                valuation,
                status="inputs_incomplete",
                operation="update_valuation_inputs",
                inputs=[merged[key] for key in sorted(merged)],
                calculation=None,
                review=None,
                approvals=[],
                actor=normalized_actor,
                reason=normalized_reason,
            )

        return self._mutate_valuation(
            valuation_id,
            operation="update_valuation_inputs",
            payload=payload,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_version_number=expected_version_number,
            expected_version_hash=expected_version_hash,
            apply=apply,
        )

    def calculate_valuation(
        self,
        valuation_id: str,
        *,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        normalized_reason = _reason(reason)
        payload = {
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(valuation: dict[str, Any]) -> dict[str, Any]:
            if valuation["status"] not in {
                "inputs_incomplete",
                "calculated_screen_grade",
            }:
                raise DealConflictError(
                    "Calculation requires inputs_incomplete or calculated_screen_grade"
                )
            current = valuation["versions"][-1]
            from .valuation import ValuationHardFailure
            from .valuation_workflow import (
                calculate_screen_from_version,
                failed_calculation_from_exception,
            )

            try:
                calculation = calculate_screen_from_version(valuation, current)
            except ValuationHardFailure as exc:
                calculation = failed_calculation_from_exception(valuation, current, exc)
            if not isinstance(calculation, Mapping):
                raise DealServiceError("Trusted valuation engine must return an object")
            normalized_calculation = copy.deepcopy(dict(calculation))
            used_ids = normalized_calculation.get("used_input_ids", [])
            if not isinstance(used_ids, list) or not all(
                isinstance(value, str) for value in used_ids
            ):
                raise DealServiceError("calculation.used_input_ids must be a string list")
            normalized_calculation["used_input_ids"] = sorted(set(used_ids))
            normalized_calculation["authority"] = "screen_grade_only"
            normalized_calculation["formal_valuation_opinion"] = False
            by_id = {item["input_id"]: item for item in current["inputs"]}
            missing = set(normalized_calculation["used_input_ids"]) - set(by_id)
            if missing:
                raise DealServiceError(f"Unknown calculation input ids: {sorted(missing)}")
            unconfirmed = [
                input_id
                for input_id in normalized_calculation["used_input_ids"]
                if by_id[input_id].get("status") != "confirmed_input"
            ]
            if unconfirmed:
                raise DealPermissionError(
                    f"Candidate inputs cannot enter the model: {sorted(unconfirmed)}"
                )
            return self._append_version(
                valuation,
                status="calculated_screen_grade",
                operation="calculate_valuation",
                inputs=current["inputs"],
                calculation=normalized_calculation,
                review=None,
                approvals=[],
                actor=normalized_actor,
                reason=normalized_reason,
            )

        return self._mutate_valuation(
            valuation_id,
            operation="calculate_valuation",
            payload=payload,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_version_number=expected_version_number,
            expected_version_hash=expected_version_hash,
            apply=apply,
        )

    def review_valuation(
        self,
        valuation_id: str,
        *,
        review: Mapping[str, Any],
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "review_valuation")
        normalized_reason = _reason(reason)
        review_payload = copy.deepcopy(dict(review))
        review_payload["decision"] = _text(
            review_payload.get("decision"), "review.decision", limit=80
        )
        payload = {
            "review": review_payload,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(valuation: dict[str, Any]) -> dict[str, Any]:
            if valuation["status"] != "calculated_screen_grade":
                raise DealConflictError("Only a calculated screen-grade version may be reviewed")
            current = valuation["versions"][-1]
            review_value = copy.deepcopy(review_payload)
            review_value.update(
                {
                    "reviewed_by": normalized_actor,
                    "reviewed_at": _utc_now(),
                    "authority": "human_only",
                }
            )
            reviewed_calculation = _calculation_for_lifecycle(
                current["calculation"],
                lifecycle_status="fa_reviewed",
            )
            return self._append_version(
                valuation,
                status="fa_reviewed",
                operation="review_valuation",
                inputs=current["inputs"],
                calculation=reviewed_calculation,
                review=review_value,
                approvals=current["approvals"],
                actor=normalized_actor,
                reason=normalized_reason,
            )

        return self._mutate_valuation(
            valuation_id,
            operation="review_valuation",
            payload=payload,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_version_number=expected_version_number,
            expected_version_hash=expected_version_hash,
            apply=apply,
        )

    def approve_valuation(
        self,
        valuation_id: str,
        *,
        use: str,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        normalized_reason = _reason(reason)
        normalized_use = _text(use, "use", limit=20).casefold()
        if normalized_use not in {"internal", "external"}:
            raise DealServiceError("use must be internal or external")
        _require_capability(
            normalized_actor,
            "approve_internal" if normalized_use == "internal" else "approve_external",
        )
        payload = {
            "use": normalized_use,
            "actor": normalized_actor,
            "reason": normalized_reason,
        }

        def apply(valuation: dict[str, Any]) -> dict[str, Any]:
            current = valuation["versions"][-1]
            if normalized_use == "internal":
                if valuation["status"] != "fa_reviewed":
                    raise DealConflictError("Internal approval requires fa_reviewed")
                status = "approved_for_internal_use"
            else:
                if valuation["status"] != "approved_for_internal_use":
                    raise DealConflictError("External approval requires approved_for_internal_use")
                status = "approved_for_external_use"
            blockers = _approval_blockers(current.get("calculation"))
            if blockers:
                raise DealConflictError(
                    f"{normalized_use.title()} approval is blocked by "
                    + ", ".join(blockers)
                )
            now = _utc_now()
            approval = {
                "use": normalized_use,
                "approved_by": normalized_actor,
                "approved_at": now,
                "reason": normalized_reason,
                "authority": "human_only",
            }
            approved_calculation = _calculation_for_lifecycle(
                current["calculation"],
                lifecycle_status=status,
            )
            return self._append_version(
                valuation,
                status=status,
                operation="approve_valuation",
                inputs=current["inputs"],
                calculation=approved_calculation,
                review=current["review"],
                approvals=[*current["approvals"], approval],
                actor=normalized_actor,
                reason=normalized_reason,
            )

        return self._mutate_valuation(
            valuation_id,
            operation="approve_valuation",
            payload=payload,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_version_number=expected_version_number,
            expected_version_hash=expected_version_hash,
            apply=apply,
        )

    def supersede_valuation(
        self,
        valuation_id: str,
        *,
        actor: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
        expected_version_number: int,
        expected_version_hash: str,
    ) -> dict[str, Any]:
        normalized_actor = _actor(actor)
        _require_capability(normalized_actor, "supersede_valuation")
        normalized_reason = _reason(reason)
        payload = {"actor": normalized_actor, "reason": normalized_reason}

        def apply(valuation: dict[str, Any]) -> dict[str, Any]:
            if valuation["status"] == "superseded":
                raise DealConflictError("Valuation is already superseded")
            current = valuation["versions"][-1]
            return self._append_version(
                valuation,
                status="superseded",
                operation="supersede_valuation",
                inputs=current["inputs"],
                calculation=current["calculation"],
                review=current["review"],
                approvals=current["approvals"],
                actor=normalized_actor,
                reason=normalized_reason,
            )

        return self._mutate_valuation(
            valuation_id,
            operation="supersede_valuation",
            payload=payload,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            expected_version_number=expected_version_number,
            expected_version_hash=expected_version_hash,
            apply=apply,
        )
