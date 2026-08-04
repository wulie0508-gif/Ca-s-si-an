from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from cleantech_finance.mentor_matching import (
    MENTOR_MATCH_RULE_VERSION,
    REQUIRED_COLUMNS,
    MentorCatalogError,
    load_mentor_catalog,
    match_mentor_candidates,
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _row(mentor_id: str, display_name: str, **overrides: str) -> dict[str, str]:
    values = {
        "mentor_id": mentor_id,
        "display_name": display_name,
        "expertise_tags": "hydrogen|fundraising",
        "industry_tags": "Hydrogen|Clean Energy",
        "stage_tags": "early commercialization",
        "geography_tags": "China|USA",
        "market_tags": "industrial",
        "languages": "Chinese|English",
        "availability_status": "available",
        "consent_status": "consented",
        "conflict_status": "clear",
        "valid_until": "2026-12-31",
        "source": "mentor operations",
        "source_url": "https://example.test/mentor-source",
        "updated_at": "2026-08-01T09:00:00+08:00",
    }
    values.update(overrides)
    return values


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding="utf-8")


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    ElementTree.register_namespace("", _MAIN_NS)
    ElementTree.register_namespace("r", _DOC_REL_NS)

    workbook = ElementTree.Element(f"{{{_MAIN_NS}}}workbook")
    sheets = ElementTree.SubElement(workbook, f"{{{_MAIN_NS}}}sheets")
    sheet = ElementTree.SubElement(
        sheets,
        f"{{{_MAIN_NS}}}sheet",
        {"name": "Mentors", "sheetId": "1"},
    )
    sheet.set(f"{{{_DOC_REL_NS}}}id", "rId1")

    relationships = ElementTree.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
    ElementTree.SubElement(
        relationships,
        f"{{{_PACKAGE_REL_NS}}}Relationship",
        {
            "Id": "rId1",
            "Type": f"{_DOC_REL_NS}/worksheet",
            "Target": "worksheets/sheet1.xml",
        },
    )

    worksheet = ElementTree.Element(f"{{{_MAIN_NS}}}worksheet")
    sheet_data = ElementTree.SubElement(worksheet, f"{{{_MAIN_NS}}}sheetData")
    for row_number, values in enumerate(rows, 1):
        row_node = ElementTree.SubElement(
            sheet_data, f"{{{_MAIN_NS}}}row", {"r": str(row_number)}
        )
        for column_number, value in enumerate(values, 1):
            cell = ElementTree.SubElement(
                row_node,
                f"{{{_MAIN_NS}}}c",
                {"r": f"{_column_name(column_number)}{row_number}", "t": "inlineStr"},
            )
            inline = ElementTree.SubElement(cell, f"{{{_MAIN_NS}}}is")
            text = ElementTree.SubElement(inline, f"{{{_MAIN_NS}}}t")
            text.text = value

    content_types = ElementTree.Element(f"{{{_CONTENT_TYPES_NS}}}Types")
    ElementTree.SubElement(
        content_types,
        f"{{{_CONTENT_TYPES_NS}}}Default",
        {
            "Extension": "rels",
            "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
        },
    )
    ElementTree.SubElement(
        content_types,
        f"{{{_CONTENT_TYPES_NS}}}Default",
        {"Extension": "xml", "ContentType": "application/xml"},
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            ElementTree.tostring(content_types, encoding="utf-8", xml_declaration=True),
        )
        archive.writestr(
            "xl/workbook.xml",
            ElementTree.tostring(workbook, encoding="utf-8", xml_declaration=True),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            ElementTree.tostring(relationships, encoding="utf-8", xml_declaration=True),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            ElementTree.tostring(worksheet, encoding="utf-8", xml_declaration=True),
        )


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def test_empty_template_is_valid_and_distinct_from_not_connected() -> None:
    template = Path(__file__).parents[1] / "templates" / "mentor-catalog-template.csv"
    catalog = load_mentor_catalog(template)

    not_connected = match_mentor_candidates(
        {"tags": {"industry": ["hydrogen"]}}, None, as_of="2026-08-02"
    )
    empty_catalog = match_mentor_candidates(
        {"tags": {"industry": ["hydrogen"]}}, catalog, as_of="2026-08-02"
    )

    assert catalog["status"] == "empty_catalog"
    assert catalog["row_count"] == 0
    assert not_connected["status"] == "not_connected"
    assert not_connected["catalog_reference"] is None
    assert empty_catalog["status"] == "empty_catalog"
    assert empty_catalog["catalog_reference"]["catalog_sha256"] == catalog["catalog_sha256"]


def test_csv_candidates_are_traceable_deterministic_and_not_scored(tmp_path: Path) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(
        path,
        [
            _row("mentor-b", "Beta", stage_tags="pilot", market_tags="mobility"),
            _row("mentor-a", "Alpha", stage_tags="early commercialization"),
        ],
    )
    profile = {
        "tags": {
            "industry": ["hydrogen"],
            "stage": ["early commercialization"],
            "technology": ["hydrogen"],
            "market": ["industrial"],
            "geography": ["China"],
            "languages": ["English"],
        }
    }

    first = match_mentor_candidates(profile, path, as_of="2026-08-02")
    second = match_mentor_candidates(profile, path, as_of="2026-08-02")

    assert first == second
    assert first["status"] == "candidate_matches_ready"
    assert [item["mentor_id"] for item in first["candidate_matches"]] == [
        "mentor-a",
        "mentor-b",
    ]
    alpha = first["candidate_matches"][0]
    assert [item["dimension"] for item in alpha["matched_dimensions"]] == [
        "expertise",
        "industry",
        "stage",
        "geography",
        "market",
        "language",
    ]
    assert alpha["source_reference"]["source_row"] == 3
    assert len(alpha["source_reference"]["catalog_sha256"]) == 64
    assert len(alpha["source_reference"]["row_sha256"]) == 64
    assert alpha["rule_version"] == MENTOR_MATCH_RULE_VERSION
    assert alpha["authority"] == "candidate_match_only"
    keys = _all_keys(first)
    assert "score" not in keys
    assert "composite_score" not in keys
    assert "assigned_mentor_id" not in keys
    assert first["boundaries"]["automatic_assignment"] is False
    assert first["boundaries"]["aggregate_score_produced"] is False


def test_unmet_constraints_are_preserved_without_affecting_candidate_authority(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(path, [_row("mentor-1", "One", market_tags="mobility", languages="Chinese")])

    result = match_mentor_candidates(
        {
            "tags": {
                "industry": ["hydrogen"],
                "market": ["industrial"],
                "languages": ["English"],
            }
        },
        path,
        as_of="2026-08-02",
    )

    candidate = result["candidate_matches"][0]
    assert [item["dimension"] for item in candidate["matched_dimensions"]] == ["industry"]
    assert [item["dimension"] for item in candidate["unmet_constraints"]] == [
        "market",
        "language",
    ]
    assert "行业=hydrogen" in candidate["rationale_zh"]


def test_hard_exclusions_cover_consent_availability_conflict_and_validity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(
        path,
        [
            _row("available", "Available", valid_until="2026-08-02"),
            _row("unavailable", "Unavailable", availability_status="unavailable"),
            _row("no-consent", "No consent", consent_status="pending"),
            _row("conflict", "Conflict", conflict_status="conflict"),
            _row("expired", "Expired", valid_until="2026-08-01"),
            _row("no-validity", "No validity", valid_until=""),
        ],
    )

    result = match_mentor_candidates(
        {"tags": {"industry": ["hydrogen"]}}, path, as_of="2026-08-02"
    )

    assert [item["mentor_id"] for item in result["candidate_matches"]] == ["available"]
    reason_codes = {
        item["mentor_id"]: [reason["code"] for reason in item["reasons"]]
        for item in result["hard_exclusions"]
    }
    assert reason_codes["unavailable"] == ["availability_not_available"]
    assert reason_codes["no-consent"] == ["consent_not_granted"]
    assert reason_codes["conflict"] == ["conflict_not_clear"]
    assert reason_codes["expired"] == ["validity_expired"]
    assert reason_codes["no-validity"] == ["valid_until_missing"]
    assert result["summary"]["hard_exclusion_count"] == 5


@pytest.mark.parametrize(
    ("mentor_id", "display_name", "missing_field"),
    [("", "Missing ID", "mentor_id"), ("mentor-1", "", "display_name")],
)
def test_missing_identity_fields_fail_closed(
    tmp_path: Path,
    mentor_id: str,
    display_name: str,
    missing_field: str,
) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(path, [_row(mentor_id, display_name)])

    with pytest.raises(MentorCatalogError, match=missing_field):
        load_mentor_catalog(path)


def test_duplicate_ids_fail_closed_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(path, [_row("Mentor-1", "One"), _row("mentor-1", "Duplicate")])

    with pytest.raises(MentorCatalogError, match="duplicate mentor_id"):
        load_mentor_catalog(path)


def test_xlsx_catalog_is_readable_and_matches_candidate(tmp_path: Path) -> None:
    path = tmp_path / "mentors.xlsx"
    mentor = _row("xlsx-mentor", "XLSX Mentor")
    _write_minimal_xlsx(
        path,
        [list(REQUIRED_COLUMNS), [mentor[column] for column in REQUIRED_COLUMNS]],
    )

    catalog = load_mentor_catalog(path)
    result = match_mentor_candidates(
        {"tags": {"industry": ["hydrogen"]}}, catalog, as_of="2026-08-02"
    )

    assert catalog["source_format"] == "xlsx"
    assert catalog["row_count"] == 1
    assert catalog["mentors"][0]["source_row"] == 2
    assert [item["mentor_id"] for item in result["candidate_matches"]] == ["xlsx-mentor"]


def test_empty_profile_does_not_match_or_assign_eligible_mentors(tmp_path: Path) -> None:
    path = tmp_path / "mentors.csv"
    _write_csv(path, [_row("mentor-1", "One")])

    result = match_mentor_candidates({}, path, as_of="2026-08-02")

    assert result["status"] == "insufficient_profile"
    assert result["candidate_matches"] == []
    assert result["unmatched_eligible_mentors"][0]["reason"] == "profile_tags_missing"
    assert result["boundaries"]["automatic_assignment"] is False
