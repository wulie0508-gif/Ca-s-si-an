"""Deterministic CSV/XLSX course and policy matching."""

from __future__ import annotations

import csv
import hashlib
import json
import posixpath
import re
import secrets
import unicodedata
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

CATALOG_PARSER_VERSION = "2.0.0"
CATALOG_ATTESTATION_SCHEMA_VERSION = "1.0"
POLICY_ALLOWED_REVIEW_STATUSES = ("已复核通过", "approved", "verified")
COURSE_ALLOWED_REVIEW_STATUSES = (
    "active",
    "approved",
    "published",
    "synthetic_fixture",
    "已发布",
    "已复核通过",
)
COURSE_ACTIVE_STATUSES = ("active", "available", "published", "开放", "可用")
_ROW_NUMBER = "__source_row__"
_SHEET_NAME = "__source_sheet__"

DEFAULT_MATCHING_CONFIG: dict[str, Any] = {
    "tag_weights": {
        "industry": 3.0,
        "stage": 2.5,
        "need": 3.0,
        "technology": 2.0,
        "geography": 1.5,
        "market": 1.5,
    },
    "minimum_match_score": 2.0,
    "maximum_results": 5,
    # Kept in exported configuration for transparency. The policy filter below
    # intentionally uses POLICY_ALLOWED_REVIEW_STATUSES so a config cannot weaken it.
    "policy_allowed_review_statuses": list(POLICY_ALLOWED_REVIEW_STATUSES),
    "field_aliases": {
        "id": ["id", "course_id", "policy_id", "编号", "课程编号", "政策编号"],
        "title": ["title", "name", "课程名称", "政策名称", "名称"],
        "review_status": ["review_status", "复核状态", "审核状态"],
        "expiry_date": [
            "expiry_date",
            "valid_until",
            "有效期至",
            "截止日期",
            "失效日期",
            "有效期/申报窗口",
        ],
        "industry": ["industry_tags", "industry", "行业标签", "适用行业"],
        "stage": ["stage_tags", "stage", "阶段标签", "企业阶段"],
        "need": [
            "need_tags",
            "needs",
            "需求标签",
            "痛点标签",
            "关键主题标签",
        ],
        "technology": ["technology_tags", "technology", "技术标签", "关键主题标签"],
        "geography": [
            "geography_tags",
            "geography",
            "地区标签",
            "适用地区",
            "层级",
        ],
        "market": ["market_tags", "market", "市场标签", "目标市场", "关键主题标签"],
        "provider": [
            "provider",
            "issuing_authority",
            "publisher",
            "authority",
            "发文机关",
            "发布机构",
            "主管部门",
            "提供方",
        ],
        "source_url": [
            "source_url",
            "official_url",
            "policy_url",
            "url",
            "原文来源 URL",
            "来源网址",
            "政策原文链接",
            "官方链接",
            "原文链接",
        ],
        "active_status": ["active_status", "status", "状态", "发布状态"],
        "data_class": ["data_class", "record_origin", "数据类别"],
        "simulation_only": ["simulation_only", "synthetic", "仅模拟"],
        "disclosure_label": ["disclosure_label", "模拟说明", "披露标签"],
        "summary": ["summary", "description", "简介", "课程简介"],
        "updated_at": ["updated_at", "last_updated", "更新时间"],
        "languages": ["languages", "language", "语言"],
        "delivery_format": ["delivery_format", "format", "授课形式"],
        "duration_minutes": ["duration_minutes", "duration", "时长分钟"],
    },
}


def load_matching_config(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return json.loads(json.dumps(DEFAULT_MATCHING_CONFIG, ensure_ascii=False))
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Matching configuration root must be an object")
    payload = payload.get("matching", payload)
    if not isinstance(payload, dict):
        raise ValueError("matching configuration must be an object")
    config = json.loads(json.dumps(DEFAULT_MATCHING_CONFIG, ensure_ascii=False))
    for key, value in payload.items():
        if key in {"tag_weights", "field_aliases"} and isinstance(value, dict):
            config[key].update(value)
        else:
            config[key] = value
    return config


def _load_catalog_attestation(
    path: str | Path | None,
    *,
    catalog: dict[str, Any],
) -> dict[str, Any] | None:
    """Load a hash-bound local declaration without changing row review state."""

    if path is None:
        return None
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Catalog attestation does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Catalog attestation must be readable UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Catalog attestation root must be an object")
    if payload.get("schema_version") != CATALOG_ATTESTATION_SCHEMA_VERSION:
        raise ValueError(
            "Catalog attestation schema_version must be "
            f"{CATALOG_ATTESTATION_SCHEMA_VERSION}"
        )
    attested_hash = str(payload.get("catalog_sha256") or "").strip().casefold()
    if not re.fullmatch(r"[a-f0-9]{64}", attested_hash):
        raise ValueError("Catalog attestation catalog_sha256 must be a SHA-256 digest")
    if not secrets.compare_digest(attested_hash, str(catalog["sha256"]).casefold()):
        raise ValueError("Catalog attestation does not match the catalog SHA-256")
    if payload.get("byte_length") != catalog["byte_length"]:
        raise ValueError("Catalog attestation byte_length does not match")
    if payload.get("canonical_view_sha256") != catalog["canonical_view_sha256"]:
        raise ValueError("Catalog attestation canonical_view_sha256 does not match")
    if payload.get("parser_version") != catalog["parser_version"]:
        raise ValueError("Catalog attestation parser_version does not match")
    if payload.get("source_sheet") != catalog["source_sheet"]:
        raise ValueError("Catalog attestation source_sheet does not match")
    if payload.get("header_row") != catalog["header_row"]:
        raise ValueError("Catalog attestation header_row does not match")
    if payload.get("record_count") != len(catalog["rows"]):
        raise ValueError("Catalog attestation record_count does not match")
    attested_by = str(payload.get("attested_by") or "").strip()
    if not attested_by or len(attested_by) > 120:
        raise ValueError(
            "Catalog attestation attested_by is required and must be at most "
            "120 characters"
        )
    attested_at = str(payload.get("attested_at") or "").strip()
    try:
        parsed_at = datetime.fromisoformat(attested_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Catalog attestation attested_at must be ISO 8601") from exc
    if parsed_at.tzinfo is None:
        raise ValueError("Catalog attestation attested_at must include a timezone")
    if parsed_at > datetime.now(parsed_at.tzinfo) + timedelta(minutes=5):
        raise ValueError("Catalog attestation attested_at must not be in the future")
    if payload.get("scope") != "reference_suggestions":
        raise ValueError(
            "Catalog attestation scope must be reference_suggestions"
        )
    if payload.get("review_status") != "reviewed":
        raise ValueError("Catalog attestation review_status must be reviewed")
    if payload.get("not_eligibility_determination") is not True:
        raise ValueError(
            "Catalog attestation must acknowledge not_eligibility_determination"
        )
    if payload.get("official_verification_required") is not True:
        raise ValueError(
            "Catalog attestation must acknowledge official_verification_required"
        )
    if payload.get("revoked") is not False:
        raise ValueError("Catalog attestation must not be revoked")
    statement = str(payload.get("statement") or "").strip()
    if len(statement) > 500:
        raise ValueError("Catalog attestation statement must be at most 500 characters")
    return {
        "state": "confirmed",
        "method": "catalog_sha256_attestation",
        "assurance": "unsigned_local_declaration",
        "catalog_sha256": attested_hash,
        "byte_length": catalog["byte_length"],
        "canonical_view_sha256": catalog["canonical_view_sha256"],
        "parser_version": catalog["parser_version"],
        "source_sheet": catalog["source_sheet"],
        "header_row": catalog["header_row"],
        "record_count": len(catalog["rows"]),
        "attested_by": attested_by,
        "attested_at": parsed_at.isoformat(),
        "scope": "reference_suggestions",
        "review_status": "reviewed",
        "not_eligibility_determination": True,
        "official_verification_required": True,
        "statement": statement or None,
    }


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    value = 0
    for character in letters.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _worksheet_rows(
    archive: zipfile.ZipFile,
    worksheet_path: str,
    shared: list[str],
) -> list[tuple[int, list[str]]]:
    sheet = ElementTree.fromstring(archive.read(worksheet_path))
    rows: list[tuple[int, list[str]]] = []
    for row_node in sheet.findall(".//{*}sheetData/{*}row"):
        try:
            row_number = int(row_node.attrib.get("r", len(rows) + 1))
        except ValueError:
            row_number = len(rows) + 1
        values: dict[int, str] = {}
        for cell in row_node.findall("{*}c"):
            index = _column_index(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
            else:
                raw = cell.findtext("{*}v") or ""
                if cell_type == "s" and raw:
                    value = shared[int(raw)]
                elif cell_type == "b":
                    value = "true" if raw == "1" else "false"
                else:
                    value = raw
            values[index] = value.strip()
        row = (
            [values.get(index, "") for index in range(max(values) + 1)]
            if values
            else []
        )
        rows.append((row_number, row))
    return rows


def _xlsx_sheets(payload: bytes) -> list[tuple[str, list[tuple[int, list[str]]]]]:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("{*}si"):
                shared.append("".join(node.text or "" for node in item.findall(".//{*}t")))

        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relation.attrib.get("Id"): relation.attrib.get("Target")
            for relation in relations.findall("{*}Relationship")
        }
        sheets: list[tuple[str, list[tuple[int, list[str]]]]] = []
        relation_key = (
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        for sheet_node in workbook.findall(".//{*}sheet"):
            relation_id = sheet_node.attrib.get(relation_key)
            target = targets.get(relation_id)
            if not target:
                continue
            worksheet_path = target.lstrip("/")
            if not worksheet_path.startswith("xl/"):
                worksheet_path = posixpath.normpath(f"xl/{worksheet_path}")
            sheets.append(
                (
                    sheet_node.attrib.get("name", f"Sheet{len(sheets) + 1}"),
                    _worksheet_rows(archive, worksheet_path, shared),
                )
            )
        return sheets


def _normalized_header(value: str) -> str:
    return value.strip().casefold()


def _header_match(
    row: list[str],
    aliases: dict[str, list[str]],
) -> tuple[int, int] | None:
    values = {_normalized_header(value) for value in row if value.strip()}
    matched = {
        field
        for field, choices in aliases.items()
        if any(_normalized_header(choice) in values for choice in choices)
    }
    if not {"id", "title"}.issubset(matched):
        return None
    return len(matched), len(values)


def _unique_headers(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    counts: Counter[str] = Counter()
    for index, raw in enumerate(raw_headers, start=1):
        base = raw.strip() or f"column_{index}"
        counts[base] += 1
        headers.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return headers


def _select_xlsx_table(
    payload: bytes,
    aliases: dict[str, list[str]],
) -> tuple[str, int, list[str], list[dict[str, str]]]:
    candidates: list[
        tuple[int, int, int, int, int, str, list[tuple[int, list[str]]]]
    ] = []
    for sheet_index, (sheet_name, raw_rows) in enumerate(_xlsx_sheets(payload)):
        for row_position, (row_number, row) in enumerate(raw_rows[:50]):
            score = _header_match(row, aliases)
            if score is None:
                continue
            matched_fields, populated_cells = score
            candidates.append(
                (
                    matched_fields,
                    populated_cells,
                    -sheet_index,
                    -row_number,
                    row_position,
                    sheet_name,
                    raw_rows,
                )
            )
    if not candidates:
        raise ValueError(
            "No catalog table found in workbook; expected an id and title header row"
        )

    _, _, _, negative_row_number, header_position, sheet_name, raw_rows = max(
        candidates,
        key=lambda candidate: candidate[:4],
    )
    header_row = -negative_row_number
    headers = _unique_headers(raw_rows[header_position][1])
    records: list[dict[str, str]] = []
    for source_row, raw in raw_rows[header_position + 1 :]:
        row = {
            headers[index]: (raw[index].strip() if index < len(raw) else "")
            for index in range(len(headers))
        }
        if not any(row.values()):
            continue
        row[_ROW_NUMBER] = str(source_row)
        row[_SHEET_NAME] = sheet_name
        records.append(row)
    return sheet_name, header_row, headers, records


def _canonical_catalog_view_sha256(
    *,
    source_sheet: str | None,
    header_row: int,
    headers: list[str],
    rows: list[dict[str, str]],
) -> str:
    def normalized(value: str) -> str:
        return unicodedata.normalize("NFC", value)

    canonical_rows = [
        {
            normalized(str(key)): normalized(str(value))
            for key, value in sorted(row.items())
        }
        for row in sorted(
            rows,
            key=lambda item: (
                item.get(_SHEET_NAME, ""),
                int(item.get(_ROW_NUMBER, "0") or 0),
            ),
        )
    ]
    payload = json.dumps(
        {
            "source_sheet": normalized(source_sheet or ""),
            "header_row": header_row,
            "headers": [normalized(value) for value in headers],
            "rows": canonical_rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_catalog(
    path: str | Path,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load one catalog and return its traceable table-selection metadata."""

    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Catalog does not exist: {source}")
    try:
        source_payload = source.read_bytes()
    except OSError as exc:
        raise ValueError(f"Catalog is unreadable: {source}") from exc
    settings = config or load_matching_config()
    aliases = settings["field_aliases"]
    if source.suffix.lower() == ".csv":
        try:
            decoded = source_payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Catalog CSV must be UTF-8") from exc
        with StringIO(decoded, newline="") as handle:
            reader = csv.DictReader(handle)
            headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
            rows = []
            for source_row, raw in enumerate(reader, start=2):
                row = {
                    str(key).strip(): str(value or "").strip()
                    for key, value in raw.items()
                }
                if any(row.values()):
                    row[_ROW_NUMBER] = str(source_row)
                    row[_SHEET_NAME] = ""
                    rows.append(row)
        if _header_match(headers, aliases) is None:
            raise ValueError("Catalog CSV requires recognized id and title columns")
        sheet_name: str | None = None
        header_row = 1
    elif source.suffix.lower() == ".xlsx":
        try:
            sheet_name, header_row, headers, rows = _select_xlsx_table(
                source_payload,
                aliases,
            )
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
            raise ValueError("Catalog XLSX is not a readable OpenXML workbook") from exc
    else:
        raise ValueError("Course and policy catalogs must be .csv or .xlsx files")

    canonical_view_sha256 = _canonical_catalog_view_sha256(
        source_sheet=sheet_name,
        header_row=header_row,
        headers=headers,
        rows=rows,
    )
    return {
        "path": str(source.resolve()),
        "file_name": source.name,
        "sha256": hashlib.sha256(source_payload).hexdigest(),
        "byte_length": len(source_payload),
        "canonical_view_sha256": canonical_view_sha256,
        "parser_version": CATALOG_PARSER_VERSION,
        "source_sheet": sheet_name,
        "header_row": header_row,
        "headers": headers,
        "rows": rows,
    }


def _field(row: dict[str, str], aliases: list[str]) -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(alias.strip().lower())
        if value:
            return value.strip()
    return ""


def _field_with_key(
    row: dict[str, str], aliases: list[str]
) -> tuple[str, str | None]:
    normalized = {key.strip().lower(): (key, value) for key, value in row.items()}
    for alias in aliases:
        match = normalized.get(alias.strip().lower())
        if match and match[1]:
            return match[1].strip(), match[0].strip().lower()
    return "", None


def _boolean(value: Any) -> bool | None:
    key = str(value or "").strip().casefold()
    if not key:
        return None
    if key in {"true", "yes", "1", "是"}:
        return True
    if key in {"false", "no", "0", "否"}:
        return False
    return None


def _tags(value: Any) -> set[str]:
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = re.split(r"[,，;；|/\n]+", str(value or ""))
    return {part.strip().casefold() for part in parts if part.strip()}


def _parse_date(value: str) -> date | None:
    """Parse the last explicit date from an expiry/date-window field.

    Catalogs commonly store a validity window such as
    ``2026-07-01 至 2030-12-31`` in the same cell used for ``valid_until``.
    Taking the first ten characters incorrectly expires the record on the
    window's start date, so this expiry-oriented parser deliberately uses the
    final well-formed date token.
    """

    text = value.strip()
    if not text:
        return None
    if text.casefold() in {"长期有效", "持续有效", "long-term", "ongoing"}:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        serial = float(text)
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(serial))
    matches = re.findall(
        r"(?<!\d)(\d{4})\s*(?:年|[-./])\s*(\d{1,2})"
        r"(?:\s*(?:月|[-./])\s*(\d{1,2})\s*日?)?",
        text,
    )
    candidates: list[date] = []
    for year_text, month_text, day_text in matches:
        try:
            candidates.append(
                date(
                    int(year_text),
                    int(month_text),
                    int(day_text or "1"),
                )
            )
        except ValueError:
            continue
    if candidates:
        return candidates[-1]
    return None


def _policy_filter(
    row: dict[str, str],
    *,
    config: dict[str, Any],
    as_of: date,
) -> tuple[bool, str]:
    aliases = config["field_aliases"]
    review = _field(row, aliases["review_status"]).casefold()
    allowed = {value.casefold() for value in POLICY_ALLOWED_REVIEW_STATUSES}
    if review not in allowed:
        return False, "review_status_not_approved"
    expiry_raw = _field(row, aliases["expiry_date"])
    expiry = _parse_date(expiry_raw) if expiry_raw else None
    indefinite = expiry_raw.casefold() in {"长期有效", "持续有效", "long-term", "ongoing"}
    if expiry_raw and expiry is None and not indefinite:
        return False, "expiry_date_invalid"
    if expiry and expiry < as_of:
        return False, "expired"
    return True, "passed"


def _policy_reference_filter(
    row: dict[str, str],
    *,
    config: dict[str, Any],
    as_of: date,
) -> tuple[bool, str]:
    """Apply date safety to confirmed reference data without changing row review."""

    aliases = config["field_aliases"]
    expiry_raw = _field(row, aliases["expiry_date"])
    expiry = _parse_date(expiry_raw) if expiry_raw else None
    indefinite = expiry_raw.casefold() in {"长期有效", "持续有效", "long-term", "ongoing"}
    if expiry_raw and expiry is None and not indefinite:
        return True, "date_requires_official_verification"
    if not expiry_raw:
        return True, "date_not_supplied_requires_official_verification"
    if expiry and expiry < as_of:
        return False, "expired"
    return True, "passed_for_reference"


def _course_filter(
    row: dict[str, str],
    *,
    config: dict[str, Any],
    as_of: date,
) -> tuple[bool, str]:
    """Apply gates when a modern course catalog declares the relevant fields.

    Legacy catalogs without review or active-state columns remain readable, but
    new templates provide both fields and therefore fail closed when populated
    with an unapproved or inactive value.
    """

    aliases = config["field_aliases"]
    review = _field(row, aliases["review_status"]).casefold()
    if review and review not in {value.casefold() for value in COURSE_ALLOWED_REVIEW_STATUSES}:
        return False, "review_status_not_published"
    active = _field(row, aliases["active_status"]).casefold()
    if active and active not in {value.casefold() for value in COURSE_ACTIVE_STATUSES}:
        return False, "course_not_active"
    expiry_raw = _field(row, aliases["expiry_date"])
    expiry = _parse_date(expiry_raw) if expiry_raw else None
    indefinite = expiry_raw.casefold() in {"长期有效", "持续有效", "long-term", "ongoing"}
    if expiry_raw and expiry is None and not indefinite:
        return False, "expiry_date_invalid"
    if expiry and expiry < as_of:
        return False, "expired"
    data_class = _field(row, aliases["data_class"]).casefold()
    simulation = _boolean(_field(row, aliases["simulation_only"]))
    synthetic = data_class == "synthetic_fixture"
    if synthetic != (simulation is True):
        return False, "synthetic_contract_invalid"
    if synthetic and not _field(row, aliases["disclosure_label"]):
        return False, "synthetic_disclosure_missing"
    return True, "passed"


def catalog_summary(
    catalog_path: str | Path,
    *,
    category: str = "policy",
    as_of: str | date | None = None,
    config: dict[str, Any] | None = None,
    attestation_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return non-content metadata and hard-filter counts for a formal catalog."""

    if category not in {"course", "policy"}:
        raise ValueError("category must be course or policy")
    settings = config or load_matching_config()
    catalog = load_catalog(catalog_path, config=settings)
    rows = catalog["rows"]
    aliases = settings["field_aliases"]
    review_counts = Counter(
        _field(row, aliases["review_status"]) or "missing"
        for row in rows
    )
    excluded_counts: Counter[str] = Counter()
    eligible_rows = len(rows)
    reference_confirmation = (
        _load_catalog_attestation(attestation_path, catalog=catalog)
        if category == "policy"
        else None
    )
    reference_count = 0
    reference_excluded_counts: Counter[str] = Counter()
    reference_note_counts: Counter[str] = Counter()
    if category == "policy":
        as_of_date = (
            date.fromisoformat(as_of)
            if isinstance(as_of, str)
            else as_of or date.today()
        )
        eligible_rows = 0
        for row in rows:
            eligible, reason = _policy_filter(row, config=settings, as_of=as_of_date)
            if eligible:
                eligible_rows += 1
            else:
                excluded_counts[reason] += 1
        if reference_confirmation is not None:
            for row in rows:
                usable, reason = _policy_reference_filter(
                    row,
                    config=settings,
                    as_of=as_of_date,
                )
                if usable:
                    reference_count += 1
                    if reason != "passed_for_reference":
                        reference_note_counts[reason] += 1
                else:
                    reference_excluded_counts[reason] += 1
    state = "ready" if eligible_rows else "quarantined"
    return {
        key: catalog[key]
        for key in (
            "file_name",
            "sha256",
            "byte_length",
            "canonical_view_sha256",
            "parser_version",
            "source_sheet",
            "header_row",
            "headers",
        )
    } | {
        "category": category,
        "state": state,
        "record_count": len(rows),
        "eligible_count": eligible_rows,
        "review_status_counts": dict(sorted(review_counts.items())),
        "excluded_reason_counts": dict(sorted(excluded_counts.items())),
        "human_review_required": category == "policy",
        "reference_state": (
            "ready"
            if reference_confirmation is not None and reference_count > 0
            else "unconfirmed"
            if reference_confirmation is None
            else "no_current_records"
        ),
        "reference_count": reference_count,
        "reference_excluded_reason_counts": dict(
            sorted(reference_excluded_counts.items())
        ),
        "reference_note_counts": dict(sorted(reference_note_counts.items())),
        "reference_confirmation": reference_confirmation,
        "reference_usage": (
            "suggestions_only" if reference_confirmation is not None else None
        ),
    }


def browse_catalog_resources(
    catalog_path: str | Path,
    *,
    category: str,
    as_of: str | date | None = None,
    config: dict[str, Any] | None = None,
    attestation_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return real catalog rows for browsing without matching or scoring them."""

    if category not in {"course", "policy"}:
        raise ValueError("category must be course or policy")
    settings = config or load_matching_config()
    catalog = load_catalog(catalog_path, config=settings)
    rows = catalog["rows"]
    aliases = settings["field_aliases"]
    as_of_date = (
        date.fromisoformat(as_of)
        if isinstance(as_of, str)
        else as_of or date.today()
    )
    confirmation = None
    if category == "policy" and attestation_path is not None:
        confirmation = _load_catalog_attestation(attestation_path, catalog=catalog)

    metadata = {
        key: catalog[key]
        for key in (
            "file_name",
            "sha256",
            "byte_length",
            "canonical_view_sha256",
            "parser_version",
            "source_sheet",
            "header_row",
        )
    } | {"record_count": len(rows)}
    boundaries = {
        "catalog_rows_only": True,
        "matching_performed": False,
        "aggregate_score_produced": False,
        "automatic_assignment": False,
        "eligibility_determination": False,
        "official_live_verification_required": category == "policy",
    }
    if category == "policy" and confirmation is None:
        return {
            "category": category,
            "status": "attestation_required",
            "items": [],
            "catalog_metadata": metadata,
            "attestation": None,
            "excluded_reason_counts": {},
            "invalid_identity_row_count": 0,
            "authority": "catalog_metadata_only",
            "boundaries": boundaries,
        }

    items: list[dict[str, Any]] = []
    excluded_counts: Counter[str] = Counter()
    invalid_identity_rows = 0
    for row in rows:
        source_row = int(row[_ROW_NUMBER])
        item_id = _field(row, aliases["id"])
        title = _field(row, aliases["title"])
        if not item_id or not title:
            invalid_identity_rows += 1
            continue
        if category == "policy":
            usable, temporal_reason = _policy_reference_filter(
                row,
                config=settings,
                as_of=as_of_date,
            )
            if not usable:
                excluded_counts[temporal_reason] += 1
                continue
            effective_status = {
                "passed_for_reference": (
                    "within_catalog_date_window_requires_official_verification"
                ),
                "date_requires_official_verification": (
                    "catalog_date_invalid_requires_official_verification"
                ),
                "date_not_supplied_requires_official_verification": (
                    "catalog_date_missing_requires_official_verification"
                ),
            }[temporal_reason]
        else:
            usable, course_reason = _course_filter(
                row,
                config=settings,
                as_of=as_of_date,
            )
            if not usable:
                excluded_counts[course_reason] += 1
                continue
            effective_status = "not_evaluated"
        source_review_status = (
            _field(row, aliases["review_status"]) or "missing"
        )
        review_fields = (
            {
                "review_status": "项目方确认可作参考",
                "source_review_status": source_review_status,
                "review_status_authority": (
                    "catalog_sha256_attestation_reference_only"
                ),
            }
            if category == "policy"
            else {
                "review_status": source_review_status,
                "review_status_authority": "source_value_only",
            }
        )
        provider = _field(row, aliases["provider"])
        if any(
            marker in provider
            for marker in ("待人工", "待确认", "原文待", "待复核", "未确认")
        ):
            provider = ""
        effective_status_label_zh = {
            "within_catalog_date_window_requires_official_verification": (
                "目录时效未见过期，仍须按官方原文核验"
            ),
            "catalog_date_invalid_requires_official_verification": (
                "时效字段需按官方原文核验"
            ),
            "catalog_date_missing_requires_official_verification": (
                "时效未录入，需按官方原文核验"
            ),
            "not_evaluated": "未执行时效判断",
        }[effective_status]
        item = {
                "id": item_id,
                "title": title,
                "source_url": _field(row, aliases["source_url"]),
                "provider": provider,
                "effective_status": effective_status,
                "effective_status_label_zh": effective_status_label_zh,
                **review_fields,
                "source_row": source_row,
                "source_sheet": row[_SHEET_NAME] or None,
                "catalog_sha256": catalog["sha256"],
                "authority": (
                    "reference_catalog_entry_only"
                    if category == "policy"
                    else "course_catalog_entry_only"
                ),
                "not_eligibility_determination": category == "policy",
                "requires_live_official_verification": category == "policy",
            }
        if category == "course":
            data_class = _field(row, aliases["data_class"]) or "operator_declared"
            simulation_only = _boolean(
                _field(row, aliases["simulation_only"])
            ) is True
            item.update(
                {
                    "summary": _field(row, aliases["summary"]),
                    "active_status": _field(row, aliases["active_status"]),
                    "updated_at": _field(row, aliases["updated_at"]),
                    "languages": sorted(_tags(_field(row, aliases["languages"]))),
                    "delivery_format": _field(row, aliases["delivery_format"]),
                    "duration_minutes": _field(row, aliases["duration_minutes"]),
                    "data_class": data_class,
                    "simulation_only": simulation_only,
                    "disclosure_label": _field(row, aliases["disclosure_label"]),
                    "automatic_enrollment": False,
                }
            )
        items.append(item)
    items.sort(key=lambda item: (item["id"].casefold(), item["source_row"]))

    if not rows:
        status = "empty_catalog"
    elif items:
        status = "ready"
    elif category == "policy" and excluded_counts:
        status = "no_current_entries"
    else:
        status = "no_browsable_entries"
    attestation = None
    if confirmation is not None:
        attestation = {
            **confirmation,
            "status": "confirmed_for_reference_only",
            "meaning_zh": (
                "项目方确认该目录可作参考；不确认单条政策资格，且仍须以官方实时信息核验。"
            ),
            "not_eligibility_determination": True,
            "official_live_verification_required": True,
        }
    return {
        "category": category,
        "status": status,
        "items": items,
        "catalog_metadata": metadata | {"browsable_count": len(items)},
        "attestation": attestation,
        "excluded_reason_counts": dict(sorted(excluded_counts.items())),
        "invalid_identity_row_count": invalid_identity_rows,
        "authority": (
            "reference_catalog_only"
            if category == "policy"
            else "course_catalog_only"
        ),
        "boundaries": boundaries,
    }


def _normalized_profile_tags(
    profile_tags: dict[str, list[str] | str],
    *,
    settings: dict[str, Any],
) -> dict[str, set[str]]:
    return {
        dimension: _tags(profile_tags.get(dimension, []))
        for dimension in settings["tag_weights"]
    }


def _row_relevance(
    row: dict[str, str],
    *,
    normalized_profile: dict[str, set[str]],
    settings: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    aliases = settings["field_aliases"]
    score = 0.0
    rationale: list[dict[str, Any]] = []
    used_source_fields: set[str] = set()
    for dimension, weight in settings["tag_weights"].items():
        raw_tags, source_field = _field_with_key(row, aliases[dimension])
        if source_field is not None and source_field in used_source_fields:
            continue
        if source_field is not None:
            used_source_fields.add(source_field)
        catalog_tags = _tags(raw_tags)
        overlap = sorted(normalized_profile[dimension] & catalog_tags)
        if overlap:
            contribution = float(weight) * len(overlap)
            score += contribution
            rationale.append(
                {
                    "dimension": dimension,
                    "matched_tags": overlap,
                    "weight": float(weight),
                    "contribution": contribution,
                    "source_field": source_field,
                }
            )
    return score, rationale


def match_catalog(
    catalog_path: str | Path,
    *,
    category: str,
    profile_tags: dict[str, list[str] | str],
    as_of: str | date,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Match one formal catalog without semantic or aggregate scoring."""

    if category not in {"course", "policy"}:
        raise ValueError("category must be course or policy")
    settings = config or load_matching_config()
    as_of_date = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    catalog = load_catalog(catalog_path, config=settings)
    rows = catalog["rows"]
    aliases = settings["field_aliases"]
    normalized_profile = _normalized_profile_tags(
        profile_tags,
        settings=settings,
    )
    matches: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    eligible_count = 0
    for row in rows:
        source_row = int(row[_ROW_NUMBER])
        item_id = _field(row, aliases["id"]) or f"row-{source_row}"
        title = _field(row, aliases["title"]) or item_id
        if category == "policy":
            eligible, reason = _policy_filter(row, config=settings, as_of=as_of_date)
            if not eligible:
                excluded.append(
                    {
                        "item_id": item_id,
                        "title": title,
                        "row": source_row,
                        "source_sheet": row[_SHEET_NAME] or None,
                        "reason": reason,
                    }
                )
                continue
        else:
            eligible, reason = _course_filter(
                row,
                config=settings,
                as_of=as_of_date,
            )
            if not eligible:
                excluded.append(
                    {
                        "item_id": item_id,
                        "title": title,
                        "row": source_row,
                        "source_sheet": row[_SHEET_NAME] or None,
                        "reason": reason,
                    }
                )
                continue
        eligible_count += 1
        score, rationale = _row_relevance(
            row,
            normalized_profile=normalized_profile,
            settings=settings,
        )
        if score >= float(settings["minimum_match_score"]):
            match = {
                "category": category,
                "item_id": item_id,
                "title": title,
                "match_score": round(score, 4),
                "rationale": rationale,
                "hard_filter_status": "passed",
                "source_row": source_row,
                "source_sheet": row[_SHEET_NAME] or None,
            }
            if category == "course":
                match.update(
                    {
                        "provider": _field(row, aliases["provider"]),
                        "source_url": _field(row, aliases["source_url"]),
                        "summary": _field(row, aliases["summary"]),
                        "data_class": (
                            _field(row, aliases["data_class"])
                            or "operator_declared"
                        ),
                        "simulation_only": _boolean(
                            _field(row, aliases["simulation_only"])
                        )
                        is True,
                        "disclosure_label": _field(
                            row, aliases["disclosure_label"]
                        ),
                        "automatic_enrollment": False,
                    }
                )
            else:
                match.update(
                    {
                        "provider": _field(row, aliases["provider"]),
                        "source_url": _field(row, aliases["source_url"]),
                        "catalog_date_value": _field(row, aliases["expiry_date"]),
                        "requires_live_official_verification": True,
                        "not_eligibility_determination": True,
                    }
                )
            matches.append(match)
    matches.sort(key=lambda item: (-item["match_score"], item["item_id"]))
    matches = matches[: int(settings["maximum_results"])]
    if matches:
        status = "matched"
        message = None
    elif category == "policy" and rows and eligible_count == 0:
        status = "catalog_quarantined"
        message = "政策目录已载入，但没有通过人工复核且在有效期内的条目。"
    else:
        status = "no_high_match"
        message = "无高匹配；未执行硬推荐。"
    return {
        "category": category,
        "catalog": str(Path(catalog_path).resolve()),
        "catalog_metadata": {
            key: catalog[key]
            for key in (
                "file_name",
                "sha256",
                "byte_length",
                "canonical_view_sha256",
                "parser_version",
                "source_sheet",
                "header_row",
            )
        }
        | {"record_count": len(rows), "eligible_count": eligible_count},
        "status": status,
        "message": message,
        "matches": matches,
        "excluded": excluded,
        "rules": {
            "tag_weights": settings["tag_weights"],
            "minimum_match_score": settings["minimum_match_score"],
            "policy_hard_filter_enabled": category == "policy",
            "course_declared_field_gates_enabled": category == "course",
            "policy_allowed_review_statuses": list(POLICY_ALLOWED_REVIEW_STATUSES),
            "course_allowed_review_statuses": list(COURSE_ALLOWED_REVIEW_STATUSES),
            "duplicate_source_field_counting": "once_per_row",
        },
    }


def suggest_policy_references(
    catalog_path: str | Path,
    *,
    profile_tags: dict[str, list[str] | str],
    as_of: str | date,
    attestation_path: str | Path,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return reference-only policy suggestions from an owner-confirmed catalog."""

    settings = config or load_matching_config()
    as_of_date = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    catalog = load_catalog(catalog_path, config=settings)
    confirmation = _load_catalog_attestation(attestation_path, catalog=catalog)
    if confirmation is None:
        raise ValueError("A catalog attestation is required for policy references")
    rows = catalog["rows"]
    aliases = settings["field_aliases"]
    normalized_profile = _normalized_profile_tags(
        profile_tags,
        settings=settings,
    )
    suggestions: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    reference_candidate_count = 0
    for row in rows:
        source_row = int(row[_ROW_NUMBER])
        item_id = _field(row, aliases["id"]) or f"row-{source_row}"
        title = _field(row, aliases["title"]) or item_id
        usable, reason = _policy_reference_filter(
            row,
            config=settings,
            as_of=as_of_date,
        )
        if not usable:
            excluded.append(
                {
                    "item_id": item_id,
                    "title": title,
                    "row": source_row,
                    "source_sheet": row[_SHEET_NAME] or None,
                    "reason": reason,
                }
            )
            continue
        reference_candidate_count += 1
        score, rationale = _row_relevance(
            row,
            normalized_profile=normalized_profile,
            settings=settings,
        )
        if score >= float(settings["minimum_match_score"]):
            suggestions.append(
                {
                    "category": "policy_reference",
                    "item_id": item_id,
                    "title": title,
                    "relevance_score": round(score, 4),
                    "rationale": rationale,
                    "source_review_status": (
                        _field(row, aliases["review_status"]) or "missing"
                    ),
                    "provider": _field(row, aliases["provider"]),
                    "source_url": _field(row, aliases["source_url"]),
                    "catalog_date_value": _field(row, aliases["expiry_date"]),
                    "reference_confirmation": "catalog_sha256_attestation",
                    "temporal_status": reason,
                    "requires_live_official_verification": True,
                    "source_row": source_row,
                    "source_sheet": row[_SHEET_NAME] or None,
                    "authority": "reference_suggestion_only",
                    "not_eligibility_determination": True,
                }
            )
    suggestions.sort(
        key=lambda item: (-item["relevance_score"], item["item_id"])
    )
    suggestions = suggestions[: int(settings["maximum_results"])]
    if suggestions:
        status = "suggested"
        message = f"已生成 {len(suggestions)} 条政策参考建议。"
    elif reference_candidate_count == 0:
        status = "no_reference_candidates"
        message = "参考库已确认，但当前没有处于有效期内的记录。"
    else:
        status = "no_high_reference"
        message = "参考库可用，但当前标签没有达到相关性阈值。"
    return {
        "category": "policy_reference",
        "status": status,
        "message": message,
        "suggestions": suggestions,
        "excluded": excluded,
        "catalog_metadata": {
            "file_name": catalog["file_name"],
            "sha256": catalog["sha256"],
            "byte_length": catalog["byte_length"],
            "canonical_view_sha256": catalog["canonical_view_sha256"],
            "parser_version": catalog["parser_version"],
            "source_sheet": catalog["source_sheet"],
            "header_row": catalog["header_row"],
            "record_count": len(rows),
            "reference_candidate_count": reference_candidate_count,
            "reference_confirmation": confirmation,
        },
        "authority": "reference_suggestion_only",
        "not_eligibility_determination": True,
        "official_verification_required": True,
        "rules": {
            "tag_weights": settings["tag_weights"],
            "minimum_relevance_score": settings["minimum_match_score"],
            "expiry_filter_enabled": True,
            "row_review_status_overridden": False,
            "catalog_confirmation_scope": "reference_suggestions",
            "duplicate_source_field_counting": "once_per_row",
        },
    }
