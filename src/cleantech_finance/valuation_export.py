"""Dependency-free OOXML export for auditable P0 valuation workbooks.

The exporter accepts plain deal, valuation, and immutable valuation-version
records. It builds a formula-bearing ``.xlsx`` package using only the Python
standard library.  Exporting a failed or incomplete version is intentional: the
workbook preserves audit evidence while suppressing calculations that lack the
required inputs.

This module is an export surface, not a valuation opinion, approval mechanism,
or calculation authority.  It never blends valuation methods or upgrades
candidate inputs to facts.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import Enum
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape, quoteattr

EXPORT_SCHEMA_VERSION = "1.0.0"
REQUIRED_SHEETS = (
    "Dashboard",
    "Financials",
    "Trading Comps",
    "Precedents",
    "DCF",
    "Sensitivities",
    "Sources & Assumptions",
    "Checks",
    "Versions",
)
PRECEDENTS_P0_STATUS = "Not Implemented in P0"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_EXT_PROPS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

_FORBIDDEN_PACKAGE_PARTS = (
    "xl/vbaproject.bin",
    "xl/externalLinks/",
    "xl/embeddings/",
    "xl/connections.xml",
)
_SHA256_RE = re.compile(r"^(?:sha256:)?[a-fA-F0-9]{64}$")


class ValuationExportError(ValueError):
    """Raised when the workbook package itself cannot be safely exported."""


@dataclass(frozen=True)
class ValuationWorkbookValidation:
    valid: bool
    sheet_names: tuple[str, ...]
    formula_count: int
    issues: tuple[str, ...]


@dataclass(frozen=True)
class _AuditCheck:
    check_id: str
    scope: str
    status: str
    message: str
    actual: Any = None
    expected: Any = None
    difference: Any = None
    tolerance: Any = None


@dataclass(frozen=True)
class _Cell:
    value: Any = None
    style: int = 0
    formula: str | None = None
    cached: Any = None


@dataclass
class _Worksheet:
    name: str
    cells: dict[tuple[int, int], _Cell] = field(default_factory=dict)
    merges: list[str] = field(default_factory=list)
    widths: dict[int, float] = field(default_factory=dict)
    row_heights: dict[int, float] = field(default_factory=dict)
    freeze: tuple[int, int, str] | None = None
    auto_filter: str | None = None

    def set(
        self,
        row: int,
        column: int,
        value: Any = None,
        *,
        style: int = 0,
        formula: str | None = None,
        cached: Any = None,
    ) -> None:
        if row < 1 or column < 1:
            raise ValuationExportError("Worksheet coordinates are one-based")
        self.cells[(row, column)] = _Cell(value, style, formula, cached)

    def merge(self, start_row: int, start_column: int, end_row: int, end_column: int) -> None:
        self.merges.append(
            f"{_cell_reference(start_row, start_column)}:{_cell_reference(end_row, end_column)}"
        )

    def set_widths(self, widths: Sequence[float]) -> None:
        self.widths.update({index: width for index, width in enumerate(widths, start=1)})

    def title(self, row: int, text: str, end_column: int, *, style: int = 1) -> None:
        for column in range(1, end_column + 1):
            self.set(row, column, text if column == 1 else "", style=style)
        self.merge(row, 1, row, end_column)
        self.row_heights[row] = 26

    def section(self, row: int, text: str, end_column: int) -> None:
        self.title(row, text, end_column, style=2)
        self.row_heights[row] = 20

    def to_xml(self) -> str:
        max_row = max((row for row, _ in self.cells), default=1)
        max_column = max((column for _, column in self.cells), default=1)
        rows: dict[int, list[tuple[int, _Cell]]] = defaultdict(list)
        for (row, column), cell in self.cells.items():
            rows[row].append((column, cell))
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">',
            '<sheetPr><outlinePr summaryBelow="1" summaryRight="1"/></sheetPr>',
            f'<dimension ref="A1:{_column_name(max_column)}{max_row}"/>',
            '<sheetViews><sheetView workbookViewId="0" showGridLines="0">',
        ]
        if self.freeze:
            x_split, y_split, top_left = self.freeze
            attributes = []
            if x_split:
                attributes.append(f'xSplit="{x_split}"')
            if y_split:
                attributes.append(f'ySplit="{y_split}"')
            attributes.extend(
                (
                    f'topLeftCell="{top_left}"',
                    'activePane="bottomRight"'
                    if x_split and y_split
                    else 'activePane="bottomLeft"',
                    'state="frozen"',
                )
            )
            parts.append(f"<pane {' '.join(attributes)}/>")
        parts.extend(("</sheetView></sheetViews>", '<sheetFormatPr defaultRowHeight="15"/>'))
        if self.widths:
            parts.append("<cols>")
            for column, width in sorted(self.widths.items()):
                parts.append(
                    f'<col min="{column}" max="{column}" width="{width:.2f}" customWidth="1"/>'
                )
            parts.append("</cols>")
        parts.append("<sheetData>")
        for row_number in sorted(rows):
            height = self.row_heights.get(row_number)
            row_attributes = f'r="{row_number}"'
            if height:
                row_attributes += f' ht="{height:.2f}" customHeight="1"'
            parts.append(f"<row {row_attributes}>")
            for column, cell in sorted(rows[row_number], key=lambda item: item[0]):
                parts.append(_cell_xml(row_number, column, cell))
            parts.append("</row>")
        parts.append("</sheetData>")
        if self.auto_filter:
            parts.append(f"<autoFilter ref={quoteattr(self.auto_filter)}/>")
        if self.merges:
            parts.append(f'<mergeCells count="{len(self.merges)}">')
            parts.extend(f"<mergeCell ref={quoteattr(item)}/>" for item in self.merges)
            parts.append("</mergeCells>")
        parts.extend(
            (
                '<pageMargins left="0.35" right="0.35" top="0.50" bottom="0.50" '
                'header="0.20" footer="0.20"/>',
                '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>',
                "</worksheet>",
            )
        )
        return "".join(parts)


def _column_name(column: int) -> str:
    value = column
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_reference(row: int, column: int, *, absolute: bool = False) -> str:
    prefix = "$" if absolute else ""
    return f"{prefix}{_column_name(column)}{prefix}{row}"


def _clean_xml_text(value: Any) -> str:
    text = str(value)
    text = "".join(character for character in text if character in "\t\n\r" or ord(character) >= 32)
    return text[:32767]


def _numeric_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValuationExportError("Workbook numeric values must be finite")
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValuationExportError("Workbook numeric values must be finite")
        return repr(value)
    raise TypeError(value)


def _excel_date_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _cell_xml(row: int, column: int, cell: _Cell) -> str:
    reference = _cell_reference(row, column)
    style = f' s="{cell.style}"' if cell.style else ""
    if cell.formula is not None:
        formula = cell.formula[1:] if cell.formula.startswith("=") else cell.formula
        cached = cell.cached
        if isinstance(cached, str):
            return (
                f'<c r="{reference}"{style} t="str"><f>{escape(formula)}</f>'
                f"<v>{escape(_clean_xml_text(cached))}</v></c>"
            )
        if isinstance(cached, bool):
            return (
                f'<c r="{reference}"{style} t="b"><f>{escape(formula)}</f>'
                f"<v>{_numeric_text(cached)}</v></c>"
            )
        if cached is None:
            return f'<c r="{reference}"{style}><f>{escape(formula)}</f></c>'
        return (
            f'<c r="{reference}"{style}><f>{escape(formula)}</f><v>{_numeric_text(cached)}</v></c>'
        )
    value = cell.value
    if value is None:
        return f'<c r="{reference}"{style}/>'
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return f'<c r="{reference}"{style}><v>{_excel_date_serial(value)}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{reference}"{style} t="b"><v>{_numeric_text(value)}</v></c>'
    if isinstance(value, (Decimal, int, float)):
        return f'<c r="{reference}"{style}><v>{_numeric_text(value)}</v></c>'
    text = _clean_xml_text(value)
    preserve = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f'<c r="{reference}"{style} t="inlineStr"><is><t{preserve}>{escape(text)}</t></is></c>'


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical_value(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValuationExportError("Hash payload contains a non-finite Decimal")
        return format(value, "f")
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValuationExportError("Hash payload contains a non-finite float")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValuationExportError(f"Unsupported hash payload type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _recomputed_version_hash(version: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in version.items() if key != "version_hash"})


def _as_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValuationExportError(f"{label} must be a mapping")
    return dict(value)


def _record_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("rows", "records", "items", "periods", "scenarios"):
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                value = nested
                break
        else:
            return [dict(value)]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _status(value: Any, *, fallback: str) -> str:
    if isinstance(value, Mapping):
        value = value.get("status")
    normalized = str(value or fallback).strip().casefold().replace(" ", "_")
    return normalized or fallback


def _text(value: Any, *, fallback: str = "Not supplied") -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _quantize(value: Decimal, quantum: str = "0.01") -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def _date_value(value: Any) -> date | str:
    normalized = str(value or "").strip()
    if not normalized:
        return "Not supplied"
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return normalized


def _actor_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("id") or value.get("name") or value.get("actor_id"))
    return _text(value)


def _calculation_record(valuation: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
    calculation = version.get("calculation")
    if isinstance(calculation, Mapping):
        return dict(calculation)
    calculation = valuation.get("calculation")
    return dict(calculation) if isinstance(calculation, Mapping) else {}


def _section_record(
    name: str,
    valuation: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> Any:
    return calculation.get(name) if calculation.get(name) is not None else valuation.get(name)


def _method_record(calculation: Mapping[str, Any], name: str) -> dict[str, Any]:
    methods = calculation.get("methods")
    if not isinstance(methods, Mapping):
        return {}
    method = methods.get(name)
    return dict(method) if isinstance(method, Mapping) else {}


def _first_supplied(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


_FINANCIAL_ALIASES = {
    "revenue": "revenue",
    "ebitda": "ebitda",
    "ebit": "ebit",
    "tax_rate": "tax_rate",
    "taxrate": "tax_rate",
    "depreciation_amortization": "depreciation_amortization",
    "d&a": "depreciation_amortization",
    "da": "depreciation_amortization",
    "capex": "capex",
    "change_in_nwc": "change_in_nwc",
    "changeinnwc": "change_in_nwc",
    "fcff": "fcff",
}


def _financial_value(record: Mapping[str, Any], *names: str) -> Any:
    facts = record.get("facts") if isinstance(record.get("facts"), Mapping) else {}
    for name in names:
        value = record.get(name)
        if value is None:
            value = facts.get(name)
        if isinstance(value, Mapping):
            value = value.get("value")
        if value is not None:
            return value
    return None


def _normalize_financials(
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    version_inputs = _record_list(version.get("inputs"))
    timing_by_key: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    timing_by_period: dict[tuple[str, str], dict[str, Any]] = {}
    timing_by_input_id: dict[str, dict[str, Any]] = {}
    for item in version_inputs:
        if str(item.get("input_group") or "").strip().casefold() != "dcf_timing":
            continue
        scenario = str(item.get("scenario") or "base").strip().casefold()
        period_index = str(item.get("period_index") or "").strip()
        period = str(item.get("period") or "").strip()
        field_name = str(item.get("field") or "").strip().casefold()
        if not period_index or field_name not in {"period_end", "discount_exponent"}:
            continue
        target = timing_by_key[(scenario, period_index)]
        target[field_name] = item.get("value")
        target["timing_basis"] = item.get("timing_basis")
        input_id = str(item.get("input_id") or "").strip()
        source_parts = [
            input_id,
            str(item.get("source_id") or "").strip(),
            str(item.get("locator") or "").strip(),
            str(item.get("as_of") or "").strip(),
        ]
        source_reference = " | ".join(part for part in source_parts if part)
        if source_reference:
            target.setdefault("source_references", []).append(source_reference)
        if period:
            timing_by_period[(scenario, period)] = target
        if input_id:
            timing_by_input_id[input_id] = target

    raw = _section_record("financials", valuation, calculation)
    records = _record_list(raw)
    dcf = _section_record("dcf", valuation, calculation)
    if not records and isinstance(dcf, Mapping):
        scenarios = _record_list(dcf.get("scenarios") or dcf.get("scenario_results"))
        for scenario in scenarios:
            forecast = _record_list(scenario.get("forecast") or scenario.get("periods"))
            if not forecast:
                forecast = _record_list(scenario.get("projections"))
            for item in forecast:
                item.setdefault("scenario", scenario.get("name") or scenario.get("scenario"))
                item.setdefault("discount_timing_basis", scenario.get("discount_timing_basis"))
                records.append(item)
    if not records:
        grouped: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
        for item in version_inputs:
            name = (
                str(item.get("field") or item.get("name") or "")
                .strip()
                .casefold()
                .replace(" ", "_")
                .replace("-", "_")
            )
            canonical = _FINANCIAL_ALIASES.get(name)
            period = str(item.get("period") or "").strip()
            if not canonical or not period:
                continue
            scenario = str(item.get("scenario") or item.get("scenario_name") or "base").casefold()
            input_group = str(item.get("input_group") or "").strip().casefold()
            period_type = str(item.get("period_type") or "").strip().casefold()
            financial_basis = str(item.get("financial_basis") or "").strip().casefold()
            period_end = str(item.get("period_end") or "").strip()
            period_index = str(item.get("period_index") or "").strip()
            target = grouped.setdefault(
                (
                    input_group,
                    scenario,
                    period,
                    period_type,
                    financial_basis,
                    period_end,
                    period_index,
                ),
                {
                    "scenario": scenario,
                    "period": period,
                    "period_index": period_index,
                    "input_group": input_group,
                    "period_type": period_type,
                    "financial_basis": financial_basis,
                    "period_end": period_end,
                    "source_ids": [],
                    "input_statuses": [],
                },
            )
            target[canonical] = item.get("value")
            if item.get("source_id"):
                target["source_ids"].append(str(item["source_id"]))
            if item.get("status"):
                target["input_statuses"].append(str(item["status"]))
        for target in grouped.values():
            if target.get("input_group") != "dcf":
                continue
            timing = timing_by_key.get(
                (str(target.get("scenario") or "base"), str(target.get("period_index") or "")),
                {},
            )
            if timing.get("period_end"):
                target["period_end"] = timing["period_end"]
            target["discount_exponent"] = timing.get("discount_exponent")
            target["discount_timing_basis"] = timing.get("timing_basis")
            target["timing_source_id"] = "; ".join(
                sorted(set(timing.get("source_references") or []))
            )
        records = list(grouped.values())
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        scenario = (
            str(record.get("scenario") or record.get("scenario_name") or "base").strip().casefold()
        )
        period = str(
            record.get("period") or record.get("fiscal_period") or f"Period {index}"
        ).strip()
        exponent_input_id = str(record.get("discount_exponent_input_id") or "").strip()
        period_index = str(record.get("period_index") or "").strip()
        timing = timing_by_input_id.get(exponent_input_id, {})
        if not timing and period_index:
            timing = timing_by_key.get((scenario, period_index), {})
        if not timing:
            timing = timing_by_period.get((scenario, period), {})
        period_end = _first_supplied(record.get("period_end"), timing.get("period_end"))
        discount_exponent = _first_supplied(
            record.get("discount_exponent"), timing.get("discount_exponent")
        )
        timing_basis = _first_supplied(
            record.get("discount_timing_basis"), timing.get("timing_basis")
        )
        timing_source_id = _first_supplied(
            record.get("timing_source_id"),
            "; ".join(sorted(set(timing.get("source_references") or []))),
        )
        source_ids = record.get("source_ids")
        if not isinstance(source_ids, list):
            source_ids = [record.get("source_id")] if record.get("source_id") else []
        source_id = ", ".join(sorted({str(item) for item in source_ids if item}))
        statuses = record.get("input_statuses")
        if not isinstance(statuses, list):
            statuses = [record.get("input_status") or record.get("status")]
        normalized.append(
            {
                "scenario": scenario or "base",
                "period": period,
                "revenue": _decimal(_financial_value(record, "revenue")),
                "ebitda": _decimal(_financial_value(record, "ebitda")),
                "ebit": _decimal(_financial_value(record, "ebit")),
                "tax_rate": _decimal(_financial_value(record, "tax_rate")),
                "depreciation_amortization": _decimal(
                    _financial_value(record, "depreciation_amortization", "d_and_a", "da")
                ),
                "capex": _decimal(_financial_value(record, "capex")),
                "change_in_nwc": _decimal(_financial_value(record, "change_in_nwc", "nwc_change")),
                "fcff_supplied": _decimal(_financial_value(record, "fcff")),
                "source_id": source_id or _text(record.get("source_id")),
                "input_status": ", ".join(sorted({str(item) for item in statuses if item}))
                or "Not supplied",
                "input_group": _text(record.get("input_group")),
                "period_type": _text(record.get("period_type")),
                "financial_basis": _text(record.get("financial_basis")),
                "period_end": _text(period_end),
                "discount_exponent": _decimal(discount_exponent),
                "discount_timing_basis": _text(timing_basis),
                "timing_source_id": _text(timing_source_id),
            }
        )
    return normalized


def _percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        raise ValuationExportError("Percentile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * percentile
    lower = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _build_financials_sheet(
    rows: list[dict[str, Any]],
    *,
    currency: str,
    unit: str,
    checks: list[_AuditCheck],
) -> tuple[_Worksheet, list[dict[str, Any]]]:
    sheet = _Worksheet("Financials")
    sheet.set_widths(
        (14, 14, 15, 15, 15, 13, 15, 15, 17, 16, 24, 20, 15, 18, 14, 24)
    )
    sheet.freeze = (2, 4, "C5")
    sheet.title(1, "Financials — Source Inputs and Formula FCFF", 12)
    sheet.set(
        2,
        1,
        f"Currency: {currency} | Unit: {unit} | Formula cells are black; linked/source inputs are green.",
        style=11,
    )
    sheet.merge(2, 1, 2, 16)
    headers = (
        "Scenario",
        "Period",
        "Revenue",
        "EBITDA",
        "EBIT",
        "Tax Rate",
        "D&A",
        "CapEx",
        "Change in NWC",
        "FCFF",
        "Source ID",
        "Input Status",
        "Period Type",
        "Financial Basis",
        "Period End",
        "Input Group",
    )
    for column, header in enumerate(headers, start=1):
        sheet.set(4, column, header, style=3)
    if not rows:
        sheet.set(
            5,
            1,
            "No financial forecast records supplied; calculation cells are intentionally unavailable.",
            style=12,
        )
        sheet.merge(5, 1, 5, 16)
        checks.append(
            _AuditCheck(
                "financial_forecast_available",
                "readiness",
                "failed",
                "No financial forecast records were supplied to the export.",
            )
        )
        return sheet, rows
    for offset, record in enumerate(rows, start=5):
        record["sheet_row"] = offset
        sheet.set(offset, 1, record["scenario"])
        sheet.set(offset, 2, record["period"])
        for column, field_name in (
            (3, "revenue"),
            (4, "ebitda"),
            (5, "ebit"),
            (7, "depreciation_amortization"),
            (8, "capex"),
            (9, "change_in_nwc"),
        ):
            value = record[field_name]
            sheet.set(
                offset,
                column,
                value if value is not None else "N/A",
                style=5 if value is not None else 11,
            )
        tax_rate = record["tax_rate"]
        sheet.set(
            offset,
            6,
            tax_rate if tax_rate is not None else "N/A",
            style=19 if tax_rate is not None else 11,
        )
        fcff_inputs = (
            record["ebit"],
            record["tax_rate"],
            record["depreciation_amortization"],
            record["capex"],
            record["change_in_nwc"],
        )
        if all(item is not None for item in fcff_inputs):
            ebit, tax_rate, depreciation, capex, nwc = fcff_inputs
            assert all(isinstance(item, Decimal) for item in fcff_inputs)
            fcff = _quantize(ebit * (Decimal(1) - tax_rate) + depreciation - capex - nwc)
            record["fcff"] = fcff
            formula = f"E{offset}*(1-F{offset})+G{offset}-H{offset}-I{offset}"
            sheet.set(offset, 10, style=6, formula=formula, cached=fcff)
        elif record["fcff_supplied"] is not None:
            record["fcff"] = record["fcff_supplied"]
            sheet.set(offset, 10, record["fcff_supplied"], style=5)
            checks.append(
                _AuditCheck(
                    f"fcff_formula_available:{record['scenario']}:{record['period']}",
                    "readiness",
                    "warning",
                    "FCFF was supplied but component inputs were incomplete; no formula was invented.",
                    actual=record["fcff_supplied"],
                    expected="EBIT, tax rate, D&A, CapEx, and Change in NWC",
                )
            )
        else:
            record["fcff"] = None
            sheet.set(offset, 10, "N/A — inputs incomplete", style=12)
            checks.append(
                _AuditCheck(
                    f"fcff_inputs_complete:{record['scenario']}:{record['period']}",
                    "readiness",
                    "failed",
                    "FCFF cannot calculate because one or more component inputs are missing.",
                )
            )
        sheet.set(offset, 11, record["source_id"], style=18)
        sheet.set(offset, 12, record["input_status"])
        sheet.set(offset, 13, record.get("period_type") or "Not disclosed")
        sheet.set(offset, 14, record.get("financial_basis") or "Not disclosed")
        sheet.set(offset, 15, record.get("period_end") or "Not disclosed")
        sheet.set(offset, 16, record.get("input_group") or "legacy / supplied section")
    sheet.auto_filter = f"A4:P{4 + len(rows)}"
    return sheet, rows


def _normalize_trading_comps(
    valuation: Mapping[str, Any],
    calculation: Mapping[str, Any],
    version: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw = _section_record("trading_comps", valuation, calculation)
    method = _method_record(calculation, "trading_comps")
    if raw is None:
        raw = method.get("result") or method
    metric = None
    outlier_peer_ids: set[str] = set()
    if isinstance(raw, Mapping):
        metric = raw.get("metric")
        statistics = raw.get("statistics")
        if isinstance(statistics, Mapping):
            outlier_peer_ids = {str(item) for item in statistics.get("outlier_peer_ids") or []}
        raw = raw.get("observations") or raw.get("peers") or raw.get("records") or raw
    records = _record_list(raw)
    source_by_peer: dict[str, str] = {}
    for item in _record_list(version.get("inputs")):
        peer_id = str(item.get("peer_id") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        if peer_id and source_id:
            source_by_peer.setdefault(peer_id, source_id)
    normalized = []
    for index, record in enumerate(records, start=1):
        status = _status(record.get("status"), fallback="N/A")
        value = _decimal(
            record.get("value") if record.get("value") is not None else record.get("multiple")
        )
        included = bool(record.get("included_in_statistics") or record.get("included"))
        if status in {"n/a", "n/m", "not_available", "not_meaningful", "excluded"}:
            value = None
            included = False
        peer_id = _text(record.get("peer_id"), fallback=f"peer-{index}")
        normalized.append(
            {
                "peer_id": peer_id,
                "peer_name": _text(record.get("peer_name") or record.get("name")),
                "classification": _text(record.get("classification")),
                "rationale": _text(record.get("rationale") or record.get("reason")),
                "metric": _text(record.get("metric") or metric),
                "status": str(record.get("display_value") or record.get("status") or "N/A"),
                "multiple": value,
                "included": included,
                "outlier": bool(
                    record.get("outlier") or record.get("is_outlier") or peer_id in outlier_peer_ids
                ),
                "source_id": _text(record.get("source_id") or source_by_peer.get(peer_id)),
            }
        )
    return normalized


def _build_trading_comps_sheet(
    records: list[dict[str, Any]],
    checks: list[_AuditCheck],
) -> tuple[_Worksheet, dict[str, Any]]:
    sheet = _Worksheet("Trading Comps")
    sheet.set_widths((16, 24, 20, 40, 22, 15, 14, 12, 12, 18, 24))
    sheet.freeze = (2, 5, "C6")
    sheet.title(1, "Trading Comparable Companies", 11)
    sheet.set(
        2,
        1,
        "Target baseline and excluded/aspirational peers remain visible but do not enter selected external-peer statistics unless explicitly marked.",
        style=11,
    )
    sheet.merge(2, 1, 2, 11)
    selected_values = [
        record["multiple"]
        for record in records
        if record["included"] and record["multiple"] is not None
    ]
    summary: dict[str, Any] = {"sample_count": len(selected_values)}
    labels = ((1, "Sample Count"), (3, "Median"), (5, "P25"), (7, "P75"))
    for column, label in labels:
        sheet.set(3, column, label, style=16)
    data_start = 6
    data_end = data_start + len(records) - 1
    if selected_values:
        median = _quantize(_percentile(selected_values, Decimal("0.5")))
        p25 = _quantize(_percentile(selected_values, Decimal("0.25")))
        p75 = _quantize(_percentile(selected_values, Decimal("0.75")))
        summary.update({"median": median, "p25": p25, "p75": p75})
        sheet.set(
            3, 2, style=17, formula=f"COUNT(J{data_start}:J{data_end})", cached=len(selected_values)
        )
        sheet.set(3, 4, style=10, formula=f"MEDIAN(J{data_start}:J{data_end})", cached=median)
        sheet.set(3, 6, style=10, formula=f"QUARTILE.INC(J{data_start}:J{data_end},1)", cached=p25)
        sheet.set(3, 8, style=10, formula=f"QUARTILE.INC(J{data_start}:J{data_end},3)", cached=p75)
    else:
        for column in (2, 4, 6, 8):
            sheet.set(3, column, "N/A", style=11)
        checks.append(
            _AuditCheck(
                "selected_external_peer_sample_available",
                "readiness",
                "failed",
                "No valid selected external peer multiple is available.",
            )
        )
    if 0 < len(selected_values) < 4:
        checks.append(
            _AuditCheck(
                "selected_external_peer_sample_size",
                "readiness",
                "warning",
                f"Only {len(selected_values)} selected external peers; comps remain screen-grade.",
                actual=len(selected_values),
                expected=">= 4",
            )
        )
    headers = (
        "Peer ID",
        "Peer Name",
        "Classification",
        "Inclusion / Exclusion Rationale",
        "Metric",
        "Status",
        "Multiple",
        "Included",
        "Outlier",
        "Statistical Multiple",
        "Source ID",
    )
    for column, header in enumerate(headers, start=1):
        sheet.set(5, column, header, style=3)
    if not records:
        sheet.set(6, 1, "No trading-comps observations supplied.", style=12)
        sheet.merge(6, 1, 6, 11)
        return sheet, summary
    for row, record in enumerate(records, start=data_start):
        values = (
            record["peer_id"],
            record["peer_name"],
            record["classification"],
            record["rationale"],
            record["metric"],
            record["status"],
        )
        for column, value in enumerate(values, start=1):
            sheet.set(row, column, value)
        sheet.set(
            row,
            7,
            record["multiple"] if record["multiple"] is not None else record["status"],
            style=9 if record["multiple"] is not None else 11,
        )
        sheet.set(row, 8, record["included"])
        sheet.set(row, 9, record["outlier"])
        if record["included"] and record["multiple"] is not None:
            sheet.set(row, 10, record["multiple"], style=9)
        sheet.set(row, 11, record["source_id"], style=18)
    sheet.auto_filter = f"A5:K{data_end}"
    summary.update(
        {
            "sample_count_ref": "'Trading Comps'!B3",
            "median_ref": "'Trading Comps'!D3",
            "p25_ref": "'Trading Comps'!F3",
            "p75_ref": "'Trading Comps'!H3",
        }
    )
    return sheet, summary


def _build_precedents_sheet() -> _Worksheet:
    sheet = _Worksheet("Precedents")
    sheet.set_widths((24, 90))
    sheet.title(1, "Precedent Transactions", 2)
    sheet.set(3, 1, "P0 Status", style=16)
    sheet.set(3, 2, PRECEDENTS_P0_STATUS, style=11)
    sheet.set(5, 1, "Boundary", style=16)
    sheet.set(
        5,
        2,
        "No precedent-transaction sample, control premium, synergy adjustment, or valuation conclusion is generated in P0.",
    )
    sheet.set(7, 1, "Next implementation", style=16)
    sheet.set(
        7,
        2,
        "Add announcement-date financial bases, transaction status, control scope, source provenance, and transparent inclusion/exclusion rules before use.",
    )
    return sheet


def _normalize_dcf_scenarios(
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
    calculation: Mapping[str, Any],
    financials: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = _section_record("dcf", valuation, calculation)
    dcf = dict(raw) if isinstance(raw, Mapping) else {}
    scenario_records = _record_list(dcf.get("scenarios") or dcf.get("scenario_results"))
    method = _method_record(calculation, "dcf")
    if not scenario_records:
        suite = method.get("suite")
        if isinstance(suite, Mapping):
            scenario_records = _record_list(suite.get("scenario_results"))
    if not scenario_records and dcf:
        scenario_records = [{**dcf, "name": dcf.get("name") or "base"}]
    scenario_inputs: dict[str, dict[str, Any]] = defaultdict(dict)
    version_bridge: dict[str, Any] = {}
    configured_discount_convention: Any = None
    for item in _record_list(version.get("inputs")):
        field_name = str(item.get("field") or "").strip().casefold()
        scenario_name = str(item.get("scenario") or "").strip().casefold()
        group = str(item.get("input_group") or "").strip().casefold()
        if group == "dcf" and scenario_name and field_name:
            scenario_inputs[scenario_name][field_name] = item.get("value")
        elif group == "bridge" and field_name:
            version_bridge[field_name] = item.get("value")
        elif field_name == "discount_convention":
            configured_discount_convention = item.get("value")
    if not scenario_records:
        names = {str(item.get("scenario") or "base") for item in financials}
        names.update(scenario_inputs)
        for name in sorted(names):
            scenario_records.append({"name": name})
    bridge = dcf.get("bridge")
    if not isinstance(bridge, Mapping):
        bridge = calculation.get("bridge") if isinstance(calculation.get("bridge"), Mapping) else {}
    bridge = {**version_bridge, **dict(bridge)}
    normalized = []
    for record in scenario_records:
        name = str(record.get("name") or record.get("scenario") or "base").strip().casefold()
        inputs = scenario_inputs.get(name, {})
        normalized.append(
            {
                "name": name or "base",
                "display_name": (name or "base").replace("_", " ").title(),
                "wacc": _decimal(
                    _first_supplied(record.get("wacc"), dcf.get("wacc"), inputs.get("wacc"))
                ),
                "terminal_growth": _decimal(
                    _first_supplied(
                        record.get("terminal_growth_rate"),
                        record.get("terminal_growth"),
                        dcf.get("terminal_growth_rate"),
                        dcf.get("terminal_growth"),
                        inputs.get("terminal_growth"),
                    )
                ),
                "exit_multiple": _decimal(
                    _first_supplied(
                        record.get("exit_multiple"),
                        dcf.get("exit_multiple"),
                        inputs.get("exit_multiple"),
                    )
                ),
                "terminal_metric": _decimal(
                    _first_supplied(
                        record.get("terminal_metric"),
                        dcf.get("terminal_metric"),
                        inputs.get("terminal_metric"),
                    )
                ),
                "discount_convention": str(
                    _first_supplied(
                        record.get("discount_convention"),
                        dcf.get("discount_convention"),
                        configured_discount_convention,
                        "period_end",
                    )
                ).casefold(),
                "bridge": dict(record.get("bridge"))
                if isinstance(record.get("bridge"), Mapping)
                else dict(bridge),
            }
        )
    return normalized, dcf


def _discount_denominator(
    rate: Decimal,
    index: int,
    convention: str,
    *,
    explicit_exponent: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    base = Decimal(1) + rate
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_UP
        if explicit_exponent is not None:
            exponent = explicit_exponent
            denominator = base**exponent
        elif convention == "mid_year":
            exponent = Decimal(index) - Decimal("0.5")
            denominator = (base ** (index - 1)) * base.sqrt(context)
        else:
            exponent = Decimal(index)
            denominator = base**index
    return denominator, exponent


def _bridge_value(bridge: Mapping[str, Any], *names: str) -> Decimal | None:
    for name in names:
        value = bridge.get(name)
        if isinstance(value, Mapping):
            value = value.get("value")
        result = _decimal(value)
        if result is not None:
            return result
    return None


def _add_dcf_summary_label(
    sheet: _Worksheet,
    summary_rows: dict[str, int],
    label: str,
    key: str,
    row: int,
) -> None:
    sheet.set(row, 1, label, style=16)
    summary_rows[key] = row


def _build_dcf_sheet(
    scenarios: list[dict[str, Any]],
    financials: Sequence[dict[str, Any]],
    checks: list[_AuditCheck],
) -> tuple[_Worksheet, dict[str, dict[str, Any]]]:
    sheet = _Worksheet("DCF")
    sheet.set_widths((26, 18, 18, 18, 18, 24, 18, 18, 22, 24, 30))
    sheet.freeze = (1, 3, "B4")
    sheet.title(1, "DCF — FCFF, Terminal Value, and EV-to-Equity Bridge", 11)
    sheet.set(
        2,
        1,
        "Formula outputs are recalculated from visible forecast, explicit timing, and assumption cells. Invalid WACC / growth combinations remain unavailable.",
        style=11,
    )
    sheet.merge(2, 1, 2, 11)
    scenario_meta: dict[str, dict[str, Any]] = {}
    current_row = 4
    if not scenarios:
        sheet.set(
            current_row, 1, "No DCF scenario supplied; this is an audit-only export.", style=12
        )
        sheet.merge(current_row, 1, current_row, 11)
        checks.append(
            _AuditCheck(
                "dcf_scenarios_available",
                "readiness",
                "failed",
                "No DCF scenarios were supplied.",
            )
        )
        return sheet, scenario_meta
    for scenario in scenarios:
        name = scenario["name"]
        forecasts = [
            item
            for item in financials
            if str(item.get("scenario")) == name
            and str(item.get("input_group") or "") != "financials"
        ]
        sheet.section(current_row, f"{scenario['display_name']} Scenario", 11)
        input_row = current_row + 1
        for column, label in (
            (1, "WACC"),
            (3, "Terminal Growth"),
            (5, "Exit Multiple"),
            (7, "Terminal Metric"),
            (9, "Discount Convention"),
        ):
            sheet.set(input_row, column, label, style=16)
        wacc = scenario["wacc"]
        growth = scenario["terminal_growth"]
        exit_multiple = scenario["exit_multiple"]
        terminal_metric = scenario["terminal_metric"]
        sheet.set(
            input_row, 2, wacc if wacc is not None else "N/A", style=7 if wacc is not None else 12
        )
        sheet.set(
            input_row,
            4,
            growth if growth is not None else "N/A",
            style=7 if growth is not None else 12,
        )
        sheet.set(
            input_row,
            6,
            exit_multiple if exit_multiple is not None else "N/A",
            style=9 if exit_multiple is not None else 11,
        )
        sheet.set(
            input_row,
            8,
            terminal_metric if terminal_metric is not None else "N/A",
            style=4 if terminal_metric is not None else 11,
        )
        convention = "mid_year" if scenario["discount_convention"] == "mid_year" else "period_end"
        sheet.set(input_row, 10, convention)
        headers_row = current_row + 3
        for column, header in enumerate(
            (
                "Period",
                "FCFF",
                "Discount Exponent",
                "Discount Factor",
                "PV FCFF",
                "Financials Source Cell",
                "Period End",
                "Timing Basis",
                "Timing Source ID",
            ),
            start=1,
        ):
            sheet.set(headers_row, column, header, style=3)
        data_start = headers_row + 1
        present_values: list[Decimal] = []
        last_discount_factor: Decimal | None = None
        last_fcff: Decimal | None = None
        if not forecasts:
            sheet.set(data_start, 1, "No matching forecast periods supplied.", style=12)
            sheet.merge(data_start, 1, data_start, 6)
            data_end = data_start
            checks.append(
                _AuditCheck(
                    f"dcf_forecast_available:{name}",
                    "readiness",
                    "failed",
                    f"No forecast periods are available for {name} scenario.",
                )
            )
        else:
            for index, forecast in enumerate(forecasts, start=1):
                row = data_start + index - 1
                fcff = forecast.get("fcff")
                sheet.set(row, 1, forecast.get("period") or f"Period {index}")
                if fcff is not None:
                    source_row = int(forecast["sheet_row"])
                    sheet.set(
                        row,
                        2,
                        style=5,
                        formula=f"'Financials'!J{source_row}",
                        cached=fcff,
                    )
                    sheet.set(row, 6, f"Financials!J{source_row}", style=18)
                else:
                    sheet.set(row, 2, "N/A", style=12)
                    sheet.set(row, 6, "Financials FCFF unavailable", style=12)
                explicit_exponent = forecast.get("discount_exponent")
                timing_basis = forecast.get("discount_timing_basis") or (
                    "explicit_per_period"
                    if explicit_exponent is not None
                    else f"positional_{convention}"
                )
                sheet.set(row, 7, forecast.get("period_end") or "Not disclosed")
                sheet.set(row, 8, timing_basis)
                sheet.set(row, 9, forecast.get("timing_source_id") or "Not disclosed", style=18)
                if wacc is not None and wacc > Decimal("-1"):
                    denominator, exponent = _discount_denominator(
                        wacc,
                        index,
                        convention,
                        explicit_exponent=explicit_exponent,
                    )
                    discount_factor = Decimal(1) / denominator
                    last_discount_factor = discount_factor
                    sheet.set(row, 3, exponent)
                    sheet.set(
                        row,
                        4,
                        style=8,
                        formula=f"1/(1+$B${input_row})^C{row}",
                        cached=discount_factor,
                    )
                    if fcff is not None:
                        present_value = fcff * discount_factor
                        present_values.append(present_value)
                        sheet.set(
                            row,
                            5,
                            style=6,
                            formula=f"B{row}*D{row}",
                            cached=_quantize(present_value),
                        )
                else:
                    sheet.set(row, 3, "N/A", style=12)
                    sheet.set(row, 4, "N/A — WACC missing", style=12)
                    sheet.set(row, 5, "N/A", style=12)
                if fcff is not None:
                    last_fcff = fcff
            data_end = data_start + len(forecasts) - 1
        summary_start = data_end + 2
        summary_rows: dict[str, int] = {}
        _add_dcf_summary_label(
            sheet, summary_rows, "PV Explicit FCFF", "pv_explicit", summary_start
        )
        pv_explicit = sum(present_values, Decimal(0)) if present_values else None
        if present_values:
            sheet.set(
                summary_start,
                2,
                style=14,
                formula=f"SUM(E{data_start}:E{data_end})",
                cached=_quantize(pv_explicit),
            )
        else:
            sheet.set(summary_start, 2, "N/A", style=12)
        _add_dcf_summary_label(
            sheet, summary_rows, "Terminal FCFF", "terminal_fcff", summary_start + 1
        )
        terminal_fcff: Decimal | None = None
        if last_fcff is not None and growth is not None:
            terminal_fcff = last_fcff * (Decimal(1) + growth)
            sheet.set(
                summary_start + 1,
                2,
                style=6,
                formula=f"B{data_end}*(1+$D${input_row})",
                cached=_quantize(terminal_fcff),
            )
        else:
            sheet.set(summary_start + 1, 2, "N/A", style=12)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Terminal Value — Gordon Growth",
            "terminal_value",
            summary_start + 2,
        )
        terminal_value: Decimal | None = None
        if terminal_fcff is not None and wacc is not None and growth is not None:
            if wacc <= growth:
                sheet.set(summary_start + 2, 2, "N/A — WACC <= terminal growth", style=12)
                checks.append(
                    _AuditCheck(
                        f"wacc_above_terminal_growth:{name}",
                        "calculation",
                        "failed",
                        f"{name} WACC must be strictly greater than terminal growth.",
                        actual=wacc,
                        expected=f"> {growth}",
                    )
                )
            else:
                terminal_value = terminal_fcff / (wacc - growth)
                sheet.set(
                    summary_start + 2,
                    2,
                    style=6,
                    formula=f"B{summary_start + 1}/($B${input_row}-$D${input_row})",
                    cached=_quantize(terminal_value),
                )
                checks.append(
                    _AuditCheck(
                        f"wacc_above_terminal_growth:{name}",
                        "calculation",
                        "passed",
                        f"{name} WACC is strictly greater than terminal growth.",
                        actual=wacc,
                        expected=f"> {growth}",
                    )
                )
        else:
            sheet.set(summary_start + 2, 2, "N/A", style=12)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "PV Terminal Value",
            "pv_terminal",
            summary_start + 3,
        )
        pv_terminal: Decimal | None = None
        if terminal_value is not None and last_discount_factor is not None:
            pv_terminal = terminal_value * last_discount_factor
            sheet.set(
                summary_start + 3,
                2,
                style=6,
                formula=f"B{summary_start + 2}*D{data_end}",
                cached=_quantize(pv_terminal),
            )
        else:
            sheet.set(summary_start + 3, 2, "N/A", style=12)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Enterprise Value — Gordon Growth",
            "enterprise_value",
            summary_start + 4,
        )
        enterprise_value: Decimal | None = None
        if pv_explicit is not None and pv_terminal is not None:
            enterprise_value = pv_explicit + pv_terminal
            sheet.set(
                summary_start + 4,
                2,
                style=14,
                formula=f"B{summary_start}+B{summary_start + 3}",
                cached=_quantize(enterprise_value),
            )
        else:
            sheet.set(summary_start + 4, 2, "N/A", style=12)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Terminal Value Share of EV",
            "terminal_share",
            summary_start + 5,
        )
        terminal_share: Decimal | None = None
        if pv_terminal is not None and enterprise_value not in {None, Decimal(0)}:
            terminal_share = pv_terminal / enterprise_value
            sheet.set(
                summary_start + 5,
                2,
                style=8,
                formula=f"B{summary_start + 3}/B{summary_start + 4}",
                cached=terminal_share,
            )
            if terminal_share > Decimal("0.75"):
                checks.append(
                    _AuditCheck(
                        f"terminal_value_concentration:{name}",
                        "readiness",
                        "warning",
                        f"{name} terminal value contributes more than 75% of enterprise value.",
                        actual=_quantize(terminal_share, "0.0001"),
                        expected="<= 75%",
                    )
                )
        else:
            sheet.set(summary_start + 5, 2, "N/A", style=11)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Terminal Value — Exit Multiple",
            "exit_terminal",
            summary_start + 6,
        )
        exit_terminal: Decimal | None = None
        if (
            terminal_metric is not None
            and exit_multiple is not None
            and terminal_metric > 0
            and exit_multiple > 0
        ):
            exit_terminal = terminal_metric * exit_multiple
            sheet.set(
                summary_start + 6,
                2,
                style=6,
                formula=f"$F${input_row}*$H${input_row}",
                cached=_quantize(exit_terminal),
            )
        else:
            sheet.set(summary_start + 6, 2, "N/A — cross-check inputs unavailable", style=11)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Enterprise Value — Exit Multiple",
            "exit_enterprise",
            summary_start + 7,
        )
        exit_enterprise: Decimal | None = None
        if (
            exit_terminal is not None
            and pv_explicit is not None
            and last_discount_factor is not None
        ):
            exit_enterprise = pv_explicit + exit_terminal * last_discount_factor
            sheet.set(
                summary_start + 7,
                2,
                style=14,
                formula=f"B{summary_start}+B{summary_start + 6}*D{data_end}",
                cached=_quantize(exit_enterprise),
            )
        else:
            sheet.set(summary_start + 7, 2, "N/A", style=11)
        _add_dcf_summary_label(
            sheet,
            summary_rows,
            "Exit vs Gordon Difference",
            "cross_check",
            summary_start + 8,
        )
        if exit_enterprise is not None and enterprise_value not in {None, Decimal(0)}:
            difference = (exit_enterprise - enterprise_value) / abs(enterprise_value)
            sheet.set(
                summary_start + 8,
                2,
                style=8,
                formula=f"(B{summary_start + 7}-B{summary_start + 4})/ABS(B{summary_start + 4})",
                cached=difference,
            )
        else:
            sheet.set(summary_start + 8, 2, "N/A", style=11)
        bridge = scenario["bridge"]
        cash = _bridge_value(bridge, "cash_like", "cash")
        non_operating = _bridge_value(bridge, "non_operating_assets", "non_operating_asset")
        debt = _bridge_value(bridge, "debt_like", "debt")
        other_claims = _bridge_value(bridge, "other_claims")
        shares = _bridge_value(bridge, "fully_diluted_shares", "share_count")
        bridge_start = summary_start + 10
        sheet.section(bridge_start, f"{scenario['display_name']} EV-to-Equity Bridge", 6)
        bridge_rows = {
            "enterprise_value": bridge_start + 1,
            "cash": bridge_start + 2,
            "non_operating": bridge_start + 3,
            "debt": bridge_start + 4,
            "other_claims": bridge_start + 5,
            "equity": bridge_start + 6,
            "shares": bridge_start + 7,
            "per_share": bridge_start + 8,
        }
        bridge_labels = (
            ("enterprise_value", "Enterprise Value"),
            ("cash", "+ Cash-like Items"),
            ("non_operating", "+ Non-operating Assets"),
            ("debt", "- Debt-like Items"),
            ("other_claims", "- Other Claims"),
            ("equity", "Equity Value"),
            ("shares", "Fully Diluted Shares"),
            ("per_share", "Per-share Value"),
        )
        for key, label in bridge_labels:
            sheet.set(bridge_rows[key], 1, label, style=16)
        if enterprise_value is not None:
            sheet.set(
                bridge_rows["enterprise_value"],
                2,
                style=5,
                formula=f"B{summary_rows['enterprise_value']}",
                cached=_quantize(enterprise_value),
            )
        else:
            sheet.set(bridge_rows["enterprise_value"], 2, "N/A", style=12)
        for key, value in (
            ("cash", cash),
            ("non_operating", non_operating),
            ("debt", debt),
            ("other_claims", other_claims),
            ("shares", shares),
        ):
            sheet.set(
                bridge_rows[key],
                2,
                value if value is not None else "N/A",
                style=4 if value is not None else 11,
            )
        equity_value: Decimal | None = None
        per_share: Decimal | None = None
        bridge_complete = all(
            item is not None for item in (enterprise_value, cash, non_operating, debt, other_claims)
        )
        if bridge_complete:
            assert (
                enterprise_value is not None
                and cash is not None
                and non_operating is not None
                and debt is not None
                and other_claims is not None
            )
            equity_value = enterprise_value + cash + non_operating - debt - other_claims
            sheet.set(
                bridge_rows["equity"],
                2,
                style=14,
                formula=(
                    f"B{bridge_rows['enterprise_value']}+B{bridge_rows['cash']}+"
                    f"B{bridge_rows['non_operating']}-B{bridge_rows['debt']}-"
                    f"B{bridge_rows['other_claims']}"
                ),
                cached=_quantize(equity_value),
            )
            checks.append(
                _AuditCheck(
                    f"ev_to_equity_bridge_complete:{name}",
                    "calculation",
                    "passed",
                    f"{name} EV-to-equity bridge has all required components.",
                )
            )
        else:
            sheet.set(bridge_rows["equity"], 2, "N/A — bridge incomplete", style=12)
            checks.append(
                _AuditCheck(
                    f"ev_to_equity_bridge_complete:{name}",
                    "readiness",
                    "failed",
                    f"{name} enterprise value can be shown, but equity value is blocked by an incomplete bridge.",
                )
            )
        if equity_value is not None and shares is not None and shares > 0:
            per_share = equity_value / shares
            sheet.set(
                bridge_rows["per_share"],
                2,
                style=6,
                formula=f"B{bridge_rows['equity']}/B{bridge_rows['shares']}",
                cached=_quantize(per_share),
            )
        else:
            sheet.set(bridge_rows["per_share"], 2, "N/A", style=11)
        scenario_meta[name] = {
            "wacc": wacc,
            "wacc_ref": f"'DCF'!B{input_row}",
            "terminal_growth": growth,
            "terminal_growth_ref": f"'DCF'!D{input_row}",
            "enterprise_value": _quantize(enterprise_value)
            if enterprise_value is not None
            else None,
            "enterprise_value_ref": f"'DCF'!B{summary_rows['enterprise_value']}",
            "equity_value": _quantize(equity_value) if equity_value is not None else None,
            "equity_value_ref": f"'DCF'!B{bridge_rows['equity']}",
            "per_share": _quantize(per_share) if per_share is not None else None,
            "per_share_ref": f"'DCF'!B{bridge_rows['per_share']}",
            "terminal_share": terminal_share,
            "terminal_share_ref": f"'DCF'!B{summary_rows['terminal_share']}",
        }
        current_row = bridge_start + 10
    return sheet, scenario_meta


def _normalize_sensitivities(
    valuation: Mapping[str, Any], calculation: Mapping[str, Any]
) -> list[dict[str, Any]]:
    raw = _section_record("sensitivities", valuation, calculation)
    if raw is None:
        dcf_method = _method_record(calculation, "dcf")
        raw = dcf_method.get("sensitivities") or dcf_method.get("sensitivity")
    if isinstance(raw, Mapping) and not any(
        key in raw for key in ("rows", "records", "items", "column_values")
    ):
        records = []
        for name, value in raw.items():
            if not isinstance(value, Mapping):
                continue
            record = dict(value)
            record.setdefault("name", str(name).replace("_", " ").title())
            records.append(record)
        return records
    return _record_list(raw)


def _build_sensitivities_sheet(records: list[dict[str, Any]]) -> _Worksheet:
    sheet = _Worksheet("Sensitivities")
    sheet.set_widths((22, 18, 18, 18, 18, 18, 18, 24))
    sheet.freeze = (1, 3, "B4")
    sheet.title(1, "Valuation Sensitivities", 8)
    sheet.set(
        2,
        1,
        "Only supplied, model-derived sensitivity outputs are exported; missing grids are not backfilled with invented assumptions.",
        style=11,
    )
    sheet.merge(2, 1, 2, 8)
    if not records:
        sheet.set(4, 1, "No sensitivity grids supplied for this version.", style=11)
        sheet.merge(4, 1, 4, 8)
        return sheet
    current_row = 4
    for index, record in enumerate(records, start=1):
        name = _text(record.get("name"), fallback=f"Sensitivity {index}")
        row_driver = _text(record.get("row_driver"), fallback="Row driver")
        column_driver = _text(record.get("column_driver"), fallback="Column driver")
        columns = record.get("column_values")
        if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray)):
            columns = []
        rows = _record_list(record.get("rows"))
        sheet.section(current_row, name, max(2, len(columns) + 1))
        sheet.set(current_row + 1, 1, f"{row_driver} \\ {column_driver}", style=3)
        for column, value in enumerate(columns, start=2):
            numeric = _decimal(value)
            sheet.set(
                current_row + 1,
                column,
                numeric if numeric is not None else value,
                style=7 if "wacc" in column_driver or "growth" in column_driver else 9,
            )
        for row_offset, row_record in enumerate(rows, start=current_row + 2):
            row_value = _decimal(row_record.get("row_value"))
            sheet.set(
                row_offset,
                1,
                row_value if row_value is not None else row_record.get("row_value"),
                style=7 if "wacc" in row_driver or "growth" in row_driver else 9,
            )
            cells = row_record.get("cells")
            if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes, bytearray)):
                cells = []
            for column, cell in enumerate(cells, start=2):
                if isinstance(cell, Mapping):
                    value = _decimal(
                        cell.get("enterprise_value")
                        if cell.get("enterprise_value") is not None
                        else cell.get("value")
                    )
                    hard_failure = cell.get("hard_failure_code")
                else:
                    value = _decimal(cell)
                    hard_failure = None
                if value is not None:
                    sheet.set(row_offset, column, value, style=6)
                else:
                    sheet.set(
                        row_offset, column, f"N/A — {hard_failure or 'not calculated'}", style=12
                    )
        current_row += max(len(rows) + 4, 6)
    return sheet


def _source_records(
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = _record_list(_section_record("sources", valuation, calculation))
    if not sources:
        by_id: dict[str, dict[str, Any]] = {}
        for item in _record_list(version.get("inputs")):
            source_id = str(item.get("source_id") or "").strip()
            if not source_id:
                continue
            target = by_id.setdefault(source_id, {"source_id": source_id})
            for field_name in ("locator", "as_of", "currency", "unit", "reviewed_by", "status"):
                candidate = item.get(field_name)
                if candidate is None:
                    continue
                if target.get(field_name) is None:
                    target[field_name] = candidate
                elif target[field_name] != candidate:
                    target[field_name] = "mixed"
        sources = list(by_id.values())
    assumptions = _record_list(_section_record("assumptions", valuation, calculation))
    return sources, assumptions


def _build_sources_sheet(
    sources: list[dict[str, Any]], assumptions: list[dict[str, Any]]
) -> _Worksheet:
    sheet = _Worksheet("Sources & Assumptions")
    sheet.set_widths((24, 32, 34, 14, 12, 14, 20, 20, 52, 48))
    sheet.freeze = (2, 4, "C5")
    sheet.title(1, "Sources & Assumptions", 10)
    sheet.set(
        2,
        1,
        "Plain-text source URLs are retained without creating external workbook relationships.",
        style=11,
    )
    sheet.merge(2, 1, 2, 10)
    headers = (
        "Source ID",
        "Title",
        "Locator",
        "As Of",
        "Currency",
        "Unit",
        "Review Status",
        "Reviewed By",
        "URL",
        "Notes",
    )
    for column, header in enumerate(headers, start=1):
        sheet.set(4, column, header, style=3)
    if not sources:
        sheet.set(5, 1, "No source register supplied.", style=12)
        sheet.merge(5, 1, 5, 10)
        last_source_row = 5
    else:
        for row, source in enumerate(sources, start=5):
            values = (
                source.get("source_id") or source.get("id"),
                source.get("title") or source.get("name"),
                source.get("locator"),
                source.get("as_of") or source.get("published"),
                source.get("currency"),
                source.get("unit"),
                source.get("review_status") or source.get("status"),
                _actor_name(source.get("reviewed_by")),
                source.get("url") or source.get("source_url"),
                source.get("notes") or source.get("note"),
            )
            for column, value in enumerate(values, start=1):
                sheet.set(row, column, _text(value), style=18 if column in {1, 9} else 0)
        last_source_row = 4 + len(sources)
        sheet.auto_filter = f"A4:J{last_source_row}"
    assumption_start = last_source_row + 3
    sheet.section(assumption_start, "Explicit Assumptions", 8)
    assumption_headers = (
        "Assumption ID",
        "Name",
        "Value",
        "Unit",
        "Source / Basis",
        "Status",
        "Owner",
        "Notes",
    )
    for column, header in enumerate(assumption_headers, start=1):
        sheet.set(assumption_start + 1, column, header, style=3)
    if not assumptions:
        sheet.set(assumption_start + 2, 1, "No separate assumption ledger supplied.", style=11)
        sheet.merge(assumption_start + 2, 1, assumption_start + 2, 8)
    else:
        for row, assumption in enumerate(assumptions, start=assumption_start + 2):
            values = (
                assumption.get("assumption_id") or assumption.get("id"),
                assumption.get("name"),
                assumption.get("value"),
                assumption.get("unit"),
                assumption.get("source_id") or assumption.get("basis"),
                assumption.get("status"),
                _actor_name(assumption.get("owner") or assumption.get("entered_by")),
                assumption.get("notes") or assumption.get("note"),
            )
            for column, value in enumerate(values, start=1):
                numeric = _decimal(value) if column == 3 else None
                sheet.set(
                    row,
                    column,
                    numeric if numeric is not None else _text(value),
                    style=4 if numeric is not None else 0,
                )
    return sheet


def _normalize_provided_checks(
    valuation: Mapping[str, Any],
    calculation: Mapping[str, Any],
) -> list[_AuditCheck]:
    raw_records = _record_list(valuation.get("checks"))

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if str(key) == "checks":
                    raw_records.extend(_record_list(nested))
                else:
                    collect(nested)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for nested in value:
                collect(nested)

    collect(calculation)
    checks = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(raw_records, start=1):
        check = _AuditCheck(
            _text(
                item.get("check_id") or item.get("id"),
                fallback=f"provided-check-{index}",
            ),
            _text(item.get("scope"), fallback="calculation").casefold(),
            _status(item.get("status"), fallback="warning"),
            _text(item.get("message") or item.get("note")),
            item.get("actual"),
            item.get("expected"),
            item.get("difference"),
            item.get("tolerance"),
        )
        identity = (check.check_id, check.scope, check.status, check.message)
        if identity in seen:
            continue
        seen.add(identity)
        checks.append(check)
    return checks


def _hard_failure_checks(
    version: Mapping[str, Any], calculation: Mapping[str, Any]
) -> list[_AuditCheck]:
    raw = calculation.get("hard_failures")
    if raw is None:
        raw = version.get("hard_failures")
    if raw is None:
        return []
    if isinstance(raw, (str, Mapping)):
        raw = [raw]
    if not isinstance(raw, Sequence):
        return []
    checks = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, Mapping):
            code = _text(item.get("code") or item.get("check_id"), fallback=f"hard-failure-{index}")
            message = _text(item.get("message") or item.get("reason"))
        else:
            code = f"hard-failure-{index}"
            message = _text(item)
        checks.append(_AuditCheck(code, "calculation", "failed", message))
    return checks


def _build_checks_sheet(checks: list[_AuditCheck]) -> tuple[_Worksheet, dict[str, Any]]:
    sheet = _Worksheet("Checks")
    sheet.set_widths((34, 16, 14, 30, 30, 18, 16, 70))
    sheet.freeze = (3, 5, "D6")
    sheet.title(1, "Calculation Integrity and Decision Readiness Checks", 8)
    sheet.set(
        2,
        1,
        "Calculation integrity and decision readiness remain separate; a clean formula scan does not prove source readiness.",
        style=11,
    )
    sheet.merge(2, 1, 2, 8)
    failed_count = sum(check.status == "failed" for check in checks)
    warning_count = sum(check.status == "warning" for check in checks)
    sheet.set(3, 1, "Failed Checks", style=16)
    sheet.set(
        3, 2, style=17, formula=f'COUNTIF(C6:C{5 + len(checks)},"failed")', cached=failed_count
    )
    sheet.set(3, 3, "Warnings", style=16)
    sheet.set(
        3, 4, style=17, formula=f'COUNTIF(C6:C{5 + len(checks)},"warning")', cached=warning_count
    )
    model_status = "FAILED CHECKS PRESENT" if failed_count else "NO FAILED CHECKS"
    sheet.set(3, 5, "Checks Summary", style=16)
    sheet.set(
        3,
        6,
        style=12 if failed_count else 13,
        formula='IF(B3>0,"FAILED CHECKS PRESENT","NO FAILED CHECKS")',
        cached=model_status,
    )
    headers = (
        "Check ID",
        "Scope",
        "Status",
        "Actual",
        "Expected",
        "Difference",
        "Tolerance",
        "Message / Fix Hint",
    )
    for column, header in enumerate(headers, start=1):
        sheet.set(5, column, header, style=3)
    for row, check in enumerate(checks, start=6):
        style = 12 if check.status == "failed" else 11 if check.status == "warning" else 13
        values = (
            check.check_id,
            check.scope,
            check.status,
            check.actual,
            check.expected,
            check.difference,
            check.tolerance,
            check.message,
        )
        for column, value in enumerate(values, start=1):
            numeric = _decimal(value) if column in {4, 6, 7} else None
            cell_style = (
                style
                if column in {3, 8}
                else 21
                if column in {4, 5, 6, 7} and numeric is None
                else 0
            )
            sheet.set(
                row,
                column,
                numeric if numeric is not None else _text(value, fallback=""),
                style=cell_style,
            )
        if any(len(_text(value, fallback="")) > 40 for value in values[3:7]):
            sheet.row_heights[row] = 30
    if checks:
        sheet.auto_filter = f"A5:H{5 + len(checks)}"
    return sheet, {
        "failed_count": failed_count,
        "warning_count": warning_count,
        "summary": model_status,
    }


def _build_versions_sheet(
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
    *,
    version_hash: str,
    recomputed_hash: str,
    payload_hash: str,
) -> _Worksheet:
    sheet = _Worksheet("Versions")
    sheet.set_widths((30, 70, 22, 22, 22, 56))
    sheet.title(1, "Valuation Version and Hash Ledger", 6)
    sheet.set(
        2,
        1,
        "The stored version hash identifies the immutable valuation snapshot; recomputed hash verifies the record body.",
        style=11,
    )
    sheet.merge(2, 1, 2, 6)
    sheet.set(4, 1, "Field", style=3)
    sheet.set(4, 2, "Value", style=3)
    current_rows = (
        (5, "Version Hash", version_hash),
        (6, "Recomputed Version Hash", recomputed_hash),
        (8, "Export Payload Hash", payload_hash),
        (9, "Version ID", version.get("version_id")),
        (10, "Version Number", version.get("version_number")),
        (11, "Version Status", version.get("status")),
        (12, "Operation", version.get("operation")),
        (13, "Created At", version.get("created_at")),
        (14, "Created By", _actor_name(version.get("created_by"))),
        (15, "Reason", version.get("reason")),
        (16, "Workbook Schema", EXPORT_SCHEMA_VERSION),
    )
    for row, label, value in current_rows:
        sheet.set(row, 1, label, style=16)
        sheet.set(row, 2, _text(value), style=18 if "Hash" in label else 0)
    hashes_match = version_hash.removeprefix("sha256:") == recomputed_hash.removeprefix("sha256:")
    sheet.set(7, 1, "Hash Match", style=16)
    sheet.set(7, 2, style=13 if hashes_match else 12, formula="B5=B6", cached=hashes_match)
    history_start = 19
    sheet.section(history_start, "Version History", 6)
    headers = ("Version", "Version ID", "Status", "Operation", "Created At", "Version Hash")
    for column, header in enumerate(headers, start=1):
        sheet.set(history_start + 1, column, header, style=3)
    history = _record_list(valuation.get("versions"))
    if not history:
        history = [dict(version)]
    for row, item in enumerate(history, start=history_start + 2):
        values = (
            item.get("version_number"),
            item.get("version_id"),
            item.get("status"),
            item.get("operation"),
            item.get("created_at"),
            item.get("version_hash"),
        )
        for column, value in enumerate(values, start=1):
            sheet.set(
                row,
                column,
                value if isinstance(value, int) else _text(value),
                style=18 if column == 6 else 0,
            )
    sheet.auto_filter = f"A20:F{20 + len(history)}"
    return sheet


def _status_style(status: str) -> int:
    normalized = status.casefold()
    if any(token in normalized for token in ("fail", "not_ready", "blocked", "incomplete")):
        return 12
    if any(token in normalized for token in ("pass", "approved", "reviewed")):
        return 13
    return 11


def _build_dashboard_sheet(
    deal: Mapping[str, Any],
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
    *,
    version_hash: str,
    calculation_integrity: str,
    decision_readiness: str,
    scenario_meta: Mapping[str, Mapping[str, Any]],
    comps_meta: Mapping[str, Any],
    checks_meta: Mapping[str, Any],
    checks: Sequence[_AuditCheck],
) -> _Worksheet:
    header = deal.get("deal_header") if isinstance(deal.get("deal_header"), Mapping) else deal
    sheet = _Worksheet("Dashboard")
    sheet.set_widths((28, 32, 5, 28, 24, 5, 28, 42, 18))
    sheet.freeze = (0, 1, "A2")
    target = _text(header.get("target") or valuation.get("target_legal_entity"))
    sheet.title(1, f"{target} — Valuation Dashboard", 9)
    metadata = (
        (2, "Target", target),
        (3, "Buyer", header.get("buyer")),
        (4, "Deal ID", deal.get("deal_id")),
        (5, "Valuation ID", valuation.get("valuation_id")),
        (6, "Version", version.get("version_number") or version.get("version_id")),
        (
            7,
            "Valuation Date",
            _date_value(header.get("valuation_date") or valuation.get("valuation_date")),
        ),
    )
    for row, label, value in metadata:
        sheet.set(row, 1, label, style=16)
        sheet.set(row, 2, value, style=15 if isinstance(value, date) else 0)
    sheet.set(8, 1, "Version Hash", style=16)
    sheet.set(8, 2, style=18, formula="'Versions'!B5", cached=version_hash)
    currency = _text(header.get("currency") or valuation.get("base_currency"))
    unit = _text(valuation.get("unit"), fallback="record-defined")
    sheet.set(9, 1, "Currency / Unit", style=16)
    sheet.set(9, 2, f"{currency} / {unit}")
    sheet.section(11, "Status — Calculation and Decision Readiness Are Independent", 9)
    status_rows = (
        (12, "Calculation Integrity", calculation_integrity),
        (13, "Decision Readiness", decision_readiness),
        (14, "Version Status", _status(version.get("status"), fallback="not_supplied")),
    )
    for row, label, value in status_rows:
        sheet.set(row, 1, label, style=16)
        sheet.set(row, 2, value, style=_status_style(value))
    sheet.set(15, 1, "Checks Summary", style=16)
    sheet.set(
        15,
        2,
        style=12 if checks_meta["failed_count"] else 13,
        formula="'Checks'!F3",
        cached=checks_meta["summary"],
    )
    sheet.set(15, 4, "Failed / Warning", style=16)
    sheet.set(15, 5, f"{checks_meta['failed_count']} / {checks_meta['warning_count']}")
    sheet.section(17, "Key Valuation Outputs — No Method Blending", 9)
    base = scenario_meta.get("base") or next(iter(scenario_meta.values()), {})
    output_rows = (
        (18, "Base Enterprise Value", "enterprise_value", 6),
        (19, "Base Equity Value", "equity_value", 6),
        (20, "Base Per-share Value", "per_share", 6),
        (21, "WACC", "wacc", 8),
        (22, "Terminal Growth", "terminal_growth", 8),
        (23, "Terminal Value Share", "terminal_share", 8),
    )
    for row, label, key, style in output_rows:
        sheet.set(row, 1, label, style=16)
        value = base.get(key)
        reference = base.get(f"{key}_ref")
        if value is not None and reference:
            sheet.set(row, 2, style=style, formula=str(reference), cached=value)
        else:
            sheet.set(row, 2, "N/A", style=11)
    sheet.set(18, 4, "Selected External Peers", style=16)
    if comps_meta.get("sample_count"):
        sheet.set(
            18,
            5,
            style=17,
            formula=str(comps_meta["sample_count_ref"]),
            cached=comps_meta["sample_count"],
        )
        for row, label, key, reference_key in (
            (19, "Comps Median", "median", "median_ref"),
            (20, "Comps P25", "p25", "p25_ref"),
            (21, "Comps P75", "p75", "p75_ref"),
        ):
            sheet.set(row, 4, label, style=16)
            sheet.set(
                row, 5, style=20, formula=str(comps_meta[reference_key]), cached=comps_meta[key]
            )
    else:
        sheet.set(18, 5, "N/A", style=11)
    sheet.set(23, 4, "Standalone / Synergy", style=16)
    sheet.set(23, 5, "Standalone only; synergy is not included", style=13)
    sheet.section(25, "Top Open Checks and Diligence Items", 9)
    open_checks = [check for check in checks if check.status in {"failed", "warning"}]
    if not open_checks:
        sheet.set(26, 1, "No failed or warning checks in the supplied export record.", style=13)
        sheet.merge(26, 1, 26, 9)
        next_row = 28
    else:
        for row, check in enumerate(open_checks[:6], start=26):
            sheet.set(row, 1, check.status.upper(), style=12 if check.status == "failed" else 11)
            sheet.set(row, 2, check.check_id, style=16)
            sheet.set(row, 4, check.message)
            sheet.merge(row, 4, row, 9)
        next_row = 27 + min(len(open_checks), 6)
    sheet.section(next_row, "Model Map", 9)
    model_map = (
        ("Financials", "Source inputs and formula-driven FCFF"),
        ("Trading Comps", "Peer classification, N/A / N/M, selected statistics"),
        ("Precedents", PRECEDENTS_P0_STATUS),
        ("DCF", "Scenario DCF, terminal cross-check, EV-to-equity bridge"),
        ("Sensitivities", "Supplied two-dimensional scenario grids"),
        ("Sources & Assumptions", "Input provenance and explicit assumptions"),
        ("Checks", "Mechanical integrity and readiness gaps"),
        ("Versions", "Immutable version chain and hashes"),
    )
    for row, (tab, purpose) in enumerate(model_map, start=next_row + 1):
        sheet.set(row, 1, tab, style=16)
        sheet.set(row, 2, purpose)
        sheet.merge(row, 2, row, 6)
    boundary_row = next_row + len(model_map) + 2
    sheet.section(boundary_row, "Use Boundary", 9)
    sheet.set(
        boundary_row + 1,
        1,
        "Screening and internal review support only. This workbook is not a formal valuation opinion or fairness opinion, does not approve a transaction, and applies no secret weighting.",
        style=11,
    )
    sheet.merge(boundary_row + 1, 1, boundary_row + 1, 9)
    sheet.row_heights[boundary_row + 1] = 32
    return sheet


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="4">
    <numFmt numFmtId="164" formatCode="#,##0.00;[Red](#,##0.00);-"/>
    <numFmt numFmtId="165" formatCode="0.0%;[Red](0.0%);-"/>
    <numFmt numFmtId="166" formatCode="0.0x;[Red](0.0x);-"/>
    <numFmt numFmtId="167" formatCode="yyyy-mm-dd"/>
  </numFmts>
  <fonts count="7">
    <font><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="16"/><name val="Aptos Display"/><family val="2"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/><family val="2"/></font>
    <font><color rgb="FF0000FF"/><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><color rgb="FF008000"/><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><color rgb="FFC00000"/><sz val="10"/><name val="Aptos"/><family val="2"/></font>
  </fonts>
  <fills count="7">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE2F0D9"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF4CCCC"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="3">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FF7F8C8D"/></bottom><diagonal/></border>
    <border><left/><right/><top style="medium"><color rgb="FF17365D"/></top><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="22">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment horizontal="left" vertical="center"/></xf>
    <xf numFmtId="0" fontId="5" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="164" fontId="3" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="164" fontId="4" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="165" fontId="3" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="166" fontId="3" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="0" xfId="0" applyFill="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="6" fillId="6" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="5" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="center"/></xf>
    <xf numFmtId="164" fontId="5" fillId="0" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment horizontal="right"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="165" fontId="4" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="166" fontId="4" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"><alignment horizontal="right"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment wrapText="1" vertical="top"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _workbook_xml() -> str:
    sheets = "".join(
        f'<sheet name={quoteattr(name)} sheetId="{index}" state="visible" r:id="rId{index}"/>'
        for index, name in enumerate(REQUIRED_SHEETS, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        '<fileVersion appName="xl" lastEdited="7" lowestEdited="7"/>'
        '<workbookPr defaultThemeVersion="164011"/>'
        '<bookViews><workbookView activeTab="0" firstSheet="0" visibility="visible"/></bookViews>'
        f"<sheets>{sheets}</sheets>"
        "<definedNames>"
        "<definedName name=\"VersionHash\">'Versions'!$B$5</definedName>"
        "<definedName name=\"CalculationIntegrity\">'Dashboard'!$B$12</definedName>"
        "<definedName name=\"DecisionReadiness\">'Dashboard'!$B$13</definedName>"
        "</definedNames>"
        '<calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    relationships = []
    for index in range(1, len(REQUIRED_SHEETS) + 1):
        relationships.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    relationships.append(
        f'<Relationship Id="rId{len(REQUIRED_SHEETS) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PACKAGE_REL_NS}">{"".join(relationships)}</Relationships>'
    )


def _content_types_xml() -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(REQUIRED_SHEETS) + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{_CONTENT_TYPES_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{overrides}"
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _package_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _created_timestamp(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "1980-01-01T00:00:00Z"
    if len(normalized) == 10:
        normalized += "T00:00:00Z"
    if normalized.endswith("+00:00"):
        normalized = normalized[:-6] + "Z"
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return "1980-01-01T00:00:00Z"
    return normalized


def _core_properties_xml(
    deal: Mapping[str, Any], valuation: Mapping[str, Any], version: Mapping[str, Any]
) -> str:
    header = deal.get("deal_header") if isinstance(deal.get("deal_header"), Mapping) else deal
    target = _text(header.get("target") or valuation.get("target_legal_entity"))
    creator = _actor_name(version.get("created_by"))
    created = _created_timestamp(version.get("created_at"))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<cp:coreProperties xmlns:cp="{_CORE_NS}" xmlns:dc="{_DC_NS}" '
        f'xmlns:dcterms="{_DCTERMS_NS}" xmlns:xsi="{_XSI_NS}">'
        f"<dc:title>{escape(target)} — CleanTech Finance Valuation Workbook</dc:title>"
        f"<dc:subject>P0 auditable valuation export {escape(_text(version.get('version_id')))}</dc:subject>"
        f"<dc:creator>{escape(creator)}</dc:creator>"
        "<cp:keywords>valuation, DCF, trading comps, audit</cp:keywords>"
        "<dc:description>Screening and internal-review support; not a formal valuation or fairness opinion.</dc:description>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{escape(created)}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{escape(created)}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _app_properties_xml() -> str:
    titles = "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name in REQUIRED_SHEETS)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Properties xmlns="{_EXT_PROPS_NS}" xmlns:vt="{_VT_NS}">'
        "<Application>CleanTech Finance</Application><AppVersion>0.5.0</AppVersion>"
        f'<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(REQUIRED_SHEETS)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="{len(REQUIRED_SHEETS)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
        "</Properties>"
    )


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    info.create_system = 3
    return info


def _package_bytes(parts: Mapping[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in parts.items():
            archive.writestr(_zip_info(name), content.encode("utf-8"))
    return buffer.getvalue()


def validate_valuation_workbook(
    source: str | Path | bytes | bytearray | memoryview,
) -> ValuationWorkbookValidation:
    """Validate workbook structure, formulas, and prohibited OOXML relationships."""

    package: Path | io.BytesIO
    if isinstance(source, (bytes, bytearray, memoryview)):
        package = io.BytesIO(bytes(source))
    else:
        package = Path(source)
    issues: list[str] = []
    sheet_names: tuple[str, ...] = ()
    formula_count = 0
    try:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            lowered = [name.casefold() for name in names]
            for forbidden in _FORBIDDEN_PACKAGE_PARTS:
                normalized_forbidden = forbidden.casefold()
                if any(
                    name == normalized_forbidden or name.startswith(normalized_forbidden)
                    for name in lowered
                ):
                    issues.append(f"Forbidden OOXML part present: {forbidden}")
            required_parts = {
                "[Content_Types].xml",
                "_rels/.rels",
                "xl/workbook.xml",
                "xl/_rels/workbook.xml.rels",
                "xl/styles.xml",
            }
            missing_parts = sorted(required_parts - set(names))
            if missing_parts:
                issues.append(f"Missing OOXML parts: {', '.join(missing_parts)}")
            for name in names:
                if name.endswith((".xml", ".rels")):
                    try:
                        root = ElementTree.fromstring(archive.read(name))
                    except ElementTree.ParseError as exc:
                        issues.append(f"Malformed XML part {name}: {exc}")
                        continue
                    if name.endswith(".rels"):
                        for relationship in root:
                            if relationship.attrib.get("TargetMode") == "External":
                                issues.append(f"External relationship present in {name}")
            if "xl/workbook.xml" in names:
                workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
                sheets_node = workbook.find(f"{{{_MAIN_NS}}}sheets")
                sheets = list(sheets_node) if sheets_node is not None else []
                sheet_names = tuple(item.attrib.get("name", "") for item in sheets)
                if sheet_names != REQUIRED_SHEETS:
                    issues.append("Worksheet order mismatch: " + ", ".join(sheet_names))
                for sheet in sheets:
                    if sheet.attrib.get("state", "visible") != "visible":
                        issues.append(f"Hidden worksheet present: {sheet.attrib.get('name')}")
            for index in range(1, len(REQUIRED_SHEETS) + 1):
                name = f"xl/worksheets/sheet{index}.xml"
                if name not in names:
                    issues.append(f"Missing worksheet part: {name}")
                    continue
                worksheet = ElementTree.fromstring(archive.read(name))
                formulas = worksheet.findall(f".//{{{_MAIN_NS}}}f")
                formula_count += len(formulas)
                for formula in formulas:
                    text = formula.text or ""
                    if "#REF!" in text or "[" in text or "]" in text:
                        issues.append(f"Unsafe or broken formula in {name}: {text}")
                for row in worksheet.findall(f".//{{{_MAIN_NS}}}row"):
                    if row.attrib.get("hidden") in {"1", "true"}:
                        issues.append(f"Hidden row present in {name}")
                for column in worksheet.findall(f".//{{{_MAIN_NS}}}col"):
                    if column.attrib.get("hidden") in {"1", "true"}:
                        issues.append(f"Hidden column present in {name}")
            if formula_count == 0:
                issues.append("Workbook contains no verifiable formulas")
            precedents_name = "xl/worksheets/sheet4.xml"
            if precedents_name in names and PRECEDENTS_P0_STATUS.encode(
                "utf-8"
            ) not in archive.read(precedents_name):
                issues.append("Precedents sheet does not disclose its P0 status")
            versions_name = "xl/worksheets/sheet9.xml"
            if versions_name in names:
                versions_text = archive.read(versions_name).decode("utf-8")
                if not re.search(r"[a-fA-F0-9]{64}", versions_text):
                    issues.append("Versions sheet does not contain a SHA-256 version hash")
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        issues.append(f"Invalid XLSX package: {exc}")
    return ValuationWorkbookValidation(
        valid=not issues,
        sheet_names=sheet_names,
        formula_count=formula_count,
        issues=tuple(issues),
    )


def _build_valuation_workbook(
    *,
    deal: Mapping[str, Any] | None,
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
) -> bytes:
    """Export a deterministic nine-sheet P0 valuation workbook.

    ``deal`` may use the DealStore ``deal_header`` shape. ``valuation`` may
    contain its full immutable ``versions`` chain. ``version`` is the selected
    valuation snapshot and may be failed, incomplete, reviewed, or approved.
    """

    deal_record = _as_mapping(deal or {}, label="deal")
    valuation_record = _as_mapping(valuation, label="valuation")
    version_record = _as_mapping(version, label="version")
    calculation = _calculation_record(valuation_record, version_record)
    recomputed_hash = _recomputed_version_hash(version_record)
    declared_hash = str(version_record.get("version_hash") or "").strip().casefold()
    version_hash = declared_hash if _SHA256_RE.fullmatch(declared_hash) else recomputed_hash
    payload_hash = _digest(
        {"deal": deal_record, "valuation": valuation_record, "version": version_record}
    )
    checks = _normalize_provided_checks(valuation_record, calculation)
    checks.extend(_hard_failure_checks(version_record, calculation))
    declared_matches = not declared_hash or declared_hash.removeprefix("sha256:") == recomputed_hash
    checks.append(
        _AuditCheck(
            "valuation_version_hash_matches_record",
            "calculation",
            "passed" if declared_matches else "failed",
            "Stored valuation version hash matches the immutable version record."
            if declared_matches
            else "Stored valuation version hash does not match the immutable version record.",
            actual=declared_hash or recomputed_hash,
            expected=recomputed_hash,
        )
    )
    header = (
        deal_record.get("deal_header")
        if isinstance(deal_record.get("deal_header"), Mapping)
        else deal_record
    )
    required_metadata = {
        "deal_id": deal_record.get("deal_id"),
        "target": header.get("target") or valuation_record.get("target_legal_entity"),
        "transaction_scope": header.get("transaction_scope")
        or valuation_record.get("transaction_scope"),
        "currency": header.get("currency") or valuation_record.get("base_currency"),
        "valuation_date": header.get("valuation_date") or valuation_record.get("valuation_date"),
    }
    missing_metadata = sorted(
        key for key, value in required_metadata.items() if not str(value or "").strip()
    )
    checks.append(
        _AuditCheck(
            "required_deal_metadata_present",
            "readiness",
            "failed" if missing_metadata else "passed",
            "Required deal and valuation metadata are present."
            if not missing_metadata
            else f"Missing required metadata: {', '.join(missing_metadata)}",
            actual=", ".join(missing_metadata) if missing_metadata else "complete",
            expected="deal_id, target, transaction_scope, currency, valuation_date",
        )
    )
    checks.append(
        _AuditCheck(
            "precedent_transactions_p0_boundary",
            "readiness",
            "warning",
            PRECEDENTS_P0_STATUS,
        )
    )
    financial_rows = _normalize_financials(valuation_record, version_record, calculation)
    currency = _text(header.get("currency") or valuation_record.get("base_currency"))
    unit = _text(valuation_record.get("unit"), fallback="record-defined")
    financials_sheet, financial_rows = _build_financials_sheet(
        financial_rows,
        currency=currency,
        unit=unit,
        checks=checks,
    )
    comps_records = _normalize_trading_comps(
        valuation_record,
        calculation,
        version_record,
    )
    trading_comps_sheet, comps_meta = _build_trading_comps_sheet(comps_records, checks)
    scenarios, _ = _normalize_dcf_scenarios(
        valuation_record,
        version_record,
        calculation,
        financial_rows,
    )
    dcf_sheet, scenario_meta = _build_dcf_sheet(scenarios, financial_rows, checks)
    sensitivity_sheet = _build_sensitivities_sheet(
        _normalize_sensitivities(valuation_record, calculation)
    )
    sources, assumptions = _source_records(valuation_record, version_record, calculation)
    sources_sheet = _build_sources_sheet(sources, assumptions)
    calculation_integrity = _status(
        calculation.get("calculation_integrity") or valuation_record.get("calculation_integrity"),
        fallback="not_calculated" if not calculation else "not_assessable",
    )
    decision_readiness = _status(
        calculation.get("decision_readiness") or valuation_record.get("decision_readiness"),
        fallback="not_ready" if not calculation else "screen_grade",
    )
    if any(check.scope == "calculation" and check.status == "failed" for check in checks):
        calculation_integrity = "failed"
    if any(check.status == "failed" for check in checks):
        decision_readiness = "not_ready"
    checks.append(
        _AuditCheck(
            "calculation_integrity_status_disclosed",
            "calculation",
            "passed" if calculation_integrity != "not_assessable" else "warning",
            f"Calculation integrity is disclosed as {calculation_integrity}.",
        )
    )
    checks.append(
        _AuditCheck(
            "decision_readiness_status_disclosed",
            "readiness",
            "passed" if decision_readiness not in {"not_assessable", "not_supplied"} else "warning",
            f"Decision readiness is disclosed as {decision_readiness}.",
        )
    )
    checks_sheet, checks_meta = _build_checks_sheet(checks)
    versions_sheet = _build_versions_sheet(
        valuation_record,
        version_record,
        version_hash=version_hash,
        recomputed_hash=recomputed_hash,
        payload_hash=payload_hash,
    )
    dashboard_sheet = _build_dashboard_sheet(
        deal_record,
        valuation_record,
        version_record,
        version_hash=version_hash,
        calculation_integrity=calculation_integrity,
        decision_readiness=decision_readiness,
        scenario_meta=scenario_meta,
        comps_meta=comps_meta,
        checks_meta=checks_meta,
        checks=checks,
    )
    worksheets = (
        dashboard_sheet,
        financials_sheet,
        trading_comps_sheet,
        _build_precedents_sheet(),
        dcf_sheet,
        sensitivity_sheet,
        sources_sheet,
        checks_sheet,
        versions_sheet,
    )
    parts: dict[str, str] = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _package_rels_xml(),
        "docProps/core.xml": _core_properties_xml(deal_record, valuation_record, version_record),
        "docProps/app.xml": _app_properties_xml(),
        "xl/workbook.xml": _workbook_xml(),
        "xl/_rels/workbook.xml.rels": _workbook_rels_xml(),
        "xl/styles.xml": _styles_xml(),
    }
    for index, worksheet in enumerate(worksheets, start=1):
        parts[f"xl/worksheets/sheet{index}.xml"] = worksheet.to_xml()
    payload = _package_bytes(parts)
    validation = validate_valuation_workbook(payload)
    if not validation.valid:
        raise ValuationExportError(
            "Generated workbook failed OOXML validation: " + "; ".join(validation.issues)
        )
    return payload


def export_valuation_workbook(
    *,
    deal: Mapping[str, Any] | None = None,
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
) -> bytes:
    """Return a deterministic, dependency-free P0 valuation XLSX package.

    The keyword-only byte-oriented interface lets CLI, API, and Agent callers
    choose their own persistence boundary. ``deal`` may be omitted when a
    failed or partial valuation version must still be exported for audit.
    """

    return _build_valuation_workbook(
        deal=deal,
        valuation=valuation,
        version=version,
    )


def export_valuation_xlsx(
    *,
    deal: Mapping[str, Any] | None = None,
    valuation: Mapping[str, Any],
    version: Mapping[str, Any],
) -> bytes:
    """Alias with an explicit XLSX-oriented name for service/API integration."""

    return export_valuation_workbook(
        deal=deal,
        valuation=valuation,
        version=version,
    )


__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "PRECEDENTS_P0_STATUS",
    "REQUIRED_SHEETS",
    "ValuationExportError",
    "ValuationWorkbookValidation",
    "export_valuation_workbook",
    "export_valuation_xlsx",
    "validate_valuation_workbook",
]
