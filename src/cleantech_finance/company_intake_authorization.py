"""Deterministic content-use authorization controls for company intake.

Only explicit CSV, JSON, and JSONL fields are inspected.  Markdown and free prose
never create, expand, or revoke a permission.  Every source record remains an
unverified candidate pending human verification; the module performs no external
action and never closes a question automatically.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timezone
from io import StringIO
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "company-intake-content-authorization-1.0.0"
MAX_STRUCTURED_ROWS = 10_000

PERMISSION_ORDER = (
    "recording",
    "internal_analysis",
    "public_release",
    "brand_and_logo",
    "translation",
    "ai_media",
)

PERMISSION_LABELS = {
    "recording": "录音",
    "internal_analysis": "内部分析",
    "public_release": "公开发布",
    "brand_and_logo": "品牌与 Logo",
    "translation": "翻译",
    "ai_media": "AI 媒体",
}

_PERMISSION_ALIASES = {
    "recording": "recording",
    "internal analysis": "internal_analysis",
    "public release": "public_release",
    "brand and logo use": "brand_and_logo",
    "brand and logo": "brand_and_logo",
    "brand/logo": "brand_and_logo",
    "translation": "translation",
    "ai media": "ai_media",
}

QUESTION_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "R04-Q01",
        "priority": "critical",
        "boundary": "recording",
        "question_zh": "请确认是否需要新录音；历史已过期授权不能覆盖新的录制。",
        "recompute_scope": [
            "recording_permission_gate",
            "recording_requests",
            "dashboard_next_action",
        ],
    },
    {
        "id": "R04-Q02",
        "priority": "critical",
        "boundary": "internal_analysis",
        "question_zh": "请明确命名团队、工作区、内容范围与排除项；内部分析许可不得扩张。",
        "recompute_scope": [
            "internal_analysis_scope_gate",
            "privacy_scope",
            "internal_analysis_requests",
        ],
    },
    {
        "id": "R04-Q03",
        "priority": "critical",
        "boundary": "public_release",
        "question_zh": "公开发布被拒绝；请撤回请求或提交明确取代拒绝决定的新签署授权。",
        "recompute_scope": [
            "public_release_gate",
            "publication_requests",
            "output_availability",
        ],
    },
    {
        "id": "R04-Q04",
        "priority": "critical",
        "boundary": "brand_and_logo",
        "question_zh": "品牌许可仅限明示范围；公开、翻译、修改、转授权或联名需独立授权。",
        "recompute_scope": [
            "brand_permission_gate",
            "brand_requests",
            "publication_gate",
        ],
    },
    {
        "id": "R04-Q05",
        "priority": "critical",
        "boundary": "translation",
        "question_zh": "翻译权限缺失；在独立、明确授权前不得执行供分发使用的翻译。",
        "recompute_scope": [
            "translation_permission_gate",
            "translation_requests",
            "publication_gate",
        ],
    },
    {
        "id": "R04-Q06",
        "priority": "critical",
        "boundary": "ai_media",
        "question_zh": "AI 媒体用途被拒绝；声音、形象、转录与录音不得用于生成或范围外训练。",
        "recompute_scope": [
            "ai_media_permission_gate",
            "privacy_scope",
            "ai_media_requests",
        ],
    },
    {
        "id": "R04-Q07",
        "priority": "high",
        "boundary": "interview_statement_candidate_evidence",
        "question_zh": "访谈材料只证明陈述被记录；事实主张仍需逐项一手证据与人工复核。",
        "recompute_scope": [
            "claim_evidence_gaps",
            "interview_preparation",
            "publication_gate",
        ],
    },
    {
        "id": "R04-Q08",
        "priority": "critical",
        "boundary": "agent_candidate_authority",
        "question_zh": "请隔离无 authority 的 Agent override candidate，并确认没有下游动作执行。",
        "recompute_scope": [
            "agent_override_conflicts",
            "candidate_quarantine",
            "dashboard_next_action",
        ],
    },
)

_QUESTION_BY_ID = {item["id"]: item for item in QUESTION_SPECS}
_DENIED_VALUES = frozenset({"denied", "active denial"})
_MISSING_VALUES = frozenset(
    {
        "missing",
        "missing / not authorized",
        "not authorized",
        "no authorization instrument",
        "no authorizing instrument",
    }
)
_LIMITED_VALUES = frozenset(
    {
        "limited grant",
        "active scope-limited",
        "granted for original scheduled capture only",
    }
)
_GRANTED_VALUES = frozenset({"granted", "active"})
_AGENT_PERMISSION_FLAGS = {
    "public_release_approved": "public_release",
    "brand_and_logo_public_use_approved": "brand_and_logo",
    "translation_approved": "translation",
    "ai_voice_and_avatar_approved": "ai_media",
}


def _clean(value: Any, *, limit: int = 800) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _first(row: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = _clean(row.get(field))
        if value:
            return value
    return ""


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _permission(value: Any) -> str | None:
    return _PERMISSION_ALIASES.get(_clean(value, limit=80).casefold())


def _parse_timestamp(value: Any) -> datetime | None:
    text = _clean(value, limit=80)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _diagnostic_as_of(value: str | date | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
    else:
        text = _clean(value, limit=80)
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                parsed = datetime.combine(
                    date.fromisoformat(text), time.min, tzinfo=timezone.utc
                )
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("authorization as_of must be an ISO date or datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _authorization_record(
    row: Mapping[str, Any],
    *,
    row_number: int,
    record_kind: str,
    permission_override: str | None = None,
) -> dict[str, Any] | None:
    permission = permission_override or _permission(row.get("permission_type"))
    if permission not in PERMISSION_ORDER:
        return None
    return {
        "authorization_id": _first(row, "authorization_id", "license_id"),
        "permission": permission,
        "permission_label_zh": PERMISSION_LABELS[permission],
        "authorization_subject": _first(row, "authorization_subject"),
        "content_subject": _first(row, "content_subject", "asset_id"),
        "decision": _first(row, "decision"),
        "scope": _first(row, "scope", "permitted_scope"),
        "permitted_audience": _first(row, "permitted_audience"),
        "effective_at": _first(row, "effective_at"),
        "expires_at": _first(row, "expires_at"),
        "declared_status": _first(row, "current_status"),
        "authority": _first(row, "authority_class", "source_authority"),
        "approval_status": _first(row, "approval_status"),
        "signature_status": _first(row, "signature_status"),
        "assertion_status": _first(row, "assertion_status"),
        "explicit_exclusions": _first(
            row, "explicit_exclusions", "prohibited_scope"
        ),
        "source_document_id": _first(row, "source_document_id"),
        "version": _first(row, "version"),
        "row_number": row_number,
        "record_kind": record_kind,
        "accepted_as_authorization": False,
    }


def _use_request(row: Mapping[str, Any], row_number: int) -> dict[str, Any] | None:
    request_id = _first(row, "request_id")
    if not request_id:
        return None
    raw_permission = _first(row, "required_permission")
    return {
        "request_id": request_id,
        "requester_role": _first(row, "requester_role"),
        "requested_action": _first(row, "requested_action"),
        "source_content": _first(row, "source_content"),
        "target_audience_or_channel": _first(row, "target_audience_or_channel"),
        "required_permission": _permission(raw_permission),
        "required_permission_raw": raw_permission,
        "authorization_reference": _first(row, "authorization_reference"),
        "declared_request_status": _first(row, "request_status"),
        "decision_authority": _first(row, "decision_authority"),
        "effective_at": _first(row, "effective_at"),
        "expires_at": _first(row, "expires_at"),
        "version": _first(row, "version"),
        "row_number": row_number,
        "request_status_is_authority": False,
    }


def _response_mapping(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    source_question_id = _first(payload, "question_id")
    match = re.fullmatch(r"R04(?:-FA)?-Q(0[1-8])", source_question_id)
    if not match:
        return None
    submitted = payload.get("submitted_files")
    if not isinstance(submitted, Sequence) or isinstance(submitted, (str, bytes)):
        submitted = payload.get("submitted_materials")
    files = (
        sorted({_clean(item, limit=240) for item in submitted if _clean(item)})
        if isinstance(submitted, Sequence) and not isinstance(submitted, (str, bytes))
        else []
    )
    return {
        "source_question_id": source_question_id,
        "question_id": f"R04-Q{match.group(1)}",
        "declared_response_state": _first(
            payload, "response_state", "status", "classification"
        ),
        "submitted_files": files,
        "remaining_gap": _first(payload, "remaining_gap", "unavailable_reason"),
    }


def _parse_csv(text: str) -> dict[str, Any]:
    try:
        reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    except csv.Error:
        return {}
    if not reader.fieldnames:
        return {}
    fields = {str(item or "").strip() for item in reader.fieldnames}
    is_authorization_register = {"authorization_id", "permission_type", "decision"}.issubset(
        fields
    )
    is_brand_license = {"license_id", "asset_id", "decision", "permitted_scope"}.issubset(
        fields
    )
    is_request_register = {"request_id", "required_permission", "authorization_reference"}.issubset(
        fields
    )
    records: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if row_number > MAX_STRUCTURED_ROWS + 1:
            break
        row = {str(key or "").strip(): value for key, value in raw_row.items()}
        if is_authorization_register:
            record = _authorization_record(
                row,
                row_number=row_number,
                record_kind="authorization_register",
            )
            if record:
                records.append(record)
        if is_brand_license:
            record = _authorization_record(
                row,
                row_number=row_number,
                record_kind="brand_license",
                permission_override="brand_and_logo",
            )
            if record:
                records.append(record)
        if is_request_register and (request := _use_request(row, row_number)):
            requests.append(request)
        if "question_id" in fields and (receipt := _response_mapping(row)):
            receipts.append(receipt)
    return {
        "source_format": "csv",
        "authorization_records": records,
        "use_requests": requests,
        "override_candidates": [],
        "response_mappings": receipts,
        "interview_statement_sources": [],
        "detected": bool(records or requests or receipts),
    }


def _manifest_authorization_records(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    summary = payload.get("authorization_summary")
    if not isinstance(summary, Sequence) or isinstance(summary, (str, bytes)):
        return []
    records: list[dict[str, Any]] = []
    for index, raw_item in enumerate(summary, start=1):
        if not isinstance(raw_item, Mapping):
            continue
        record = _authorization_record(
            raw_item,
            row_number=index,
            record_kind="manifest_summary",
        )
        if record:
            record["authorization_id"] = ""
            records.append(record)
    return records


def _manifest_interview_sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return []
    candidates: list[dict[str, Any]] = []
    for index, raw_item in enumerate(files, start=1):
        if not isinstance(raw_item, Mapping):
            continue
        source_class = _first(raw_item, "source_class")
        assertion_status = _first(raw_item, "assertion_status")
        if source_class.casefold() != "enterprise-prepared transcript":
            continue
        candidates.append(
            {
                "file_name": _first(raw_item, "filename"),
                "source_class": source_class,
                "assertion_status": assertion_status,
                "approval_status": _first(raw_item, "approval_status"),
                "signature_status": _first(raw_item, "signature_status"),
                "entry_index": index,
                "statement_made_candidate": True,
                "fact_verified": False,
                "claims_extracted_from_prose": False,
                "evidence_gap": "primary_evidence_and_human_review_required",
            }
        )
    return candidates


def _agent_override_candidate(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if _first(payload, "artifact_type").casefold() != "agent-candidate":
        return None
    candidate_payload = payload.get("candidate_payload")
    boundary = payload.get("authority_boundary")
    if not isinstance(candidate_payload, Mapping):
        candidate_payload = {}
    if not isinstance(boundary, Mapping):
        boundary = {}
    attempted_permissions = sorted(
        permission
        for key, permission in _AGENT_PERMISSION_FLAGS.items()
        if candidate_payload.get(key) is True
    )
    attempted_fact_verification = candidate_payload.get("facts_verified") is True
    denied_authority_fields = sorted(
        str(key) for key, value in boundary.items() if value is False
    )
    no_authority = _first(payload, "source_authority").casefold() in {
        "",
        "none",
        "no authority",
    }
    override_instruction_present = bool(
        _first(candidate_payload, "candidate_override_instruction")
    )
    override_attempt = bool(
        attempted_permissions
        or attempted_fact_verification
        or override_instruction_present
    )
    return {
        "candidate_id": _first(payload, "candidate_id"),
        "attempted_permissions": attempted_permissions,
        "attempted_fact_verification": attempted_fact_verification,
        "override_instruction_present": override_instruction_present,
        "source_authority": _first(payload, "source_authority"),
        "approval_status": _first(payload, "approval_status"),
        "signature_status": _first(payload, "signature_status"),
        "authority_boundary_false_fields": denied_authority_fields,
        "override_attempt": override_attempt,
        "self_declared_no_authority": no_authority,
        "no_effective_authority": True,
        "isolated": override_attempt,
        "may_change_authorization": False,
    }


def _parse_json_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    records = _manifest_authorization_records(payload)
    payload_fields = {str(key).strip() for key in payload}
    if {
        "authorization_id",
        "permission_type",
        "decision",
    }.issubset(payload_fields):
        if record := _authorization_record(
            payload,
            row_number=1,
            record_kind="authorization_json",
        ):
            records.append(record)
    if {
        "license_id",
        "asset_id",
        "decision",
        "permitted_scope",
    }.issubset(payload_fields):
        if record := _authorization_record(
            payload,
            row_number=1,
            record_kind="brand_license_json",
            permission_override="brand_and_logo",
        ):
            records.append(record)
    requests: list[dict[str, Any]] = []
    if {
        "request_id",
        "required_permission",
        "authorization_reference",
    }.issubset(payload_fields):
        if request := _use_request(payload, 1):
            requests.append(request)
    interview_sources = _manifest_interview_sources(payload)
    override = _agent_override_candidate(payload)
    receipts: list[dict[str, Any]] = []
    if receipt := _response_mapping(payload):
        receipts.append(receipt)
    for raw_item in payload.get("question_submission_mapping") or []:
        if isinstance(raw_item, Mapping) and (receipt := _response_mapping(raw_item)):
            receipts.append(receipt)
    return {
        "source_format": "json",
        "authorization_records": records,
        "use_requests": requests,
        "override_candidates": [override] if override else [],
        "response_mappings": receipts,
        "interview_statement_sources": interview_sources,
        "detected": bool(
            records or requests or interview_sources or override or receipts
        ),
    }


def _parse_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return _parse_json_payload(payload)


def _parse_jsonl(text: str) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    overrides: list[dict[str, Any]] = []
    interview_sources: list[dict[str, Any]] = []
    for line in text.splitlines()[:MAX_STRUCTURED_ROWS]:
        if not line.strip():
            continue
        try:
            parsed = _parse_json_payload(json.loads(line))
        except json.JSONDecodeError:
            continue
        records.extend(parsed.get("authorization_records") or [])
        requests.extend(parsed.get("use_requests") or [])
        overrides.extend(parsed.get("override_candidates") or [])
        receipts.extend(parsed.get("response_mappings") or [])
        interview_sources.extend(parsed.get("interview_statement_sources") or [])
    return {
        "source_format": "jsonl",
        "authorization_records": records,
        "use_requests": requests,
        "override_candidates": overrides,
        "response_mappings": receipts,
        "interview_statement_sources": interview_sources,
        "detected": bool(records or requests or overrides or receipts or interview_sources),
    }


def parse_structured_authorization_metadata(
    file_name: str, text: str
) -> dict[str, Any]:
    """Parse authorization fields from supported structured formats only."""

    suffix = Path(file_name).suffix.casefold()
    if suffix == ".csv":
        return _parse_csv(text)
    if suffix == ".json":
        return _parse_json(text)
    if suffix == ".jsonl":
        return _parse_jsonl(text)
    return {}


def _record_state(record: Mapping[str, Any], as_of: datetime) -> str:
    decision = _clean(record.get("decision"), limit=100).casefold()
    declared = _clean(record.get("declared_status"), limit=100).casefold()
    authority = _clean(record.get("authority"), limit=120).casefold()
    if decision in _DENIED_VALUES or declared in _DENIED_VALUES:
        return "denied"
    if (
        decision in _MISSING_VALUES
        or declared in _MISSING_VALUES
        or authority in _MISSING_VALUES
    ):
        return "missing"
    effective = _parse_timestamp(record.get("effective_at"))
    expires = _parse_timestamp(record.get("expires_at"))
    if effective and as_of < effective:
        return "not_yet_effective"
    if expires and as_of > expires:
        return "expired"
    if decision in _LIMITED_VALUES or declared in _LIMITED_VALUES:
        return "limited"
    if decision in _GRANTED_VALUES or declared in _GRANTED_VALUES:
        return "active_scoped_grant"
    return "unrecognized"


def _matrix_status(states: set[str]) -> str:
    if not states:
        return "missing"
    if "denied" in states and states.intersection(
        {"limited", "active_scoped_grant"}
    ):
        return "mixed_scope_control"
    if "denied" in states:
        return "denied"
    if "missing" in states:
        return "missing"
    if "expired" in states:
        return "expired"
    if "not_yet_effective" in states:
        return "not_yet_effective"
    if "limited" in states:
        return "limited"
    if "active_scoped_grant" in states:
        return "active_scoped_grant"
    return "unrecognized"


def _exact_scope_match(
    request: Mapping[str, Any], record: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    comparisons = (
        ("requested_action", "scope"),
        ("source_content", "content_subject"),
        ("target_audience_or_channel", "permitted_audience"),
    )
    mismatches: list[str] = []
    for request_field, record_field in comparisons:
        requested = _clean(request.get(request_field))
        authorized = _clean(record.get(record_field))
        if not requested or not authorized or requested.casefold() != authorized.casefold():
            mismatches.append(f"{request_field}!={record_field}")
    return not mismatches, mismatches


def _resolve_request(
    request: Mapping[str, Any],
    records_by_id: Mapping[str, list[Mapping[str, Any]]],
    as_of: datetime,
) -> dict[str, Any]:
    reference = _clean(request.get("authorization_reference"), limit=160)
    candidates = records_by_id.get(reference.casefold(), []) if reference else []
    reason = "unmatched_authorization_reference"
    state: str | None = None
    controlling: Mapping[str, Any] | None = None
    scope_mismatches: list[str] = []
    within_scope = False
    if len(candidates) > 1:
        reason = "ambiguous_authorization_reference"
    elif len(candidates) == 1:
        controlling = candidates[0]
        if request.get("required_permission") != controlling.get("permission"):
            reason = "permission_type_mismatch"
        else:
            state = _record_state(controlling, as_of)
            if state in {
                "denied",
                "missing",
                "expired",
                "not_yet_effective",
                "unrecognized",
            }:
                reason = state
            else:
                within_scope, scope_mismatches = _exact_scope_match(
                    request, controlling
                )
                reason = (
                    "within_explicit_scope_candidate"
                    if within_scope
                    else "scope_not_exactly_matched"
                )
    return {
        **dict(request),
        "resolution": reason,
        "blocked": True,
        "controlling_authorization_candidate_id": (
            controlling.get("authorization_id") if controlling else None
        ),
        "controlling_record_state": state,
        "scope_mismatches": scope_mismatches,
        "within_explicit_scope_candidate": within_scope,
        "requires_human_acceptance": True,
        "accepted_as_authorized_action": False,
        "action_executed": False,
        "authority": "exact_reference_candidate_resolution_only",
    }


def diagnose_company_intake_authorization(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    as_of: str | date | datetime | None = None,
) -> dict[str, Any]:
    """Evaluate structured authorization candidates without granting any action."""

    evaluated_at = _diagnostic_as_of(as_of)
    records: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    overrides: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    interview_sources: list[dict[str, Any]] = []
    uploaded_names = {
        _clean(artifact.get("file_name"), limit=240).casefold()
        for artifact in artifacts
        if _clean(artifact.get("file_name"), limit=240)
    }
    for artifact in artifacts:
        recognition = artifact.get("recognition")
        if not isinstance(recognition, Mapping):
            continue
        parsed = recognition.get("structured_authorization_metadata")
        if not isinstance(parsed, Mapping):
            continue
        artifact_id = _clean(artifact.get("id"), limit=80)
        file_name = _clean(artifact.get("file_name"), limit=240)
        for key, target in (
            ("authorization_records", records),
            ("use_requests", requests),
            ("override_candidates", overrides),
            ("response_mappings", receipts),
            ("interview_statement_sources", interview_sources),
        ):
            for raw_item in parsed.get(key) or []:
                if not isinstance(raw_item, Mapping):
                    continue
                target.append(
                    {
                        **dict(raw_item),
                        "source_artifact_id": artifact_id,
                        "source_file_name": file_name,
                    }
                )

    for record in records:
        record["evaluated_state"] = _record_state(record, evaluated_at)
        record["record_id"] = _stable_id(
            "R04-AUTH",
            "|".join(
                [
                    _clean(record.get("source_file_name")),
                    _clean(record.get("authorization_id")),
                    _clean(record.get("permission")),
                    _clean(record.get("content_subject")),
                    _clean(record.get("row_number")),
                ]
            ),
        )

    records.sort(
        key=lambda item: (
            PERMISSION_ORDER.index(item["permission"]),
            _clean(item.get("authorization_id")).casefold(),
            _clean(item.get("content_subject")).casefold(),
            _clean(item.get("source_file_name")).casefold(),
            int(item.get("row_number") or 0),
        )
    )
    permission_matrix: list[dict[str, Any]] = []
    for permission in PERMISSION_ORDER:
        candidates = [item for item in records if item["permission"] == permission]
        states = {item["evaluated_state"] for item in candidates}
        permission_matrix.append(
            {
                "permission": permission,
                "label_zh": PERMISSION_LABELS[permission],
                "status": _matrix_status(states),
                "candidate_count": len(candidates),
                "candidate_record_ids": [item["record_id"] for item in candidates],
                "candidate_states": sorted(states),
                "selected_authorization_id": None,
                "general_action_authorized": False,
                "requires_exact_request_scope_review": True,
                "authority": "unverified_structured_candidates_only",
            }
        )

    records_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        authorization_id = _clean(record.get("authorization_id"), limit=160)
        if authorization_id and record.get("record_kind") != "manifest_summary":
            records_by_id[authorization_id.casefold()].append(record)
    resolved_requests = [
        _resolve_request(request, records_by_id, evaluated_at) for request in requests
    ]
    resolved_requests.sort(key=lambda item: _clean(item.get("request_id")).casefold())

    override_conflicts: list[dict[str, Any]] = []
    quarantined_agent_artifact_ids: set[str] = set()
    for candidate in overrides:
        if not candidate.get("isolated"):
            continue
        artifact_id = _clean(candidate.get("source_artifact_id"), limit=80)
        if artifact_id:
            quarantined_agent_artifact_ids.add(artifact_id)
        conflict = {
            **candidate,
            "conflict_id": _stable_id(
                "R04-OVERRIDE",
                f"{candidate.get('candidate_id')}|{candidate.get('source_file_name')}",
            ),
            "resolution": "isolated_untrusted_override_candidate",
            "selected_as_authority": False,
            "permission_results_affected": False,
            "downstream_action_executed": False,
        }
        override_conflicts.append(conflict)
    override_conflicts.sort(key=lambda item: item["conflict_id"])

    receipt_rows: list[dict[str, Any]] = []
    seen_receipts: set[str] = set()
    for receipt in receipts:
        key = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        if key in seen_receipts:
            continue
        seen_receipts.add(key)
        submitted_files = list(receipt.get("submitted_files") or [])
        receipt_rows.append(
            {
                **receipt,
                "receipt_id": _stable_id("R04-RECEIPT", key),
                "all_referenced_files_uploaded": all(
                    _clean(item, limit=240).casefold() in uploaded_names
                    for item in submitted_files
                ),
                "accepted_as_authorization": False,
                "accepted_as_fact": False,
                "question_closed": False,
                "authority": "candidate_response_receipt_only",
            }
        )
    receipt_rows.sort(key=lambda item: (item["question_id"], item["receipt_id"]))

    unique_interview_sources: list[dict[str, Any]] = []
    seen_interviews: set[str] = set()
    for item in interview_sources:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen_interviews:
            continue
        seen_interviews.add(key)
        unique_interview_sources.append(
            {
                **item,
                "gap_id": _stable_id("R04-CLAIM-GAP", key),
                "accepted_as_fact": False,
            }
        )
    unique_interview_sources.sort(key=lambda item: item["gap_id"])

    permission_status = {
        item["permission"]: item["status"] for item in permission_matrix
    }
    receipt_question_ids = {item["question_id"] for item in receipt_rows}
    has_authorization_records = bool(records)
    trigger_by_question = {
        "R04-Q01": (
            has_authorization_records and permission_status["recording"] != "missing"
        ),
        "R04-Q02": (
            has_authorization_records
            and permission_status["internal_analysis"] != "missing"
        ),
        "R04-Q03": (
            has_authorization_records
            and permission_status["public_release"] != "missing"
        ),
        "R04-Q04": (
            has_authorization_records
            and permission_status["brand_and_logo"] != "missing"
        ),
        "R04-Q05": (
            has_authorization_records and permission_status["translation"] == "missing"
        ),
        "R04-Q06": (
            has_authorization_records and permission_status["ai_media"] != "missing"
        ),
        "R04-Q07": bool(unique_interview_sources),
        "R04-Q08": bool(override_conflicts),
    }
    trigger_by_question = {
        question_id: triggered or question_id in receipt_question_ids
        for question_id, triggered in trigger_by_question.items()
    }
    questions: list[dict[str, Any]] = []
    for spec in QUESTION_SPECS:
        if not trigger_by_question[spec["id"]]:
            continue
        question_receipts = [
            item for item in receipt_rows if item["question_id"] == spec["id"]
        ]
        questions.append(
            {
                **spec,
                "state": "open",
                "candidate_response_receipts": question_receipts,
                "accepted_as_resolved": False,
                "question_closed": False,
                "authority": "deterministic_authorization_question_only",
            }
        )

    applicable = bool(
        records
        or resolved_requests
        or override_conflicts
        or receipt_rows
        or unique_interview_sources
    )
    authorization_blockers = [
        item["id"]
        for item in questions
        if item["id"] != "R04-Q07"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "diagnostic_as_of": _iso_utc(evaluated_at),
        "applicability": {
            "status": "applicable" if applicable else "not_applicable",
            "reason_code": (
                "explicit_structured_authorization_metadata_detected"
                if applicable
                else "no_explicit_structured_authorization_metadata"
            ),
        },
        "authorization_status": {
            "status": "blocked" if authorization_blockers else "not_applicable",
            "blocking_question_ids": authorization_blockers,
            "public_release_authorized": False,
            "translation_authorized": False,
            "ai_media_authorized": False,
            "authority": "content_use_preflight_gate_only",
        },
        "permission_matrix": permission_matrix if applicable else [],
        "authorization_records": records,
        "content_use_requests": resolved_requests,
        "override_conflicts": override_conflicts,
        "quarantined_agent_artifact_ids": sorted(quarantined_agent_artifact_ids),
        "interview_statement_evidence_gaps": unique_interview_sources,
        "candidate_response_receipts": receipt_rows,
        "questions": questions,
        "boundaries": {
            "structured_formats_only": True,
            "free_prose_permission_inference_used": False,
            "manifest_or_management_record_accepted_as_external_truth": False,
            "candidate_response_accepted_automatically": False,
            "question_closed_automatically": False,
            "agent_candidate_may_override": False,
            "interview_statement_accepted_as_fact": False,
            "public_release_authorized": False,
            "translation_performed": False,
            "ai_media_generated": False,
            "deal_or_valuation_created": False,
            "aggregate_rating_produced": False,
        },
    }
