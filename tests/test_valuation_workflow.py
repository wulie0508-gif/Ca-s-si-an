from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cleantech_finance.deal_service import DealStore
from cleantech_finance.valuation import InputGateError, ValuationHardFailure
from cleantech_finance.valuation_workflow import (
    ValuationWorkflowError,
    calculate_screen_from_version,
    failed_calculation_from_exception,
    prepare_screen_inputs,
)

FA = {"id": "fa-valuation-001", "role": "fa"}


def _scenario(
    ebit: tuple[str, str, str],
    *,
    wacc: str,
    terminal_growth: str,
    terminal_metric: str,
    exit_multiple: str,
) -> dict:
    return {
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "terminal_metric": terminal_metric,
        "exit_multiple": exit_multiple,
        "periods": [
            {
                "period": f"FY{2026 + index}",
                "period_end": f"{2026 + index}-12-31",
                "discount_exponent": str(index),
                "ebit": value,
                "tax_rate": "0.25",
                "depreciation_amortization": "10",
                "capex": "22" if index == 1 else "20",
                "change_in_nwc": "7" if index == 1 else "5",
            }
            for index, value in enumerate(ebit, start=1)
        ],
    }


def _financial_period_payload(period: str, period_end: str, basis: str) -> dict:
    return {
        "period": period,
        "period_end": period_end,
        "basis": basis,
        "revenue": "200",
        "ebitda": "60",
        "ebit": "50",
        "tax_rate": "0.25",
        "depreciation_amortization": "10",
        "capex": "20",
        "change_in_nwc": "5",
        "fcff": "22.50",
    }


def _financial_contract_payload() -> dict:
    return {
        "historical": [
            _financial_period_payload("FY2023", "2023-12-31", "Reported"),
            _financial_period_payload("FY2024", "2024-12-31", "Reported"),
            _financial_period_payload("FY2025", "2025-12-31", "Adjusted"),
        ],
        "ltm": _financial_period_payload(
            "LTM 2026-06-30",
            "2026-06-30",
            "Adjusted",
        ),
        "forecast": [
            _financial_period_payload("FY2027E", "2027-12-31", "Management"),
            _financial_period_payload(
                "FY2028E",
                "2028-12-31",
                "Analyst Estimate",
            ),
            _financial_period_payload(
                "FY2029E",
                "2029-12-31",
                "Analyst Estimate",
            ),
        ],
    }


def _screen(
    *, confirm: bool = True, business_model: str = "mature_equipment_manufacturing"
) -> dict:
    peers = []
    for index, multiple in enumerate(("6", "7", "8", "9", "30"), start=1):
        peers.append(
            {
                "peer_id": f"peer-{index}",
                "name": f"External Peer {index}",
                "classification": "core_peer" if index < 5 else "secondary_peer",
                "rationale": "Comparable equipment mix and commercial maturity.",
                "enterprise_value": str(int(multiple) * 100),
                "ltm_ebitda": "100",
                "ltm_ebitda_period": "LTM 2026-06-30",
            }
        )
    return {
        "confirm_inputs": confirm,
        "business_model": business_model,
        "discount_convention": "period_end",
        "unit": "USDm",
        "source": {
            "source_id": "management-model-v3",
            "locator": "Forecast and bridge tabs; human-checked 2026-08-03",
            "as_of": "2026-08-03",
        },
        "scenarios": {
            "downside": _scenario(
                ("80", "90", "100"),
                wacc="0.12",
                terminal_growth="0.02",
                terminal_metric="110",
                exit_multiple="7",
            ),
            "base": _scenario(
                ("100", "110", "120"),
                wacc="0.10",
                terminal_growth="0.03",
                terminal_metric="130",
                exit_multiple="8",
            ),
            "upside": _scenario(
                ("120", "135", "150"),
                wacc="0.09",
                terminal_growth="0.035",
                terminal_metric="160",
                exit_multiple="9",
            ),
        },
        "bridge": {
            "cash_like": "100",
            "debt_like": "200",
            "non_operating_assets": "10",
            "other_claims": "5",
            "fully_diluted_shares": "50",
        },
        "trading_comps": {
            "metric": "ev_ltm_ebitda",
            "target_metric": "100",
            "target_metric_period": "LTM 2026-06-30",
            "peers": peers,
        },
    }


def _remove_discount_timing(request: dict, *, keep_period_ends: bool = False) -> dict:
    request = deepcopy(request)
    for scenario in request["scenarios"].values():
        for period in scenario["periods"]:
            period.pop("discount_exponent", None)
            if not keep_period_ends:
                period.pop("period_end", None)
    return request


def _valuation(
    tmp_path: Path,
    screen: dict,
    *,
    methods: tuple[str, ...] = ("trading_comps", "dcf_fcff"),
    valuation_date: str = "2026-08-03",
) -> tuple[DealStore, dict, dict]:
    store = DealStore(tmp_path / "deals")
    deal = store.create_deal(
        company_id="company-target-001",
        buyer="Buyer Holdings",
        target="Target CleanTech",
        transaction_scope="100% equity acquisition",
        currency="USD",
        valuation_date=valuation_date,
        owner="FA Team",
        confidentiality_level="confidential",
        actor=FA,
        reason="Create an independent transaction scope",
        idempotency_key="create-deal-valuation-workflow",
    )
    valuation = store.create_valuation_case(
        deal["deal_id"],
        target_legal_entity="Target CleanTech Co., Ltd.",
        transaction_scope="100% equity acquisition",
        valuation_date=valuation_date,
        base_currency="USD",
        methods=methods,
        actor=FA,
        reason="Open deterministic screen-grade valuation",
        idempotency_key="create-valuation-workflow",
        expected_deal_revision=deal["revision"],
        expected_deal_hash=deal["record_hash"],
    )
    inputs = prepare_screen_inputs(screen, valuation)
    version = valuation["versions"][-1]
    store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=inputs,
        actor=FA,
        reason="Confirm source-bearing screen inputs",
        idempotency_key="update-screen-inputs",
        expected_version_number=version["version_number"],
        expected_version_hash=version["version_hash"],
    )
    updated = store.get_valuation(valuation["valuation_id"])
    return store, updated, updated["versions"][-1]


def test_screen_recalculates_from_immutable_stored_inputs_deterministically(
    tmp_path: Path,
) -> None:
    store, valuation, input_version = _valuation(tmp_path, _screen())

    first = calculate_screen_from_version(valuation, input_version)
    second = calculate_screen_from_version(valuation, input_version)

    assert first == second
    share_input = next(
        item
        for item in input_version["inputs"]
        if item["input_id"] == "bridge-fully-diluted-shares"
    )
    assert share_input["unit"] == "million_shares"
    assert first["calculation_integrity"]["status"] == "passed"
    assert first["decision_readiness"]["human_review_required"] is True
    assert {item["method"] for item in first["method_ranges"]} == {
        "dcf_fcff",
        "trading_comps",
    }
    assert first["boundaries"]["secret_method_weighting_applied"] is False
    assert first["boundaries"]["formal_valuation_opinion_produced"] is False
    assert first["financial_input_contract"]["status"] == "not_provided"
    assert any("No complete 3-year history" in warning for warning in first["warnings"])
    assert first["methods"]["dcf"]["sensitivities"]["wacc_x_terminal_growth"]
    assert first["methods"]["dcf"]["sensitivities"]["wacc_x_exit_multiple"]
    calculated = store.calculate_valuation(
        valuation["valuation_id"],
        actor=FA,
        reason="Run only the trusted deterministic engine",
        idempotency_key="calculate-screen-workflow",
        expected_version_number=input_version["version_number"],
        expected_version_hash=input_version["version_hash"],
    )
    assert calculated["status"] == "calculated_screen_grade"
    assert calculated["calculation_hash"]


def test_financial_contract_is_normalized_and_recalculated_from_stored_inputs(
    tmp_path: Path,
) -> None:
    request = _screen()
    request["financials"] = _financial_contract_payload()
    request["financials"]["historical"].append(
        _financial_period_payload("FY2025", "2025-12-31", "Reported")
    )
    request["financials"]["ltm"]["revenue_source"] = {
        "source_id": "ltm-revenue-reconciliation",
        "locator": "LTM schedule, Revenue row",
        "as_of": "2026-07-15",
    }
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    contract = result["financial_input_contract"]
    assert contract["status"] == "passed"
    assert contract["historical_period_count"] == 3
    assert contract["ltm_period_count"] == 1
    assert contract["forecast_period_count"] == 3
    assert len(contract["periods"]) == 8
    assert set(contract["bases"]) == {
        "reported",
        "adjusted",
        "management",
        "analyst_estimate",
    }
    stored_revenue = next(
        item for item in version["inputs"] if item["input_id"] == "financial-historical-1-revenue"
    )
    assert stored_revenue["period_end"] == "2023-12-31"
    assert stored_revenue["financial_basis"] == "reported"
    assert stored_revenue["source_id"] == "management-model-v3"
    ltm_revenue = next(
        item for item in version["inputs"] if item["input_id"] == "financial-ltm-1-revenue"
    )
    ltm_ebitda = next(
        item for item in version["inputs"] if item["input_id"] == "financial-ltm-1-ebitda"
    )
    assert ltm_revenue["source_id"] == "ltm-revenue-reconciliation"
    assert ltm_revenue["as_of"] == "2026-07-15"
    assert ltm_ebitda["source_id"] == "management-model-v3"
    fy2025_bases = {
        item["basis"] for item in contract["periods"] if item["period_end"] == "2025-12-31"
    }
    assert fy2025_bases == {"reported", "adjusted"}
    assert "financial-ltm-1-revenue" in result["used_input_ids"]
    assert result["calculation_integrity"]["status"] == "passed"


def test_incomplete_financial_contract_is_rejected_before_storage() -> None:
    valuation_case = {"valuation_date": "2026-08-03", "base_currency": "USD"}
    request = _screen()
    request["financials"] = _financial_contract_payload()
    request["financials"]["historical"] = request["financials"]["historical"][:2]
    with pytest.raises(ValuationWorkflowError, match="at least 3 unique annual periods"):
        prepare_screen_inputs(request, valuation_case)

    request = _screen()
    request["financials"] = _financial_contract_payload()
    del request["financials"]["ltm"]["revenue"]
    with pytest.raises(ValuationWorkflowError, match="financials.ltm.revenue"):
        prepare_screen_inputs(request, valuation_case)


def test_peer_capitalization_sources_derive_trading_comps_ev(tmp_path: Path) -> None:
    request = _screen()
    for peer, multiple in zip(
        request["trading_comps"]["peers"],
        ("6", "7", "8", "9", "30"),
        strict=True,
    ):
        peer.pop("enterprise_value")
        peer.update(
            {
                "share_price": multiple,
                "share_price_period": "2026-08-03",
                "fully_diluted_shares": "100",
                "fully_diluted_shares_period": "2026-08-03",
                "cash_like": "0",
                "cash_like_period": "2026-08-03",
                "debt_like": "0",
                "debt_like_period": "2026-08-03",
            }
        )
    request["trading_comps"]["peers"][0]["share_price_source"] = {
        "source_id": "market-close-2026-08-03",
        "locator": "Exchange closing-price record",
        "as_of": "2026-08-03",
    }
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    trading = result["methods"]["trading_comps"]
    assert trading["result"]["statistics"]["median"] == "8.00"
    assert len(trading["peer_capitalizations"]) == 5
    first = trading["peer_capitalizations"][0]
    assert first["equity_value"] == "600.00"
    assert first["enterprise_value"] == "600.00"
    assert "Share Price" in first["formula"]
    share_price = next(
        item for item in version["inputs"] if item["input_id"] == "peer-peer-1-share-price"
    )
    assert share_price["unit"] == "USD_per_share"
    assert share_price["source_id"] == "market-close-2026-08-03"
    assert "peer-peer-1-share-price" in result["used_input_ids"]


def test_peer_capitalization_rejects_partial_or_ambiguous_numerator_inputs() -> None:
    valuation_case = {"valuation_date": "2026-08-03", "base_currency": "USD"}
    request = _screen()
    request["trading_comps"]["peers"][0]["share_price"] = "6"
    with pytest.raises(ValuationWorkflowError, match="capitalization is missing"):
        prepare_screen_inputs(request, valuation_case)

    request = _screen()
    request["trading_comps"]["peers"][0].update(
        {
            "share_price": "6",
            "fully_diluted_shares": "100",
            "cash_like": "0",
            "debt_like": "0",
        }
    )
    with pytest.raises(ValuationWorkflowError, match="cannot mix derived capitalization"):
        prepare_screen_inputs(request, valuation_case)


def test_candidate_inputs_cannot_activate_a_method_or_calculate(tmp_path: Path) -> None:
    _, valuation, version = _valuation(tmp_path, _screen(confirm=False))

    exponent = next(
        item
        for item in version["inputs"]
        if item["input_id"] == "base-y1-discount-exponent"
    )
    assert exponent["status"] == "candidate_input"
    assert exponent["human_confirmed"] is False
    with pytest.raises(InputGateError, match="human-confirmed"):
        calculate_screen_from_version(valuation, version)


def test_non_year_end_confirmed_dcf_without_explicit_timing_is_rejected() -> None:
    request = _remove_discount_timing(_screen())

    with pytest.raises(ValuationWorkflowError, match="source-bearing discount_exponent"):
        prepare_screen_inputs(
            request,
            {"valuation_date": "2026-06-30", "base_currency": "USD"},
        )


def test_candidate_missing_timing_can_be_stored_but_old_confirmed_inputs_fail_closed(
    tmp_path: Path,
) -> None:
    request = _remove_discount_timing(_screen(confirm=False))
    _, valuation, candidate = _valuation(
        tmp_path,
        request,
        valuation_date="2026-06-30",
    )
    assert not any(item.get("input_group") == "dcf_timing" for item in candidate["inputs"])

    bypass_attempt = deepcopy(candidate)
    for item in bypass_attempt["inputs"]:
        item["status"] = "confirmed_input"
        item["human_confirmed"] = True
        item["reviewed_by"] = FA

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_screen_from_version(valuation, bypass_attempt)
    assert captured.value.code == "discount_timing_inputs_missing"


def test_explicit_four_period_stub_timing_is_used_disclosed_and_reused(
    tmp_path: Path,
) -> None:
    request = _screen()
    for scenario in request["scenarios"].values():
        first = deepcopy(scenario["periods"][0])
        first.update(
            {
                "period": "H2 2026E",
                "period_end": "2026-12-31",
                "discount_exponent": "0.5",
            }
        )
        scenario["periods"].insert(0, first)
        for exponent, period in zip(
            ("1.5", "2.5", "3.5"),
            scenario["periods"][1:],
            strict=True,
        ):
            period["discount_exponent"] = exponent
    _, valuation, version = _valuation(
        tmp_path,
        request,
        valuation_date="2026-06-30",
    )

    result = calculate_screen_from_version(valuation, version)

    assert result["screen_schema_version"] == "1.2"
    timing = result["methods"]["dcf"]["discount_timing"]
    assert timing["basis"] == "explicit_per_period"
    assert timing["scenario_consistent"] is True
    assert [row["period_end"] for row in timing["scenarios"]["base"]] == [
        "2026-12-31",
        "2027-12-31",
        "2028-12-31",
        "2029-12-31",
    ]
    assert [row["discount_exponent"] for row in timing["scenarios"]["base"]] == [
        "0.5",
        "1.5",
        "2.5",
        "3.5",
    ]
    base = next(
        item
        for item in result["methods"]["dcf"]["suite"]["scenario_results"]
        if item["scenario"] == "base"
    )
    assert [item["period_end"] for item in base["projections"]] == [
        "2026-12-31",
        "2027-12-31",
        "2028-12-31",
        "2029-12-31",
    ]
    assert [item["discount_exponent"] for item in base["projections"]] == [
        "0.5",
        "1.5",
        "2.5",
        "3.5",
    ]
    growth_sensitivity = result["methods"]["dcf"]["sensitivities"][
        "wacc_x_terminal_growth"
    ]
    base_row = next(row for row in growth_sensitivity["rows"] if row["row_value"] == "0.100000")
    growth_index = growth_sensitivity["column_values"].index("0.030000")
    assert base_row["cells"][growth_index]["enterprise_value"] == base[
        "enterprise_value_perpetuity"
    ]
    exit_sensitivity = result["methods"]["dcf"]["sensitivities"][
        "wacc_x_exit_multiple"
    ]
    exit_row = next(row for row in exit_sensitivity["rows"] if row["row_value"] == "0.100000")
    multiple_index = exit_sensitivity["column_values"].index("8")
    assert exit_row["cells"][multiple_index]["enterprise_value"] == base[
        "enterprise_value_exit_multiple"
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda request: request["scenarios"]["base"]["periods"][1].pop("discount_exponent"), "every period"),
        (lambda request: request["scenarios"]["base"]["periods"][0].__setitem__("discount_exponent", "0"), "greater than zero"),
        (lambda request: request["scenarios"]["base"]["periods"][1].__setitem__("discount_exponent", "1"), "strictly increasing"),
        (lambda request: request["scenarios"]["upside"]["periods"][0].__setitem__("discount_exponent", "0.75"), "must align"),
        (lambda request: request["scenarios"]["upside"]["periods"][0].__setitem__("period_end", "2027-06-30"), "must align"),
    ),
)
def test_invalid_or_conflicting_discount_timing_is_rejected(
    mutation: object,
    message: str,
) -> None:
    request = _screen()
    mutation(request)  # type: ignore[operator]

    with pytest.raises(ValuationWorkflowError, match=message):
        prepare_screen_inputs(
            request,
            {"valuation_date": "2026-06-30", "base_currency": "USD"},
        )


def test_legacy_positional_timing_requires_confirmed_structured_year_ends(
    tmp_path: Path,
) -> None:
    request = _remove_discount_timing(_screen(), keep_period_ends=True)
    _, valuation, version = _valuation(
        tmp_path,
        request,
        valuation_date="2026-12-31",
    )

    result = calculate_screen_from_version(valuation, version)

    assert result["methods"]["dcf"]["discount_timing"]["basis"] == (
        "validated_annual_period_end"
    )
    base = next(
        item
        for item in result["methods"]["dcf"]["suite"]["scenario_results"]
        if item["scenario"] == "base"
    )
    assert [item["discount_exponent"] for item in base["projections"]] == [
        "1",
        "2",
        "3",
    ]

    free_text_only = _remove_discount_timing(_screen())
    with pytest.raises(ValuationWorkflowError, match="source-bearing discount_exponent"):
        prepare_screen_inputs(
            free_text_only,
            {"valuation_date": "2026-12-31", "base_currency": "USD"},
        )


def test_wacc_not_above_growth_materializes_a_hard_failure_snapshot(
    tmp_path: Path,
) -> None:
    request = _screen()
    request["scenarios"]["base"]["wacc"] = "0.03"
    request["scenarios"]["base"]["terminal_growth"] = "0.03"
    _, valuation, version = _valuation(tmp_path, request)

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_screen_from_version(valuation, version)

    failure = failed_calculation_from_exception(valuation, version, captured.value)
    assert failure["calculation_integrity"]["status"] == "failed"
    assert failure["decision_readiness"]["status"] == "not_ready"
    assert failure["hard_failures"] == [captured.value.code]
    assert failure["methods"] == {}


def test_duplicate_forecast_period_is_a_hard_failure(tmp_path: Path) -> None:
    request = _screen()
    for period in request["scenarios"]["base"]["periods"]:
        period["period"] = "FY2027"
    _, valuation, version = _valuation(tmp_path, request)

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_screen_from_version(valuation, version)

    assert captured.value.code == "duplicate_forecast_period"


def test_stale_input_dates_are_visible_readiness_warnings(tmp_path: Path) -> None:
    request = _screen()
    request["source"]["as_of"] = "2018-01-01"
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    assert any("365 days" in warning for warning in result["warnings"])
    assert result["calculation_integrity"]["status"] == "passed"


def test_negative_bridge_magnitude_is_a_hard_failure(tmp_path: Path) -> None:
    request = _screen()
    request["bridge"]["debt_like"] = "-200"
    _, valuation, version = _valuation(tmp_path, request)

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_screen_from_version(valuation, version)

    assert captured.value.code == "invalid_bridge_sign"


def test_non_positive_target_metric_is_nm_and_does_not_create_a_range(
    tmp_path: Path,
) -> None:
    request = _screen()
    request["trading_comps"]["target_metric"] = "-10"
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    trading = result["methods"]["trading_comps"]
    assert trading["target_metric_status"] == "N/M"
    assert trading["implied_range"] is None
    assert [item["method"] for item in result["method_ranges"]] == ["dcf_fcff"]
    assert any("N/M" in warning for warning in result["warnings"])


def test_fewer_than_five_comps_do_not_create_percentiles_or_implied_range(
    tmp_path: Path,
) -> None:
    request = _screen()
    request["trading_comps"]["peers"] = request["trading_comps"]["peers"][:4]
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    trading = result["methods"]["trading_comps"]
    statistics = trading["result"]["statistics"]
    assert statistics["sample_count"] == 4
    assert statistics["median"] == "7.50"
    assert statistics["p25"] is None
    assert statistics["p75"] is None
    assert statistics["reasonable_range_low"] is None
    assert statistics["reasonable_range_high"] is None
    assert trading["implied_range"] is None
    assert [item["method"] for item in result["method_ranges"]] == ["dcf_fcff"]
    assert any("at least five" in warning for warning in result["warnings"])


def test_price_earnings_range_is_labeled_as_equity_value(tmp_path: Path) -> None:
    request = _screen()
    request["trading_comps"]["metric"] = "price_earnings"
    request["trading_comps"]["target_metric"] = "10"
    for peer in request["trading_comps"]["peers"]:
        peer["equity_value"] = peer.pop("enterprise_value")
        peer["ltm_net_income"] = peer.pop("ltm_ebitda")
        peer["ltm_net_income_period"] = peer.pop("ltm_ebitda_period")
    _, valuation, version = _valuation(tmp_path, request)

    result = calculate_screen_from_version(valuation, version)

    implied = result["methods"]["trading_comps"]["implied_range"]
    assert implied["value_basis"] == "equity_value"
    assert implied["equity_value_low"] == implied["value_low"]
    assert "enterprise_value_low" not in implied
    method_range = next(
        item for item in result["method_ranges"] if item["method"] == "trading_comps"
    )
    assert method_range["value_basis"] == "equity_value"


@pytest.mark.parametrize(
    ("selected_methods", "expected_method"),
    (("dcf_fcff", "dcf"), ("trading_comps", "trading_comps")),
)
def test_only_selected_methods_are_calculated(
    tmp_path: Path,
    selected_methods: str,
    expected_method: str,
) -> None:
    _, valuation, version = _valuation(
        tmp_path,
        _screen(),
        methods=(selected_methods,),
    )

    result = calculate_screen_from_version(valuation, version)

    assert set(result["methods"]) == {expected_method}
    if selected_methods == "dcf_fcff":
        assert not any(input_id.startswith("peer-") for input_id in result["used_input_ids"])
    else:
        assert not any("-y1-" in input_id for input_id in result["used_input_ids"])


@pytest.mark.parametrize(
    "business_model",
    ("project_developer_operating_asset", "pre_commercial_technology"),
)
def test_p0_fail_closed_for_unsupported_business_models(
    tmp_path: Path, business_model: str
) -> None:
    _, valuation, version = _valuation(
        tmp_path,
        _screen(business_model=business_model),
    )

    result = calculate_screen_from_version(valuation, version)

    assert result["applicability"]["p0_supported"] is False
    assert result["methods"] == {}
    assert result["method_ranges"] == []
    assert result["decision_readiness"]["status"] == "not_ready"


def test_unsupported_business_model_does_not_require_irrelevant_corporate_dcf_inputs() -> None:
    inputs = prepare_screen_inputs(
        {
            "confirm_inputs": True,
            "business_model": "project_developer_operating_asset",
            "discount_convention": "period_end",
            "unit": "USDm",
            "source": {
                "source_id": "human-business-model-review",
                "locator": "FA routing memo, page 1",
                "as_of": "2026-08-03",
            },
        },
        {"valuation_date": "2026-08-03", "base_currency": "USD"},
    )

    assert [item["input_id"] for item in inputs] == [
        "config-business-model",
        "config-discount-convention",
    ]


def test_loss_making_but_revenue_generating_company_uses_revenue_comps(
    tmp_path: Path,
) -> None:
    request = _screen(business_model="early_commercial")
    request["scenarios"]["downside"]["periods"] = _scenario(
        ("-40", "-20", "10"),
        wacc="0.12",
        terminal_growth="0.02",
        terminal_metric="20",
        exit_multiple="7",
    )["periods"]
    request["scenarios"]["base"]["periods"] = _scenario(
        ("-30", "0", "30"),
        wacc="0.10",
        terminal_growth="0.03",
        terminal_metric="40",
        exit_multiple="8",
    )["periods"]
    request["scenarios"]["upside"]["periods"] = _scenario(
        ("-20", "20", "50"),
        wacc="0.09",
        terminal_growth="0.035",
        terminal_metric="60",
        exit_multiple="9",
    )["periods"]
    request["trading_comps"]["metric"] = "ev_ltm_revenue"
    request["trading_comps"]["target_metric"] = "200"
    for peer in request["trading_comps"]["peers"]:
        peer["ltm_revenue"] = peer.pop("ltm_ebitda")
        peer["ltm_revenue_period"] = peer.pop("ltm_ebitda_period")

    _, valuation, version = _valuation(tmp_path, request)
    result = calculate_screen_from_version(valuation, version)

    assert result["applicability"]["status"] == "applicable"
    assert result["hard_failures"] == []
    assert result["methods"]["trading_comps"]["result"]["metric"] == ("ev_ltm_revenue")
    assert result["methods"]["dcf"]["suite"]["scenario_results"][0]["projections"][0][
        "fcff"
    ].startswith("-")


def test_float_payloads_and_partial_forecasts_are_rejected_before_storage() -> None:
    request = _screen()
    valuation_case = {"valuation_date": "2026-08-03", "base_currency": "USD"}
    request["scenarios"]["base"]["wacc"] = 0.10
    with pytest.raises(ValuationWorkflowError, match="floats are forbidden"):
        prepare_screen_inputs(request, valuation_case)

    request = deepcopy(_screen())
    request["scenarios"]["base"]["periods"] = request["scenarios"]["base"]["periods"][:2]
    with pytest.raises(ValuationWorkflowError, match="3 to 5 forecast years"):
        prepare_screen_inputs(request, valuation_case)

    request = _screen()
    request["scenarios"]["base"]["periods"][0]["ebit"] = "1e100"
    with pytest.raises(ValuationWorkflowError, match="precision or magnitude"):
        prepare_screen_inputs(request, valuation_case)


def test_share_count_scale_must_match_amount_scale(tmp_path: Path) -> None:
    request = _screen()
    request["share_unit"] = "shares"
    _, valuation, version = _valuation(tmp_path, request)

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_screen_from_version(valuation, version)

    assert captured.value.code == "share_unit_conflict"


def test_unknown_amount_unit_is_rejected_before_storage() -> None:
    request = _screen()
    request["unit"] = "bananas"

    with pytest.raises(ValuationWorkflowError, match="unscaled, million, or billion"):
        prepare_screen_inputs(
            request,
            {"valuation_date": "2026-08-03", "base_currency": "USD"},
        )
