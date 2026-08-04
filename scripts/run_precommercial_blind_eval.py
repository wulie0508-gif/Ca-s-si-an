"""Reproducible synthetic black-box checks for pre-commercial applicability.

The harness calls the public ``run_audit`` API only.  It does not import rule
definitions and it never authors an expected red/amber/green result.  Every
generated company, filing, citation, and financial value is explicitly synthetic.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cleantech_finance.audit import run_audit

SYNTHETIC_NOTICE = (
    "SYNTHETIC BLIND EVALUATION INPUT; no company, security, filing, transaction, "
    "person, or cited fact is real."
)
VALIDATED_DIMENSIONS = {
    "profitability-unit-economics",
    "cash-runway",
}
PRECOMMERCIAL_SCOPE = "pre-commercial-solid-state-lithium-metal-battery-development"
SUBJECT_SOURCE_ID = "synthetic-subject"
BENCHMARK_SOURCE_ID = "synthetic-benchmark"
MISSING_PROFITABILITY_FACTS = {
    "revenue",
    "operating_cost",
    "cost_of_goods_sold",
    "cogs",
    "gross_profit",
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fact(
    value: int,
    locator: str,
    *,
    statement_scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value": value,
        "source_id": SUBJECT_SOURCE_ID,
        "locator": locator,
        "accounting_scope": "consolidated",
    }
    if statement_scope is not None:
        result["statement_scope"] = statement_scope
    return result


def _period(
    year: int,
    *,
    net_income: int,
    operating_cash_flow: int,
    capex: int,
    cash: int,
) -> dict[str, Any]:
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return {
        "period": f"FY{year}",
        "fiscal_year": year,
        "period_type": "annual",
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "duration_days": 366 if leap else 365,
        "facts": {
            "net_income": _fact(
                net_income,
                f"SYNTHETIC operations statement, FY{year}",
                statement_scope={
                    "operations": "total_operations",
                    "attribution": "consolidated",
                },
            ),
            "operating_cash_flow": _fact(
                operating_cash_flow,
                f"SYNTHETIC cash-flow statement, FY{year} operating cash flow",
                statement_scope={
                    "operations": "total_operations",
                    "attribution": "not_applicable",
                },
            ),
            "capex": _fact(
                capex,
                f"SYNTHETIC cash-flow statement, FY{year} capex magnitude",
            ),
            "cash_and_equivalents": _fact(
                cash,
                f"SYNTHETIC balance sheet, FY{year} cash only",
            ),
        },
    }


def _cik_for(seed: int, variant: int = 0) -> str:
    value = (seed * 97_409 + variant * 1_000_003) % 9_000_000_000
    return f"{value + 1_000_000_000:010d}"


def _base_manifest(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    organization = f"SYNTHETIC Precommercial Entity {seed}"
    ticker = f"S{seed % 100_000:05d}"
    cik = _cik_for(seed)
    entity_id = f"sec-cik-{cik}"

    prior_ocf = -rng.randint(80_000_000, 420_000_000)
    latest_ocf = -rng.randint(60_000_000, 450_000_000)
    prior_capex = rng.randint(8_000_000, 110_000_000)
    latest_capex = rng.randint(8_000_000, 110_000_000)
    prior_cash = rng.randint(90_000_000, 900_000_000)
    latest_cash = rng.randint(90_000_000, 900_000_000)
    periods = [
        _period(
            2024,
            net_income=-rng.randint(100_000_000, 650_000_000),
            operating_cash_flow=prior_ocf,
            capex=prior_capex,
            cash=prior_cash,
        ),
        _period(
            2025,
            net_income=-rng.randint(100_000_000, 650_000_000),
            operating_cash_flow=latest_ocf,
            capex=latest_capex,
            cash=latest_cash,
        ),
    ]
    if rng.choice((False, True)):
        periods.reverse()

    return {
        "synthetic": True,
        "synthetic_notice": SYNTHETIC_NOTICE,
        "subject": {
            "organization": organization,
            "technology": (
                "SYNTHETIC pre-commercial solid-state lithium-metal battery development"
            ),
            "ticker": ticker,
            "cik": cik,
            "identity": {
                "entity_id": entity_id,
                "scheme": "sec_cik",
                "value": cik,
                "legal_name": organization,
                "display_name": organization,
                "display_name_zh": f"合成预商业化企业 {seed}",
                "legal_name_citation": {
                    "source_id": SUBJECT_SOURCE_ID,
                    "locator": "SYNTHETIC source line 2",
                },
                "aliases": [],
            },
        },
        "assessment": {
            "as_of": "2025-12-31",
            "horizon_years": 5,
            "geography": "SYNTHETIC global test geography",
            "value_chain_scope": "SYNTHETIC pre-commercial technology development",
        },
        "sources": [
            {
                "id": SUBJECT_SOURCE_ID,
                "path": "subject.txt",
                "url": "https://example.invalid/synthetic-subject",
                "title": "SYNTHETIC subject source",
                "publisher": "SYNTHETIC fixture publisher",
                "published": "2025-12-31",
                "kind": "synthetic_regulatory_filing",
                "role": "subject",
                "subject_entity_id": entity_id,
            },
            {
                "id": BENCHMARK_SOURCE_ID,
                "path": "benchmark.txt",
                "url": "https://example.invalid/synthetic-benchmark",
                "title": "SYNTHETIC wrong-role canary source",
                "publisher": "SYNTHETIC fixture publisher",
                "published": "2025-12-31",
                "kind": "synthetic_benchmark",
                "role": "benchmark",
            },
        ],
        "applicability_context": {
            "contract_version": "1.0.0",
            "commercialization_stage": {
                "state": "pre_commercial",
                "as_of": "2025-12-31",
                "basis": [
                    {
                        "source_id": SUBJECT_SOURCE_ID,
                        "locator": "SYNTHETIC source line 3: pre-commercial stage",
                    }
                ],
            },
            "recognized_operating_revenue": {
                "state": "none_recognized",
                "periods": ["FY2025", "FY2024"],
                "basis": [
                    {
                        "source_id": SUBJECT_SOURCE_ID,
                        "locator": (
                            "SYNTHETIC source line 4: no recognized operating revenue "
                            "for FY2024 and FY2025"
                        ),
                    }
                ],
            },
        },
        "financials": {"currency": "USD", "periods": periods},
        "auxiliary_validation": {"enabled": False, "selected_source_ids": []},
        "judgment_context": {
            "contract_version": "0.3.0",
            "prepared_by": "synthetic-public-api-blind-harness",
            "prepared_at": "2026-08-02",
            "subindustry": {
                "scope_id": PRECOMMERCIAL_SCOPE,
                "name": "SYNTHETIC pre-commercial battery technology development",
                "name_zh": "合成预商业化电池技术开发",
                "value_chain_position": "SYNTHETIC technology development",
                "value_chain_position_zh": "合成技术开发",
                "summary": (
                    "SYNTHETIC subject-stage evidence describes pre-commercial "
                    "technology development."
                ),
                "summary_zh": "合成主体阶段证据描述的是预商业化技术开发。",
                "basis": [
                    {
                        "source_id": SUBJECT_SOURCE_ID,
                        "locator": "SYNTHETIC source line 3",
                    }
                ],
            },
            "dimensions": {
                "cash-runway": {
                    "benchmark": {
                        "scope": (
                            "SYNTHETIC own-history cash direction only; no universal "
                            "threshold is authored by this harness."
                        ),
                        "scope_zh": "仅使用合成主体自身现金历史；本工具不预设统一阈值。",
                        "observations": [
                            {
                                "comparison_type": "subject_history",
                                "entity": "SYNTHETIC subject",
                                "business_model": "SYNTHETIC pre-commercial development",
                                "metric": "Operating cash flow",
                                "period": "FY2025",
                                "value": latest_ocf,
                                "unit": "USD",
                                "display_value": f"SYNTHETIC USD {latest_ocf}",
                                "citation": {
                                    "source_id": SUBJECT_SOURCE_ID,
                                    "locator": (
                                        "SYNTHETIC cash-flow statement, FY2025 operating cash flow"
                                    ),
                                },
                            }
                        ],
                        "limitations": [
                            "SYNTHETIC historical cash observations are not forecasts."
                        ],
                        "limitations_zh": ["合成历史现金观察不构成预测。"],
                    },
                    "gaps": [
                        {
                            "kind": "evidence_gap",
                            "text": "SYNTHETIC forward funding needs are absent.",
                            "text_zh": "缺少合成的前瞻资金需求。",
                        },
                        {
                            "kind": "human_judgment",
                            "text": "SYNTHETIC durability requires human judgment.",
                            "text_zh": "合成趋势的持续性需要人工判断。",
                        },
                        {
                            "kind": "verification",
                            "text": "SYNTHETIC liquidity scope requires verification.",
                            "text_zh": "合成流动性口径需要核验。",
                        },
                    ],
                }
            },
        },
    }


def _source_text(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            SYNTHETIC_NOTICE,
            f"Legal name: {manifest['subject']['organization']}",
            "As of 2025-12-31 the synthetic technology remains pre-commercial.",
            (
                "No operating revenue was recognized in this synthetic fixture for "
                "FY2024 or FY2025; missing revenue is not a numeric zero."
            ),
            "All financial values below are generated solely for contract testing.",
        ]
    )


def _run(manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ctf-synthetic-precommercial-") as raw_dir:
        case_dir = Path(raw_dir)
        (case_dir / "subject.txt").write_text(
            _source_text(manifest) + "\n",
            encoding="utf-8",
        )
        (case_dir / "benchmark.txt").write_text(
            SYNTHETIC_NOTICE
            + "\nThis is a role-boundary canary and is not eligible subject evidence.\n",
            encoding="utf-8",
        )
        manifest_path = case_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return run_audit(
            str(manifest_path),
            only_dimensions=set(VALIDATED_DIMENSIONS),
            allowed_input_root=str(case_dir),
        )


def _outcomes(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return list(audit.get("judgment_layer", {}).get("dimension_outcomes") or [])


def _cards(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return list(audit.get("judgment_layer", {}).get("cards") or [])


def _one(items: list[dict[str, Any]], dimension_id: str) -> dict[str, Any] | None:
    matches = [item for item in items if item.get("dimension_id") == dimension_id]
    return matches[0] if len(matches) == 1 else None


def _stable_contract_view(audit: dict[str, Any]) -> dict[str, Any]:
    judgment = audit.get("judgment_layer") or {}
    execution = audit.get("execution") or {}
    return {
        "applicability_context": audit.get("applicability_context"),
        "financial_analysis": audit.get("financial_analysis"),
        "judgment_layer": {
            "status": judgment.get("status"),
            "cards": judgment.get("cards"),
            "dimension_outcomes": judgment.get("dimension_outcomes"),
            "structured_stage_trace": judgment.get("structured_stage_trace"),
            "framework_coverage": judgment.get("framework_coverage"),
            "validation": judgment.get("validation"),
        },
        "validation": audit.get("validation"),
        "execution": {
            "mode": execution.get("mode"),
            "model_calls": execution.get("model_calls"),
            "network_calls": execution.get("network_calls"),
            "imported_agent_stage_outputs": execution.get("imported_agent_stage_outputs"),
        },
    }


def _applicability_result_view(audit: dict[str, Any]) -> dict[str, Any]:
    profitability = _one(_outcomes(audit), "profitability-unit-economics") or {}
    return {
        "context": audit.get("applicability_context"),
        "status": profitability.get("status"),
        "signal": profitability.get("signal"),
        "reason_code": profitability.get("reason_code"),
        "policy_id": profitability.get("policy_id"),
        "policy_version": profitability.get("policy_version"),
        "policy_digest": profitability.get("policy_digest"),
        "inputs_digest": profitability.get("inputs_digest"),
        "inputs": profitability.get("inputs"),
    }


def _cash_result_view(audit: dict[str, Any]) -> dict[str, Any]:
    outcome = _one(_outcomes(audit), "cash-runway") or {}
    card = _one(_cards(audit), "cash-runway") or {}
    application = (card.get("cells") or {}).get("4_framework_application") or {}
    metrics = (audit.get("financial_analysis") or {}).get("metrics") or []
    return {
        "outcome": outcome,
        "card_signal": card.get("signal"),
        "application": {
            "signal": application.get("signal"),
            "path": application.get("path"),
            "path_zh": application.get("path_zh"),
            "summary": application.get("summary"),
            "summary_zh": application.get("summary_zh"),
            "rule_provenance": application.get("rule_provenance"),
        },
        "financial_metrics": metrics,
    }


def _missing_profitability_fact_leak(audit: dict[str, Any]) -> bool:
    metrics = (audit.get("financial_analysis") or {}).get("metrics") or []
    for metric in metrics:
        metric_id = str(metric.get("id") or "").replace("-", "_")
        if metric_id in MISSING_PROFITABILITY_FACTS:
            return True
        for input_ in metric.get("inputs") or []:
            name = str(input_.get("name") or "").replace("-", "_")
            if name in MISSING_PROFITABILITY_FACTS:
                return True
    for card in _cards(audit):
        facts = ((card.get("cells") or {}).get("2_extracted_facts") or {}).get("items") or []
        for fact in facts:
            fact_id = str(fact.get("id") or "").replace("-", "_")
            if fact_id in MISSING_PROFITABILITY_FACTS:
                return True
    return False


def _positive_oracle_failures(audit: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    outcomes = _outcomes(audit)
    cards = _cards(audit)
    counts = Counter(item.get("dimension_id") for item in outcomes)
    if counts != Counter({dimension_id: 1 for dimension_id in VALIDATED_DIMENSIONS}):
        failures.append("O01_exactly_one_outcome_per_dimension")

    profitability = _one(outcomes, "profitability-unit-economics")
    profitability_cards = [
        item for item in cards if item.get("dimension_id") == "profitability-unit-economics"
    ]
    if profitability is None or profitability.get("status") != "not_yet_applicable":
        failures.append("O02_profitability_not_yet_applicable")
    elif profitability.get("signal") is not None:
        failures.append("O03_not_yet_has_no_signal")
    if profitability_cards:
        failures.append("O04_not_yet_has_no_card")
    if profitability and not all(
        isinstance(profitability.get(key), str) and profitability.get(key)
        for key in ("policy_digest", "inputs_digest")
    ):
        failures.append("O05_applicability_digests_present")

    cash_outcome = _one(outcomes, "cash-runway")
    cash_card = _one(cards, "cash-runway")
    if cash_outcome is None or cash_outcome.get("status") != "evaluated":
        failures.append("O06_cash_evaluated_independently")
    if cash_card is None:
        failures.append("O07_cash_has_one_card")
    elif cash_outcome is not None:
        application = (cash_card.get("cells") or {}).get("4_framework_application") or {}
        if (
            cash_outcome.get("signal") is None
            or cash_card.get("signal") != cash_outcome.get("signal")
            or application.get("signal") != cash_outcome.get("signal")
        ):
            failures.append("O08_cash_signal_is_rule_owned_and_consistent")

    if _missing_profitability_fact_leak(audit):
        failures.append("O09_missing_profitability_facts_not_fabricated_or_zero")
    if (audit.get("execution") or {}).get("model_calls") != 0:
        failures.append("O10_zero_model_calls")
    if (audit.get("execution") or {}).get("network_calls") != 0:
        failures.append("O11_zero_network_calls")
    if not (audit.get("validation") or {}).get("passed"):
        failures.append("O12_positive_audit_validates")
    return failures


def _rename_identity(manifest: dict[str, Any], seed: int) -> None:
    organization = f"SYNTHETIC Renamed Entity {seed}"
    cik = _cik_for(seed, variant=1)
    entity_id = f"sec-cik-{cik}"
    subject = manifest["subject"]
    subject["organization"] = organization
    subject["ticker"] = f"R{seed % 100_000:05d}"
    subject["cik"] = cik
    identity = subject["identity"]
    identity["entity_id"] = entity_id
    identity["value"] = cik
    identity["legal_name"] = organization
    identity["display_name"] = organization
    identity["display_name_zh"] = f"合成重命名企业 {seed}"
    for source in manifest["sources"]:
        if source.get("role") in {"subject", "auxiliary", "identity"}:
            source["subject_entity_id"] = entity_id


def _attempt(manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"kind": "audit", "audit": _run(manifest)}
    except ValueError as exc:
        return {"kind": "validation_exception", "exception_type": type(exc).__name__}


def _fails_closed(attempt: dict[str, Any]) -> bool:
    if attempt["kind"] == "validation_exception":
        return True
    audit = attempt["audit"]
    profitability = _one(_outcomes(audit), "profitability-unit-economics")
    granted = profitability is not None and profitability.get("status") == "not_yet_applicable"
    return not granted and not bool((audit.get("validation") or {}).get("passed"))


def _negative_case(
    manifest: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    candidate = copy.deepcopy(manifest)
    mutate(candidate)
    attempt = _attempt(candidate)
    return {
        "fails_closed": _fails_closed(attempt),
        "result_kind": attempt["kind"],
        "validation_passed": (
            None
            if attempt["kind"] != "audit"
            else bool((attempt["audit"].get("validation") or {}).get("passed"))
        ),
    }


def _evaluate_seed(seed: int, repeats: int) -> tuple[dict[str, Any], int]:
    manifest = _base_manifest(seed)
    baseline_runs = [_run(copy.deepcopy(manifest)) for _ in range(repeats)]
    api_calls = repeats
    baseline = baseline_runs[0]
    failures = _positive_oracle_failures(baseline)
    stable_views = [_stable_contract_view(item) for item in baseline_runs]
    if len({_digest(item) for item in stable_views}) != 1:
        failures.append("M01_same_seed_repeat_determinism")

    renamed = copy.deepcopy(manifest)
    _rename_identity(renamed, seed)
    renamed_audit = _run(renamed)
    api_calls += 1
    if _applicability_result_view(renamed_audit) != _applicability_result_view(baseline):
        failures.append("M02_identity_rename_applicability_invariance")
    if _cash_result_view(renamed_audit) != _cash_result_view(baseline):
        failures.append("M03_identity_rename_cash_invariance")

    permuted = copy.deepcopy(manifest)
    permuted["financials"]["periods"].reverse()
    permuted["applicability_context"]["recognized_operating_revenue"]["periods"].reverse()
    permuted_audit = _run(permuted)
    api_calls += 1
    if _applicability_result_view(permuted_audit) != _applicability_result_view(baseline):
        failures.append("M04_period_order_applicability_invariance")
    if _cash_result_view(permuted_audit) != _cash_result_view(baseline):
        failures.append("M05_period_order_cash_invariance")

    def missing_stage_evidence(candidate: dict[str, Any]) -> None:
        candidate["applicability_context"]["commercialization_stage"]["basis"] = []

    def missing_revenue_evidence(candidate: dict[str, Any]) -> None:
        candidate["applicability_context"]["recognized_operating_revenue"]["basis"] = []

    def wrong_role_stage(candidate: dict[str, Any]) -> None:
        candidate["applicability_context"]["commercialization_stage"]["basis"][0]["source_id"] = (
            BENCHMARK_SOURCE_ID
        )

    def wrong_role_revenue(candidate: dict[str, Any]) -> None:
        candidate["applicability_context"]["recognized_operating_revenue"]["basis"][0][
            "source_id"
        ] = BENCHMARK_SOURCE_ID

    def near_scope(candidate: dict[str, Any]) -> None:
        candidate["judgment_context"]["subindustry"]["scope_id"] = PRECOMMERCIAL_SCOPE + "-adjacent"

    negative_mutations = {
        "missing_stage_evidence": missing_stage_evidence,
        "missing_no_revenue_evidence": missing_revenue_evidence,
        "wrong_role_stage_citation": wrong_role_stage,
        "wrong_role_revenue_citation": wrong_role_revenue,
        "near_scope": near_scope,
    }
    negative_results = {
        name: _negative_case(manifest, mutation) for name, mutation in negative_mutations.items()
    }
    api_calls += len(negative_results)
    for name, result in negative_results.items():
        if not result["fails_closed"]:
            failures.append(f"N_{name}_fails_closed")

    return (
        {
            "synthetic": True,
            "seed": seed,
            "stable_contract_digest": _digest(stable_views[0]),
            "applicability_result_digest": _digest(_applicability_result_view(baseline)),
            "cash_result_digest": _digest(_cash_result_view(baseline)),
            "expected_signal_authored": False,
            "negative_cases": negative_results,
            "failures": sorted(set(failures)),
        },
        api_calls,
    )


def evaluate(*, seed_start: int, seed_count: int, repeats: int) -> dict[str, Any]:
    """Run a configurable set of synthetic public-API metamorphic checks."""

    if seed_count < 1 or repeats < 2:
        raise ValueError("seed_count must be positive and repeats must be at least 2")
    records: list[dict[str, Any]] = []
    api_calls = 0
    for seed in range(seed_start, seed_start + seed_count):
        record, seed_calls = _evaluate_seed(seed, repeats)
        records.append(record)
        api_calls += seed_calls
    failed = [record for record in records if record["failures"]]
    return {
        "synthetic": True,
        "synthetic_notice": SYNTHETIC_NOTICE,
        "public_api": "cleantech_finance.audit.run_audit",
        "imports_internal_rule_definitions": False,
        "expected_signal_authored": False,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "repeats": repeats,
        "api_call_count": api_calls,
        "passed_seed_count": seed_count - len(failed),
        "failed_seed_count": len(failed),
        "passed": not failed,
        "failed_records": failed,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Run reproducible SYNTHETIC pre-commercial applicability black-box checks.")
    )
    parser.add_argument("--seed-start", type=int, default=40_001)
    parser.add_argument("--seed-count", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(
        seed_start=args.seed_start,
        seed_count=args.seed_count,
        repeats=args.repeats,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in report.items() if key != "records"}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
