"""Run and verify every registered new-company loop in deterministic order."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleantech_finance.audit import run_audit
from cleantech_finance.reporting import write_artifacts

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "evals" / "company-loops-v0.3.json"


def _signals(audit: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "profitability-unit-economics": None,
        "cash-runway": None,
    }
    for card in audit.get("judgment_layer", {}).get("cards", []):
        result[card["dimension_id"]] = card["signal"]
    return result


def run_registry() -> list[dict[str, Any]]:
    cases = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if len(cases) < 10:
        raise ValueError("Company-loop gate requires at least 10 registered cases")
    summaries: list[dict[str, Any]] = []
    for case in cases:
        manifest = ROOT / case["manifest"]
        audit = run_audit(
            str(manifest),
            only_dimensions={"profitability-unit-economics", "cash-runway"},
        )
        if not audit["validation"]["passed"]:
            raise ValueError(
                f"{case['id']} failed audit validation: "
                + "; ".join(audit["validation"]["errors"])
            )
        actual_signals = _signals(audit)
        if actual_signals != case["expected_signals"]:
            raise ValueError(
                f"{case['id']} signals {actual_signals} != {case['expected_signals']}"
            )
        actual_auxiliary = audit["auxiliary_validation"]["status"]
        if actual_auxiliary != case["expected_auxiliary_status"]:
            raise ValueError(
                f"{case['id']} auxiliary status {actual_auxiliary} != "
                f"{case['expected_auxiliary_status']}"
            )
        if audit["execution"]["model_calls"] != 0:
            raise ValueError(f"{case['id']} used a model in the offline core")
        output_dir = ROOT / case["output_dir"]
        write_artifacts(audit, output_dir)
        summaries.append(
            {
                "iteration": case["iteration"],
                "id": case["id"],
                "entity_id": case["entity_id"],
                "signals": actual_signals,
                "auxiliary_status": actual_auxiliary,
                "citations": audit["validation"]["citation_count"],
                "model_calls": 0,
                "output_dir": str(output_dir.resolve()),
            }
        )
    return summaries


def main() -> int:
    try:
        result = run_registry()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(
            {"passed": True, "case_count": len(result), "cases": result},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
