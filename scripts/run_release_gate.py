"""Run the ordered Sungrow -> Enphase public-company release gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from download_demo_sources import download
from evaluate_audit import evaluate
from evaluate_cards import evaluate_cards

from cleantech_finance.audit import run_audit
from cleantech_finance.reporting import write_artifacts

CASES = (
    {
        "id": "sungrow",
        "manifest": Path("examples/sungrow/manifest.auto.json"),
        "ground_truth": Path("evals/sungrow-2025.json"),
        "card_ground_truth": Path("evals/sungrow-cards-v0.2.json"),
    },
    {
        "id": "enphase",
        "manifest": Path("examples/enphase/manifest.auto.json"),
        "ground_truth": Path("evals/enphase-2025.json"),
        "card_ground_truth": Path("evals/enphase-cards-v0.2.json"),
    },
)


def run_case(case: dict[str, Any], output_root: Path) -> dict[str, Any]:
    case_id = case["id"]
    audit = run_audit(str(case["manifest"]))
    case_output = output_root / case_id
    artifacts = write_artifacts(audit, case_output)
    ground_truth = json.loads(case["ground_truth"].read_text(encoding="utf-8"))
    evaluation = evaluate(audit, ground_truth)
    evaluation_path = case_output / "evaluation.json"
    evaluation_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    card_ground_truth = json.loads(case["card_ground_truth"].read_text(encoding="utf-8"))
    card_evaluation = evaluate_cards(audit, card_ground_truth)
    card_evaluation_path = case_output / "card_evaluation.json"
    card_evaluation_path.write_text(
        json.dumps(card_evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "case": case_id,
        "passed": evaluation["passed"] and card_evaluation["passed"],
        "extraction_checks": f"{evaluation['passed_checks']}/{evaluation['total_checks']}",
        "card_checks": f"{card_evaluation['passed_checks']}/{card_evaluation['total_checks']}",
        "citation_count": audit["validation"]["citation_count"],
        "model_calls": audit["execution"]["model_calls"],
        "artifacts": artifacts,
        "evaluation": str(evaluation_path.resolve()),
        "card_evaluation": str(card_evaluation_path.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the ordered real-company release gate; stop on the first failure."
    )
    parser.add_argument("--out", default="outputs/release-gate")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use already-downloaded, checksum-verified filings.",
    )
    args = parser.parse_args()

    if not args.skip_download:
        for case in CASES:
            download(case["id"])

    results: list[dict[str, Any]] = []
    for case in CASES:
        try:
            result = run_case(case, Path(args.out))
        except (OSError, RuntimeError, ValueError) as exc:
            print(json.dumps({"case": case["id"], "passed": False, "error": str(exc)}, indent=2))
            return 2
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["passed"]:
            print(f"Release gate stopped after {case['id']}: repair and rerun both cases.")
            return 2

    print(
        json.dumps(
            {
                "release_gate": "passed",
                "order": [item["case"] for item in results],
                "extraction_checks": {
                    item["case"]: item["extraction_checks"] for item in results
                },
                "card_checks": {item["case"]: item["card_checks"] for item in results},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
