"""Deterministic evidence controls for structured company-intake materials.

The module inspects explicit CSV/JSON/JSONL fields only.  It reconciles uploader
declarations with stored bytes, exposes document-control candidates, and surfaces
exact structured conflicts.  It never chooses an authoritative source, accepts a
claim as fact, closes a question, or starts a downstream calculation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "company-intake-evidence-control-1.0.0"
MAX_STRUCTURED_ROWS = 10_000

QUESTION_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "R03-Q01",
        "priority": "critical",
        "dimension": "input_integrity",
        "question_zh": "请更正清单或重新提交文件，使声明哈希、字节数与实际上传内容一致。",
        "recompute_scope": [
            "manifest_reconciliation",
            "artifact_quarantine",
            "dependent_duplicate_groups",
        ],
    },
    {
        "id": "R03-Q02",
        "priority": "high",
        "dimension": "duplicate_evidence",
        "question_zh": "请确认重复材料的底层文件与权威副本；相同内容不得重复计为证据。",
        "recompute_scope": [
            "actual_payload_duplicate_groups",
            "declared_underlying_candidate_groups",
            "candidate_evidence_units",
        ],
    },
    {
        "id": "R03-Q03",
        "priority": "critical",
        "dimension": "document_control",
        "question_zh": "请由人工确认适用版本及其权威、批准、签字和生效依据；系统不会按新旧自动选择。",
        "recompute_scope": [
            "affected_document_families",
            "authority_selection_gate",
        ],
    },
    {
        "id": "R03-Q04",
        "priority": "high",
        "dimension": "structured_conflicts",
        "question_zh": "请复核相同结构化主张键下的冲突候选，并记录人工处置。",
        "recompute_scope": [
            "affected_claim_keys",
            "mapped_readiness_gates",
        ],
    },
)
QUESTION_BY_ID = {item["id"]: item for item in QUESTION_SPECS}

_CONTROL_FIELDS = (
    "version",
    "forecast_version",
    "as_of_date",
    "effective_date",
    "effective_at",
    "expires_at",
    "approval_status",
    "signature_status",
    "authority_class",
    "source_authority",
    "assertion_status",
)
_FORECAST_VALUE_FIELDS = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expense",
    "management_adjusted_ebitda",
)
_RECORD_VALUE_FIELDS = (
    "percentage",
    "ownership_status",
    "license_status",
    "pledge_status",
    "holder_or_counterparty",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _clean(value: Any, *, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _first(row: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = _clean(row.get(field))
        if value:
            return value
    return ""


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _document_control(row: Mapping[str, Any], row_number: int) -> dict[str, Any] | None:
    record_type = _first(row, "record_type")
    record_id = _first(row, "record_id")
    period = _first(row, "period", "period_label")
    has_forecast_values = any(_clean(row.get(field)) for field in _FORECAST_VALUE_FIELDS)
    if record_type and record_id:
        family_key = f"record:{record_type.casefold()}:{record_id.casefold()}"
    elif period and has_forecast_values:
        family_key = f"forecast:{period.casefold()}"
    else:
        related_subject = _first(row, "related_subject", "subject")
        document_type = _first(row, "document_type")
        document_id = _first(
            row,
            "document_id",
            "artifact_id",
            "evidence_id",
            "authorization_id",
            "claim_id",
        )
        if related_subject and document_type:
            family_key = (
                f"subject:{related_subject.casefold()}:{document_type.casefold()}"
            )
        elif document_id:
            family_key = f"document:{document_id.casefold()}"
        else:
            return None
    controls = {
        "version": _first(row, "version", "forecast_version"),
        "as_of_date": _first(row, "as_of_date"),
        "effective_date": _first(row, "effective_date", "effective_at"),
        "expires_at": _first(row, "expires_at"),
        "approval_status": _first(row, "approval_status"),
        "signature_status": _first(row, "signature_status"),
        "authority_class": _first(row, "authority_class", "source_authority"),
        "assertion_status": _first(row, "assertion_status"),
    }
    if not any(controls.values()):
        return None
    return {
        "family_key": family_key,
        "row_number": row_number,
        "document_id": _first(
            row,
            "document_id",
            "artifact_id",
            "evidence_id",
            "authorization_id",
            "claim_id",
            "record_id",
        ),
        **controls,
    }


def _assertion_candidates(
    row: Mapping[str, Any], row_number: int
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    period = _first(row, "period", "period_label")
    if period and any(_clean(row.get(field)) for field in _FORECAST_VALUE_FIELDS):
        for field in _FORECAST_VALUE_FIELDS:
            value = _clean(row.get(field))
            if value:
                candidates.append(
                    {
                        "claim_key": f"forecast:{period.casefold()}:{field}",
                        "value": value,
                        "row_number": row_number,
                        "field": field,
                    }
                )
    record_type = _first(row, "record_type")
    record_id = _first(row, "record_id")
    if record_type and record_id:
        for field in _RECORD_VALUE_FIELDS:
            value = _clean(row.get(field))
            if value:
                candidates.append(
                    {
                        "claim_key": (
                            f"record:{record_type.casefold()}:{record_id.casefold()}:{field}"
                        ),
                        "value": value,
                        "row_number": row_number,
                        "field": field,
                    }
                )
    return candidates


def _parse_csv(text: str) -> dict[str, Any]:
    try:
        reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    except csv.Error:
        return {}
    if not reader.fieldnames:
        return {}
    controls: list[dict[str, Any]] = []
    duplicate_declarations: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if row_number > MAX_STRUCTURED_ROWS + 1:
            break
        row = {str(key or "").strip(): value for key, value in raw_row.items()}
        control = _document_control(row, row_number)
        if control:
            controls.append(control)
        digest = _first(row, "artifact_content_sha256")
        if digest:
            duplicate_declarations.append(
                {
                    "row_number": row_number,
                    "artifact_id": _first(row, "artifact_id"),
                    "filename": _first(row, "filename"),
                    "declared_underlying_sha256": digest.casefold(),
                    "duplicate_group": _first(row, "duplicate_group"),
                    "related_subject": _first(row, "related_subject", "subject"),
                }
            )
        assertions.extend(_assertion_candidates(row, row_number))
    return {
        "source_format": "csv",
        "manifest_declarations": [],
        "document_controls": controls,
        "duplicate_declarations": duplicate_declarations,
        "assertion_candidates": assertions,
        "response_mappings": [],
        "is_manifest": False,
        "detected": bool(controls or duplicate_declarations or assertions),
    }


def _manifest_declarations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    files = payload.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return declarations
    for index, raw_item in enumerate(files, start=1):
        if not isinstance(raw_item, Mapping):
            continue
        filename = _clean(raw_item.get("filename"), limit=240)
        if not filename:
            continue
        question_ids = raw_item.get("question_ids")
        declarations.append(
            {
                "entry_index": index,
                "filename": filename,
                "declared_sha256": _first(
                    raw_item, "declared_sha256", "sha256"
                ).casefold(),
                "declared_byte_count": _integer(
                    raw_item.get("byte_count", raw_item.get("bytes"))
                ),
                "version": _first(raw_item, "version"),
                "as_of_date": _first(raw_item, "as_of_date"),
                "effective_date": _first(raw_item, "effective_date"),
                "approval_status": _first(raw_item, "approval_status"),
                "signature_status": _first(raw_item, "signature_status"),
                "authority_class": _first(
                    raw_item, "authority_class", "source_authority"
                ),
                "assertion_status": _first(raw_item, "assertion_status"),
                "question_ids": sorted(
                    {
                        _clean(item, limit=48)
                        for item in question_ids
                        if _clean(item, limit=48)
                    }
                )
                if isinstance(question_ids, Sequence)
                and not isinstance(question_ids, (str, bytes))
                else [],
            }
        )
    return declarations


def _response_mapping(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    question_id = _first(payload, "question_id")
    if not question_id:
        return None
    files = payload.get("submitted_files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        files = payload.get("supplement_files")
    return {
        "question_id": question_id,
        "declared_response_state": _first(
            payload, "response_state", "status", "classification"
        ),
        "submitted_files": sorted(
            {
                _clean(item, limit=240)
                for item in files
                if _clean(item, limit=240)
            }
        )
        if isinstance(files, Sequence) and not isinstance(files, (str, bytes))
        else [],
        "remaining_gap": _first(payload, "remaining_gap", "unavailable_reason"),
    }


def _parse_json_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    declarations = _manifest_declarations(payload)
    response_mappings: list[dict[str, Any]] = []
    direct = _response_mapping(payload)
    if direct:
        response_mappings.append(direct)
    for raw_item in payload.get("question_submission_mapping") or []:
        if isinstance(raw_item, Mapping) and (mapping := _response_mapping(raw_item)):
            response_mappings.append(mapping)
    for declaration in declarations:
        for question_id in declaration["question_ids"]:
            response_mappings.append(
                {
                    "question_id": question_id,
                    "declared_response_state": "payload_declared_for_question",
                    "submitted_files": [declaration["filename"]],
                    "remaining_gap": "",
                }
            )
    return {
        "source_format": "json",
        "manifest_declarations": declarations,
        "document_controls": [],
        "duplicate_declarations": [],
        "assertion_candidates": [],
        "response_mappings": response_mappings,
        "is_manifest": bool(declarations),
        "detected": bool(declarations or response_mappings),
    }


def _parse_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return _parse_json_payload(payload)


def _parse_jsonl(text: str) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []
    for line in text.splitlines()[:MAX_STRUCTURED_ROWS]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping) and (mapping := _response_mapping(payload)):
            mappings.append(mapping)
    return {
        "source_format": "jsonl",
        "manifest_declarations": [],
        "document_controls": [],
        "duplicate_declarations": [],
        "assertion_candidates": [],
        "response_mappings": mappings,
        "is_manifest": False,
        "detected": bool(mappings),
    }


def parse_structured_evidence_metadata(file_name: str, text: str) -> dict[str, Any]:
    """Parse exact structured evidence-control fields without prose inference."""

    suffix = Path(file_name).suffix.casefold()
    if suffix == ".csv":
        return _parse_csv(text)
    if suffix == ".json":
        return _parse_json(text)
    if suffix == ".jsonl":
        return _parse_jsonl(text)
    return {}


def _manifest_reconciliation(
    artifacts: Sequence[Mapping[str, Any]],
    declarations: Sequence[Mapping[str, Any]],
    manifest_artifact_ids: set[str],
) -> dict[str, Any]:
    actual_by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        name = _clean(artifact.get("file_name"), limit=240)
        if name:
            actual_by_name[name.casefold()].append(artifact)

    duplicate_entry_keys: set[tuple[str, str]] = set()
    seen_entries: set[tuple[str, str]] = set()
    for declaration in declarations:
        key = (
            _clean(declaration.get("source_artifact_id"), limit=80),
            _clean(declaration.get("filename"), limit=240).casefold(),
        )
        if key in seen_entries:
            duplicate_entry_keys.add(key)
        seen_entries.add(key)

    entries: list[dict[str, Any]] = []
    quarantined: set[str] = set()
    blocking_statuses = {
        "mismatch",
        "missing_upload",
        "invalid_digest",
        "duplicate_manifest_entry",
        "ambiguous_upload_name",
    }
    for declaration in declarations:
        filename = _clean(declaration.get("filename"), limit=240)
        declared_digest = _clean(declaration.get("declared_sha256"), limit=80).casefold()
        declared_bytes = declaration.get("declared_byte_count")
        source_artifact_id = _clean(declaration.get("source_artifact_id"), limit=80)
        candidates = sorted(
            actual_by_name.get(filename.casefold(), []),
            key=lambda item: _clean(item.get("id"), limit=80),
        )
        actual_digests = sorted(
            {_clean(item.get("sha256"), limit=80).casefold() for item in candidates}
        )
        actual_bytes = sorted(
            {
                int(item.get("byte_size"))
                for item in candidates
                if isinstance(item.get("byte_size"), int)
            }
        )
        duplicate_key = (source_artifact_id, filename.casefold())
        if duplicate_key in duplicate_entry_keys:
            status = "duplicate_manifest_entry"
        elif not _SHA256_PATTERN.fullmatch(declared_digest):
            status = "invalid_digest"
        elif not candidates:
            status = "missing_upload"
        elif len(actual_digests) > 1:
            status = "ambiguous_upload_name"
        elif declared_digest not in actual_digests:
            status = "mismatch"
        elif declared_bytes is not None and declared_bytes not in actual_bytes:
            status = "mismatch"
        else:
            status = "matched"
        if status in blocking_statuses:
            quarantined.update(
                _clean(item.get("id"), limit=80) for item in candidates
            )
        entries.append(
            {
                "declaration_id": _stable_id(
                    "R03-DECL",
                    f"{source_artifact_id}:{declaration.get('entry_index')}:{filename}",
                ),
                "source_manifest_artifact_id": source_artifact_id,
                "filename": filename,
                "declared_sha256": declared_digest or None,
                "actual_sha256_candidates": actual_digests,
                "declared_byte_count": declared_bytes,
                "actual_byte_count_candidates": actual_bytes,
                "actual_artifact_ids": [
                    _clean(item.get("id"), limit=80) for item in candidates
                ],
                "status": status,
                "declaration_selected_automatically": False,
            }
        )

    declared_names = {
        _clean(item.get("filename"), limit=240).casefold() for item in declarations
    }
    unlisted = sorted(
        _clean(artifact.get("id"), limit=80)
        for artifact in artifacts
        if _clean(artifact.get("id"), limit=80) not in manifest_artifact_ids
        and _clean(artifact.get("file_name"), limit=240).casefold()
        not in declared_names
    )
    effective_unlisted = unlisted if declarations else []
    if effective_unlisted:
        for artifact_id in effective_unlisted:
            quarantined.add(artifact_id)
    counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        counts[entry["status"]] += 1
    if effective_unlisted:
        counts["unlisted_upload"] += len(effective_unlisted)
    blocking = any(key in blocking_statuses for key in counts) or bool(
        effective_unlisted
    )
    return {
        "status": "blocked" if blocking else "passed" if declarations else "not_declared",
        "entries": sorted(
            entries,
            key=lambda item: (item["filename"].casefold(), item["declaration_id"]),
        ),
        "status_counts": dict(sorted(counts.items())),
        "unlisted_upload_artifact_ids": effective_unlisted,
        "quarantined_artifact_ids": sorted(item for item in quarantined if item),
        "declaration_or_payload_auto_repaired": False,
        "authority": "exact_upload_reconciliation_only",
    }


def diagnose_company_intake_evidence_control(
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return fail-closed evidence controls without accepting or selecting facts."""

    declarations: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    duplicate_declarations: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    response_mappings: list[dict[str, Any]] = []
    manifest_artifact_ids: set[str] = set()
    uploaded_names = {
        _clean(artifact.get("file_name"), limit=240) for artifact in artifacts
    }
    for artifact in artifacts:
        recognition = artifact.get("recognition")
        if not isinstance(recognition, Mapping):
            continue
        parsed = recognition.get("structured_evidence_metadata")
        if not isinstance(parsed, Mapping):
            continue
        artifact_id = _clean(artifact.get("id"), limit=80)
        file_name = _clean(artifact.get("file_name"), limit=240)
        if parsed.get("is_manifest"):
            manifest_artifact_ids.add(artifact_id)
        for key, target in (
            ("manifest_declarations", declarations),
            ("document_controls", controls),
            ("duplicate_declarations", duplicate_declarations),
            ("assertion_candidates", assertions),
            ("response_mappings", response_mappings),
        ):
            for raw_item in parsed.get(key) or []:
                if isinstance(raw_item, Mapping):
                    target.append(
                        {
                            **dict(raw_item),
                            "source_artifact_id": artifact_id,
                            "source_file_name": file_name,
                        }
                    )

    reconciliation = _manifest_reconciliation(
        artifacts, declarations, manifest_artifact_ids
    )
    quarantined = set(reconciliation["quarantined_artifact_ids"])

    payload_groups: list[dict[str, Any]] = []
    by_payload_digest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        digest = _clean(artifact.get("sha256"), limit=80).casefold()
        if _SHA256_PATTERN.fullmatch(digest):
            by_payload_digest[digest].append(artifact)
    for digest, members in sorted(by_payload_digest.items()):
        if len(members) < 2:
            continue
        aliases = sorted(
            (
                {
                    "artifact_id": _clean(item.get("id"), limit=80),
                    "file_name": _clean(item.get("file_name"), limit=240),
                }
                for item in members
            ),
            key=lambda item: (item["file_name"].casefold(), item["artifact_id"]),
        )
        payload_groups.append(
            {
                "group_id": _stable_id("R03-PAYLOAD", digest),
                "sha256": digest,
                "artifact_count": len(aliases),
                "candidate_evidence_unit_count": 1,
                "accepted_evidence_unit_count": 0,
                "aliases": aliases,
                "canonical_artifact_id": None,
                "authority": "actual_uploaded_bytes_only",
            }
        )

    declared_groups: list[dict[str, Any]] = []
    by_declared_digest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for declaration in duplicate_declarations:
        digest = _clean(
            declaration.get("declared_underlying_sha256"), limit=80
        ).casefold()
        if _SHA256_PATTERN.fullmatch(digest):
            by_declared_digest[digest].append(declaration)
    for digest, members in sorted(by_declared_digest.items()):
        unique_members: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for member in members:
            key = (
                _clean(member.get("artifact_id"), limit=120),
                _clean(member.get("filename"), limit=240),
                _clean(member.get("duplicate_group"), limit=120),
                _clean(member.get("related_subject"), limit=160),
            )
            item = unique_members.setdefault(
                key,
                {
                    **dict(member),
                    "source_artifact_ids": [],
                },
            )
            source_id = _clean(member.get("source_artifact_id"), limit=80)
            if source_id and source_id not in item["source_artifact_ids"]:
                item["source_artifact_ids"].append(source_id)
        distinct_members = list(unique_members.values())
        if len(distinct_members) < 2:
            continue
        source_ids = sorted(
            {
                source_id
                for item in distinct_members
                for source_id in item["source_artifact_ids"]
            }
        )
        matching_payload_ids = sorted(
            _clean(item.get("id"), limit=80)
            for item in by_payload_digest.get(digest, [])
        )
        source_quarantined = any(item in quarantined for item in source_ids)
        underlying_status = "present" if matching_payload_ids else "missing"
        aliases = sorted(
            (
                {
                    "declared_artifact_id": _clean(item.get("artifact_id"), limit=120),
                    "file_name": _clean(item.get("filename"), limit=240),
                    "source_artifact_ids": sorted(item["source_artifact_ids"]),
                }
                for item in distinct_members
            ),
            key=lambda item: (
                item["file_name"].casefold(),
                item["declared_artifact_id"],
                json.dumps(item["source_artifact_ids"]),
            ),
        )
        declared_groups.append(
            {
                "group_id": _stable_id("R03-DECLARED", digest),
                "declared_underlying_sha256": digest,
                "aliases": aliases,
                "underlying_payload_status": underlying_status,
                "matching_uploaded_artifact_ids": matching_payload_ids,
                "source_index_quarantined": source_quarantined,
                "candidate_evidence_unit_count": (
                    1 if matching_payload_ids and not source_quarantined else 0
                ),
                "accepted_evidence_unit_count": 0,
                "canonical_artifact_id": None,
                "authority": "submitter_declared_underlying_hash_candidate_only",
            }
        )

    controls_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for control in controls:
        controls_by_family[_clean(control.get("family_key"), limit=400)].append(
            control
        )
    document_families: list[dict[str, Any]] = []
    selection_required = False
    for family_key, family_controls in sorted(controls_by_family.items()):
        ordered = sorted(
            family_controls,
            key=lambda item: (
                _clean(item.get("version")),
                _clean(item.get("source_file_name")).casefold(),
                _clean(item.get("source_artifact_id"), limit=80),
                int(item.get("row_number") or 0),
            ),
        )
        signatures = {
            json.dumps(
                {
                    key: item.get(key)
                    for key in (
                        "version",
                        "as_of_date",
                        "effective_date",
                        "expires_at",
                        "approval_status",
                        "signature_status",
                        "authority_class",
                        "assertion_status",
                    )
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            for item in ordered
        }
        requires_selection = len(signatures) > 1
        selection_required = selection_required or requires_selection
        document_families.append(
            {
                "family_id": _stable_id("R03-FAMILY", family_key),
                "family_key": family_key,
                "candidate_count": len(ordered),
                "requires_human_selection": requires_selection,
                "candidates": ordered,
                "selected_authoritative_artifact_id": None,
                "authority": "structured_document_control_candidates_only",
            }
        )

    assertions_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assertion in assertions:
        assertions_by_key[_clean(assertion.get("claim_key"), limit=400)].append(
            assertion
        )
    conflicts: list[dict[str, Any]] = []
    for claim_key, claim_assertions in sorted(assertions_by_key.items()):
        values = sorted({_clean(item.get("value")) for item in claim_assertions})
        if len(values) < 2:
            continue
        ordered = sorted(
            claim_assertions,
            key=lambda item: (
                _clean(item.get("value")),
                _clean(item.get("source_file_name")).casefold(),
                _clean(item.get("source_artifact_id"), limit=80),
                int(item.get("row_number") or 0),
            ),
        )
        conflicts.append(
            {
                "conflict_id": _stable_id("R03-CONFLICT", claim_key),
                "claim_key": claim_key,
                "values": values,
                "candidates": ordered,
                "resolution_status": "unresolved",
                "selected_candidate": None,
                "free_prose_truth_inference_used": False,
                "authority": "exact_structured_key_conflict_only",
            }
        )

    receipts: list[dict[str, Any]] = []
    for index, mapping in enumerate(
        sorted(
            response_mappings,
            key=lambda item: (
                _clean(item.get("question_id")),
                _clean(item.get("source_file_name")).casefold(),
                json.dumps(item, ensure_ascii=False, sort_keys=True),
            ),
        ),
        start=1,
    ):
        submitted_files = [
            _clean(item, limit=240)
            for item in mapping.get("submitted_files") or []
            if _clean(item, limit=240)
        ]
        receipts.append(
            {
                "receipt_id": f"R03-RECEIPT-{index:04d}",
                "question_id": _clean(mapping.get("question_id"), limit=48),
                "declared_response_state": _clean(
                    mapping.get("declared_response_state"), limit=80
                ),
                "submitted_files": submitted_files,
                "all_referenced_files_uploaded": all(
                    item in uploaded_names for item in submitted_files
                ),
                "remaining_gap": _clean(mapping.get("remaining_gap")) or None,
                "source_artifact_id": _clean(
                    mapping.get("source_artifact_id"), limit=80
                ),
                "accepted_as_truth": False,
                "question_closed": False,
                "authority": "candidate_response_receipt_only",
            }
        )

    triggered: list[str] = []
    if reconciliation["status"] == "blocked":
        triggered.append("R03-Q01")
    if payload_groups or declared_groups:
        triggered.append("R03-Q02")
    if selection_required:
        triggered.append("R03-Q03")
    if conflicts:
        triggered.append("R03-Q04")
    questions = [
        {
            **QUESTION_BY_ID[question_id],
            "state": "open",
            "accepted_as_truth": False,
            "question_closed": False,
            "authority": "deterministic_evidence_control_question_only",
        }
        for question_id in triggered
    ]
    blocking_ids = [
        item["id"] for item in questions if item["priority"] == "critical"
    ]
    applicable = bool(
        declarations
        or controls
        or duplicate_declarations
        or assertions
        or response_mappings
        or payload_groups
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "applicability": {
            "status": "applicable" if applicable else "not_applicable",
            "reason_code": (
                "explicit_structured_evidence_controls_detected"
                if applicable
                else "no_explicit_structured_evidence_controls"
            ),
        },
        "integrity_gate": {
            "status": reconciliation["status"],
            "blocking_question_ids": blocking_ids,
            "evidence_promotion_allowed": False,
            "authority": "input_integrity_gate_only",
        },
        "manifest_reconciliation": reconciliation,
        "actual_payload_duplicate_groups": payload_groups,
        "declared_underlying_candidate_groups": declared_groups,
        "document_control_families": document_families,
        "selected_authoritative_artifact_id": None,
        "structured_conflicts": conflicts,
        "candidate_response_receipts": receipts,
        "questions": questions,
        "recompute_scope": {
            "mode": "dependency_scoped_diagnostic_only",
            "calculation_performed": False,
            "automatic_full_case_recompute_claimed": False,
        },
        "boundaries": {
            "free_prose_truth_inference_used": False,
            "manifest_or_payload_auto_repaired": False,
            "canonical_evidence_selected_automatically": False,
            "authoritative_source_selected_automatically": False,
            "conflict_resolved_automatically": False,
            "candidate_response_accepted_automatically": False,
            "question_closed_automatically": False,
            "financial_calculation_performed": False,
            "deal_or_valuation_created": False,
            "aggregate_rating_produced": False,
            "public_release_authorized": False,
        },
    }
