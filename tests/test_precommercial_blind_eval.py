from __future__ import annotations

from scripts.run_precommercial_blind_eval import evaluate


def test_precommercial_public_api_blind_eval_is_reproducible_and_passes() -> None:
    first = evaluate(seed_start=95_001, seed_count=3, repeats=2)
    second = evaluate(seed_start=95_001, seed_count=3, repeats=2)

    assert first == second
    assert first["synthetic"] is True
    assert first["imports_internal_rule_definitions"] is False
    assert first["expected_signal_authored"] is False
    assert first["passed"] is True
    assert first["failed_seed_count"] == 0
    assert first["passed_seed_count"] == 3
    assert first["api_call_count"] >= 27
