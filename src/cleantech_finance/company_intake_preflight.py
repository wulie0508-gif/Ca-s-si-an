"""Deterministic structured-metadata preflight for company-intake finance packs.

Only explicit CSV columns and JSON keys are inspected. Free prose, filenames, dates,
amount size, and apparent recency never select a financial basis.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "company-intake-financial-basis-1.0.0"
MAX_STRUCTURED_ROWS = 10_000

QUESTION_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "R02-Q01",
        "priority": "critical",
        "dimension": "entity_scope",
        "question_zh": "请确认本轮财务分析采用的法律主体与合并范围。",
    },
    {
        "id": "R02-Q02",
        "priority": "critical",
        "dimension": "related_entity",
        "question_zh": "请说明各 component_entity 的法律、控制和会计关系及是否纳入口径。",
    },
    {
        "id": "R02-Q03",
        "priority": "critical",
        "dimension": "reporting_period",
        "question_zh": "请锁定可比较期间并提供不同期间之间的受控桥接。",
    },
    {
        "id": "R02-Q04",
        "priority": "critical",
        "dimension": "currency_and_unit",
        "question_zh": "请确认统一展示币种和单位，并提供逐来源换算桥。",
    },
    {
        "id": "R02-Q05",
        "priority": "critical",
        "dimension": "vat_basis",
        "question_zh": "请锁定收入与成本的 VAT 口径并提供含税/不含税桥接。",
    },
    {
        "id": "R02-Q06",
        "priority": "critical",
        "dimension": "cash_as_of_and_restrictions",
        "question_zh": "请锁定现金评估日，并逐账户区分可用与受限现金。",
    },
    {
        "id": "R02-Q07",
        "priority": "critical",
        "dimension": "forecast_version",
        "question_zh": "请确认预测版本、主体、税基和批准状态；未批准版本不得选用。",
    },
    {
        "id": "R02-Q08",
        "priority": "high",
        "dimension": "source_precedence_and_reconciliation",
        "question_zh": "请提供来源优先级和跨表对账桥；不得按日期或数值静默选值。",
    },
)
QUESTION_BY_ID = {item["id"]: item for item in QUESTION_SPECS}

_CASH_LINE_ITEMS = frozenset(
    {
        "cash",
        "cash and bank balances",
        "available cash",
        "pledged cash",
        "total bank balance",
        "total and available cash",
    }
)
_UNKNOWN_VALUES = frozenset(
    {"", "unknown", "not specified", "not available", "n/a", "na", "未说明", "未知"}
)
_APPROVED_VALUES = frozenset({"approved", "board approved", "已批准", "批准"})


def _clean(value: Any, *, limit: int = 320) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _first(row: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = _clean(row.get(field))
        if value:
            return value
    return ""


def _period(row: Mapping[str, Any]) -> dict[str, str] | None:
    value = {
        "label": _first(row, "period_label", "declared_period_label"),
        "start": _first(row, "period_start"),
        "end": _first(row, "period_end"),
    }
    return value if any(value.values()) else None


def _basis_record(row: Mapping[str, Any], row_number: int) -> dict[str, Any] | None:
    record: dict[str, Any] = {
        "row_number": row_number,
        "entity_scope": _first(row, "entity_scope", "source_scope", "declared_entity_scope"),
        "component_entity": _first(row, "component_entity"),
        "period": _period(row),
        "as_of_date": _first(row, "as_of_date", "declared_as_of"),
        "currency": _first(row, "currency", "declared_currency"),
        "unit": _first(row, "unit", "value_unit", "source_unit", "declared_unit"),
        "vat_basis": _first(row, "tax_basis", "declared_tax_basis"),
    }
    return record if any(value for key, value in record.items() if key != "row_number") else None


def _cash_candidate(row: Mapping[str, Any], row_number: int) -> dict[str, Any] | None:
    line_item = _first(row, "line_item", "metric").casefold()
    cash_headers = any(field in row for field in ("restriction_class", "availability_class"))
    if not cash_headers and line_item not in _CASH_LINE_ITEMS:
        return None
    return {
        "row_number": row_number,
        "entity_scope": _first(row, "entity_scope", "source_scope"),
        "component_entity": _first(row, "component_entity"),
        "as_of_date": _first(row, "as_of_date"),
        "currency": _first(row, "currency"),
        "unit": _first(row, "unit", "source_unit"),
        "restriction_class": _first(row, "restriction_class"),
        "availability_class": _first(row, "availability_class"),
        "amount_text": _first(row, "balance", "amount", "source_value"),
        "line_item": _first(row, "line_item", "metric"),
    }


def _forecast_candidate(row: Mapping[str, Any], row_number: int) -> dict[str, Any] | None:
    version = _first(row, "forecast_version")
    if not version:
        return None
    return {
        "row_number": row_number,
        "forecast_version": version,
        "as_of_date": _first(row, "as_of_date"),
        "approval_status": _first(row, "approval_status"),
        "entity_scope": _first(row, "entity_scope"),
        "period_label": _first(row, "period_label"),
        "currency": _first(row, "currency"),
        "unit": _first(row, "unit"),
        "vat_basis": _first(row, "tax_basis"),
    }


def _parse_csv(text: str) -> dict[str, Any]:
    try:
        reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    except csv.Error:
        return {}
    if not reader.fieldnames:
        return {}
    basis_records: list[dict[str, Any]] = []
    cash_candidates: list[dict[str, Any]] = []
    forecast_candidates: list[dict[str, Any]] = []
    precedence_declarations: list[dict[str, Any]] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if row_number > MAX_STRUCTURED_ROWS + 1:
            break
        row = {str(key or "").strip(): value for key, value in raw_row.items()}
        if record := _basis_record(row, row_number):
            basis_records.append(record)
        if cash := _cash_candidate(row, row_number):
            cash_candidates.append(cash)
        if forecast := _forecast_candidate(row, row_number):
            forecast_candidates.append(forecast)
        if _first(row, "metric").casefold() == "priority":
            precedence_declarations.append(
                {
                    "row_number": row_number,
                    "declaration": _first(row, "normalization_or_reconciliation"),
                    "authority": "structured_candidate_declaration_only",
                }
            )
    return {
        "source_format": "csv",
        "basis_records": basis_records,
        "cash_candidates": cash_candidates,
        "forecast_candidates": forecast_candidates,
        "precedence_declarations": precedence_declarations,
        "response_mappings": [],
        "detected": bool(
            basis_records
            or cash_candidates
            or forecast_candidates
            or precedence_declarations
        ),
    }


def _manifest_file_record(item: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    row = {
        "declared_entity_scope": item.get("declared_entity_scope"),
        "declared_period_label": item.get("declared_period_label"),
        "declared_as_of": item.get("declared_as_of"),
        "declared_currency": item.get("declared_currency"),
        "declared_unit": item.get("declared_unit"),
        "declared_tax_basis": item.get("declared_tax_basis"),
    }
    record = _basis_record(row, index)
    if record is not None:
        record["declared_filename"] = _clean(item.get("filename"))
    return record


def _parse_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    basis_records: list[dict[str, Any]] = []
    forecast_candidates: list[dict[str, Any]] = []
    cash_candidates: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("files") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        if record := _manifest_file_record(item, index):
            basis_records.append(record)
        for version_index, raw_version in enumerate(item.get("declared_versions") or [], start=1):
            if not isinstance(raw_version, Mapping):
                continue
            forecast_candidates.append(
                {
                    "row_number": version_index,
                    "forecast_version": _clean(raw_version.get("forecast_version")),
                    "as_of_date": _clean(raw_version.get("as_of")),
                    "approval_status": "",
                    "entity_scope": _clean(raw_version.get("entity_scope")),
                    "period_label": "",
                    "currency": "",
                    "unit": _clean(raw_version.get("unit")),
                    "vat_basis": _clean(raw_version.get("tax_basis")),
                }
            )
        restrictions = item.get("declared_restriction_classes")
        if isinstance(restrictions, Sequence) and not isinstance(restrictions, str):
            for restriction in restrictions:
                cash_candidates.append(
                    {
                        "row_number": index,
                        "entity_scope": _clean(item.get("declared_entity_scope")),
                        "component_entity": "",
                        "as_of_date": _clean(item.get("declared_as_of")),
                        "currency": _clean(item.get("declared_currency")),
                        "unit": _clean(item.get("declared_unit")),
                        "restriction_class": _clean(restriction),
                        "availability_class": "",
                        "amount_text": "",
                        "line_item": "",
                    }
                )

    policy = payload.get("submission_policy")
    precedence_declarations: list[dict[str, Any]] = []
    if isinstance(policy, Mapping) and isinstance(
        policy.get("cross_file_source_priority_declared"), bool
    ):
        precedence_declarations.append(
            {
                "declared": policy["cross_file_source_priority_declared"],
                "authority": "structured_manifest_policy_only",
            }
        )

    response_mappings: list[dict[str, Any]] = []
    for raw_mapping in payload.get("question_submission_mapping") or []:
        if not isinstance(raw_mapping, Mapping):
            continue
        question_id = _clean(raw_mapping.get("question_id"), limit=32)
        if question_id not in QUESTION_BY_ID:
            continue
        submitted_files = raw_mapping.get("submitted_files")
        response_mappings.append(
            {
                "question_id": question_id,
                "declared_response_state": _clean(
                    raw_mapping.get("response_state"), limit=32
                ),
                "submitted_files": [
                    _clean(item)
                    for item in submitted_files
                    if _clean(item)
                ]
                if isinstance(submitted_files, Sequence)
                and not isinstance(submitted_files, str)
                else [],
                "remaining_gap": _clean(raw_mapping.get("remaining_gap")),
            }
        )

    selected_basis = payload.get("selected_normalization_basis")
    return {
        "source_format": "json",
        "basis_records": basis_records,
        "cash_candidates": cash_candidates,
        "forecast_candidates": forecast_candidates,
        "precedence_declarations": precedence_declarations,
        "response_mappings": response_mappings,
        "declared_normalization_basis": (
            {str(key): _clean(value) for key, value in selected_basis.items()}
            if isinstance(selected_basis, Mapping)
            else {}
        ),
        "detected": bool(
            basis_records
            or cash_candidates
            or forecast_candidates
            or precedence_declarations
            or response_mappings
        ),
    }


def parse_structured_financial_metadata(file_name: str, text: str) -> dict[str, Any]:
    """Parse exact structured fields; unsupported formats fail closed to no metadata."""

    suffix = Path(file_name).suffix.casefold()
    if suffix == ".csv":
        return _parse_csv(text)
    if suffix == ".json":
        return _parse_json(text)
    return {}


def _unique_candidates(
    records: Sequence[Mapping[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(field)
        if value in (None, "", {}):
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        item = found.setdefault(key, {"value": value, "sources": []})
        source = {
            "artifact_id": record.get("artifact_id"),
            "file_name": record.get("file_name"),
            "row_number": record.get("row_number"),
        }
        if source not in item["sources"]:
            item["sources"].append(source)
    return [found[key] for key in sorted(found)]


def _is_unknown(value: Any) -> bool:
    if isinstance(value, Mapping):
        return not any(_clean(item) for item in value.values())
    normalized = _clean(value).casefold()
    return normalized in _UNKNOWN_VALUES or normalized.startswith("not specified")


def _dimension(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates or any(_is_unknown(item["value"]) for item in candidates):
        status = "unknown"
    elif len(candidates) > 1:
        status = "multiple"
    else:
        status = "single_candidate"
    return {
        "status": status,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selected_candidate": None,
        "authority": "structured_metadata_candidates_only",
    }


def diagnose_company_intake_financial_basis(
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project explicit structured metadata without selecting or calculating values."""

    records: list[dict[str, Any]] = []
    cash_candidates: list[dict[str, Any]] = []
    forecast_candidates: list[dict[str, Any]] = []
    precedence_declarations: list[dict[str, Any]] = []
    response_mappings: list[dict[str, Any]] = []
    declared_bases: list[dict[str, Any]] = []
    uploaded_names = {
        _clean(artifact.get("file_name"))
        for artifact in artifacts
        if _clean(artifact.get("file_name"))
    }
    detected_artifact_ids: list[str] = []
    for artifact in artifacts:
        recognition = artifact.get("recognition")
        if not isinstance(recognition, Mapping):
            continue
        parsed = recognition.get("structured_financial_metadata")
        if not isinstance(parsed, Mapping) or not parsed.get("detected"):
            continue
        artifact_id = _clean(artifact.get("id"), limit=80)
        file_name = _clean(artifact.get("file_name"))
        detected_artifact_ids.append(artifact_id)
        for key, target in (
            ("basis_records", records),
            ("cash_candidates", cash_candidates),
            ("forecast_candidates", forecast_candidates),
            ("precedence_declarations", precedence_declarations),
            ("response_mappings", response_mappings),
        ):
            for raw_item in parsed.get(key) or []:
                if not isinstance(raw_item, Mapping):
                    continue
                target.append(
                    {
                        **dict(raw_item),
                        "artifact_id": artifact_id,
                        "file_name": file_name,
                    }
                )
        declared_basis = parsed.get("declared_normalization_basis")
        if isinstance(declared_basis, Mapping) and declared_basis:
            declared_bases.append(
                {
                    "artifact_id": artifact_id,
                    "file_name": file_name,
                    "values": dict(declared_basis),
                    "authority": "unverified_candidate_declaration",
                }
            )

    applicable = bool(detected_artifact_ids)
    if not applicable:
        return {
            "schema_version": SCHEMA_VERSION,
            "rule_version": RULE_VERSION,
            "applicability": {
                "status": "not_applicable",
                "reason_code": "no_explicit_structured_financial_metadata",
            },
            "calculation_status": {"status": "not_applicable", "blocking_question_ids": []},
            "questions": [],
            "candidate_response_receipts": [],
            "boundaries": {
                "free_prose_inference_used": False,
                "candidate_selected_automatically": False,
                "financial_calculation_performed": False,
                "fact_accepted_automatically": False,
                "deal_or_valuation_created": False,
                "aggregate_rating_produced": False,
            },
        }

    dimensions = {
        "entity_scope": _dimension(_unique_candidates(records, "entity_scope")),
        "component_entity": _dimension(_unique_candidates(records, "component_entity")),
        "reporting_period": _dimension(_unique_candidates(records, "period")),
        "currency": _dimension(_unique_candidates(records, "currency")),
        "unit": _dimension(_unique_candidates(records, "unit")),
        "vat_basis": _dimension(_unique_candidates(records, "vat_basis")),
        "cash_as_of": _dimension(_unique_candidates(cash_candidates, "as_of_date")),
        "cash_restriction": _dimension(
            _unique_candidates(cash_candidates, "restriction_class")
        ),
        "cash_availability": _dimension(
            _unique_candidates(cash_candidates, "availability_class")
        ),
    }

    forecast_versions = _unique_candidates(forecast_candidates, "forecast_version")
    approval_values = _unique_candidates(forecast_candidates, "approval_status")
    forecast_unapproved = bool(forecast_candidates) and (
        not approval_values
        or any(
            _clean(item["value"]).casefold() not in _APPROVED_VALUES
            for item in approval_values
        )
    )
    forecast_status = (
        "not_present"
        if not forecast_candidates
        else "unapproved"
        if forecast_unapproved
        else "multiple"
        if len(forecast_versions) > 1
        else "single_approved_candidate"
    )

    receipt_by_question: dict[str, dict[str, Any]] = {}
    for mapping in response_mappings:
        question_id = _clean(mapping.get("question_id"), limit=32)
        if question_id not in QUESTION_BY_ID:
            continue
        submitted_files = [
            _clean(item) for item in mapping.get("submitted_files") or [] if _clean(item)
        ]
        receipt_by_question[question_id] = {
            "question_id": question_id,
            "receipt_state": "candidate_response_received",
            "declared_response_state": _clean(mapping.get("declared_response_state")),
            "submitted_files": submitted_files,
            "all_referenced_files_uploaded": all(
                item in uploaded_names for item in submitted_files
            ),
            "remaining_gap": _clean(mapping.get("remaining_gap")) or None,
            "accepted_as_truth": False,
            "question_closed": False,
            "authority": "supplement_manifest_mapping_only",
            "source_artifact_id": mapping.get("artifact_id"),
        }

    triggered_ids: list[str] = []
    if dimensions["entity_scope"]["status"] != "single_candidate":
        triggered_ids.append("R02-Q01")
    if (
        dimensions["component_entity"]["candidate_count"] > 1
        or dimensions["entity_scope"]["status"] == "multiple"
    ):
        triggered_ids.append("R02-Q02")
    if dimensions["reporting_period"]["status"] != "single_candidate":
        triggered_ids.append("R02-Q03")
    if (
        dimensions["currency"]["status"] != "single_candidate"
        or dimensions["unit"]["status"] != "single_candidate"
    ):
        triggered_ids.append("R02-Q04")
    if dimensions["vat_basis"]["status"] != "single_candidate":
        triggered_ids.append("R02-Q05")
    if (
        dimensions["cash_as_of"]["status"] != "single_candidate"
        or dimensions["cash_restriction"]["status"] != "single_candidate"
        or dimensions["cash_availability"]["status"] != "single_candidate"
    ):
        triggered_ids.append("R02-Q06")
    if forecast_status in {"unapproved", "multiple"}:
        triggered_ids.append("R02-Q07")
    if len(detected_artifact_ids) > 1:
        triggered_ids.append("R02-Q08")

    questions = []
    for spec in QUESTION_SPECS:
        if spec["id"] not in triggered_ids:
            continue
        questions.append(
            {
                **spec,
                "state": "open",
                "candidate_response": receipt_by_question.get(spec["id"]),
                "authority": "deterministic_preflight_question_only",
            }
        )
    blocking_ids = [
        item["id"] for item in questions if item["priority"] == "critical"
    ]
    precedence_status = (
        "candidate_declared"
        if any(
            item.get("declared") is True or bool(_clean(item.get("declaration")))
            for item in precedence_declarations
        )
        else "explicitly_not_declared"
        if any(item.get("declared") is False for item in precedence_declarations)
        else "not_declared"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "applicability": {
            "status": "applicable",
            "reason_code": "explicit_structured_financial_metadata_detected",
            "detected_artifact_ids": sorted(set(detected_artifact_ids)),
        },
        "dimensions": dimensions,
        "forecast": {
            "status": forecast_status,
            "versions": forecast_versions,
            "approval_statuses": approval_values,
            "candidates": forecast_candidates,
            "selected_version": None,
            "authority": "structured_metadata_candidates_only",
        },
        "cash_candidates": cash_candidates,
        "source_precedence": {
            "status": precedence_status,
            "declarations": precedence_declarations,
            "selected_precedence": None,
            "authority": "candidate_declaration_only",
        },
        "declared_normalization_bases": declared_bases,
        "candidate_response_receipts": [
            receipt_by_question[key] for key in sorted(receipt_by_question)
        ],
        "questions": questions,
        "calculation_status": {
            "status": "blocked" if blocking_ids else "human_review_required",
            "blocking_question_ids": blocking_ids,
            "financial_calculation_performed": False,
            "reason_zh": (
                "关键财务口径存在多个候选、未知值或未批准预测。"
                if blocking_ids
                else "结构化候选口径仍需人工确认。"
            ),
            "authority": "preflight_gate_only",
        },
        "boundaries": {
            "free_prose_inference_used": False,
            "candidate_selected_automatically": False,
            "financial_calculation_performed": False,
            "fact_accepted_automatically": False,
            "deal_or_valuation_created": False,
            "aggregate_rating_produced": False,
        },
    }
