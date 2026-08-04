"""Deterministic mentor-catalog loading and candidate-only matching.

The module is deliberately independent of the HTTP bridge, workspace persistence,
and web UI. Catalog rows are traceable to their source row and hashes. Matching
never assigns a mentor and never emits a composite score.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import posixpath
import re
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

MENTOR_CATALOG_SCHEMA_VERSION = "1.0.0"
MENTOR_MATCH_RULE_VERSION = "mentor-matching-1.1.0"

REQUIRED_COLUMNS: tuple[str, ...] = (
    "mentor_id",
    "display_name",
    "expertise_tags",
    "industry_tags",
    "stage_tags",
    "geography_tags",
    "market_tags",
    "languages",
    "availability_status",
    "consent_status",
    "conflict_status",
    "valid_until",
    "source",
    "source_url",
    "updated_at",
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "data_class",
    "simulation_only",
    "disclosure_label",
    "profile_summary",
)

TAG_COLUMNS = {
    "expertise_tags",
    "industry_tags",
    "stage_tags",
    "geography_tags",
    "market_tags",
    "languages",
}

DIMENSION_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "expertise",
        "label_zh": "专业能力",
        "mentor_field": "expertise_tags",
        "profile_fields": ("expertise", "expertise_tags", "technology", "need"),
    },
    {
        "id": "industry",
        "label_zh": "行业",
        "mentor_field": "industry_tags",
        "profile_fields": ("industry", "industry_tags"),
    },
    {
        "id": "stage",
        "label_zh": "企业阶段",
        "mentor_field": "stage_tags",
        "profile_fields": ("stage", "stage_tags"),
    },
    {
        "id": "geography",
        "label_zh": "地域",
        "mentor_field": "geography_tags",
        "profile_fields": ("geography", "geography_tags"),
    },
    {
        "id": "market",
        "label_zh": "目标市场",
        "mentor_field": "market_tags",
        "profile_fields": ("market", "market_tags"),
    },
    {
        "id": "language",
        "label_zh": "语言",
        "mentor_field": "languages",
        "profile_fields": ("language", "languages"),
    },
)

AVAILABLE_STATUSES = frozenset({"available", "active", "可用", "开放"})
CONSENTED_STATUSES = frozenset(
    {"consented", "approved", "granted", "yes", "true", "已授权", "同意", "允许"}
)
CLEAR_CONFLICT_STATUSES = frozenset(
    {"clear", "none", "no_conflict", "无冲突", "已排除冲突"}
)

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_CATALOG_ROWS = 100_000

_TAG_SPLIT_RE = re.compile(r"[|,;，；\n\r]+")
_CELL_REFERENCE_RE = re.compile(r"^([A-Za-z]+)")
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_BUILTIN_DATE_FORMAT_IDS = frozenset(
    {*range(14, 23), *range(27, 37), *range(45, 48), *range(50, 59)}
)


class MentorCatalogError(ValueError):
    """Raised when a mentor catalog cannot be safely interpreted."""


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


MENTOR_MATCH_RULE_DIGEST = _canonical_digest(
    {
        "schema_version": MENTOR_CATALOG_SCHEMA_VERSION,
        "rule_version": MENTOR_MATCH_RULE_VERSION,
        "dimensions": DIMENSION_RULES,
        "available_statuses": sorted(AVAILABLE_STATUSES),
        "consented_statuses": sorted(CONSENTED_STATUSES),
        "clear_conflict_statuses": sorted(CLEAR_CONFLICT_STATUSES),
        "synthetic_contract": {
            "data_class": "synthetic_fixture",
            "simulation_only": True,
            "display_name_prefix": "模拟导师",
            "contactable": False,
        },
        "core_match_rule": (
            "when expertise or industry is requested, at least one of those "
            "dimensions must match"
        ),
        "ordering": "mentor_id_casefold_ascending",
    }
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _status_key(value: Any) -> str:
    cleaned = _clean_text(value).casefold()
    return re.sub(r"[\s\-]+", "_", cleaned)


def _tag_values(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = _TAG_SPLIT_RE.split(value)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_values = [str(item) for item in value if item is not None]
    else:
        raw_values = [] if value is None else [str(value)]
    by_key: dict[str, str] = {}
    for raw in raw_values:
        cleaned = _clean_text(raw)
        if cleaned:
            by_key.setdefault(cleaned.casefold(), cleaned)
    return [by_key[key] for key in sorted(by_key)]


def _decode_csv(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise MentorCatalogError("mentor catalog CSV must be UTF-8 or GB18030 encoded")


def _csv_rows(payload: bytes) -> list[tuple[int, list[str]]]:
    try:
        reader = csv.reader(io.StringIO(_decode_csv(payload), newline=""))
        rows = [(row_number, [_clean_text(value) for value in row]) for row_number, row in enumerate(reader, 1)]
    except csv.Error as exc:
        raise MentorCatalogError(f"invalid mentor catalog CSV: {exc}") from exc
    if len(rows) > MAX_CATALOG_ROWS + 1:
        raise MentorCatalogError(f"mentor catalog exceeds {MAX_CATALOG_ROWS} data rows")
    return rows


def _xlsx_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise MentorCatalogError(f"XLSX is missing required member: {name}") from exc


def _relationship_target(archive: zipfile.ZipFile) -> tuple[str, bool]:
    workbook = ElementTree.fromstring(_xlsx_member(archive, "xl/workbook.xml"))
    workbook_properties = workbook.find(f"{{{_MAIN_NS}}}workbookPr")
    date_1904 = bool(
        workbook_properties is not None
        and _status_key(workbook_properties.get("date1904")) in {"1", "true"}
    )
    first_sheet = workbook.find(f".//{{{_MAIN_NS}}}sheet")
    if first_sheet is None:
        raise MentorCatalogError("XLSX workbook has no worksheet")
    relationship_id = first_sheet.get(f"{{{_DOC_REL_NS}}}id")
    if not relationship_id:
        raise MentorCatalogError("XLSX first worksheet has no relationship id")

    relationships = ElementTree.fromstring(
        _xlsx_member(archive, "xl/_rels/workbook.xml.rels")
    )
    target = None
    for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target")
            break
    if not target:
        raise MentorCatalogError("XLSX first worksheet relationship cannot be resolved")
    if target.startswith("/"):
        worksheet_path = target.lstrip("/")
    else:
        worksheet_path = posixpath.normpath(posixpath.join("xl", target))
    if not worksheet_path.startswith("xl/") or ".." in worksheet_path.split("/"):
        raise MentorCatalogError("XLSX worksheet relationship resolves outside the workbook")
    return worksheet_path, date_1904


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(_xlsx_member(archive, "xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _looks_like_date_format(format_code: str) -> bool:
    cleaned = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", format_code).casefold()
    return bool(re.search(r"[ymdhs]", cleaned))


def _date_style_indexes(archive: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in archive.namelist():
        return set()
    root = ElementTree.fromstring(_xlsx_member(archive, "xl/styles.xml"))
    custom_formats: dict[int, str] = {}
    for item in root.findall(f".//{{{_MAIN_NS}}}numFmt"):
        try:
            format_id = int(item.get("numFmtId", ""))
        except ValueError:
            continue
        custom_formats[format_id] = item.get("formatCode", "")
    date_styles: set[int] = set()
    cell_formats = root.find(f"{{{_MAIN_NS}}}cellXfs")
    if cell_formats is None:
        return date_styles
    for index, item in enumerate(cell_formats.findall(f"{{{_MAIN_NS}}}xf")):
        try:
            format_id = int(item.get("numFmtId", "0"))
        except ValueError:
            continue
        if format_id in _BUILTIN_DATE_FORMAT_IDS or _looks_like_date_format(
            custom_formats.get(format_id, "")
        ):
            date_styles.add(index)
    return date_styles


def _excel_date(value: str, *, date_1904: bool) -> str:
    try:
        serial = float(value)
    except ValueError:
        return value
    base = datetime(1904, 1, 1) if date_1904 else datetime(1899, 12, 30)
    converted = base + timedelta(days=serial)
    if converted.time() == datetime.min.time():
        return converted.date().isoformat()
    return converted.isoformat(timespec="seconds")


def _column_index(reference: str, fallback: int) -> int:
    match = _CELL_REFERENCE_RE.match(reference)
    if not match:
        return fallback
    result = 0
    for character in match.group(1).upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _xlsx_cell_text(
    cell: ElementTree.Element,
    *,
    shared_strings: list[str],
    date_styles: set[int],
    date_1904: bool,
) -> str:
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        return _clean_text(
            "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
        )
    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s":
        try:
            return _clean_text(shared_strings[int(value)])
        except (ValueError, IndexError) as exc:
            raise MentorCatalogError("XLSX contains an invalid shared-string reference") from exc
    if cell_type == "b":
        return "true" if value == "1" else "false"
    try:
        style_index = int(cell.get("s", "-1"))
    except ValueError:
        style_index = -1
    if value and style_index in date_styles:
        value = _excel_date(value, date_1904=date_1904)
    return _clean_text(value)


def _xlsx_rows(payload: bytes) -> list[tuple[int, list[str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            total_size = sum(item.file_size for item in archive.infolist())
            if total_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise MentorCatalogError("XLSX uncompressed content exceeds the safety limit")
            worksheet_path, date_1904 = _relationship_target(archive)
            shared_strings = _shared_strings(archive)
            date_styles = _date_style_indexes(archive)
            worksheet = ElementTree.fromstring(_xlsx_member(archive, worksheet_path))
            rows = []
            for fallback_row, row in enumerate(
                worksheet.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"), 1
            ):
                try:
                    row_number = int(row.get("r", fallback_row))
                except ValueError:
                    row_number = fallback_row
                values: list[str] = []
                for fallback_column, cell in enumerate(row.findall(f"{{{_MAIN_NS}}}c")):
                    column = _column_index(cell.get("r", ""), fallback_column)
                    if column >= len(values):
                        values.extend("" for _ in range(column - len(values) + 1))
                    values[column] = _xlsx_cell_text(
                        cell,
                        shared_strings=shared_strings,
                        date_styles=date_styles,
                        date_1904=date_1904,
                    )
                rows.append((row_number, values))
                if len(rows) > MAX_CATALOG_ROWS + 1:
                    raise MentorCatalogError(
                        f"mentor catalog exceeds {MAX_CATALOG_ROWS} data rows"
                    )
            return rows
    except MentorCatalogError:
        raise
    except (zipfile.BadZipFile, ElementTree.ParseError, OSError) as exc:
        raise MentorCatalogError(f"invalid mentor catalog XLSX: {exc}") from exc


def _header_map(header: list[str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, value in enumerate(header):
        key = _clean_text(value).casefold()
        if not key:
            continue
        if key in positions:
            raise MentorCatalogError(f"duplicate mentor catalog column: {key}")
        positions[key] = index
    missing = [column for column in REQUIRED_COLUMNS if column not in positions]
    if missing:
        raise MentorCatalogError(f"mentor catalog is missing required columns: {missing}")
    return positions


def _record_from_row(
    values: list[str],
    positions: Mapping[str, int],
    *,
    source_row: int,
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for column in REQUIRED_COLUMNS:
        index = positions[column]
        value = values[index] if index < len(values) else ""
        record[column] = _tag_values(value) if column in TAG_COLUMNS else _clean_text(value)
    for column in OPTIONAL_COLUMNS:
        index = positions.get(column)
        value = values[index] if index is not None and index < len(values) else ""
        record[column] = _clean_text(value)
    if not record["mentor_id"] or not record["display_name"]:
        missing = [field for field in ("mentor_id", "display_name") if not record[field]]
        raise MentorCatalogError(
            f"mentor catalog row {source_row} is missing fail-closed fields: {missing}"
        )
    simulation_key = _status_key(record["simulation_only"])
    data_class_key = _status_key(record["data_class"])
    simulation_only = simulation_key in {"true", "yes", "1"}
    if simulation_key not in {"", "true", "yes", "1", "false", "no", "0"}:
        raise MentorCatalogError(
            f"mentor catalog row {source_row} has invalid simulation_only"
        )
    if (data_class_key == "synthetic_fixture") != simulation_only:
        raise MentorCatalogError(
            f"mentor catalog row {source_row} must pair "
            "data_class=synthetic_fixture with simulation_only=true"
        )
    if simulation_only:
        if not record["disclosure_label"]:
            raise MentorCatalogError(
                f"mentor catalog row {source_row} requires disclosure_label"
            )
        if not record["display_name"].startswith("模拟导师"):
            raise MentorCatalogError(
                f"mentor catalog row {source_row} synthetic display_name "
                "must start with 模拟导师"
            )
    record["simulation_only"] = simulation_only
    record["data_class"] = record["data_class"] or "operator_declared"
    record["source_row"] = source_row
    record["row_sha256"] = _canonical_digest(
        {column: record[column] for column in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)}
    )
    return record


def _records_from_rows(rows: list[tuple[int, list[str]]]) -> list[dict[str, Any]]:
    header_index = next((index for index, (_, row) in enumerate(rows) if any(row)), None)
    if header_index is None:
        raise MentorCatalogError("mentor catalog has no header row")
    positions = _header_map(rows[header_index][1])
    records = []
    seen_ids: dict[str, int] = {}
    for source_row, values in rows[header_index + 1 :]:
        if not any(_clean_text(value) for value in values):
            continue
        record = _record_from_row(values, positions, source_row=source_row)
        mentor_key = record["mentor_id"].casefold()
        if mentor_key in seen_ids:
            raise MentorCatalogError(
                f"duplicate mentor_id {record['mentor_id']!r} at rows "
                f"{seen_ids[mentor_key]} and {source_row}"
            )
        seen_ids[mentor_key] = source_row
        records.append(record)
    return records


def load_mentor_catalog(path: str | Path) -> dict[str, Any]:
    """Load a CSV or XLSX catalog into a stable, source-traceable structure."""

    source_path = Path(path)
    payload = source_path.read_bytes()
    if len(payload) > MAX_INPUT_BYTES:
        raise MentorCatalogError("mentor catalog input exceeds the safety limit")
    suffix = source_path.suffix.casefold()
    if suffix == ".csv":
        rows = _csv_rows(payload)
        source_format = "csv"
    elif suffix == ".xlsx":
        rows = _xlsx_rows(payload)
        source_format = "xlsx"
    else:
        raise MentorCatalogError("mentor catalog must use .csv or .xlsx")
    mentors = _records_from_rows(rows)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    return {
        "schema_version": MENTOR_CATALOG_SCHEMA_VERSION,
        "status": "ready" if mentors else "empty_catalog",
        "source_file": source_path.name,
        "source_format": source_format,
        "catalog_sha256": catalog_sha256,
        "row_count": len(mentors),
        "synthetic_count": sum(
            bool(mentor.get("simulation_only")) for mentor in mentors
        ),
        "mentors": mentors,
        "authority": "declared_mentor_catalog",
    }


def _parse_as_of(value: date | datetime | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    cleaned = _clean_text(value)
    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError as exc:
        raise ValueError("as_of must be an ISO date or date-like object") from exc


def _valid_until(value: Any) -> tuple[date | None, str | None]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None, "valid_until_missing"
    try:
        return date.fromisoformat(cleaned[:10]), None
    except ValueError:
        return None, "valid_until_invalid"


def _hard_exclusion_reasons(mentor: Mapping[str, Any], as_of: date) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    availability = _status_key(mentor.get("availability_status"))
    if availability not in AVAILABLE_STATUSES:
        reasons.append(
            {
                "code": "availability_not_available",
                "field": "availability_status",
                "observed": _clean_text(mentor.get("availability_status")),
            }
        )
    consent = _status_key(mentor.get("consent_status"))
    if consent not in CONSENTED_STATUSES:
        reasons.append(
            {
                "code": "consent_not_granted",
                "field": "consent_status",
                "observed": _clean_text(mentor.get("consent_status")),
            }
        )
    conflict = _status_key(mentor.get("conflict_status"))
    if conflict not in CLEAR_CONFLICT_STATUSES:
        reasons.append(
            {
                "code": "conflict_not_clear",
                "field": "conflict_status",
                "observed": _clean_text(mentor.get("conflict_status")),
            }
        )
    valid_until, validity_error = _valid_until(mentor.get("valid_until"))
    if validity_error:
        reasons.append(
            {
                "code": validity_error,
                "field": "valid_until",
                "observed": _clean_text(mentor.get("valid_until")),
            }
        )
    elif valid_until is not None and valid_until < as_of:
        reasons.append(
            {
                "code": "validity_expired",
                "field": "valid_until",
                "observed": valid_until.isoformat(),
            }
        )
    return reasons


def _profile_values(profile: Mapping[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(profile, Mapping):
        return {}
    raw = profile.get("tags", profile)
    if not isinstance(raw, Mapping):
        return {}
    values: dict[str, list[str]] = {}
    for rule in DIMENSION_RULES:
        combined: list[str] = []
        for field in rule["profile_fields"]:
            combined.extend(_tag_values(raw.get(field)))
        normalized = _tag_values(combined)
        if normalized:
            values[rule["id"]] = normalized
    return values


def _intersection(profile_values: list[str], mentor_values: list[str]) -> list[str]:
    mentor_keys = {value.casefold() for value in mentor_values}
    return [value for value in profile_values if value.casefold() in mentor_keys]


def _source_reference(
    mentor: Mapping[str, Any], catalog: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "source_file": catalog["source_file"],
        "source_row": mentor["source_row"],
        "catalog_sha256": catalog["catalog_sha256"],
        "row_sha256": mentor["row_sha256"],
        "declared_source": mentor["source"],
        "source_url": mentor["source_url"],
        "updated_at": mentor["updated_at"],
        "data_class": mentor.get("data_class", "operator_declared"),
        "simulation_only": mentor.get("simulation_only") is True,
        "disclosure_label": mentor.get("disclosure_label") or None,
    }


def _catalog_for_matching(
    catalog: Mapping[str, Any] | str | Path | None,
) -> dict[str, Any] | None:
    if catalog is None:
        return None
    if isinstance(catalog, (str, Path)):
        return load_mentor_catalog(catalog)
    if not isinstance(catalog, Mapping):
        raise MentorCatalogError("catalog must be a loaded catalog, path, or None")
    if catalog.get("schema_version") != MENTOR_CATALOG_SCHEMA_VERSION:
        raise MentorCatalogError("unsupported mentor catalog schema_version")
    mentors = catalog.get("mentors")
    if not isinstance(mentors, list) or not all(isinstance(item, Mapping) for item in mentors):
        raise MentorCatalogError("loaded mentor catalog must contain a mentor list")
    return dict(catalog)


def _empty_match_result(*, status: str, as_of: date) -> dict[str, Any]:
    return {
        "schema_version": MENTOR_CATALOG_SCHEMA_VERSION,
        "rule_version": MENTOR_MATCH_RULE_VERSION,
        "rule_digest": MENTOR_MATCH_RULE_DIGEST,
        "status": status,
        "catalog_status": status,
        "evaluated_as_of": as_of.isoformat(),
        "catalog_reference": None,
        "profile_dimensions": {},
        "candidate_matches": [],
        "hard_exclusions": [],
        "unmatched_eligible_mentors": [],
        "summary": {
            "catalog_rows": 0,
            "eligible_rows": 0,
            "candidate_match_count": 0,
            "hard_exclusion_count": 0,
        },
        "ordering": "mentor_id_casefold_ascending_not_ranked",
        "boundaries": {
            "candidate_only": True,
            "automatic_assignment": False,
            "aggregate_score_produced": False,
            "human_confirmation_required": True,
        },
    }


def browse_mentor_catalog(
    catalog: Mapping[str, Any] | str | Path,
    *,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Return only catalog entries that pass all hard directory gates."""

    evaluation_date = _parse_as_of(as_of)
    loaded_catalog = _catalog_for_matching(catalog)
    if loaded_catalog is None:
        raise MentorCatalogError("mentor catalog must be connected before browsing")
    metadata = {
        "source_file": loaded_catalog["source_file"],
        "source_format": loaded_catalog["source_format"],
        "catalog_sha256": loaded_catalog["catalog_sha256"],
        "record_count": len(loaded_catalog["mentors"]),
    }
    if not loaded_catalog["mentors"]:
        return {
            "category": "mentor",
            "status": "empty_catalog",
            "items": [],
            "catalog_metadata": metadata | {"browsable_count": 0},
            "excluded_reason_counts": {},
            "evaluated_as_of": evaluation_date.isoformat(),
            "rule_version": MENTOR_MATCH_RULE_VERSION,
            "rule_digest": MENTOR_MATCH_RULE_DIGEST,
            "authority": "candidate_directory_only",
            "boundaries": {
                "hard_gates_applied": True,
                "matching_performed": False,
                "aggregate_score_produced": False,
                "automatic_assignment": False,
                "human_confirmation_required": True,
            },
        }

    items = []
    excluded_counts: Counter[str] = Counter()
    mentors = sorted(
        loaded_catalog["mentors"],
        key=lambda item: (
            _clean_text(item["mentor_id"]).casefold(),
            _clean_text(item["display_name"]).casefold(),
            int(item["source_row"]),
        ),
    )
    for mentor in mentors:
        reasons = _hard_exclusion_reasons(mentor, evaluation_date)
        if reasons:
            for reason in reasons:
                excluded_counts[reason["code"]] += 1
            continue
        items.append(
            {
                "mentor_id": mentor["mentor_id"],
                "display_name": mentor["display_name"],
                "expertise_tags": list(mentor["expertise_tags"]),
                "industry_tags": list(mentor["industry_tags"]),
                "stage_tags": list(mentor["stage_tags"]),
                "geography_tags": list(mentor["geography_tags"]),
                "market_tags": list(mentor["market_tags"]),
                "languages": list(mentor["languages"]),
                "availability_status": mentor["availability_status"],
                "consent_status": mentor["consent_status"],
                "conflict_status": mentor["conflict_status"],
                "valid_until": mentor["valid_until"],
                "profile_summary": mentor.get("profile_summary") or "",
                "data_class": mentor.get("data_class", "operator_declared"),
                "simulation_only": mentor.get("simulation_only") is True,
                "disclosure_label": mentor.get("disclosure_label") or None,
                "contactable": False,
                "source_reference": _source_reference(mentor, loaded_catalog),
                "rule_version": MENTOR_MATCH_RULE_VERSION,
                "authority": "eligible_directory_candidate_only",
            }
        )
    return {
        "category": "mentor",
        "status": "ready" if items else "no_eligible_entries",
        "items": items,
        "catalog_metadata": metadata | {"browsable_count": len(items)},
        "excluded_reason_counts": dict(sorted(excluded_counts.items())),
        "evaluated_as_of": evaluation_date.isoformat(),
        "rule_version": MENTOR_MATCH_RULE_VERSION,
        "rule_digest": MENTOR_MATCH_RULE_DIGEST,
        "authority": "candidate_directory_only",
        "boundaries": {
            "hard_gates_applied": True,
            "matching_performed": False,
            "aggregate_score_produced": False,
            "automatic_assignment": False,
            "human_confirmation_required": True,
        },
    }


def match_mentor_candidates(
    profile: Mapping[str, Any] | None,
    catalog: Mapping[str, Any] | str | Path | None,
    *,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Return eligible mentor candidates without ranking scores or assignment."""

    evaluation_date = _parse_as_of(as_of)
    loaded_catalog = _catalog_for_matching(catalog)
    if loaded_catalog is None:
        return _empty_match_result(status="not_connected", as_of=evaluation_date)
    if loaded_catalog.get("status") == "empty_catalog" or not loaded_catalog["mentors"]:
        result = _empty_match_result(status="empty_catalog", as_of=evaluation_date)
        result["catalog_reference"] = {
            "source_file": loaded_catalog["source_file"],
            "source_format": loaded_catalog["source_format"],
            "catalog_sha256": loaded_catalog["catalog_sha256"],
        }
        return result

    normalized_profile = _profile_values(profile)
    core_dimensions = {"expertise", "industry"}
    core_requested = any(
        normalized_profile.get(dimension) for dimension in core_dimensions
    )
    candidates = []
    hard_exclusions = []
    unmatched_eligible = []
    mentors = sorted(
        loaded_catalog["mentors"],
        key=lambda item: (
            _clean_text(item["mentor_id"]).casefold(),
            _clean_text(item["display_name"]).casefold(),
            int(item["source_row"]),
        ),
    )
    for mentor in mentors:
        source_reference = _source_reference(mentor, loaded_catalog)
        exclusion_reasons = _hard_exclusion_reasons(mentor, evaluation_date)
        if exclusion_reasons:
            hard_exclusions.append(
                {
                    "mentor_id": mentor["mentor_id"],
                    "display_name": mentor["display_name"],
                    "reasons": exclusion_reasons,
                    "source_reference": source_reference,
                    "rule_version": MENTOR_MATCH_RULE_VERSION,
                }
            )
            continue

        matched_dimensions = []
        unmet_constraints = []
        for rule in DIMENSION_RULES:
            requested = normalized_profile.get(rule["id"], [])
            if not requested:
                continue
            declared = list(mentor[rule["mentor_field"]])
            matched = _intersection(requested, declared)
            if matched:
                matched_dimensions.append(
                    {
                        "dimension": rule["id"],
                        "label_zh": rule["label_zh"],
                        "matched_values": matched,
                        "profile_values": requested,
                        "mentor_values": declared,
                    }
                )
            else:
                unmet_constraints.append(
                    {
                        "dimension": rule["id"],
                        "label_zh": rule["label_zh"],
                        "reason": "no_exact_tag_overlap",
                        "profile_values": requested,
                        "mentor_values": declared,
                    }
                )
        matched_dimension_ids = {
            item["dimension"] for item in matched_dimensions
        }
        core_matched = bool(matched_dimension_ids & core_dimensions)
        if not matched_dimensions or (core_requested and not core_matched):
            unmatched_eligible.append(
                {
                    "mentor_id": mentor["mentor_id"],
                    "display_name": mentor["display_name"],
                    "reason": (
                        "core_profile_mismatch"
                        if matched_dimensions and core_requested
                        else "no_profile_tag_overlap"
                        if normalized_profile
                        else "profile_tags_missing"
                    ),
                    "unmet_constraints": unmet_constraints,
                    "source_reference": source_reference,
                    "rule_version": MENTOR_MATCH_RULE_VERSION,
                }
            )
            continue
        rationale_parts = [
            f"{item['label_zh']}={','.join(item['matched_values'])}" for item in matched_dimensions
        ]
        candidates.append(
            {
                "mentor_id": mentor["mentor_id"],
                "display_name": mentor["display_name"],
                "matched_dimensions": matched_dimensions,
                "unmet_constraints": unmet_constraints,
                "rationale_zh": "候选匹配依据：" + "；".join(rationale_parts) + "。",
                "languages": list(mentor["languages"]),
                "availability_status": mentor["availability_status"],
                "consent_status": mentor["consent_status"],
                "conflict_status": mentor["conflict_status"],
                "valid_until": mentor["valid_until"],
                "profile_summary": mentor.get("profile_summary") or "",
                "data_class": mentor.get("data_class", "operator_declared"),
                "simulation_only": mentor.get("simulation_only") is True,
                "disclosure_label": mentor.get("disclosure_label") or None,
                "contactable": False,
                "source_reference": source_reference,
                "rule_version": MENTOR_MATCH_RULE_VERSION,
                "authority": (
                    "synthetic_candidate_match_only"
                    if mentor.get("simulation_only") is True
                    else "candidate_match_only"
                ),
            }
        )

    if not normalized_profile:
        status = "insufficient_profile"
    elif candidates:
        status = "candidate_matches_ready"
    else:
        status = "no_candidate_matches"
    eligible_count = len(mentors) - len(hard_exclusions)
    return {
        "schema_version": MENTOR_CATALOG_SCHEMA_VERSION,
        "rule_version": MENTOR_MATCH_RULE_VERSION,
        "rule_digest": MENTOR_MATCH_RULE_DIGEST,
        "status": status,
        "catalog_status": loaded_catalog["status"],
        "evaluated_as_of": evaluation_date.isoformat(),
        "catalog_reference": {
            "source_file": loaded_catalog["source_file"],
            "source_format": loaded_catalog["source_format"],
            "catalog_sha256": loaded_catalog["catalog_sha256"],
        },
        "profile_dimensions": normalized_profile,
        "candidate_matches": candidates,
        "hard_exclusions": hard_exclusions,
        "unmatched_eligible_mentors": unmatched_eligible,
        "summary": {
            "catalog_rows": len(mentors),
            "eligible_rows": eligible_count,
            "candidate_match_count": len(candidates),
            "hard_exclusion_count": len(hard_exclusions),
        },
        "ordering": "mentor_id_casefold_ascending_not_ranked",
        "boundaries": {
            "candidate_only": True,
            "automatic_assignment": False,
            "aggregate_score_produced": False,
            "human_confirmation_required": True,
        },
    }
