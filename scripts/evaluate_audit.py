"""Compare a generated audit with manually verified public-data ground truth."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _close(actual: float, expected: float, tolerance: float) -> bool:
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)


def evaluate(audit: dict[str, Any], ground: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append(
            {"name": name, "passed": bool(passed), "actual": actual, "expected": expected}
        )

    extraction = audit.get("financial_fact_extraction") or {}
    periods = extraction.get("financials", {}).get("periods", [])
    facts = {
        (period["period"], name): fact
        for period in periods
        for name, fact in period.get("facts", {}).items()
    }
    for expected in ground["facts"]:
        key = (expected["period"], expected["name"])
        actual = facts.get(key)
        check(
            f"fact:{expected['period']}:{expected['name']}:value",
            bool(actual) and _close(actual["value"], expected["value"], ground["tolerance"]),
            actual["value"] if actual else None,
            expected["value"],
        )
        check(
            f"fact:{expected['period']}:{expected['name']}:locator",
            bool(actual) and actual["locator"] == expected["locator"],
            actual["locator"] if actual else None,
            expected["locator"],
        )

    metrics = {metric["id"]: metric for metric in audit["financial_analysis"]["metrics"]}
    for metric_id, expected in ground["metrics"].items():
        actual = metrics.get(metric_id)
        check(
            f"metric:{metric_id}",
            bool(actual) and _close(actual["value"], expected, ground["tolerance"]),
            actual["value"] if actual else None,
            expected,
        )

    check("citation-integrity", audit["validation"]["passed"], audit["validation"], "passed")
    check(
        "model-calls", audit["execution"]["model_calls"] == 0, audit["execution"]["model_calls"], 0
    )
    check(
        "model-cost",
        audit["execution"]["estimated_model_cost"] == 0,
        audit["execution"]["estimated_model_cost"],
        0,
    )
    populated_ratings = [
        result["id"]
        for section in ("finance_evidence", "adoption_risk_evidence")
        for result in audit[section]
        if result.get("human_rating") is not None
    ]
    check("automated-human-ratings", not populated_ratings, populated_ratings, [])
    all_locators = [
        candidate["locator"]
        for section in ("finance_evidence", "adoption_risk_evidence")
        for result in audit[section]
        for candidate in result["candidates"]
    ]
    for forbidden in ground.get("forbidden_candidate_locators", []):
        check(
            f"forbidden-candidate:{forbidden}",
            forbidden not in all_locators,
            all_locators,
            f"must not contain {forbidden}",
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
    result = evaluate(audit, ground)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
