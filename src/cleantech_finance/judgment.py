"""Build validated five-cell evidence cards for the two proven dimensions.

The deterministic core does not perform web research or expose hidden reasoning.
An agent supplies concise, cited stage outputs in ``judgment_context``; this
module validates them, locks the maintainer-authored framework text, attaches
audited facts and calculations, and emits a machine-readable card.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Source

JUDGMENT_LAYER_VERSION = "0.2.1"
SUPPORTED_CARD_DIMENSIONS = (
    "profitability-unit-economics",
    "cash-runway",
)

FRAMEWORKS: dict[str, dict[str, Any]] = {
    "profitability-unit-economics": {
        "name": "Profitability & Unit Economics",
        "name_zh": "盈利与单位经济性",
        "locked": True,
        "methodology": "CleanTech Finance judgment framework (locked)",
        "methodology_zh": "CleanTech Finance 判断框架（锁定）",
        "basis": "Subindustry-relative comparison; no cross-model absolute thresholds.",
        "basis_zh": "采用子行业相对比较；不使用跨商业模式的绝对阈值。",
        "text": (
            "Do not compare gross margin across unlike clean-energy business models. "
            "First classify the company as manufacturing, power electronics/equipment, "
            "installation/service, or asset ownership/operation; then compare consistent "
            "gross-margin definitions with the same company over time and with genuinely "
            "comparable peers. Treat product mix, warranty, freight, incentives, and "
            "accounting scope as explanations to verify, not automatic proof of durable "
            "profitability."
        ),
        "text_zh": (
            "毛利率不跨清洁能源商业模式直接比较。先识别公司属于制造、功率电子/设备、"
            "安装/服务，还是资产持有/运营，再以一致口径与公司自身历史及真正同类公司比较。"
            "产品组合、质保、物流、激励政策和会计口径只能作为待核验解释，不能自动证明盈利具有持续性。"
        ),
    },
    "cash-runway": {
        "name": "Cash Flow & Funding Gap",
        "name_zh": "现金流与资金缺口",
        "locked": True,
        "methodology": "CleanTech Finance judgment framework (locked)",
        "methodology_zh": "CleanTech Finance 判断框架（锁定）",
        "basis": "Profit-state branch selection with subindustry-relative funding review.",
        "basis_zh": "先按盈亏状态选择分析路径，再结合子行业进行相对资金审查。",
        "text": (
            "For loss-making companies, examine cash runway; for profitable companies, "
            "examine whether operating cash flow covers capital expenditure. Clean-energy "
            "businesses face long financing cycles and material scale-up commitments, so "
            "historical positive cash flow alone does not prove funding sufficiency."
        ),
        "text_zh": (
            "亏损公司看现金跑道；盈利公司改看经营现金流能否覆盖资本开支。"
            "清洁能源资本开支重、融资节点长，因此历史正现金流本身不能证明未来资金充足。"
        ),
    },
}

SIGNALS = {"red", "amber", "green"}
GAP_KINDS = {"evidence_gap", "human_judgment", "verification"}
ABSOLUTE_THRESHOLD = re.compile(
    r"(?:[<>]=?\s*\d|\b(?:less|more)\s+than\s+\d|"
    r"\b(?:under|over|below|above|at\s+least|at\s+most)\s+\d|"
    r"\bthreshold\s*[:=]\s*\d)",
    re.IGNORECASE,
)


def _source_map(sources: list[Source]) -> dict[str, Source]:
    return {source.id: source for source in sources}


def _citation(
    raw: dict[str, Any], sources: dict[str, Source], errors: list[str]
) -> dict[str, Any]:
    source_id = raw.get("source_id")
    locator = raw.get("locator")
    source = sources.get(source_id)
    if not source:
        errors.append(f"Judgment card cites unknown source '{source_id}'")
        return {"source_id": source_id, "locator": locator or "", "url": "", "title": ""}
    if not locator:
        errors.append(f"Judgment card citation to '{source_id}' is missing a locator")
    return {
        "source_id": source.id,
        "locator": locator or "",
        "url": source.url,
        "title": source.title,
        "role": source.role,
    }


def _citations(
    raw_items: list[dict[str, Any]] | None,
    sources: dict[str, Source],
    errors: list[str],
) -> list[dict[str, Any]]:
    return [_citation(item, sources, errors) for item in (raw_items or [])]


def _money(value: float, currency: str) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{currency} {value / 1_000_000_000:,.3f}bn"
    if magnitude >= 1_000_000:
        return f"{currency} {value / 1_000_000:,.3f}m"
    return f"{currency} {value:,.2f}"


def _fact_citation(fact: dict[str, Any], sources: dict[str, Source]) -> dict[str, Any]:
    source = sources[fact["source_id"]]
    return {
        "source_id": source.id,
        "locator": fact["locator"],
        "url": source.url,
        "title": source.title,
        "role": source.role,
    }


def _periods(financials: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    periods = sorted(financials["periods"], key=lambda item: item["end_date"])
    if len(periods) < 2:
        raise ValueError("Judgment cards require two financial periods")
    return periods[-1], periods[-2]


def _financial_fact_items(
    dimension_id: str,
    financials: dict[str, Any],
    sources: dict[str, Source],
) -> list[dict[str, Any]]:
    latest, prior = _periods(financials)
    currency = financials.get("currency", "USD")

    def fact(period: dict[str, Any], name: str) -> dict[str, Any]:
        return period["facts"][name]

    def observed(name: str, label: str, period: dict[str, Any]) -> dict[str, Any]:
        item = fact(period, name)
        return {
            "id": name,
            "name": label,
            "period": period["period"],
            "value": item["value"],
            "display_value": _money(item["value"], currency),
            "label": "fact",
            "citations": [_fact_citation(item, sources)],
        }

    latest_revenue = fact(latest, "revenue")
    prior_revenue = fact(prior, "revenue")
    latest_cost = fact(latest, "operating_cost")
    prior_cost = fact(prior, "operating_cost")
    latest_margin = (latest_revenue["value"] - latest_cost["value"]) / latest_revenue["value"]
    prior_margin = (prior_revenue["value"] - prior_cost["value"]) / prior_revenue["value"]

    if dimension_id == "profitability-unit-economics":
        return [
            observed("revenue", "Revenue", latest),
            observed("operating_cost", "Operating cost / cost of revenues", latest),
            observed("net_income", "Net income", latest),
            {
                "id": "gross-margin",
                "name": "Gross margin",
                "period": latest["period"],
                "value": round(latest_margin, 4),
                "display_value": f"{latest_margin * 100:.1f}%",
                "label": "calculation",
                "formula": "(revenue - operating cost) / revenue",
                "citations": [
                    _fact_citation(latest_revenue, sources),
                    _fact_citation(latest_cost, sources),
                ],
            },
            {
                "id": "gross-margin-change",
                "name": "Gross-margin change",
                "period": f"{prior['period']} to {latest['period']}",
                "value": round(latest_margin - prior_margin, 4),
                "display_value": f"{(latest_margin - prior_margin) * 100:+.1f} pp",
                "label": "calculation",
                "formula": "latest gross margin - prior gross margin",
                "citations": [
                    _fact_citation(latest_revenue, sources),
                    _fact_citation(latest_cost, sources),
                    _fact_citation(prior_revenue, sources),
                    _fact_citation(prior_cost, sources),
                ],
            },
        ]

    latest_income = fact(latest, "net_income")
    prior_income = fact(prior, "net_income")
    latest_ocf = fact(latest, "operating_cash_flow")
    prior_ocf = fact(prior, "operating_cash_flow")
    latest_capex = fact(latest, "capex")
    prior_capex = fact(prior, "capex")
    latest_coverage = latest_ocf["value"] / abs(latest_capex["value"])
    prior_coverage = prior_ocf["value"] / abs(prior_capex["value"])
    sustained_loss = latest_income["value"] < 0 and prior_income["value"] < 0
    return [
        observed("operating_cash_flow", "Net operating cash flow", latest),
        observed("capex", "Capital expenditure cash outflow", latest),
        observed("cash_and_equivalents", "Period-end cash and equivalents", latest),
        observed("net_income", "Net income", latest),
        {
            "id": "sustained-loss",
            "name": "Loss in both observed years",
            "period": f"{prior['period']} and {latest['period']}",
            "value": sustained_loss,
            "display_value": "Yes" if sustained_loss else "No",
            "label": "calculation",
            "formula": "latest net income < 0 and prior net income < 0",
            "citations": [
                _fact_citation(latest_income, sources),
                _fact_citation(prior_income, sources),
            ],
        },
        {
            "id": "operating-cash-flow-to-capex",
            "name": "Operating cash flow / capex",
            "period": latest["period"],
            "value": round(latest_coverage, 4),
            "display_value": f"{latest_coverage:.2f}x (prior {prior_coverage:.2f}x)",
            "label": "calculation",
            "formula": "operating cash flow / abs(capex)",
            "citations": [
                _fact_citation(latest_ocf, sources),
                _fact_citation(latest_capex, sources),
                _fact_citation(prior_ocf, sources),
                _fact_citation(prior_capex, sources),
            ],
        },
    ]


def _contains_absolute_threshold(value: Any) -> bool:
    if isinstance(value, str):
        return bool(ABSOLUTE_THRESHOLD.search(value))
    if isinstance(value, dict):
        return any(_contains_absolute_threshold(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_threshold(item) for item in value)
    return False


def build_judgment_layer(
    manifest: dict[str, Any],
    financials: dict[str, Any] | None,
    sources: list[Source],
    selected_dimensions: set[str],
) -> dict[str, Any]:
    context = manifest.get("judgment_context")
    if not context:
        return {
            "version": JUDGMENT_LAYER_VERSION,
            "status": "not_provided",
            "cards": [],
            "structured_stage_trace": [],
            "framework_coverage": {"locked": 0, "implemented": 0, "ratio": 0},
            "validation": {"passed": True, "errors": []},
            "note": "Run the Agent Skill research stages and add judgment_context to generate cards.",
        }
    if not financials:
        return {
            "version": JUDGMENT_LAYER_VERSION,
            "status": "invalid",
            "cards": [],
            "structured_stage_trace": [],
            "framework_coverage": {"locked": 0, "implemented": 0, "ratio": 0},
            "validation": {"passed": False, "errors": ["Judgment cards require financial facts"]},
        }

    errors: list[str] = []
    source_lookup = _source_map(sources)
    subindustry = context.get("subindustry") or {}
    subindustry_basis = _citations(subindustry.get("basis"), source_lookup, errors)
    for key in ("name", "value_chain_position", "summary"):
        if not subindustry.get(key):
            errors.append(f"judgment_context.subindustry is missing '{key}'")
    if not subindustry_basis:
        errors.append("Subindustry classification requires at least one citation")

    cards: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    dimension_context = context.get("dimensions") or {}
    enabled = [item for item in SUPPORTED_CARD_DIMENSIONS if item in selected_dimensions]
    for dimension_id in enabled:
        raw = dimension_context.get(dimension_id)
        if not raw:
            errors.append(f"Missing judgment context for '{dimension_id}'")
            continue
        if "framework" in raw:
            errors.append(f"'{dimension_id}' attempts to override the locked framework")
        framework = FRAMEWORKS[dimension_id]
        if _contains_absolute_threshold(framework):
            errors.append(f"Locked framework '{dimension_id}' contains an absolute threshold")
        if _contains_absolute_threshold(raw):
            errors.append(f"'{dimension_id}' judgment context contains an absolute threshold")

        benchmark = raw.get("benchmark") or {}
        observations: list[dict[str, Any]] = []
        for item in benchmark.get("observations") or []:
            citation = _citation(item.get("citation") or {}, source_lookup, errors)
            observations.append({**item, "citation": citation})
        if not benchmark.get("scope") or not observations:
            errors.append(f"'{dimension_id}' requires a scoped benchmark with observations")
        if not benchmark.get("limitations"):
            errors.append(f"'{dimension_id}' benchmark requires an explicit limitation")

        application = raw.get("application") or {}
        signal = application.get("signal")
        if signal not in SIGNALS:
            errors.append(f"'{dimension_id}' signal must be red, amber, or green")
        application_basis = _citations(application.get("basis"), source_lookup, errors)
        if not application.get("path") or not application.get("summary") or not application_basis:
            errors.append(f"'{dimension_id}' application requires path, summary, and cited basis")

        gaps = raw.get("gaps") or []
        gap_kinds = {item.get("kind") for item in gaps}
        if not gaps or not GAP_KINDS.issubset(gap_kinds):
            errors.append(
                f"'{dimension_id}' needs evidence_gap, human_judgment, and verification items"
            )
        if any(not item.get("text_zh") for item in gaps):
            errors.append(f"'{dimension_id}' gap items require Chinese text in 'text_zh'")

        facts = _financial_fact_items(dimension_id, financials, source_lookup)
        cards.append(
            {
                "dimension_id": dimension_id,
                "dimension": framework["name"],
                "dimension_zh": framework["name_zh"],
                "company": manifest["subject"]["organization"],
                "signal": signal,
                "signal_meaning": "evidence signal; not an investment, credit, or risk rating",
                "signal_meaning_zh": "证据信号；不构成投资、信用或综合风险评级",
                "cells": {
                    "1_subindustry_position": {
                        "label": "agent_structured_output",
                        "name": subindustry.get("name"),
                        "value_chain_position": subindustry.get("value_chain_position"),
                        "summary": subindustry.get("summary"),
                        "basis": subindustry_basis,
                    },
                    "2_extracted_facts": {"label": "facts_and_calculations", "items": facts},
                    "3_judgment_framework": framework,
                    "4_framework_application": {
                        "label": "inference",
                        "signal": signal,
                        "path": application.get("path"),
                        "summary": application.get("summary"),
                        "basis": application_basis,
                        "benchmark": {
                            "scope": benchmark.get("scope"),
                            "observations": observations,
                            "limitations": benchmark.get("limitations"),
                        },
                    },
                    "5_gaps_and_human_judgment": {
                        "label": "needs_human_verification",
                        "items": gaps,
                    },
                },
                "disclaimer": (
                    "This card contains no investment rating. Every signal is an evidence "
                    "signal, not investment advice."
                ),
                "disclaimer_zh": (
                    "本卡不包含投资评级。所有信号均为证据信号，不构成投资建议。"
                ),
            }
        )
        traces.extend(
            [
                {
                    "dimension_id": dimension_id,
                    "stage": "subindustry_identification",
                    "actor": "agent_structured_output",
                    "output": subindustry.get("summary"),
                    "citation_count": len(subindustry_basis),
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "benchmark_retrieval",
                    "actor": "agent_structured_output",
                    "output": benchmark.get("scope"),
                    "citation_count": len(observations),
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "relative_positioning_and_trend",
                    "actor": "agent_structured_output",
                    "output": application.get("summary"),
                    "citation_count": len(application_basis),
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "gap_exposure",
                    "actor": "agent_structured_output",
                    "output": f"{len(gaps)} review items",
                    "citation_count": 0,
                },
            ]
        )

    locked = sum(card["cells"]["3_judgment_framework"]["locked"] is True for card in cards)
    implemented = len(enabled)
    return {
        "version": JUDGMENT_LAYER_VERSION,
        "status": "generated" if cards and not errors else "invalid",
        "prepared_by": context.get("prepared_by", "agent-assisted"),
        "prepared_at": context.get("prepared_at"),
        "trace_policy": "Structured stage outputs only; hidden chain-of-thought is not stored.",
        "cards": cards,
        "structured_stage_trace": traces,
        "framework_coverage": {
            "locked": locked,
            "implemented": implemented,
            "ratio": round(locked / implemented, 4) if implemented else 0,
        },
        "validation": {"passed": not errors, "errors": errors},
    }
