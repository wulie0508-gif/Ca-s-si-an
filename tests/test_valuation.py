from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from cleantech_finance.valuation import (
    CheckScope,
    CheckStatus,
    CleanTechBusinessModel,
    DCFScenario,
    DiscountConvention,
    EVToEquityBridge,
    FCFFPeriod,
    FinancialBasis,
    FinancialPeriodType,
    FinancialStatementPeriod,
    InputGateError,
    InputStatus,
    ModelCheck,
    MultipleMetric,
    MultipleStatus,
    PeerCapitalization,
    PeerClassification,
    PeerCompany,
    ScenarioName,
    ValuationError,
    ValuationHardFailure,
    ValuationInput,
    WACCComponents,
    assess_valuation_status,
    calculate_dcf_scenario,
    calculate_dcf_suite,
    calculate_ev_to_equity,
    calculate_fcff,
    calculate_implied_enterprise_value,
    calculate_peer_capitalization,
    calculate_trading_comps,
    calculate_wacc,
    gate_valuation_inputs,
    round_decimal,
    route_cleantech_valuation,
    validate_financial_input_contract,
    wacc_exit_multiple_sensitivity,
    wacc_growth_sensitivity,
)


def _input(
    input_id: str,
    value: str | int | Decimal,
    *,
    unit: str = "USDm",
    currency: str = "USD",
    status: InputStatus = InputStatus.HUMAN_CONFIRMED,
    period: str = "FY2026",
) -> ValuationInput:
    return ValuationInput(
        input_id=input_id,
        value=value,
        source_id=f"source:{input_id}",
        locator=f"Inputs!{input_id}",
        period=period,
        currency=currency,
        unit=unit,
        as_of="2026-08-03",
        entered_by="analyst",
        status=status,
        reviewed_by="fa-reviewer" if status is InputStatus.HUMAN_CONFIRMED else None,
    )


def _rate(input_id: str, value: str) -> ValuationInput:
    return _input(input_id, value, unit="ratio", currency="N/A")


def _multiple(input_id: str, value: str) -> ValuationInput:
    return _input(input_id, value, unit="multiple", currency="N/A")


def _period(prefix: str, period_number: int, ebit: str) -> FCFFPeriod:
    period = f"FY{2026 + period_number}"
    return FCFFPeriod(
        period=period,
        ebit=_input(f"{prefix}:ebit:{period_number}", ebit, period=period),
        tax_rate=_rate(f"{prefix}:tax:{period_number}", "0.25"),
        depreciation_amortization=_input(
            f"{prefix}:da:{period_number}",
            "10",
            period=period,
        ),
        capex=_input(f"{prefix}:capex:{period_number}", "20", period=period),
        change_in_nwc=_input(f"{prefix}:nwc:{period_number}", "5", period=period),
    )


def _financial_period(
    period: str,
    period_end: str,
    period_type: FinancialPeriodType,
    basis: FinancialBasis,
    *,
    prefix: str,
    fcff: str = "22.50",
) -> FinancialStatementPeriod:
    return FinancialStatementPeriod(
        period=period,
        period_end=period_end,
        period_type=period_type,
        basis=basis,
        revenue=_input(f"{prefix}:revenue", "200", period=period),
        ebitda=_input(f"{prefix}:ebitda", "60", period=period),
        ebit=_input(f"{prefix}:ebit", "50", period=period),
        tax_rate=_input(
            f"{prefix}:tax-rate",
            "0.25",
            unit="ratio",
            currency="N/A",
            period=period,
        ),
        depreciation_amortization=_input(f"{prefix}:da", "10", period=period),
        capex=_input(f"{prefix}:capex", "20", period=period),
        change_in_nwc=_input(f"{prefix}:nwc", "5", period=period),
        fcff=_input(f"{prefix}:fcff", fcff, period=period),
    )


def _complete_financial_contract() -> tuple[FinancialStatementPeriod, ...]:
    return (
        _financial_period(
            "FY2023",
            "2023-12-31",
            FinancialPeriodType.HISTORICAL,
            FinancialBasis.REPORTED,
            prefix="fy2023",
        ),
        _financial_period(
            "FY2024",
            "2024-12-31",
            FinancialPeriodType.HISTORICAL,
            FinancialBasis.REPORTED,
            prefix="fy2024",
        ),
        _financial_period(
            "FY2025",
            "2025-12-31",
            FinancialPeriodType.HISTORICAL,
            FinancialBasis.ADJUSTED,
            prefix="fy2025",
        ),
        _financial_period(
            "LTM 2026-06-30",
            "2026-06-30",
            FinancialPeriodType.LTM,
            FinancialBasis.ADJUSTED,
            prefix="ltm",
        ),
        _financial_period(
            "FY2027E",
            "2027-12-31",
            FinancialPeriodType.FORECAST,
            FinancialBasis.MANAGEMENT,
            prefix="fy2027e",
        ),
        _financial_period(
            "FY2028E",
            "2028-12-31",
            FinancialPeriodType.FORECAST,
            FinancialBasis.ANALYST_ESTIMATE,
            prefix="fy2028e",
        ),
        _financial_period(
            "FY2029E",
            "2029-12-31",
            FinancialPeriodType.FORECAST,
            FinancialBasis.ANALYST_ESTIMATE,
            prefix="fy2029e",
        ),
    )


def _scenario(
    name: ScenarioName,
    ebit_values: tuple[str, str, str] = ("100", "110", "120"),
    *,
    wacc: str = "0.10",
    terminal_growth: str = "0.03",
    convention: DiscountConvention = DiscountConvention.PERIOD_END,
    with_exit_cross_check: bool = True,
) -> DCFScenario:
    prefix = name.value
    return DCFScenario(
        name=name,
        periods=tuple(
            _period(prefix, index, ebit) for index, ebit in enumerate(ebit_values, start=1)
        ),
        terminal_growth_rate=_rate(f"{prefix}:terminal-growth", terminal_growth),
        currency="USD",
        unit="USDm",
        discount_convention=convention,
        direct_wacc=_rate(f"{prefix}:wacc", wacc),
        terminal_metric=(
            _input(f"{prefix}:terminal-ebitda", "130", period="FY2029")
            if with_exit_cross_check
            else None
        ),
        exit_multiple=(
            _multiple(f"{prefix}:exit-multiple", "8") if with_exit_cross_check else None
        ),
    )


def _peer(
    peer_id: str,
    multiple: str | None,
    *,
    classification: PeerClassification = PeerClassification.CORE,
    denominator: str = "100",
    target_baseline: bool = False,
) -> PeerCompany:
    return PeerCompany(
        peer_id=peer_id,
        name=f"Peer {peer_id}",
        classification=classification,
        rationale=f"Documented rationale for {peer_id}",
        enterprise_value=(
            _input(f"{peer_id}:ev", Decimal(multiple) * Decimal(denominator))
            if multiple is not None
            else _input(f"{peer_id}:ev", "500")
        ),
        ltm_ebitda=(_input(f"{peer_id}:ebitda", denominator) if multiple is not None else None),
        is_target_baseline=target_baseline,
    )


def test_decimal_policy_is_explicit_and_binary_floats_are_rejected() -> None:
    assert round_decimal("1.005") == Decimal("1.01")
    with pytest.raises(TypeError, match="binary floats are forbidden"):
        round_decimal(1.005)
    with pytest.raises(TypeError, match="binary floats are forbidden"):
        _input("float", 1.25)  # type: ignore[arg-type]
    with pytest.raises(ValuationError, match="precision or magnitude"):
        _input("unbounded", "1e100")


def test_input_gate_distinguishes_candidate_missing_and_duplicate_inputs() -> None:
    candidate = _input("revenue", "100", status=InputStatus.CANDIDATE)
    duplicate = _input("revenue", "101")
    result = gate_valuation_inputs(
        [candidate, duplicate],
        ["revenue", "ebitda"],
    )

    assert result.status == "blocked"
    assert result.candidate_input_ids == ("revenue",)
    assert result.missing_input_ids == ("ebitda",)
    assert result.duplicate_input_ids == ("revenue",)
    assert {check.status for check in result.checks} == {
        CheckStatus.FAILED,
    }


def test_candidate_input_cannot_enter_formula() -> None:
    period = _period("candidate", 1, "100")
    period = replace(
        period,
        ebit=_input("candidate:ebit", "100", status=InputStatus.CANDIDATE),
    )

    with pytest.raises(InputGateError, match="only human_confirmed"):
        calculate_fcff(period, currency="USD", unit="USDm")


def test_ev_bridge_preserves_ev_but_suppresses_equity_when_bridge_missing() -> None:
    result = calculate_ev_to_equity(
        "1000",
        currency="USD",
        unit="USDm",
        bridge=None,
    )

    assert result.enterprise_value == Decimal("1000.00")
    assert result.equity_value is None
    assert result.per_share_value is None
    assert result.status == "enterprise_value_only"
    assert result.checks[0].scope is CheckScope.READINESS
    assert result.checks[0].status is CheckStatus.FAILED


def test_ev_to_equity_bridge_and_per_share_value_are_formula_driven() -> None:
    bridge = EVToEquityBridge(
        cash_like_items=(_input("cash", "120"),),
        debt_like_items=(
            _input("debt", "250"),
            _input("lease", "30"),
        ),
        non_operating_asset_items=(_input("associate", "20"),),
        other_claim_items=(
            _input("minority", "15"),
            _input("pension", "5"),
        ),
    )

    result = calculate_ev_to_equity(
        "1000",
        currency="USD",
        unit="USDm",
        bridge=bridge,
        fully_diluted_shares=_input(
            "fully-diluted-shares",
            "100",
            unit="million_shares",
            currency="N/A",
        ),
    )

    assert result.cash_like == Decimal("120.00")
    assert result.debt_like == Decimal("280.00")
    assert result.non_operating_assets == Decimal("20.00")
    assert result.other_claims == Decimal("20.00")
    assert result.equity_value == Decimal("840.00")
    assert result.per_share_value == Decimal("8.40")
    assert result.input_ids == tuple(sorted(result.input_ids))
    assert all(check.status is CheckStatus.PASSED for check in result.checks)


def test_ev_bridge_rejects_negative_magnitudes() -> None:
    bridge = EVToEquityBridge(
        cash_like_items=(_input("cash", "100"),),
        debt_like_items=(_input("debt", "-200"),),
    )

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_ev_to_equity(
            "1000",
            currency="USD",
            unit="USDm",
            bridge=bridge,
        )

    assert captured.value.code == "invalid_bridge_sign"


def test_ev_bridge_rejects_candidate_and_currency_conflicts() -> None:
    candidate_bridge = EVToEquityBridge(
        cash_like_items=(_input("cash", "10", status=InputStatus.CANDIDATE),),
        debt_like_items=(_input("debt", "20"),),
    )
    with pytest.raises(InputGateError):
        calculate_ev_to_equity(
            "100",
            currency="USD",
            unit="USDm",
            bridge=candidate_bridge,
        )

    currency_bridge = EVToEquityBridge(
        cash_like_items=(_input("cash-eur", "10", currency="EUR"),),
        debt_like_items=(_input("debt-usd", "20"),),
    )
    with pytest.raises(ValuationHardFailure) as error:
        calculate_ev_to_equity(
            "100",
            currency="USD",
            unit="USDm",
            bridge=currency_bridge,
        )
    assert error.value.code == "currency_conflict"


def test_complete_financial_input_contract_covers_history_ltm_forecast_and_bases() -> None:
    result = validate_financial_input_contract(
        _complete_financial_contract(),
        currency="USD",
        unit="USDm",
    )

    assert result.status == "passed"
    assert result.historical_period_count == 3
    assert result.ltm_period_count == 1
    assert result.forecast_period_count == 3
    assert set(result.bases) == {
        FinancialBasis.REPORTED,
        FinancialBasis.ADJUSTED,
        FinancialBasis.MANAGEMENT,
        FinancialBasis.ANALYST_ESTIMATE,
    }
    assert len(result.input_ids) == 56
    assert all(check.status is CheckStatus.PASSED for check in result.checks)


def test_financial_contract_allows_multiple_bases_for_the_same_period() -> None:
    periods = (
        *_complete_financial_contract(),
        _financial_period(
            "FY2025",
            "2025-12-31",
            FinancialPeriodType.HISTORICAL,
            FinancialBasis.REPORTED,
            prefix="fy2025-reported",
        ),
    )

    result = validate_financial_input_contract(periods, currency="USD", unit="USDm")

    assert result.status == "passed"
    assert result.historical_period_count == 3
    assert len(result.periods) == 8
    assert {
        item.basis for item in result.periods if item.period_end.isoformat() == "2025-12-31"
    } == {FinancialBasis.REPORTED, FinancialBasis.ADJUSTED}


def test_financial_input_contract_exposes_fcff_formula_failure() -> None:
    periods = list(_complete_financial_contract())
    periods[-1] = replace(
        periods[-1],
        fcff=_input("fy2029e:fcff:mismatch", "999", period="FY2029E"),
    )

    result = validate_financial_input_contract(tuple(periods), currency="USD", unit="USDm")

    assert result.status == "failed"
    check = next(
        item for item in result.checks if item.check_id == "financial_fcff_formula_reconciles"
    )
    assert check.status is CheckStatus.FAILED
    assert "FY2029E" in check.message


def test_peer_capitalization_derives_equity_and_ev_from_source_inputs() -> None:
    capitalization = PeerCapitalization(
        share_price=_input("peer-price", "12.50", unit="USD_per_share"),
        fully_diluted_shares=_input(
            "peer-shares",
            "100",
            unit="million_shares",
            currency="N/A",
        ),
        cash_like_items=(_input("peer-cash", "100"),),
        debt_like_items=(_input("peer-debt", "300"),),
        non_operating_asset_items=(_input("peer-non-op", "10"),),
        other_claim_items=(_input("peer-claims", "20"),),
    )

    result = calculate_peer_capitalization(
        capitalization,
        currency="USD",
        amount_unit="USDm",
        share_unit="million_shares",
    )

    assert result.equity_value == Decimal("1250.00")
    assert result.enterprise_value == Decimal("1460.00")
    assert result.input_ids == (
        "peer-cash",
        "peer-claims",
        "peer-debt",
        "peer-non-op",
        "peer-price",
        "peer-shares",
    )
    assert all(check.status is CheckStatus.PASSED for check in result.checks)


def test_peer_capitalization_rejects_candidate_source_input() -> None:
    capitalization = PeerCapitalization(
        share_price=_input(
            "peer-price",
            "12.50",
            unit="USD_per_share",
            status=InputStatus.CANDIDATE,
        ),
        fully_diluted_shares=_input("peer-shares", "100", unit="million_shares"),
        cash_like_items=(_input("peer-cash", "0"),),
        debt_like_items=(_input("peer-debt", "0"),),
    )

    with pytest.raises(InputGateError, match="human-confirmed"):
        calculate_peer_capitalization(
            capitalization,
            currency="USD",
            amount_unit="USDm",
            share_unit="million_shares",
        )


def test_trading_comps_classification_statistics_and_defensible_range() -> None:
    peers = [
        _peer("p1", "2"),
        _peer("p2", "3"),
        _peer("p3", "4"),
        _peer("p4", "5", classification=PeerClassification.SECONDARY),
        _peer("p5", "100"),
        _peer("target", "6", target_baseline=True),
        _peer("asp", "7", classification=PeerClassification.ASPIRATIONAL),
        PeerCompany(
            "excluded",
            "Excluded Peer",
            PeerClassification.EXCLUDED,
            "Different asset perimeter",
        ),
    ]

    result = calculate_trading_comps(peers, MultipleMetric.EV_LTM_EBITDA)

    assert result.statistics.sample_count == 5
    assert result.statistics.median == Decimal("4.00")
    assert result.statistics.p25 == Decimal("3.00")
    assert result.statistics.p75 == Decimal("5.00")
    assert result.statistics.mean == Decimal("22.80")
    assert result.statistics.outlier_peer_ids == ("p5",)
    assert result.statistics.reasonable_range_low == Decimal("2.75")
    assert result.statistics.reasonable_range_high == Decimal("4.25")
    by_id = {item.peer_id: item for item in result.observations}
    assert by_id["target"].value == Decimal("6.00")
    assert by_id["target"].included_in_statistics is False
    assert by_id["asp"].included_in_statistics is False
    assert by_id["excluded"].status is MultipleStatus.EXCLUDED
    assert "no method weighting" in result.boundary


def test_negative_near_zero_and_missing_comps_denominators_are_nm_or_na() -> None:
    peers = [
        _peer("negative", "4", denominator="-100"),
        _peer("near-zero", "4", denominator="0.0000001"),
        _peer("missing", None),
    ]

    result = calculate_trading_comps(peers, MultipleMetric.EV_LTM_EBITDA)
    by_id = {item.peer_id: item for item in result.observations}

    assert by_id["negative"].status is MultipleStatus.NOT_MEANINGFUL
    assert by_id["negative"].display_value == "N/M"
    assert by_id["near-zero"].status is MultipleStatus.NOT_MEANINGFUL
    assert by_id["missing"].status is MultipleStatus.NOT_AVAILABLE
    assert by_id["missing"].display_value == "N/A"
    assert result.statistics.sample_count == 0
    assert result.statistics.reasonable_range_low is None


def test_small_peer_sample_keeps_descriptive_stats_but_suppresses_percentiles() -> None:
    result = calculate_trading_comps(
        [_peer("p1", "2"), _peer("p2", "3"), _peer("p3", "4")],
        MultipleMetric.EV_LTM_EBITDA,
    )

    sample_check = next(
        check for check in result.checks if check.check_id == "selected_peer_sample_size"
    )
    assert sample_check.scope is CheckScope.READINESS
    assert sample_check.status is CheckStatus.WARNING
    assert result.statistics.sample_count == 3
    assert result.statistics.median == Decimal("3.00")
    assert result.statistics.mean == Decimal("3.00")
    assert result.statistics.p25 is None
    assert result.statistics.p75 is None
    assert result.statistics.reasonable_range_low is None
    assert result.statistics.reasonable_range_high is None
    assert (
        result.statistics.range_method
        == "unavailable_fewer_than_five_valid_selected_external_peers"
    )


def test_comps_require_rationale_and_human_confirmed_values() -> None:
    with pytest.raises(ValuationError, match="peer rationale"):
        PeerCompany("peer", "Peer", PeerClassification.CORE, "")

    peer = _peer("candidate", "4")
    peer = replace(
        peer,
        ltm_ebitda=_input("candidate-ebitda", "100", status=InputStatus.CANDIDATE),
    )
    with pytest.raises(InputGateError):
        calculate_trading_comps([peer], MultipleMetric.EV_LTM_EBITDA)


def test_selected_multiple_is_manual_confirmed_and_unweighted() -> None:
    implied_ev = calculate_implied_enterprise_value(
        _multiple("selected-multiple", "4.25"),
        _input("target-ltm-ebitda", "80"),
    )
    assert implied_ev == Decimal("340.00")

    with pytest.raises(InputGateError):
        calculate_implied_enterprise_value(
            _input(
                "candidate-multiple",
                "4.25",
                unit="multiple",
                currency="N/A",
                status=InputStatus.CANDIDATE,
            ),
            _input("target-ltm-ebitda", "80"),
        )

    with pytest.raises(ValuationHardFailure) as captured:
        calculate_implied_enterprise_value(
            _multiple("selected-multiple", "4.25"),
            _input("target-ltm-ebitda", "-10"),
        )
    assert captured.value.code == "target_metric_not_meaningful"


def test_component_wacc_has_a_gold_formula_and_direct_wacc_is_supported() -> None:
    components = WACCComponents(
        risk_free_rate=_rate("risk-free", "0.04"),
        beta=_multiple("beta", "1.2"),
        equity_risk_premium=_rate("erp", "0.05"),
        size_premium=_rate("size-premium", "0.01"),
        country_risk_premium=_rate("country-premium", "0.005"),
        pre_tax_cost_of_debt=_rate("cost-of-debt", "0.06"),
        equity_weight=_rate("equity-weight", "0.70"),
        debt_weight=_rate("debt-weight", "0.30"),
        tax_rate=_rate("wacc-tax", "0.25"),
    )

    calculated = calculate_wacc(components=components)
    direct = calculate_wacc(direct_wacc=_rate("direct-wacc", "0.094"))

    assert calculated.cost_of_equity == Decimal("0.115000")
    assert calculated.wacc == Decimal("0.094000")
    assert calculated.method == "component_wacc"
    assert direct.wacc == Decimal("0.094000")
    assert direct.method == "direct_confirmed_wacc"


def test_wacc_requires_one_method_and_balanced_capital_structure() -> None:
    with pytest.raises(ValuationHardFailure) as error:
        calculate_wacc()
    assert error.value.code == "wacc_method_ambiguous"

    components = WACCComponents(
        risk_free_rate=_rate("rf", "0.04"),
        beta=_multiple("beta", "1"),
        equity_risk_premium=_rate("erp", "0.05"),
        size_premium=_rate("size", "0"),
        country_risk_premium=_rate("country", "0"),
        pre_tax_cost_of_debt=_rate("debt-cost", "0.06"),
        equity_weight=_rate("equity", "0.80"),
        debt_weight=_rate("debt", "0.30"),
        tax_rate=_rate("tax", "0.25"),
    )
    with pytest.raises(ValuationHardFailure) as error:
        calculate_wacc(components=components)
    assert error.value.code == "capital_structure_weights_do_not_sum_to_one"


def test_component_wacc_allows_an_explicit_all_equity_structure() -> None:
    components = WACCComponents(
        risk_free_rate=_rate("all-equity-rf", "0.04"),
        beta=_multiple("all-equity-beta", "1"),
        equity_risk_premium=_rate("all-equity-erp", "0.05"),
        size_premium=_rate("all-equity-size", "0"),
        country_risk_premium=_rate("all-equity-country", "0"),
        pre_tax_cost_of_debt=_rate("all-equity-debt-cost", "0.06"),
        equity_weight=_rate("all-equity-equity-weight", "1"),
        debt_weight=_rate("all-equity-debt-weight", "0"),
        tax_rate=_rate("all-equity-tax", "0.25"),
    )

    result = calculate_wacc(components=components)

    assert result.cost_of_equity == Decimal("0.090000")
    assert result.wacc == Decimal("0.090000")


def test_fcff_formula_is_deterministic_and_uses_positive_capex_magnitude() -> None:
    period = FCFFPeriod(
        "FY2027",
        ebit=_input("ebit", "100"),
        tax_rate=_rate("tax", "0.25"),
        depreciation_amortization=_input("da", "10"),
        capex=_input("capex", "20"),
        change_in_nwc=_input("nwc", "5"),
    )

    assert calculate_fcff(period, currency="USD", unit="USDm") == Decimal("60.00")

    with pytest.raises(ValuationHardFailure) as error:
        calculate_fcff(
            replace(period, capex=_input("negative-capex", "-20")),
            currency="USD",
            unit="USDm",
        )
    assert error.value.code == "invalid_fcff_sign_convention"


def test_period_end_dcf_gold_case_and_exit_multiple_cross_check() -> None:
    result = calculate_dcf_scenario(_scenario(ScenarioName.BASE))

    assert [projection.fcff for projection in result.projections] == [
        Decimal("60.00"),
        Decimal("67.50"),
        Decimal("75.00"),
    ]
    assert result.present_value_explicit_fcff == Decimal("166.68")
    assert result.terminal_value_perpetuity == Decimal("1103.57")
    assert result.present_value_terminal == Decimal("829.13")
    assert result.enterprise_value_perpetuity == Decimal("995.81")
    assert result.terminal_value_exit_multiple == Decimal("1040.00")
    assert result.enterprise_value_exit_multiple == Decimal("948.05")
    assert result.exit_cross_check_difference == Decimal("-0.047963")
    assert result.discount_convention is DiscountConvention.PERIOD_END
    assert all(check.status is not CheckStatus.FAILED for check in result.checks)


def test_mid_year_discounting_is_explicit_and_increases_value() -> None:
    period_end = calculate_dcf_scenario(_scenario(ScenarioName.BASE))
    mid_year = calculate_dcf_scenario(
        _scenario(
            ScenarioName.BASE,
            convention=DiscountConvention.MID_YEAR,
        )
    )

    assert mid_year.discount_convention is DiscountConvention.MID_YEAR
    assert mid_year.projections[0].discount_exponent == Decimal("0.5")
    assert mid_year.enterprise_value_perpetuity > period_end.enterprise_value_perpetuity


def test_source_bearing_fractional_discount_exponents_control_fcff_and_terminal_pv() -> None:
    scenario = _scenario(ScenarioName.BASE)
    timed_periods = tuple(
        replace(
            period,
            period_end=date(2026 + index, 12, 31),
            discount_exponent=_input(
                f"timing:{index}",
                exponent,
                unit="years",
                currency="N/A",
                period=period.period,
            ),
        )
        for index, (period, exponent) in enumerate(
            zip(scenario.periods, ("1.5", "2.5", "3.5"), strict=True),
            start=1,
        )
    )

    result = calculate_dcf_scenario(replace(scenario, periods=timed_periods))

    assert result.discount_timing_basis == "explicit_per_period"
    assert [projection.period_end for projection in result.projections] == [
        date(2027, 12, 31),
        date(2028, 12, 31),
        date(2029, 12, 31),
    ]
    assert [projection.discount_exponent for projection in result.projections] == [
        Decimal("1.5"),
        Decimal("2.5"),
        Decimal("3.5"),
    ]
    assert result.enterprise_value_perpetuity < calculate_dcf_scenario(scenario).enterprise_value_perpetuity
    assert "timing:3" in result.input_ids


def test_explicit_discount_timing_rejects_partial_non_increasing_and_scenario_conflicts() -> None:
    scenario = _scenario(ScenarioName.BASE)
    partial = replace(
        scenario,
        periods=(
            replace(
                scenario.periods[0],
                discount_exponent=_input(
                    "timing:1", "1", unit="years", currency="N/A"
                ),
            ),
            *scenario.periods[1:],
        ),
    )
    with pytest.raises(ValuationHardFailure) as partial_error:
        calculate_dcf_scenario(partial)
    assert partial_error.value.code == "discount_timing_inputs_incomplete"

    repeated_periods = tuple(
        replace(
            period,
            discount_exponent=_input(
                f"timing:{index}",
                "1",
                unit="years",
                currency="N/A",
            ),
        )
        for index, period in enumerate(scenario.periods, start=1)
    )
    with pytest.raises(ValuationHardFailure) as repeated_error:
        calculate_dcf_scenario(replace(scenario, periods=repeated_periods))
    assert repeated_error.value.code == "discount_exponents_not_increasing"

    downside = replace(_scenario(ScenarioName.DOWNSIDE), periods=repeated_periods)
    base = replace(scenario, periods=tuple(
        replace(
            period,
            discount_exponent=_input(
                f"base-timing:{index}",
                str(index),
                unit="years",
                currency="N/A",
            ),
        )
        for index, period in enumerate(scenario.periods, start=1)
    ))
    upside = replace(_scenario(ScenarioName.UPSIDE), periods=base.periods)
    with pytest.raises(ValuationHardFailure) as conflict_error:
        calculate_dcf_suite((downside, base, upside))
    assert conflict_error.value.code == "discount_timing_scenario_conflict"


def test_dcf_hard_fails_when_wacc_is_not_above_growth() -> None:
    with pytest.raises(ValuationHardFailure) as error:
        calculate_dcf_scenario(
            _scenario(
                ScenarioName.BASE,
                wacc="0.03",
                terminal_growth="0.03",
            )
        )
    assert error.value.code == "wacc_not_above_terminal_growth"


def test_dcf_supports_a_disclosed_negative_terminal_growth_rate() -> None:
    result = calculate_dcf_scenario(
        _scenario(
            ScenarioName.BASE,
            terminal_growth="-0.01",
        )
    )

    assert result.terminal_growth_rate == Decimal("-0.010000")
    assert (
        result.enterprise_value_perpetuity
        < calculate_dcf_scenario(_scenario(ScenarioName.BASE)).enterprise_value_perpetuity
    )


def test_dcf_without_exit_cross_check_stays_calculable_but_warns() -> None:
    result = calculate_dcf_scenario(_scenario(ScenarioName.BASE, with_exit_cross_check=False))

    assert result.enterprise_value_perpetuity == Decimal("995.81")
    assert result.enterprise_value_exit_multiple is None
    cross_check = next(
        check for check in result.checks if check.check_id == "exit_multiple_cross_check_available"
    )
    assert cross_check.scope is CheckScope.READINESS
    assert cross_check.status is CheckStatus.WARNING


def test_dcf_suite_requires_three_scenarios_and_checks_directionality() -> None:
    downside = _scenario(
        ScenarioName.DOWNSIDE,
        ("70", "75", "80"),
    )
    base = _scenario(ScenarioName.BASE)
    upside = _scenario(
        ScenarioName.UPSIDE,
        ("130", "145", "160"),
    )

    with pytest.raises(ValuationHardFailure) as error:
        calculate_dcf_suite([base, upside])
    assert error.value.code == "dcf_scenarios_missing"

    suite = calculate_dcf_suite([upside, downside, base])
    assert [item.scenario for item in suite.scenario_results] == [
        ScenarioName.DOWNSIDE,
        ScenarioName.BASE,
        ScenarioName.UPSIDE,
    ]
    assert all(check.status is CheckStatus.PASSED for check in suite.checks)


def test_dcf_suite_directionality_violation_requires_an_explicit_explanation() -> None:
    downside = _scenario(
        ScenarioName.DOWNSIDE,
        ("150", "160", "170"),
    )
    base = _scenario(ScenarioName.BASE)
    upside = _scenario(
        ScenarioName.UPSIDE,
        ("130", "145", "160"),
    )

    failed = calculate_dcf_suite([downside, base, upside])
    assert failed.checks[0].scope is CheckScope.CALCULATION
    assert failed.checks[0].status is CheckStatus.FAILED

    explained = calculate_dcf_suite(
        [downside, base, upside],
        directionality_explanations={
            "downside_above_base": "Downside includes a separately disclosed asset disposal.",
        },
    )
    assert explained.checks[0].scope is CheckScope.READINESS
    assert explained.checks[0].status is CheckStatus.WARNING
    assert "asset disposal" in explained.checks[0].message


def test_wacc_growth_two_dimensional_sensitivity_and_direction_checks() -> None:
    table = wacc_growth_sensitivity(
        _scenario(ScenarioName.BASE),
        wacc_values=("0.09", "0.10", "0.11"),
        terminal_growth_values=("0.02", "0.03", "0.04"),
    )

    assert table.row_driver == "wacc"
    assert table.column_driver == "terminal_growth_rate"
    assert table.column_values == (
        Decimal("0.02"),
        Decimal("0.03"),
        Decimal("0.04"),
    )
    assert all(check.status is CheckStatus.PASSED for check in table.checks)
    assert table.rows[0].cells[0].enterprise_value > table.rows[1].cells[0].enterprise_value
    assert table.rows[1].cells[2].enterprise_value > table.rows[1].cells[1].enterprise_value


def test_invalid_sensitivity_cell_is_a_visible_hard_failure_not_a_fake_value() -> None:
    table = wacc_growth_sensitivity(
        _scenario(ScenarioName.BASE),
        wacc_values=("0.03", "0.10"),
        terminal_growth_values=("0.03", "0.04"),
    )

    assert table.rows[0].cells[0].enterprise_value is None
    assert table.rows[0].cells[0].hard_failure_code == "wacc_not_above_terminal_growth"
    assert table.checks[0].status is CheckStatus.FAILED


def test_wacc_exit_multiple_sensitivity_is_monotonic() -> None:
    table = wacc_exit_multiple_sensitivity(
        _scenario(ScenarioName.BASE),
        wacc_values=("0.09", "0.10", "0.11"),
        exit_multiple_values=("7", "8", "9"),
    )

    assert table.column_driver == "exit_multiple"
    assert all(check.status is CheckStatus.PASSED for check in table.checks)
    assert table.rows[0].cells[0].enterprise_value > table.rows[1].cells[0].enterprise_value
    assert table.rows[1].cells[2].enterprise_value > table.rows[1].cells[1].enterprise_value


def test_repeated_calculation_is_exactly_deterministic() -> None:
    scenario = _scenario(ScenarioName.BASE)
    assert calculate_dcf_scenario(scenario) == calculate_dcf_scenario(scenario)


def test_cleantech_applicability_requires_human_confirmation() -> None:
    candidate = route_cleantech_valuation(
        CleanTechBusinessModel.MATURE_EQUIPMENT_MANUFACTURING,
        human_confirmed=False,
    )
    assert candidate.status == "human_confirmation_required"
    assert candidate.recommended_methods == ()
    assert candidate.p0_supported is False

    confirmed = route_cleantech_valuation(
        CleanTechBusinessModel.MATURE_EQUIPMENT_MANUFACTURING,
        human_confirmed=True,
        confirmed_by="FA lead",
    )
    assert confirmed.status == "applicable"
    assert confirmed.recommended_methods == ("trading_comps", "corporate_fcff_dcf")
    assert confirmed.p0_supported is True


@pytest.mark.parametrize(
    ("business_model", "forbidden_method"),
    [
        (CleanTechBusinessModel.PROJECT_DEVELOPER_OPERATING_ASSET, "corporate_fcff_dcf"),
        (CleanTechBusinessModel.PRE_COMMERCIAL_TECHNOLOGY, "ev_ebitda"),
    ],
)
def test_unsupported_cleantech_routes_fail_closed(
    business_model: CleanTechBusinessModel,
    forbidden_method: str,
) -> None:
    route = route_cleantech_valuation(
        business_model,
        human_confirmed=True,
        confirmed_by="FA lead",
    )

    assert route.status == "not_applicable_in_p0"
    assert route.p0_supported is False
    assert forbidden_method not in route.recommended_methods
    assert route.limitation


def test_calculation_integrity_and_decision_readiness_are_independent() -> None:
    confirmed = _input("confirmed", "100")
    warning = ModelCheck(
        "terminal_value_concentration",
        CheckScope.READINESS,
        CheckStatus.WARNING,
        "Terminal value concentration needs review.",
    )
    status = assess_valuation_status(
        inputs=[confirmed],
        required_input_ids=["confirmed"],
        checks=[warning],
    )

    assert status.calculation_integrity.status == "passed"
    assert status.decision_readiness.status == "screen_grade"
    assert status.decision_readiness.human_review_required is True
    assert status.boundaries["formal_valuation_opinion_produced"] is False
    assert status.boundaries["secret_method_weighting_applied"] is False


def test_candidate_source_blocks_readiness_without_falsely_failing_arithmetic() -> None:
    candidate = _input("candidate", "100", status=InputStatus.CANDIDATE)
    status = assess_valuation_status(
        inputs=[candidate],
        required_input_ids=["candidate"],
        checks=[],
    )

    assert status.calculation_integrity.status == "passed"
    assert status.decision_readiness.status == "not_ready"
    assert any("Candidate inputs" in item for item in status.decision_readiness.blocking_reasons)


def test_formula_failure_and_human_approval_sequence_are_enforced() -> None:
    confirmed = _input("confirmed", "100")
    failed_check = ModelCheck(
        "bridge_tie",
        CheckScope.CALCULATION,
        CheckStatus.FAILED,
        "Bridge does not tie.",
    )
    failed = assess_valuation_status(
        inputs=[confirmed],
        required_input_ids=["confirmed"],
        checks=[failed_check],
        fa_reviewed_by="FA lead",
    )
    assert failed.calculation_integrity.status == "failed"
    assert failed.decision_readiness.status == "not_ready"

    premature = assess_valuation_status(
        inputs=[confirmed],
        required_input_ids=["confirmed"],
        checks=[],
        approved_for_internal_use_by="MD",
    )
    assert premature.calculation_integrity.status == "passed"
    assert premature.decision_readiness.status == "not_ready"
    assert "cannot precede" in premature.decision_readiness.blocking_reasons[0]

    approved = assess_valuation_status(
        inputs=[confirmed],
        required_input_ids=["confirmed"],
        checks=[],
        fa_reviewed_by="FA lead",
        approved_for_internal_use_by="MD",
    )
    assert approved.decision_readiness.status == "approved_for_internal_use"
    assert approved.boundaries["agent_can_approve"] is False
