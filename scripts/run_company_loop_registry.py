"""Run and verify every registered new-company loop in deterministic order."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cleantech_finance.audit import run_audit
from cleantech_finance.reporting import write_artifacts

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "evals" / "company-loops-v0.3.json"
REQUESTED_DIMENSIONS = (
    "profitability-unit-economics",
    "cash-runway",
)
OUTCOME_STATUSES = {"evaluated", "not_applicable", "not_yet_applicable"}
SIGNALS = {"red", "amber", "green"}


def _normalize_outcome(
    outcome: dict[str, Any], *, source: str, dimension_id: str
) -> dict[str, str | None]:
    if "status" not in outcome or "signal" not in outcome:
        raise ValueError(
            f"{source} outcome for '{dimension_id}' must explicitly contain status and signal"
        )
    status = outcome["status"]
    signal = outcome["signal"]
    if not isinstance(status, str) or status not in OUTCOME_STATUSES:
        raise ValueError(f"{source} outcome for '{dimension_id}' has unsupported status '{status}'")
    if status == "evaluated":
        if not isinstance(signal, str) or signal not in SIGNALS:
            raise ValueError(f"{source} evaluated outcome for '{dimension_id}' must have a signal")
    elif signal is not None:
        raise ValueError(
            f"{source} non-evaluated outcome for '{dimension_id}' cannot have a signal"
        )
    return {"status": status, "signal": signal}


def extract_dimension_outcomes(audit: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    """Read outcomes from the judgment layer and enforce the card/outcome invariant."""

    judgment = audit.get("judgment_layer", {})
    raw_outcomes = judgment.get("dimension_outcomes")
    if not isinstance(raw_outcomes, list):
        raise ValueError("judgment_layer.dimension_outcomes must be a list")

    outcomes: dict[str, dict[str, str | None]] = {}
    for item in raw_outcomes:
        if not isinstance(item, dict):
            raise ValueError("Every dimension outcome must be an object")
        dimension_id = item.get("dimension_id")
        if dimension_id not in REQUESTED_DIMENSIONS:
            raise ValueError(f"Unexpected dimension outcome '{dimension_id}'")
        if dimension_id in outcomes:
            raise ValueError(f"Duplicate dimension outcome '{dimension_id}'")
        outcomes[dimension_id] = _normalize_outcome(
            item, source="Actual", dimension_id=dimension_id
        )

    missing = set(REQUESTED_DIMENSIONS) - set(outcomes)
    if missing:
        raise ValueError("Missing dimension outcome(s): " + ", ".join(sorted(missing)))

    raw_cards = judgment.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("judgment_layer.cards must be a list")
    cards: dict[str, dict[str, Any]] = {}
    for card in raw_cards:
        if not isinstance(card, dict):
            raise ValueError("Every judgment card must be an object")
        dimension_id = card.get("dimension_id")
        if dimension_id not in REQUESTED_DIMENSIONS:
            raise ValueError(f"Unexpected judgment card '{dimension_id}'")
        if dimension_id in cards:
            raise ValueError(f"Duplicate judgment card '{dimension_id}'")
        cards[dimension_id] = card

    evaluated = {
        dimension_id
        for dimension_id, outcome in outcomes.items()
        if outcome["status"] == "evaluated"
    }
    if set(cards) != evaluated:
        missing_cards = sorted(evaluated - set(cards))
        unexpected_cards = sorted(set(cards) - evaluated)
        details = []
        if missing_cards:
            details.append("missing evaluated card(s): " + ", ".join(missing_cards))
        if unexpected_cards:
            details.append("card(s) for non-evaluated outcome: " + ", ".join(unexpected_cards))
        raise ValueError("Card/outcome mismatch: " + "; ".join(details))
    for dimension_id, card in cards.items():
        if card.get("signal") != outcomes[dimension_id]["signal"]:
            raise ValueError(
                f"Card signal for '{dimension_id}' does not match its evaluated outcome"
            )
    return {dimension_id: outcomes[dimension_id] for dimension_id in REQUESTED_DIMENSIONS}


def validate_registry_contract(cases: Any) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        raise ValueError("Company-loop registry must be a list")
    if len(cases) < 10:
        raise ValueError("Company-loop gate requires at least 10 registered cases")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("Every company-loop registry row must be an object")

    iterations = [case.get("iteration") for case in cases]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in iterations):
        raise ValueError("Registry iterations must be integers")
    if sorted(iterations) != list(range(1, len(cases) + 1)):
        raise ValueError("Registry iterations must be unique and continuous from 1")

    for key, label in (("id", "case ids"), ("entity_id", "stable entity ids")):
        values = [case.get(key) for case in cases]
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f"Registry {label} must be non-empty strings")
        if len(set(values)) != len(values):
            raise ValueError(f"Registry requires unique {label}")

    for case in cases:
        expected = case.get("expected_outcomes")
        if not isinstance(expected, dict) or set(expected) != set(REQUESTED_DIMENSIONS):
            raise ValueError(
                f"{case['id']} expected_outcomes must contain exactly the requested dimensions"
            )
        for dimension_id in REQUESTED_DIMENSIONS:
            if not isinstance(expected[dimension_id], dict):
                raise ValueError(
                    f"{case['id']} expected outcome for '{dimension_id}' must be an object"
                )
            _normalize_outcome(
                expected[dimension_id],
                source=f"{case['id']} expected",
                dimension_id=dimension_id,
            )
    return sorted(cases, key=lambda case: case["iteration"])


def run_registry() -> list[dict[str, Any]]:
    cases = validate_registry_contract(json.loads(REGISTRY.read_text(encoding="utf-8")))
    summaries: list[dict[str, Any]] = []
    for case in cases:
        manifest = ROOT / case["manifest"]
        audit = run_audit(
            str(manifest),
            only_dimensions={"profitability-unit-economics", "cash-runway"},
        )
        if not audit["validation"]["passed"]:
            raise ValueError(
                f"{case['id']} failed audit validation: " + "; ".join(audit["validation"]["errors"])
            )
        actual_outcomes = extract_dimension_outcomes(audit)
        if actual_outcomes != case["expected_outcomes"]:
            raise ValueError(
                f"{case['id']} outcomes {actual_outcomes} != {case['expected_outcomes']}"
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
                "outcomes": actual_outcomes,
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
