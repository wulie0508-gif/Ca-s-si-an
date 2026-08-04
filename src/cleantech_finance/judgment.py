"""Build validated five-cell evidence cards for the two proven dimensions.

The deterministic core does not perform web research or expose hidden reasoning.
An agent supplies concise, cited stage outputs in ``judgment_context``; this
module validates them, locks the maintainer-authored framework text, attaches
audited facts and calculations, and emits a machine-readable card.
"""

from __future__ import annotations

import re
from typing import Any

from .fact_semantics import (
    cash_operations_scope,
    margin_operations_scope,
    select_net_income_fact,
)
from .models import Source
from .rules import dimension_applicability, evaluate_rule

JUDGMENT_LAYER_VERSION = "0.3.0"
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


def _citation(raw: dict[str, Any], sources: dict[str, Source], errors: list[str]) -> dict[str, Any]:
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
        result = {
            "id": name,
            "name": label,
            "period": period["period"],
            "value": item["value"],
            "display_value": _money(item["value"], currency),
            "label": "fact",
            "citations": [_fact_citation(item, sources)],
        }
        if "selection" in item:
            result["selection"] = item["selection"]
        if "statement_scope" in item:
            result["statement_scope"] = item["statement_scope"]
        return result

    if dimension_id == "profitability-unit-economics":

        def margin_inputs(
            period: dict[str, Any],
        ) -> tuple[float, dict[str, Any], dict[str, Any], str, str, str]:
            revenue = fact(period, "revenue")
            gross_profit = period["facts"].get("gross_profit")
            if gross_profit is not None:
                return (
                    gross_profit["value"] / revenue["value"],
                    revenue,
                    gross_profit,
                    "gross_profit",
                    "Gross profit / (loss)",
                    "gross profit / revenue",
                )
            operating_cost = fact(period, "operating_cost")
            return (
                (revenue["value"] - operating_cost["value"]) / revenue["value"],
                revenue,
                operating_cost,
                "operating_cost",
                "Operating cost / cost of revenues",
                "(revenue - operating cost) / revenue",
            )

        (
            latest_margin,
            latest_revenue,
            latest_margin_component,
            latest_component_id,
            latest_component_label,
            latest_formula,
        ) = margin_inputs(latest)
        (
            prior_margin,
            prior_revenue,
            prior_margin_component,
            _prior_component_id,
            _prior_component_label,
            _prior_formula,
        ) = margin_inputs(prior)
        latest_operations = margin_operations_scope(latest)
        prior_operations = margin_operations_scope(prior)
        if latest_operations != prior_operations:
            raise ValueError("Profitability card mixes different operations scopes")
        latest_income_id, _, _ = select_net_income_fact(latest, latest_operations)
        prior_income_id, _, _ = select_net_income_fact(prior, prior_operations)
        if latest_income_id != prior_income_id:
            raise ValueError("Profitability card mixes different net-income fact ids")
        income_label = (
            "Net income from continuing operations"
            if latest_operations == "continuing_operations"
            else "Net income"
        )
        return [
            observed("revenue", "Revenue", latest),
            observed(latest_component_id, latest_component_label, latest),
            observed(latest_income_id, income_label, latest),
            {
                "id": "gross-margin",
                "name": "Gross margin",
                "period": latest["period"],
                "value": round(latest_margin, 4),
                "display_value": f"{latest_margin * 100:.1f}%",
                "label": "calculation",
                "formula": latest_formula,
                "citations": [
                    _fact_citation(latest_revenue, sources),
                    _fact_citation(latest_margin_component, sources),
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
                    _fact_citation(latest_margin_component, sources),
                    _fact_citation(prior_revenue, sources),
                    _fact_citation(prior_margin_component, sources),
                ],
            },
        ]

    latest_operations = cash_operations_scope(latest)
    prior_operations = cash_operations_scope(prior)
    if latest_operations != prior_operations:
        raise ValueError("Cash card mixes different operations scopes")
    latest_income_id, latest_income, _ = select_net_income_fact(latest, latest_operations)
    prior_income_id, prior_income, _ = select_net_income_fact(prior, prior_operations)
    if latest_income_id != prior_income_id:
        raise ValueError("Cash card mixes different net-income fact ids")
    latest_ocf = fact(latest, "operating_cash_flow")
    prior_ocf = fact(prior, "operating_cash_flow")
    latest_capex = fact(latest, "capex")
    prior_capex = fact(prior, "capex")
    if latest_capex["value"] == 0 or prior_capex["value"] == 0:
        raise ValueError("Cash judgment requires non-zero capex in both observed periods")
    latest_coverage = latest_ocf["value"] / abs(latest_capex["value"])
    prior_coverage = prior_ocf["value"] / abs(prior_capex["value"])
    sustained_loss = latest_income["value"] < 0 and prior_income["value"] < 0
    return [
        observed("operating_cash_flow", "Net operating cash flow", latest),
        observed("capex", "Capital expenditure cash outflow", latest),
        observed("cash_and_equivalents", "Period-end cash and equivalents", latest),
        observed(latest_income_id, "Net income", latest),
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


def _unique_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("source_id")), str(item.get("locator")))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def build_judgment_layer(
    manifest: dict[str, Any],
    financials: dict[str, Any] | None,
    sources: list[Source],
    selected_dimensions: set[str],
    *,
    applicability_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = manifest.get("judgment_context")
    if not context:
        return {
            "version": JUDGMENT_LAYER_VERSION,
            "status": "not_provided",
            "cards": [],
            "dimension_outcomes": [],
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
            "dimension_outcomes": [],
            "structured_stage_trace": [],
            "framework_coverage": {"locked": 0, "implemented": 0, "ratio": 0},
            "validation": {"passed": False, "errors": ["Judgment cards require financial facts"]},
        }

    errors: list[str] = []
    if context.get("contract_version") != JUDGMENT_LAYER_VERSION:
        errors.append(f"judgment_context.contract_version must be '{JUDGMENT_LAYER_VERSION}'")
    source_lookup = _source_map(sources)
    subindustry = context.get("subindustry") or {}
    subindustry_basis = _citations(subindustry.get("basis"), source_lookup, errors)
    for key in (
        "scope_id",
        "name",
        "name_zh",
        "value_chain_position",
        "value_chain_position_zh",
        "summary",
        "summary_zh",
    ):
        if not subindustry.get(key):
            errors.append(f"judgment_context.subindustry is missing '{key}'")
    if not subindustry_basis:
        errors.append("Subindustry classification requires at least one citation")
    if any(item.get("role") != "subject" for item in subindustry_basis):
        errors.append("Subindustry classification may cite subject sources only")

    cards: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    dimension_context = context.get("dimensions") or {}
    enabled = [item for item in SUPPORTED_CARD_DIMENSIONS if item in selected_dimensions]
    for dimension_id in enabled:
        applicability = dimension_applicability(
            dimension_id,
            str(subindustry.get("scope_id") or ""),
            applicability_context,
        )
        if applicability["status"] in {"not_applicable", "not_yet_applicable"}:
            applicability_basis = _citations(
                applicability.get("basis"), source_lookup, errors
            )
            outcome_basis = _unique_citations(
                subindustry_basis + applicability_basis
            )
            outcome = {
                "dimension_id": dimension_id,
                "status": applicability["status"],
                "signal": None,
                "scope_id": subindustry.get("scope_id"),
                "reason": applicability["reason"],
                "reason_zh": applicability["reason_zh"],
                "basis": outcome_basis,
            }
            for key in (
                "reason_code",
                "policy_id",
                "policy_version",
                "policy_digest",
                "inputs_digest",
                "inputs",
            ):
                if key in applicability:
                    outcome[key] = applicability[key]
            outcomes.append(outcome)
            traces.append(
                {
                    "dimension_id": dimension_id,
                    "stage": "applicability_gate",
                    "actor": "deterministic_rule_engine",
                    "output": applicability["reason"],
                    "citation_count": len(outcome_basis),
                    "sources": outcome_basis,
                    "status": applicability["status"],
                    **(
                        {
                            "reason_code": applicability["reason_code"],
                            "policy_id": applicability["policy_id"],
                            "policy_version": applicability["policy_version"],
                            "policy_digest": applicability["policy_digest"],
                            "inputs_digest": applicability["inputs_digest"],
                        }
                        if applicability["status"] == "not_yet_applicable"
                        else {}
                    ),
                }
            )
            continue
        raw = dimension_context.get(dimension_id)
        if not raw:
            errors.append(f"Missing judgment context for '{dimension_id}'")
            continue
        if "framework" in raw:
            errors.append(f"'{dimension_id}' attempts to override the locked framework")
        external_assertions = {
            "application",
            "signal",
            "rule_id",
            "rule_version",
            "condition",
            "path",
            "summary",
            "rationale",
        }.intersection(raw)
        if external_assertions:
            errors.append(
                f"'{dimension_id}' cannot provide deterministic application fields: "
                + ", ".join(sorted(external_assertions))
            )
        framework = FRAMEWORKS[dimension_id]
        if _contains_absolute_threshold(framework):
            errors.append(f"Locked framework '{dimension_id}' contains an absolute threshold")
        if _contains_absolute_threshold(raw):
            errors.append(f"'{dimension_id}' judgment context contains an absolute threshold")

        benchmark = raw.get("benchmark") or {}
        observations: list[dict[str, Any]] = []
        for item in benchmark.get("observations") or []:
            citation = _citation(item.get("citation") or {}, source_lookup, errors)
            comparison_type = item.get("comparison_type")
            if comparison_type not in {
                "subject_history",
                "comparable_peer",
                "adjacent_context",
            }:
                errors.append(f"'{dimension_id}' benchmark observation requires comparison_type")
            if comparison_type == "subject_history" and citation.get("role") != "subject":
                errors.append(f"'{dimension_id}' subject_history must cite a subject source")
            if (
                comparison_type in {"comparable_peer", "adjacent_context"}
                and citation.get("role") != "benchmark"
            ):
                errors.append(f"'{dimension_id}' external comparison must cite a benchmark source")
            observations.append({**item, "citation": citation})
        if not benchmark.get("scope") or not observations:
            errors.append(f"'{dimension_id}' requires a scoped benchmark with observations")
        if not benchmark.get("scope_zh"):
            errors.append(f"'{dimension_id}' benchmark requires Chinese scope in 'scope_zh'")
        if observations and not any(
            item.get("comparison_type") == "subject_history" for item in observations
        ):
            errors.append(f"'{dimension_id}' benchmark must include subject_history first")
        if not benchmark.get("limitations"):
            errors.append(f"'{dimension_id}' benchmark requires an explicit limitation")
        if not benchmark.get("limitations_zh"):
            errors.append(
                f"'{dimension_id}' benchmark requires Chinese limitations in 'limitations_zh'"
            )

        gaps = raw.get("gaps") or []
        gap_kinds = {item.get("kind") for item in gaps}
        if not gaps or not GAP_KINDS.issubset(gap_kinds):
            errors.append(
                f"'{dimension_id}' needs evidence_gap, human_judgment, and verification items"
            )
        if any(not item.get("text_zh") for item in gaps):
            errors.append(f"'{dimension_id}' gap items require Chinese text in 'text_zh'")

        try:
            facts = _financial_fact_items(dimension_id, financials, source_lookup)
            application = evaluate_rule(
                dimension_id,
                str(subindustry.get("scope_id") or ""),
                financials,
                applicability_context,
            )
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            missing = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            errors.append(
                f"'{dimension_id}' financial facts or rule inputs are incomplete: {missing}"
            )
            continue
        signal = application["signal"]
        basis_fact_ids = set(application["basis_fact_ids"])
        application_basis = _unique_citations(
            [
                citation
                for fact in facts
                if fact["id"] in basis_fact_ids
                for citation in fact["citations"]
            ]
        )
        benchmark_sources = _unique_citations(
            [item["citation"] for item in observations if item.get("citation")]
        )
        reviewed_sources = _unique_citations(
            subindustry_basis + benchmark_sources + application_basis
        )
        rule_provenance = {
            key: application[key]
            for key in (
                "rule_id",
                "rule_version",
                "rule_status",
                "rule_library_version",
                "rule_digest",
                "inputs_digest",
                "subindustry_scope",
                "deterministic",
                "inputs",
                "condition",
                "rationale",
                "rationale_zh",
                "basis",
                "basis_zh",
            )
        }
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
                        "scope_id": subindustry.get("scope_id"),
                        "name": subindustry.get("name"),
                        "name_zh": subindustry.get("name_zh"),
                        "value_chain_position": subindustry.get("value_chain_position"),
                        "value_chain_position_zh": subindustry.get("value_chain_position_zh"),
                        "summary": subindustry.get("summary"),
                        "summary_zh": subindustry.get("summary_zh"),
                        "basis": subindustry_basis,
                    },
                    "2_extracted_facts": {"label": "facts_and_calculations", "items": facts},
                    "3_judgment_framework": framework,
                    "4_framework_application": {
                        "label": "deterministic_rule_output",
                        "signal": signal,
                        "path": application["path"],
                        "path_zh": application["path_zh"],
                        "summary": application["summary"],
                        "summary_zh": application["summary_zh"],
                        "basis": application_basis,
                        "rule_provenance": rule_provenance,
                        "benchmark": {
                            "scope": benchmark.get("scope"),
                            "scope_zh": benchmark.get("scope_zh"),
                            "observations": observations,
                            "limitations": benchmark.get("limitations"),
                            "limitations_zh": benchmark.get("limitations_zh"),
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
                "disclaimer_zh": ("本卡不包含投资评级。所有信号均为证据信号，不构成投资建议。"),
            }
        )
        outcomes.append(
            {
                "dimension_id": dimension_id,
                "status": "evaluated",
                "signal": signal,
                "scope_id": subindustry.get("scope_id"),
                "reason": None,
                "reason_zh": None,
                "rule_id": application["rule_id"],
            }
        )
        traces.extend(
            [
                {
                    "dimension_id": dimension_id,
                    "stage": "subindustry_identification",
                    "actor": "semantic_agent",
                    "output": subindustry.get("summary"),
                    "citation_count": len(subindustry_basis),
                    "sources": subindustry_basis,
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "benchmark_retrieval",
                    "actor": "semantic_agent",
                    "output": benchmark.get("scope"),
                    "citation_count": len(observations),
                    "sources": benchmark_sources,
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "deterministic_signal",
                    "actor": "deterministic_rule_engine",
                    "output": application["summary"],
                    "citation_count": len(application_basis),
                    "sources": application_basis,
                    "rule_id": application["rule_id"],
                    "rule_version": application["rule_version"],
                    "rule_digest": application["rule_digest"],
                    "inputs_digest": application["inputs_digest"],
                },
                {
                    "dimension_id": dimension_id,
                    "stage": "gap_exposure",
                    "actor": "semantic_agent",
                    "output": f"{len(gaps)} review items",
                    "citation_count": len(reviewed_sources),
                    "sources": reviewed_sources,
                },
            ]
        )

    locked = sum(card["cells"]["3_judgment_framework"]["locked"] is True for card in cards)
    implemented = len(cards)
    not_applicable = sum(
        item["status"] in {"not_applicable", "not_yet_applicable"}
        for item in outcomes
    )
    return {
        "version": JUDGMENT_LAYER_VERSION,
        "status": "generated" if (cards or outcomes) and not errors else "invalid",
        "prepared_by": context.get("prepared_by", "agent-assisted"),
        "prepared_at": context.get("prepared_at"),
        "trace_policy": "Structured stage outputs only; hidden chain-of-thought is not stored.",
        "cards": cards,
        "dimension_outcomes": outcomes,
        "structured_stage_trace": traces,
        "framework_coverage": {
            "locked": locked,
            "implemented": implemented,
            "not_applicable": not_applicable,
            "requested": len(enabled),
            "ratio": round(locked / implemented, 4) if implemented else 0,
        },
        "validation": {"passed": not errors, "errors": errors},
    }
