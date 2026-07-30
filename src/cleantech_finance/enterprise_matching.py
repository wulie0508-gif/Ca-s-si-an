"""Deterministic CSV/XLSX course and policy matching."""

from __future__ import annotations

import csv
import json
import posixpath
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

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
    "policy_allowed_review_statuses": ["已复核通过", "approved", "verified"],
    "field_aliases": {
        "id": ["id", "course_id", "policy_id", "编号", "课程编号", "政策编号"],
        "title": ["title", "name", "课程名称", "政策名称", "名称"],
        "review_status": ["review_status", "复核状态", "审核状态"],
        "expiry_date": ["expiry_date", "valid_until", "有效期至", "截止日期", "失效日期"],
        "industry": ["industry_tags", "industry", "行业标签", "适用行业"],
        "stage": ["stage_tags", "stage", "阶段标签", "企业阶段"],
        "need": ["need_tags", "needs", "需求标签", "痛点标签"],
        "technology": ["technology_tags", "technology", "技术标签"],
        "geography": ["geography_tags", "geography", "地区标签", "适用地区"],
        "market": ["market_tags", "market", "市场标签", "目标市场"],
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


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    value = 0
    for character in letters.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("{*}si"):
                shared.append("".join(node.text or "" for node in item.findall(".//{*}t")))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = workbook.find(".//{*}sheet")
        if first_sheet is None:
            return []
        relation_id = first_sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in relations.findall("{*}Relationship"):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            return []
        worksheet_path = target.lstrip("/")
        if not worksheet_path.startswith("xl/"):
            worksheet_path = posixpath.normpath(f"xl/{worksheet_path}")
        sheet = ElementTree.fromstring(archive.read(worksheet_path))
        rows: list[list[str]] = []
        for row_node in sheet.findall(".//{*}sheetData/{*}row"):
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
            if values:
                rows.append([values.get(index, "") for index in range(max(values) + 1)])
        return rows


def _tabular_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Catalog does not exist: {source}")
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {str(key).strip(): str(value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    if source.suffix.lower() != ".xlsx":
        raise ValueError("Course and policy catalogs must be .csv or .xlsx files")
    raw_rows = _xlsx_rows(source)
    if not raw_rows:
        return []
    headers = [header.strip() or f"column_{index + 1}" for index, header in enumerate(raw_rows[0])]
    results: list[dict[str, str]] = []
    for raw in raw_rows[1:]:
        row = {
            headers[index]: (raw[index].strip() if index < len(raw) else "")
            for index in range(len(headers))
        }
        if any(row.values()):
            results.append(row)
    return results


def _field(row: dict[str, str], aliases: list[str]) -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(alias.strip().lower())
        if value:
            return value.strip()
    return ""


def _tags(value: Any) -> set[str]:
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = re.split(r"[,，;；|/\n]+", str(value or ""))
    return {part.strip().casefold() for part in parts if part.strip()}


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        serial = float(text)
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(serial))
    normalized = text.replace("/", "-").replace(".", "-")
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        for pattern in ("%Y年%m月%d日", "%Y-%m", "%Y年%m月"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    return None


def _policy_filter(
    row: dict[str, str],
    *,
    config: dict[str, Any],
    as_of: date,
) -> tuple[bool, str]:
    aliases = config["field_aliases"]
    review = _field(row, aliases["review_status"]).casefold()
    allowed = {
        str(value).casefold()
        for value in DEFAULT_MATCHING_CONFIG["policy_allowed_review_statuses"]
    }
    if review not in allowed:
        return False, "review_status_not_approved"
    expiry_raw = _field(row, aliases["expiry_date"])
    expiry = _parse_date(expiry_raw) if expiry_raw else None
    if expiry_raw and expiry is None:
        return False, "expiry_date_invalid"
    if expiry and expiry < as_of:
        return False, "expired"
    return True, "passed"


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
    rows = _tabular_rows(catalog_path)
    aliases = settings["field_aliases"]
    normalized_profile = {
        dimension: _tags(profile_tags.get(dimension, []))
        for dimension in settings["tag_weights"]
    }
    matches: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        item_id = _field(row, aliases["id"]) or f"row-{index}"
        title = _field(row, aliases["title"]) or item_id
        if category == "policy":
            eligible, reason = _policy_filter(row, config=settings, as_of=as_of_date)
            if not eligible:
                excluded.append(
                    {
                        "item_id": item_id,
                        "title": title,
                        "row": index,
                        "reason": reason,
                    }
                )
                continue
        score = 0.0
        rationale: list[dict[str, Any]] = []
        for dimension, weight in settings["tag_weights"].items():
            catalog_tags = _tags(_field(row, aliases[dimension]))
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
                    }
                )
        if score >= float(settings["minimum_match_score"]):
            matches.append(
                {
                    "category": category,
                    "item_id": item_id,
                    "title": title,
                    "match_score": round(score, 4),
                    "rationale": rationale,
                    "hard_filter_status": "passed" if category == "policy" else "not_applicable",
                    "source_row": index,
                }
            )
    matches.sort(key=lambda item: (-item["match_score"], item["item_id"]))
    matches = matches[: int(settings["maximum_results"])]
    return {
        "category": category,
        "catalog": str(Path(catalog_path).resolve()),
        "status": "matched" if matches else "no_high_match",
        "message": None if matches else "无高匹配；未执行硬推荐。",
        "matches": matches,
        "excluded": excluded,
        "rules": {
            "tag_weights": settings["tag_weights"],
            "minimum_match_score": settings["minimum_match_score"],
            "policy_hard_filter_enabled": category == "policy",
        },
    }
