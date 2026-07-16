"""Evaluate the v0.3 deterministic five-cell judgment-card contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_CELLS = {
    "1_subindustry_position",
    "2_extracted_facts",
    "3_judgment_framework",
    "4_framework_application",
    "5_gaps_and_human_judgment",
}
EXPECTED_STAGES = {
    "subindustry_identification",
    "benchmark_retrieval",
    "deterministic_signal",
    "gap_exposure",
}
EXPECTED_GAPS = {"evidence_gap", "human_judgment", "verification"}
THRESHOLD_PATTERN = re.compile(
    r"(?:[<>]=?\s*\d|\b(?:less|more)\s+than\s+\d|"
    r"\b(?:under|over|below|above|at\s+least|at\s+most)\s+\d|"
    r"\bthreshold\s*[:=]\s*\d)",
    re.IGNORECASE,
)


def evaluate_cards(audit: dict[str, Any], ground: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append(
            {"name": name, "passed": bool(passed), "actual": actual, "expected": expected}
        )

    layer = audit.get("judgment_layer") or {}
    cards = {card["dimension_id"]: card for card in layer.get("cards", [])}
    expected_dimensions = set(ground["signals"])
    check("layer-status", layer.get("status") == "generated", layer.get("status"), "generated")
    check(
        "layer-validation",
        layer.get("validation", {}).get("passed") is True,
        layer.get("validation"),
        "passed",
    )
    check(
        "card-dimensions",
        set(cards) == expected_dimensions,
        sorted(cards),
        sorted(expected_dimensions),
    )
    coverage = layer.get("framework_coverage", {})
    check(
        "locked-framework-coverage",
        coverage.get("locked") == coverage.get("implemented") == len(expected_dimensions),
        coverage,
        {"locked": len(expected_dimensions), "implemented": len(expected_dimensions)},
    )

    for dimension_id in sorted(expected_dimensions):
        card = cards.get(dimension_id)
        if not card:
            continue
        cells = card.get("cells", {})
        check(
            f"{dimension_id}:five-cells",
            set(cells) == EXPECTED_CELLS,
            sorted(cells),
            sorted(EXPECTED_CELLS),
        )
        check(
            f"{dimension_id}:signal",
            card.get("signal") == ground["signals"][dimension_id],
            card.get("signal"),
            ground["signals"][dimension_id],
        )
        framework = cells.get("3_judgment_framework", {})
        check(
            f"{dimension_id}:framework-locked",
            framework.get("locked") is True
            and "authored_by" not in framework
            and "signature" not in framework
            and all(
                framework.get(key)
                for key in ("methodology", "methodology_zh", "basis", "basis_zh", "text", "text_zh")
            )
            and "cassian" not in json.dumps(framework, ensure_ascii=False).lower(),
            framework,
            "locked bilingual methodology with neutral basis and no personal signature",
        )
        check(
            f"{dimension_id}:no-absolute-threshold",
            not THRESHOLD_PATTERN.search(framework.get("text", "")),
            framework.get("text"),
            "relative, subindustry-first framework",
        )
        subindustry = cells.get("1_subindustry_position", {})
        check(
            f"{dimension_id}:subindustry-cited",
            bool(subindustry.get("name") and subindustry.get("basis")),
            subindustry,
            "named and cited",
        )
        facts = cells.get("2_extracted_facts", {}).get("items", [])
        check(
            f"{dimension_id}:facts-cited-and-labeled",
            bool(facts)
            and all(
                item.get("label") in {"fact", "calculation"} and item.get("citations")
                for item in facts
            ),
            len(facts),
            "all facts/calculations labeled and cited",
        )
        application = cells.get("4_framework_application", {})
        observations = application.get("benchmark", {}).get("observations", [])
        provenance = application.get("rule_provenance", {})
        check(
            f"{dimension_id}:relative-application-cited",
            bool(application.get("path") and application.get("basis") and observations)
            and all(item.get("citation") for item in observations)
            and application.get("label") == "deterministic_rule_output"
            and provenance.get("deterministic") is True
            and provenance.get("rule_status") == "validated"
            and provenance.get("rule_id")
            and provenance.get("rule_version")
            and str(provenance.get("rule_digest", "")).startswith("sha256:")
            and str(provenance.get("inputs_digest", "")).startswith("sha256:")
            and application.get("path_zh")
            and application.get("summary_zh"),
            {
                "path": application.get("path"),
                "basis": application.get("basis"),
                "observations": observations,
                "rule_provenance": provenance,
            },
            "cited benchmark plus validated deterministic scoped rule with bilingual output",
        )
        gaps = cells.get("5_gaps_and_human_judgment", {}).get("items", [])
        gap_kinds = {item.get("kind") for item in gaps}
        check(
            f"{dimension_id}:three-gap-types",
            EXPECTED_GAPS.issubset(gap_kinds)
            and all(item.get("text") and item.get("text_zh") for item in gaps),
            sorted(str(item) for item in gap_kinds),
            sorted(EXPECTED_GAPS),
        )
        check(
            f"{dimension_id}:not-a-rating",
            (
                "not an investment" in card.get("disclaimer", "").lower()
                or "no investment rating" in card.get("disclaimer", "").lower()
            )
            and "not an investment" in card.get("signal_meaning", "").lower()
            and "不构成投资" in card.get("signal_meaning_zh", "")
            and "不包含投资评级" in card.get("disclaimer_zh", "")
            and "不构成投资建议" in card.get("disclaimer_zh", ""),
            {
                "signal_meaning": card.get("signal_meaning"),
                "signal_meaning_zh": card.get("signal_meaning_zh"),
                "disclaimer": card.get("disclaimer"),
                "disclaimer_zh": card.get("disclaimer_zh"),
            },
            "bilingual evidence signal with explicit non-rating boundary",
        )

        stages = {
            item.get("stage")
            for item in layer.get("structured_stage_trace", [])
            if item.get("dimension_id") == dimension_id
        }
        check(
            f"{dimension_id}:structured-stages",
            stages == EXPECTED_STAGES
            and all(
                item.get("sources")
                for item in layer.get("structured_stage_trace", [])
                if item.get("dimension_id") == dimension_id
            )
            and any(
                item.get("stage") == "deterministic_signal"
                and item.get("actor") == "deterministic_rule_engine"
                for item in layer.get("structured_stage_trace", [])
                if item.get("dimension_id") == dimension_id
            ),
            [
                {
                    "stage": item.get("stage"),
                    "actor": item.get("actor"),
                    "source_count": len(item.get("sources") or []),
                }
                for item in layer.get("structured_stage_trace", [])
                if item.get("dimension_id") == dimension_id
            ],
            "four sourced stages with deterministic rule engine for signal",
        )

    capability = audit.get("capability_matrix", {}).get("summary", {})
    check(
        "honest-capability-matrix",
        capability.get("validated_finance_dimensions") == 2
        and capability.get("total_finance_dimensions") == 6
        and capability.get("validated_rule_dimensions") == 2
        and capability.get("authored_only_rule_dimensions") == 4
        and capability.get("validated_adoption_dimensions") == 0,
        capability,
        "2/6 finance dimensions validated, 2 rule dimensions validated, 4 authored only",
    )
    check(
        "offline-zero-model-core",
        audit.get("execution", {}).get("model_calls") == 0
        and audit.get("execution", {}).get("estimated_model_cost") == 0
        and audit.get("execution", {}).get("imported_agent_stage_outputs") is True,
        audit.get("execution"),
        "zero-model deterministic core with imported structured stage outputs",
    )
    check(
        "no-automated-rating",
        audit.get("guardrails", {}).get("automated_investment_rating") is False
        and audit.get("guardrails", {}).get("automated_arl_score") is False,
        audit.get("guardrails"),
        "no automated investment rating or ARL score",
    )

    passed = all(item["passed"] for item in checks)
    return {
        "case": ground["case"],
        "passed": passed,
        "passed_checks": sum(item["passed"] for item in checks),
        "total_checks": len(checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_json")
    parser.add_argument("ground_truth")
    parser.add_argument("--out")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8"))
    ground = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
    result = evaluate_cards(audit, ground)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
