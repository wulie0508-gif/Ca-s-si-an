from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cleantech_finance.capabilities import capability_matrix
from cleantech_finance.rules import (
    FORBIDDEN_SCOPES,
    RULES,
    evaluate_rule,
    rule_status_for_dimension,
)


def _fact(
    value: float,
    *,
    operations: str = "total_operations",
    attribution: str = "not_applicable",
) -> dict[str, object]:
    return {
        "value": value,
        "source_id": "subject",
        "locator": "p.1",
        "statement_scope": {
            "operations": operations,
            "attribution": attribution,
        },
    }


def _financials(
    *,
    latest_margin: float = 0.32,
    prior_margin: float = 0.30,
    latest_income: float = 10.0,
    prior_income: float = 8.0,
    latest_ocf: float = 20.0,
    prior_ocf: float = 15.0,
    latest_capex: float = 5.0,
    prior_capex: float = 5.0,
) -> dict[str, object]:
    def period(
        name: str,
        end_date: str,
        margin: float,
        income: float,
        ocf: float,
        capex: float,
    ) -> dict[str, object]:
        revenue = 100.0
        fiscal_year = int(name.removeprefix("FY"))
        return {
            "period": name,
            "fiscal_year": fiscal_year,
            "period_type": "annual",
            "start_date": f"{fiscal_year}-01-01",
            "end_date": end_date,
            "duration_days": 366 if fiscal_year % 4 == 0 else 365,
            "facts": {
                "revenue": _fact(revenue),
                "operating_cost": _fact(revenue * (1 - margin)),
                "net_income": _fact(income, attribution="consolidated"),
                "operating_cash_flow": _fact(ocf),
                "capex": _fact(capex),
                "cash_and_equivalents": _fact(30.0),
            },
        }

    return {
        "currency": "USD",
        "periods": [
            period("FY2024", "2024-12-31", prior_margin, prior_income, prior_ocf, prior_capex),
            period(
                "FY2025",
                "2025-12-31",
                latest_margin,
                latest_income,
                latest_ocf,
                latest_capex,
            ),
        ],
    }


def test_rule_library_is_immutable_scoped_and_uniquely_versioned() -> None:
    identities = {(rule.id, rule.version) for rule in RULES}
    assert len(identities) == len(RULES)
    assert all(rule.subindustry_scopes for rule in RULES)
    assert all(
        scope.lower() not in FORBIDDEN_SCOPES for rule in RULES for scope in rule.subindustry_scopes
    )
    assert all(rule.required_inputs for rule in RULES)
    with pytest.raises(FrozenInstanceError):
        RULES[0].status = "authored"  # type: ignore[misc]


def test_authored_does_not_mean_validated() -> None:
    assert rule_status_for_dimension("profitability-unit-economics") == "validated"
    assert rule_status_for_dimension("cash-runway") == "validated"
    assert rule_status_for_dimension("revenue-traction-quality") == "authored"
    assert rule_status_for_dimension("capex-scale-up") == "authored"
    assert rule_status_for_dimension("balance-sheet-funding") == "authored"
    assert rule_status_for_dimension("project-bankability") == "authored"
    matrix = capability_matrix()
    summary = matrix["summary"]
    assert summary["validated_finance_dimensions"] == 2
    assert summary["validated_rule_dimensions"] == 2
    assert summary["authored_only_rule_dimensions"] == 4
    by_id = {item["id"]: item for item in matrix["finance"]}
    assert by_id["revenue-traction-quality"]["rule_status"] == "authored"
    assert by_id["revenue-traction-quality"]["judgment_card"] == "not_implemented"
    assert by_id["profitability-unit-economics"]["rule_status"] == "validated"
    assert by_id["profitability-unit-economics"]["judgment_card"] == ("implemented_and_validated")


def test_same_inputs_and_rule_version_are_deterministic() -> None:
    financials = _financials()
    first = evaluate_rule("profitability-unit-economics", "power-electronics-equipment", financials)
    second = evaluate_rule(
        "profitability-unit-economics", "power-electronics-equipment", financials
    )
    assert first == second
    assert first["signal"] == "green"
    assert first["deterministic"] is True
    assert first["rule_status"] == "validated"
    assert first["rule_digest"].startswith("sha256:")
    assert first["inputs_digest"].startswith("sha256:")


def test_digest_and_signal_ignore_mapping_order() -> None:
    financials = _financials()
    reordered = {
        "periods": [
            {
                "facts": dict(reversed(list(period["facts"].items()))),
                "duration_days": period["duration_days"],
                "end_date": period["end_date"],
                "start_date": period["start_date"],
                "period_type": period["period_type"],
                "fiscal_year": period["fiscal_year"],
                "period": period["period"],
            }
            for period in reversed(financials["periods"])
        ],
        "currency": financials["currency"],
    }
    first = evaluate_rule("cash-runway", "storage-equipment", financials)
    second = evaluate_rule("cash-runway", "storage-equipment", reordered)
    assert first["signal"] == second["signal"]
    assert first["rule_digest"] == second["rule_digest"]
    assert first["inputs_digest"] == second["inputs_digest"]


def test_rules_use_own_history_not_company_identity_or_absolute_level() -> None:
    high_level_decline = _financials(latest_margin=0.60, prior_margin=0.65)
    low_level_improvement = _financials(latest_margin=0.12, prior_margin=0.10)
    negative_improvement = _financials(latest_margin=-0.20, prior_margin=-0.35)
    positive_margin_but_loss_making = _financials(
        latest_margin=0.30,
        prior_margin=0.24,
        latest_income=-20.0,
        prior_income=-30.0,
    )
    declining = evaluate_rule(
        "profitability-unit-economics",
        "power-electronics-equipment",
        high_level_decline,
    )
    improving = evaluate_rule(
        "profitability-unit-economics",
        "power-electronics-equipment",
        low_level_improvement,
    )
    loss_stage = evaluate_rule(
        "profitability-unit-economics",
        "hydrogen-fuel-cell-electrolyzer-integrated",
        negative_improvement,
    )
    company_loss_stage = evaluate_rule(
        "profitability-unit-economics",
        "ev-charging-network-hardware-saas",
        positive_margin_but_loss_making,
    )
    assert declining["signal"] == "amber"
    assert improving["signal"] == "green"
    assert loss_stage["signal"] == "amber"
    assert loss_stage["inputs"]["gross_margin_state"] == "negative"
    assert company_loss_stage["signal"] == "amber"
    assert company_loss_stage["inputs"]["gross_margin_state"] == "nonnegative"
    assert company_loss_stage["inputs"]["net_income_state"] == "loss_making"
    runtime_text = " ".join(
        str(value)
        for rule in RULES
        for value in (rule.conditions, rule.rationale, rule.path, rule.basis)
    ).lower()
    assert "sungrow" not in runtime_text
    assert "enphase" not in runtime_text


def test_cash_rule_branches_are_explicit() -> None:
    improving = evaluate_rule(
        "cash-runway", "storage-equipment", _financials(latest_ocf=20, prior_ocf=15)
    )
    declining = evaluate_rule(
        "cash-runway", "storage-equipment", _financials(latest_ocf=10, prior_ocf=15)
    )
    not_covered = evaluate_rule(
        "cash-runway", "storage-equipment", _financials(latest_ocf=-2, prior_ocf=5)
    )
    positive_but_below_capex = evaluate_rule(
        "cash-runway",
        "storage-equipment",
        _financials(latest_ocf=4.9, latest_capex=5.0, prior_ocf=15),
    )
    exactly_covered = evaluate_rule(
        "cash-runway",
        "storage-equipment",
        _financials(latest_ocf=5.0, latest_capex=5.0, prior_ocf=4.0),
    )
    assert improving["signal"] == "green"
    assert declining["signal"] == "amber"
    assert not_covered["signal"] == "red"
    assert positive_but_below_capex["signal"] == "red"
    assert positive_but_below_capex["inputs"]["cash_pattern"] == (
        "profitable_not_covered"
    )
    assert positive_but_below_capex["inputs"]["latest_ocf_to_capex"] == 0.98
    assert exactly_covered["signal"] == "green"
    assert exactly_covered["inputs"]["cash_pattern"] == (
        "profitable_covered_improving"
    )


@pytest.mark.parametrize("scope", ["", "all", "*", "any", "global"])
def test_rule_evaluation_fails_closed_for_implicit_scope(scope: str) -> None:
    with pytest.raises(ValueError, match="explicit subindustry scope"):
        evaluate_rule("cash-runway", scope, _financials())


def test_rule_evaluation_fails_closed_for_unvalidated_scope_or_dimension() -> None:
    with pytest.raises(ValueError, match="found 0"):
        evaluate_rule("cash-runway", "asset-owner", _financials())
    with pytest.raises(ValueError, match="no validated deterministic engine"):
        evaluate_rule("project-bankability", "power-electronics-equipment", _financials())


def test_asset_owner_profitability_is_not_applicable_but_cash_is_scoped() -> None:
    scope = "contracted-renewable-generation-and-storage-asset-owner"
    with pytest.raises(ValueError, match="not applicable"):
        evaluate_rule("profitability-unit-economics", scope, _financials())
    cash = evaluate_rule("cash-runway", scope, _financials())
    assert cash["signal"] == "green"
