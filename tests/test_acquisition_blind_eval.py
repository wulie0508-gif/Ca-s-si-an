from __future__ import annotations

from scripts.run_acquisition_blind_eval import evaluate


def test_reproducible_acquisition_blind_evaluation_has_no_failed_oracles() -> None:
    first = evaluate(seed_start=90_001, seed_count=5, repeats=2)
    second = evaluate(seed_start=90_001, seed_count=5, repeats=2)

    assert first == second
    assert first["synthetic"] is True
    assert first["passed"] is True
    assert first["failed_seed_count"] == 0
    assert first["passed_seed_count"] == 5
    assert first["api_call_count"] >= 45
    assert all(0 < record["completeness_ratio"] < 1 for record in first["records"])
