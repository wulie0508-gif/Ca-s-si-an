"""Conservative extraction of common audited annual-report facts.

The extractor intentionally supports a small set of statement labels. It emits
facts only when a consolidated-statement anchor, two reporting years, and two
numeric values can be linked to the same source window. Statement-level units
are normalized to whole currency units and accounting parentheses are retained
as negative values, except for the capex cash-outflow fact which is normalized
to a positive magnitude.
"""

from __future__ import annotations

import re
from typing import Any

from .ingest import ManifestError
from .models import Chunk, Source

ACCOUNTING_NUMBER = (
    r"(?:\(\s*[$€£¥]?\s*\d[\d,]*(?:\.\d+)?\s*\)"
    r"|[-−–—]?\s*[$€£¥]?\s*\d[\d,]*(?:\.\d+)?)"
)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _number(value: str) -> float:
    cleaned = value.strip().replace(",", "")
    for symbol in "$€£¥":
        cleaned = cleaned.replace(symbol, "")
    for minus in "−–—":
        cleaned = cleaned.replace(minus, "-")
    cleaned = re.sub(r"\s+", "", cleaned)
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def _unit_scale(chunks: list[Chunk]) -> tuple[float, str]:
    text = " ".join(_flat(chunk.text) for chunk in chunks).lower()
    if re.search(r"\bin\s+millions?\b", text):
        return 1_000_000.0, "millions"
    if re.search(r"\bin\s+thousands?\b", text):
        return 1_000.0, "thousands"
    return 1.0, "whole currency units"


def _window_after_anchor(
    chunks: list[Chunk], source_id: str, anchors: tuple[str, ...], size: int
) -> tuple[list[Chunk], tuple[int, int]]:
    source_chunks = [chunk for chunk in chunks if chunk.source_id == source_id]
    normalized_anchors = tuple(anchor.lower() for anchor in anchors)
    matches: list[tuple[float, int, list[Chunk]]] = []
    for index, chunk in enumerate(source_chunks):
        text = _flat(chunk.text).lower()
        compact = re.sub(r"\s+", "", text)
        if any(
            anchor in text or re.sub(r"\s+", "", anchor) in compact for anchor in normalized_anchors
        ):
            selected = source_chunks[index : index + size]
            window_text = " ".join(_flat(item.text).lower() for item in selected)
            numeric_tokens = len(re.findall(r"\d[\d,]*(?:\.\d+)?", window_text))
            statement_cues = sum(
                cue in window_text
                for cue in (
                    "revenue",
                    "cost of revenue",
                    "operating activities",
                    "cash and cash equivalents",
                    "net income",
                )
            )
            # Annual-report tables of contents often repeat statement titles.
            # Actual statements contain many numeric cells, several field cues,
            # and normally place the formal statement title near the page start.
            anchor_positions = [text.find(anchor) for anchor in normalized_anchors]
            anchor_positions = [position for position in anchor_positions if position >= 0]
            header_bonus = 150 if anchor_positions and min(anchor_positions) < 180 else 0
            notes_bonus = (
                25 if "see notes to consolidated financial statements" in window_text else 0
            )
            score = min(numeric_tokens, 100) + statement_cues * 25 + header_bonus + notes_bonus
            matches.append((score, index, selected))
    if matches:
        _, index, selected = max(matches, key=lambda item: (item[0], -item[1]))
        return selected, (index, index + len(selected))
    raise ManifestError(f"Could not find statement anchor: {anchors[0]}")


def _years(chunks: list[Chunk], configured_years: list[int]) -> tuple[int, int]:
    text = " ".join(_flat(chunk.text) for chunk in chunks[:2])
    match = re.search(r"Item\s*(20\d{2})\s+(20\d{2})", text, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    if len(configured_years) == 2:
        return max(configured_years), min(configured_years)
    raise ManifestError("Could not determine the two financial statement years")


def _extract_pair(
    chunks: list[Chunk],
    label: str,
    pattern: str,
    years: tuple[int, int],
    unit_scale: float,
    unit_label: str,
    *,
    positive_magnitude: bool = False,
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    regex = re.compile(
        pattern + rf"\s+({ACCOUNTING_NUMBER})\s+({ACCOUNTING_NUMBER})",
        re.IGNORECASE,
    )
    for chunk in chunks:
        text = _flat(chunk.text)
        match = regex.search(text)
        if match:
            values = tuple(_number(match.group(index)) * unit_scale for index in (1, 2))
            if positive_magnitude:
                values = tuple(abs(value) for value in values)
            facts = {
                years[0]: {
                    "value": values[0],
                    "source_id": chunk.source_id,
                    "locator": chunk.locator,
                },
                years[1]: {
                    "value": values[1],
                    "source_id": chunk.source_id,
                    "locator": chunk.locator,
                },
            }
            log = {
                "fact": label,
                "source_id": chunk.source_id,
                "locator": chunk.locator,
                "matched_text": match.group(0),
                "statement_unit": unit_label,
                "unit_scale": unit_scale,
                "normalization": "positive cash-outflow magnitude"
                if positive_magnitude
                else "signed value",
                "status": "extracted",
            }
            return facts, log
    raise ManifestError(
        f"Could not extract audited fact '{label}' from the anchored statement window"
    )


def extract_financial_facts(
    chunks: list[Chunk], sources: list[Source], config: dict[str, Any]
) -> dict[str, Any]:
    source_id = config.get("source_id")
    source_ids = {source.id for source in sources}
    if source_id not in source_ids:
        raise ManifestError("financial_extraction.source_id must reference a manifest source")
    configured_years = config.get("years", [])
    if not (
        isinstance(configured_years, list)
        and len(configured_years) == 2
        and all(isinstance(year, int) for year in configured_years)
    ):
        raise ManifestError("financial_extraction.years must contain exactly two integer years")

    income_chunks, _ = _window_after_anchor(
        chunks,
        source_id,
        (
            "consolidated income statement",
            "consolidated statement of profit",
            "consolidated statements of operations",
            "consolidated statement of operations",
        ),
        size=3,
    )
    cash_chunks, _ = _window_after_anchor(
        chunks,
        source_id,
        (
            "consolidated statement of cash flows",
            "consolidated statements of cash flows",
            "consolidated cash flow statement",
        ),
        size=6,
    )
    income_years = _years(income_chunks, configured_years)
    cash_years = _years(cash_chunks, configured_years)
    if income_years != cash_years:
        raise ManifestError("Income statement and cash flow statement year headers do not agree")

    income_scale, income_unit = _unit_scale(income_chunks)
    cash_scale, cash_unit = _unit_scale(cash_chunks)

    specifications = (
        (
            "revenue",
            income_chunks,
            r"(?:I\.\s*)?(?:Net\s*revenues?|Revenue)",
            income_scale,
            income_unit,
            False,
        ),
        (
            "operating_cost",
            income_chunks,
            r"(?:Including:\s*)?(?:Operating\s*costs?|Cost\s*of\s*revenues?)",
            income_scale,
            income_unit,
            False,
        ),
        (
            "net_income",
            income_chunks,
            r"(?:V\.\s*)?(?:Net\s*profit(?:/\(loss\))?\s*for\s*the\s*year|Net\s*income)",
            income_scale,
            income_unit,
            False,
        ),
        (
            "operating_cash_flow",
            cash_chunks,
            r"Net\s*cash\s*(?:flows?\s*from|provided\s*by|used\s*in)\s*operating\s*activities",
            cash_scale,
            cash_unit,
            False,
        ),
        (
            "capex",
            cash_chunks,
            r"(?:Cash\s*payments?\s*to\s*acquire\s*fixed,?\s*intangible\s*and\s*other\s*long-term\s*assets|Purchases\s*of\s*property\s*and\s*equipment)",
            cash_scale,
            cash_unit,
            True,
        ),
        (
            "cash_and_equivalents",
            cash_chunks,
            r"(?:VI\.\s*Cash\s*and\s*cash\s*equivalents\s*at\s*the\s*end\s*of\s*the\s*period|balance\s*sheets?:\s*Cash\s*and\s*cash\s*equivalents)",
            cash_scale,
            cash_unit,
            False,
        ),
    )
    facts_by_year: dict[int, dict[str, Any]] = {year: {} for year in income_years}
    extraction_log: list[dict[str, Any]] = []
    for fact_name, window, pattern, unit_scale, unit_label, positive_magnitude in specifications:
        extracted, log = _extract_pair(
            window,
            fact_name,
            pattern,
            income_years,
            unit_scale,
            unit_label,
            positive_magnitude=positive_magnitude,
        )
        extraction_log.append(log)
        for year, fact in extracted.items():
            facts_by_year[year][fact_name] = fact

    periods = [
        {
            "period": f"FY{year}",
            "end_date": f"{year}-12-31",
            "facts": facts_by_year[year],
        }
        for year in sorted(facts_by_year)
    ]
    return {
        "mode": "anchored_regex_v0.2",
        "status": "extracted",
        "source_id": source_id,
        "years": list(income_years),
        "extraction_log": extraction_log,
        "financials": {"currency": config.get("currency", "USD"), "periods": periods},
        "limitations": [
            "Only common English consolidated-statement labels are supported in v0.2.",
            "Statement-level thousands/millions units and accounting parentheses are normalized deterministically.",
            "Every extracted fact requires human comparison with the cited page before use.",
        ],
    }
