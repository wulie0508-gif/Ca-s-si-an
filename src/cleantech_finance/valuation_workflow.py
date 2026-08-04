"""Trusted adapter from UI valuation inputs to the deterministic valuation core.

The browser and Agent surfaces may submit inputs, never calculation results.  This
module normalizes a compact screen request into source-bearing input records and
rebuilds every output from the immutable stored version before persistence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from .valuation import (
    CheckScope,
    CheckStatus,
    CleanTechBusinessModel,
    DCFScenario,
    DiscountConvention,
    EVToEquityBridge,
    FCFFPeriod,
    FinancialBasis,
    FinancialInputContractResult,
    FinancialPeriodType,
    FinancialStatementPeriod,
    InputGateError,
    InputStatus,
    ModelCheck,
    MultipleMetric,
    PeerCapitalization,
    PeerCapitalizationResult,
    PeerClassification,
    PeerCompany,
    ScenarioName,
    ValuationHardFailure,
    ValuationInput,
    assess_valuation_status,
    calculate_dcf_suite,
    calculate_ev_to_equity,
    calculate_peer_capitalization,
    calculate_trading_comps,
    gate_valuation_inputs,
    round_decimal,
    route_cleantech_valuation,
    validate_financial_input_contract,
    wacc_exit_multiple_sensitivity,
    wacc_growth_sensitivity,
)

SCREEN_SCHEMA_VERSION = "1.2"
TARGET_METRIC_NEAR_ZERO = Decimal("0.000001")
MAX_DISCOUNT_EXPONENT = Decimal("100")
P0_METHODS = frozenset({"dcf_fcff", "trading_comps"})
MAX_INPUT_SIGNIFICANT_DIGITS = 28
MAX_INPUT_ADJUSTED_EXPONENT = 24
SCENARIO_ORDER = ("downside", "base", "upside")
PERIOD_FIELDS = (
    ("ebit", "EBIT", "amount"),
    ("tax_rate", "Tax rate", "ratio"),
    ("depreciation_amortization", "D&A", "amount"),
    ("capex", "CapEx", "amount"),
    ("change_in_nwc", "Change in NWC", "amount"),
)
FINANCIAL_FIELDS = (
    ("revenue", "Revenue", "amount"),
    ("ebitda", "EBITDA", "amount"),
    ("ebit", "EBIT", "amount"),
    ("tax_rate", "Tax rate", "ratio"),
    ("depreciation_amortization", "D&A", "amount"),
    ("capex", "CapEx", "amount"),
    ("change_in_nwc", "Change in NWC", "amount"),
    ("fcff", "FCFF", "amount"),
)
PEER_AMOUNT_FIELDS = (
    "enterprise_value",
    "equity_value",
    "ltm_revenue",
    "ntm_revenue",
    "ltm_ebitda",
    "ntm_ebitda",
    "ltm_ebit",
    "ltm_net_income",
)
PEER_CAPITALIZATION_FIELDS = (
    "share_price",
    "fully_diluted_shares",
    "cash_like",
    "debt_like",
    "non_operating_assets",
    "other_claims",
)
REQUIRED_PEER_CAPITALIZATION_FIELDS = frozenset(
    {"share_price", "fully_diluted_shares", "cash_like", "debt_like"}
)


class ValuationWorkflowError(ValueError):
    """Raised when the compact screen contract cannot be normalized."""


def _text(value: Any, field: str, *, limit: int = 500) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if not normalized:
        raise ValuationWorkflowError(f"{field} is required")
    if len(normalized) > limit:
        raise ValuationWorkflowError(f"{field} must be at most {limit} characters")
    return normalized


def _optional_text(value: Any, *, limit: int = 500) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(normalized) > limit:
        raise ValuationWorkflowError(f"text must be at most {limit} characters")
    return normalized or None


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValuationWorkflowError(f"{field} must be an object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValuationWorkflowError(f"{field} must be an array")
    return value


def _decimal_text(value: Any, field: str) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValuationWorkflowError(
            f"{field} must be submitted as a decimal string or integer; floats are forbidden"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValuationWorkflowError(f"{field} is not a valid decimal") from exc
    if not result.is_finite():
        raise ValuationWorkflowError(f"{field} must be finite")
    if (
        len(result.as_tuple().digits) > MAX_INPUT_SIGNIFICANT_DIGITS
        or abs(result.adjusted() if result else 0) > MAX_INPUT_ADJUSTED_EXPONENT
    ):
        raise ValuationWorkflowError(f"{field} exceeds the supported input precision or magnitude")
    return format(result, "f")


def _identifier(value: Any, field: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _text(value, field).casefold()).strip("-")
    if not normalized:
        raise ValuationWorkflowError(f"{field} does not contain a usable identifier")
    return normalized[:72]


def _iso_date(value: Any, field: str) -> str:
    normalized = _text(value, field, limit=10)
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValuationWorkflowError(f"{field} must use YYYY-MM-DD") from exc
    return normalized


def _financial_basis(value: Any, field: str) -> FinancialBasis:
    normalized = re.sub(r"[^a-z]+", "_", _text(value, field, limit=40).casefold()).strip("_")
    aliases = {
        "reported": FinancialBasis.REPORTED,
        "adjusted": FinancialBasis.ADJUSTED,
        "management": FinancialBasis.MANAGEMENT,
        "analyst_estimate": FinancialBasis.ANALYST_ESTIMATE,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValuationWorkflowError(
            f"{field} must be Reported, Adjusted, Management, or Analyst Estimate"
        ) from exc


def _source(value: Any, *, fallback_as_of: str) -> dict[str, str]:
    source = _mapping(value, "source")
    return {
        "source_id": _text(source.get("source_id"), "source.source_id", limit=160),
        "locator": _text(source.get("locator"), "source.locator", limit=240),
        "as_of": _iso_date(source.get("as_of") or fallback_as_of, "source.as_of"),
    }


def _status(confirm_inputs: bool) -> tuple[str, bool]:
    return ("confirmed_input", True) if confirm_inputs else ("candidate_input", False)


def _amount_scale(amount_unit: str) -> str | None:
    normalized = re.sub(r"[^a-z]", "", amount_unit.casefold())
    if "billion" in normalized or normalized.endswith("bn"):
        return "billion"
    if "million" in normalized or normalized.endswith(("m", "mm", "mn")):
        return "million"
    if normalized in {"unit", "units", "ones"} or (len(normalized) == 3 and normalized.isalpha()):
        return "unit"
    return None


def _share_unit_for_amount_unit(amount_unit: str) -> str:
    scale = _amount_scale(amount_unit)
    if scale is None:
        raise ValuationWorkflowError(
            "unit must identify unscaled, million, or billion currency amounts"
        )
    return "shares" if scale == "unit" else f"{scale}_shares"


def _base_record(
    *,
    input_id: str,
    name: str,
    value: Any,
    source: Mapping[str, str],
    period: str,
    currency: str,
    unit: str,
    confirm_inputs: bool,
    input_group: str,
    **metadata: Any,
) -> dict[str, Any]:
    status, human_confirmed = _status(confirm_inputs)
    return {
        "input_id": input_id,
        "name": name,
        "value": value,
        "source_id": source["source_id"],
        "locator": source["locator"],
        "period": period,
        "currency": currency,
        "unit": unit,
        "as_of": source["as_of"],
        "status": status,
        "human_confirmed": human_confirmed,
        "input_group": input_group,
        **metadata,
    }


def _config_record(
    *,
    input_id: str,
    name: str,
    value: Any,
    source: Mapping[str, str],
    valuation_date: str,
    currency: str,
    confirm_inputs: bool,
    **metadata: Any,
) -> dict[str, Any]:
    return _base_record(
        input_id=input_id,
        name=name,
        value=_text(value, name),
        source=source,
        period=valuation_date,
        currency=currency,
        unit="text",
        confirm_inputs=confirm_inputs,
        input_group="configuration",
        **metadata,
    )


def _prepare_financial_inputs(
    financials: Any,
    *,
    source: Mapping[str, str],
    valuation_date: str,
    currency: str,
    unit: str,
    confirm_inputs: bool,
) -> list[dict[str, Any]]:
    contract = _mapping(financials, "financials")
    historical = _sequence(contract.get("historical"), "financials.historical")
    forecast = _sequence(contract.get("forecast"), "financials.forecast")
    raw_ltm = contract.get("ltm")
    ltm_is_single_object = isinstance(raw_ltm, Mapping)
    ltm_rows: Sequence[Any] = (
        (raw_ltm,) if ltm_is_single_object else _sequence(raw_ltm, "financials.ltm")
    )
    groups: tuple[tuple[FinancialPeriodType, Sequence[Any]], ...] = (
        (FinancialPeriodType.HISTORICAL, historical),
        (FinancialPeriodType.LTM, ltm_rows),
        (FinancialPeriodType.FORECAST, forecast),
    )
    inputs: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    coverage_dates: dict[FinancialPeriodType, set[str]] = {
        FinancialPeriodType.HISTORICAL: set(),
        FinancialPeriodType.LTM: set(),
        FinancialPeriodType.FORECAST: set(),
    }
    for period_type, rows in groups:
        for index, raw_row in enumerate(rows, start=1):
            row_path = f"financials.{period_type.value}[{index - 1}]"
            if period_type is FinancialPeriodType.LTM and ltm_is_single_object:
                row_path = "financials.ltm"
            row = _mapping(raw_row, row_path)
            period = _text(row.get("period"), f"{row_path}.period", limit=40)
            period_end = _iso_date(row.get("period_end"), f"{row_path}.period_end")
            basis = _financial_basis(row.get("basis"), f"{row_path}.basis")
            period_key = (period_type.value, period_end, basis.value)
            if period_key in seen_keys:
                raise ValuationWorkflowError(
                    f"Duplicate {period_type.value} period_end and basis: "
                    f"{period_end} / {basis.value}"
                )
            seen_keys.add(period_key)
            coverage_dates[period_type].add(period_end)
            row_source = (
                _source(row.get("source"), fallback_as_of=valuation_date)
                if row.get("source") is not None
                else source
            )
            for field_name, label, field_unit in FINANCIAL_FIELDS:
                field_source = (
                    _source(
                        row.get(f"{field_name}_source"),
                        fallback_as_of=row_source["as_of"],
                    )
                    if row.get(f"{field_name}_source") is not None
                    else row_source
                )
                inputs.append(
                    _base_record(
                        input_id=(
                            f"financial-{period_type.value}-{index}-{field_name.replace('_', '-')}"
                        ),
                        name=f"{period} {label}",
                        value=_decimal_text(row.get(field_name), f"{row_path}.{field_name}"),
                        source=field_source,
                        period=period,
                        currency=currency,
                        unit="ratio" if field_unit == "ratio" else unit,
                        confirm_inputs=confirm_inputs,
                        input_group="financials",
                        period_type=period_type.value,
                        period_index=index,
                        period_end=period_end,
                        financial_basis=basis.value,
                        field=field_name,
                    )
                )
    if len(coverage_dates[FinancialPeriodType.HISTORICAL]) < 3:
        raise ValuationWorkflowError(
            "financials.historical must contain at least 3 unique annual periods"
        )
    if len(coverage_dates[FinancialPeriodType.LTM]) != 1:
        raise ValuationWorkflowError("financials.ltm must cover exactly 1 unique period")
    if not 3 <= len(coverage_dates[FinancialPeriodType.FORECAST]) <= 5:
        raise ValuationWorkflowError("financials.forecast must contain 3 to 5 unique periods")
    return inputs


def _request_discount_timing(
    scenarios: Mapping[str, Any],
    *,
    valuation_date: str,
    confirm_inputs: bool,
) -> dict[str, Any]:
    """Validate structured DCF timing without inferring dates from period labels."""

    valuation_day = date.fromisoformat(valuation_date)
    normalized: dict[str, dict[str, tuple[str | None, ...]]] = {}
    explicit_scenarios: list[str] = []
    for scenario_name in SCENARIO_ORDER:
        scenario = _mapping(scenarios.get(scenario_name), f"scenarios.{scenario_name}")
        periods = _sequence(scenario.get("periods"), f"scenarios.{scenario_name}.periods")
        if len(periods) < 3 or len(periods) > 5:
            raise ValuationWorkflowError(
                f"scenarios.{scenario_name}.periods must contain 3 to 5 forecast years"
            )
        exponent_values: list[str | None] = []
        period_end_values: list[str | None] = []
        for index, raw_period in enumerate(periods, start=1):
            path = f"scenarios.{scenario_name}.periods[{index - 1}]"
            period = _mapping(raw_period, path)
            raw_exponent = period.get("discount_exponent")
            exponent_values.append(
                None
                if raw_exponent in (None, "")
                else _decimal_text(raw_exponent, f"{path}.discount_exponent")
            )
            raw_period_end = period.get("period_end")
            period_end_values.append(
                None
                if raw_period_end in (None, "")
                else _iso_date(raw_period_end, f"{path}.period_end")
            )
        exponent_flags = tuple(value is not None for value in exponent_values)
        if any(exponent_flags) and not all(exponent_flags):
            raise ValuationWorkflowError(
                f"scenarios.{scenario_name} must provide discount_exponent for every period"
            )
        period_end_flags = tuple(value is not None for value in period_end_values)
        if any(period_end_flags) and not all(period_end_flags):
            raise ValuationWorkflowError(
                f"scenarios.{scenario_name} must provide period_end for every period when structured dates are used"
            )
        if all(exponent_flags):
            exponents = tuple(Decimal(str(value)) for value in exponent_values)
            if any(value <= 0 or value > MAX_DISCOUNT_EXPONENT for value in exponents):
                raise ValuationWorkflowError(
                    f"scenarios.{scenario_name} discount_exponent values must be greater than zero and no more than 100"
                )
            if any(
                current <= prior
                for prior, current in zip(exponents, exponents[1:], strict=False)
            ):
                raise ValuationWorkflowError(
                    f"scenarios.{scenario_name} discount_exponent values must be strictly increasing"
                )
            explicit_scenarios.append(scenario_name)
        if all(period_end_flags):
            period_dates = tuple(date.fromisoformat(str(value)) for value in period_end_values)
            if any(
                current <= prior
                for prior, current in zip(period_dates, period_dates[1:], strict=False)
            ):
                raise ValuationWorkflowError(
                    f"scenarios.{scenario_name} period_end values must be strictly increasing"
                )
        normalized[scenario_name] = {
            "discount_exponents": tuple(exponent_values),
            "period_ends": tuple(period_end_values),
        }

    if explicit_scenarios and len(explicit_scenarios) != len(SCENARIO_ORDER):
        raise ValuationWorkflowError(
            "All DCF scenarios must use the same complete discount timing contract"
        )
    signatures = {
        (
            normalized[name]["discount_exponents"],
            normalized[name]["period_ends"],
        )
        for name in SCENARIO_ORDER
    }
    if len(signatures) != 1:
        raise ValuationWorkflowError(
            "Base, Downside, and Upside period_end and discount_exponent values must align"
        )
    if explicit_scenarios:
        basis = "explicit_per_period"
    elif not confirm_inputs:
        basis = "candidate_timing_incomplete"
    else:
        period_ends = normalized[SCENARIO_ORDER[0]]["period_ends"]
        expected = tuple(
            date(valuation_day.year + index, 12, 31).isoformat()
            for index in range(1, len(period_ends) + 1)
        )
        if (
            (valuation_day.month, valuation_day.day) != (12, 31)
            or any(value is None for value in period_ends)
            or period_ends != expected
        ):
            raise ValuationWorkflowError(
                "Confirmed DCF timing requires a source-bearing discount_exponent for every period; positional 1..N compatibility is limited to a December 31 valuation date with consecutive structured December 31 period_end values"
            )
        basis = "validated_annual_period_end"
    return {"basis": basis, "scenarios": normalized}


def prepare_screen_inputs(
    request: Mapping[str, Any],
    valuation_case: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Normalize a compact human screen into auditable stored input records."""

    request = _mapping(request, "request")
    valuation_date = _iso_date(
        valuation_case.get("valuation_date"), "valuation_case.valuation_date"
    )
    currency = _text(
        valuation_case.get("base_currency"), "valuation_case.base_currency", limit=3
    ).upper()
    unit = _text(request.get("unit") or "million", "unit", limit=40)
    _share_unit_for_amount_unit(unit)
    share_unit = _text(
        request.get("share_unit") or _share_unit_for_amount_unit(unit),
        "share_unit",
        limit=40,
    )
    confirm_inputs = request.get("confirm_inputs") is True
    source = _source(request.get("source"), fallback_as_of=valuation_date)
    try:
        business_model = CleanTechBusinessModel(
            _text(request.get("business_model"), "business_model", limit=80)
        )
    except ValueError as exc:
        raise ValuationWorkflowError("business_model is not supported") from exc
    try:
        discount_convention = DiscountConvention(
            _text(
                request.get("discount_convention") or "period_end",
                "discount_convention",
                limit=30,
            )
        )
    except ValueError as exc:
        raise ValuationWorkflowError("discount_convention is not supported") from exc
    inputs: list[dict[str, Any]] = [
        _config_record(
            input_id="config-business-model",
            name="Business model",
            value=business_model.value,
            source=source,
            valuation_date=valuation_date,
            currency=currency,
            confirm_inputs=confirm_inputs,
            field="business_model",
        ),
        _config_record(
            input_id="config-discount-convention",
            name="Discount convention",
            value=discount_convention.value,
            source=source,
            valuation_date=valuation_date,
            currency=currency,
            confirm_inputs=confirm_inputs,
            field="discount_convention",
        ),
    ]

    if request.get("financials") is not None:
        inputs.extend(
            _prepare_financial_inputs(
                request.get("financials"),
                source=source,
                valuation_date=valuation_date,
                currency=currency,
                unit=unit,
                confirm_inputs=confirm_inputs,
            )
        )

    if business_model in {
        CleanTechBusinessModel.PROJECT_DEVELOPER_OPERATING_ASSET,
        CleanTechBusinessModel.PRE_COMMERCIAL_TECHNOLOGY,
    }:
        return inputs

    scenarios = _mapping(request.get("scenarios"), "scenarios")
    discount_timing = _request_discount_timing(
        scenarios,
        valuation_date=valuation_date,
        confirm_inputs=confirm_inputs,
    )
    for scenario_name in SCENARIO_ORDER:
        scenario = _mapping(scenarios.get(scenario_name), f"scenarios.{scenario_name}")
        periods = _sequence(scenario.get("periods"), f"scenarios.{scenario_name}.periods")
        if len(periods) < 3 or len(periods) > 5:
            raise ValuationWorkflowError(
                f"scenarios.{scenario_name}.periods must contain 3 to 5 forecast years"
            )
        inputs.extend(
            [
                _base_record(
                    input_id=f"{scenario_name}-wacc",
                    name=f"{scenario_name.title()} WACC",
                    value=_decimal_text(scenario.get("wacc"), f"scenarios.{scenario_name}.wacc"),
                    source=source,
                    period=valuation_date,
                    currency=currency,
                    unit="ratio",
                    confirm_inputs=confirm_inputs,
                    input_group="dcf",
                    scenario=scenario_name,
                    field="wacc",
                ),
                _base_record(
                    input_id=f"{scenario_name}-terminal-growth",
                    name=f"{scenario_name.title()} terminal growth",
                    value=_decimal_text(
                        scenario.get("terminal_growth"),
                        f"scenarios.{scenario_name}.terminal_growth",
                    ),
                    source=source,
                    period=valuation_date,
                    currency=currency,
                    unit="ratio",
                    confirm_inputs=confirm_inputs,
                    input_group="dcf",
                    scenario=scenario_name,
                    field="terminal_growth",
                ),
            ]
        )
        if scenario.get("terminal_metric") not in (None, ""):
            inputs.extend(
                [
                    _base_record(
                        input_id=f"{scenario_name}-terminal-metric",
                        name=f"{scenario_name.title()} terminal metric",
                        value=_decimal_text(
                            scenario.get("terminal_metric"),
                            f"scenarios.{scenario_name}.terminal_metric",
                        ),
                        source=source,
                        period=str(periods[-1].get("period") or len(periods)),
                        currency=currency,
                        unit=unit,
                        confirm_inputs=confirm_inputs,
                        input_group="dcf",
                        scenario=scenario_name,
                        field="terminal_metric",
                    ),
                    _base_record(
                        input_id=f"{scenario_name}-exit-multiple",
                        name=f"{scenario_name.title()} exit multiple",
                        value=_decimal_text(
                            scenario.get("exit_multiple"),
                            f"scenarios.{scenario_name}.exit_multiple",
                        ),
                        source=source,
                        period=valuation_date,
                        currency=currency,
                        unit="multiple",
                        confirm_inputs=confirm_inputs,
                        input_group="dcf",
                        scenario=scenario_name,
                        field="exit_multiple",
                    ),
                ]
            )
        elif scenario.get("exit_multiple") not in (None, ""):
            raise ValuationWorkflowError(
                f"scenarios.{scenario_name}.exit_multiple requires terminal_metric"
            )
        for index, raw_period in enumerate(periods, start=1):
            period = _mapping(raw_period, f"scenarios.{scenario_name}.periods[{index - 1}]")
            period_label = _text(
                period.get("period") or f"Year {index}",
                f"scenarios.{scenario_name}.periods[{index - 1}].period",
                limit=40,
            )
            timing = discount_timing["scenarios"][scenario_name]
            period_end = timing["period_ends"][index - 1]
            discount_exponent = timing["discount_exponents"][index - 1]
            if period_end is not None:
                period_end_source = (
                    _source(period.get("period_end_source"), fallback_as_of=source["as_of"])
                    if period.get("period_end_source") is not None
                    else source
                )
                inputs.append(
                    _base_record(
                        input_id=f"{scenario_name}-y{index}-period-end",
                        name=f"{scenario_name.title()} {period_label} period end",
                        value=period_end,
                        source=period_end_source,
                        period=period_label,
                        currency=currency,
                        unit="text",
                        confirm_inputs=confirm_inputs,
                        input_group="dcf_timing",
                        scenario=scenario_name,
                        period_index=index,
                        field="period_end",
                        timing_basis=discount_timing["basis"],
                    )
                )
            if discount_exponent is not None:
                exponent_source = (
                    _source(
                        period.get("discount_exponent_source"),
                        fallback_as_of=source["as_of"],
                    )
                    if period.get("discount_exponent_source") is not None
                    else source
                )
                inputs.append(
                    _base_record(
                        input_id=f"{scenario_name}-y{index}-discount-exponent",
                        name=f"{scenario_name.title()} {period_label} discount exponent",
                        value=discount_exponent,
                        source=exponent_source,
                        period=period_label,
                        currency="N/A",
                        unit="years",
                        confirm_inputs=confirm_inputs,
                        input_group="dcf_timing",
                        scenario=scenario_name,
                        period_index=index,
                        field="discount_exponent",
                        timing_basis=discount_timing["basis"],
                    )
                )
            for field_name, label, field_unit in PERIOD_FIELDS:
                inputs.append(
                    _base_record(
                        input_id=f"{scenario_name}-y{index}-{field_name.replace('_', '-')}",
                        name=f"{scenario_name.title()} {period_label} {label}",
                        value=_decimal_text(
                            period.get(field_name),
                            f"scenarios.{scenario_name}.periods[{index - 1}].{field_name}",
                        ),
                        source=source,
                        period=period_label,
                        currency=currency,
                        unit="ratio" if field_unit == "ratio" else unit,
                        confirm_inputs=confirm_inputs,
                        input_group="dcf",
                        scenario=scenario_name,
                        period_index=index,
                        field=field_name,
                    )
                )

    bridge = request.get("bridge")
    if bridge is not None:
        bridge = _mapping(bridge, "bridge")
        bridge_fields = (
            ("cash_like", "Cash-like items"),
            ("debt_like", "Debt-like items"),
            ("non_operating_assets", "Non-operating assets"),
            ("other_claims", "Other claims"),
            ("fully_diluted_shares", "Fully diluted shares"),
        )
        for field_name, label in bridge_fields:
            raw_value = bridge.get(field_name)
            if raw_value in (None, ""):
                continue
            inputs.append(
                _base_record(
                    input_id=f"bridge-{field_name.replace('_', '-')}",
                    name=label,
                    value=_decimal_text(raw_value, f"bridge.{field_name}"),
                    source=source,
                    period=valuation_date,
                    currency=currency,
                    unit=share_unit if field_name == "fully_diluted_shares" else unit,
                    confirm_inputs=confirm_inputs,
                    input_group="bridge",
                    field=field_name,
                )
            )

    comps = request.get("trading_comps")
    if comps is not None:
        comps = _mapping(comps, "trading_comps")
        try:
            metric = MultipleMetric(_text(comps.get("metric"), "trading_comps.metric", limit=40))
        except ValueError as exc:
            raise ValuationWorkflowError("trading_comps.metric is not supported") from exc
        inputs.append(
            _config_record(
                input_id="config-comps-metric",
                name="Trading comps metric",
                value=metric.value,
                source=source,
                valuation_date=valuation_date,
                currency=currency,
                confirm_inputs=confirm_inputs,
                field="comps_metric",
            )
        )
        target_metric = comps.get("target_metric")
        if target_metric not in (None, ""):
            inputs.append(
                _base_record(
                    input_id="target-comps-metric",
                    name="Target metric for implied EV",
                    value=_decimal_text(target_metric, "trading_comps.target_metric"),
                    source=source,
                    period=_text(
                        comps.get("target_metric_period") or valuation_date,
                        "trading_comps.target_metric_period",
                        limit=40,
                    ),
                    currency=currency,
                    unit=unit,
                    confirm_inputs=confirm_inputs,
                    input_group="trading_comps",
                    field="target_metric",
                )
            )
        for raw_peer in _sequence(comps.get("peers") or [], "trading_comps.peers"):
            peer = _mapping(raw_peer, "trading_comps.peer")
            peer_id = _identifier(peer.get("peer_id") or peer.get("name"), "peer_id")
            peer_source = (
                _source(peer.get("source"), fallback_as_of=valuation_date)
                if peer.get("source") is not None
                else source
            )
            try:
                classification = PeerClassification(
                    _text(peer.get("classification"), "peer.classification", limit=40)
                )
            except ValueError as exc:
                raise ValuationWorkflowError("peer.classification is not supported") from exc
            peer_metadata = {
                "peer_id": peer_id,
                "peer_name": _text(peer.get("name"), "peer.name", limit=160),
            }
            inputs.extend(
                [
                    _config_record(
                        input_id=f"peer-{peer_id}-classification",
                        name=f"{peer_metadata['peer_name']} classification",
                        value=classification.value,
                        source=peer_source,
                        valuation_date=valuation_date,
                        currency=currency,
                        confirm_inputs=confirm_inputs,
                        field="peer_classification",
                        **peer_metadata,
                    ),
                    _config_record(
                        input_id=f"peer-{peer_id}-rationale",
                        name=f"{peer_metadata['peer_name']} rationale",
                        value=_text(peer.get("rationale"), "peer.rationale"),
                        source=peer_source,
                        valuation_date=valuation_date,
                        currency=currency,
                        confirm_inputs=confirm_inputs,
                        field="peer_rationale",
                        **peer_metadata,
                    ),
                    _config_record(
                        input_id=f"peer-{peer_id}-target-baseline",
                        name=f"{peer_metadata['peer_name']} target baseline flag",
                        value="true" if peer.get("is_target_baseline") is True else "false",
                        source=peer_source,
                        valuation_date=valuation_date,
                        currency=currency,
                        confirm_inputs=confirm_inputs,
                        field="peer_target_baseline",
                        **peer_metadata,
                    ),
                ]
            )
            capitalization_fields = {
                field_name
                for field_name in PEER_CAPITALIZATION_FIELDS
                if peer.get(field_name) not in (None, "")
            }
            if capitalization_fields:
                missing_capitalization_fields = sorted(
                    REQUIRED_PEER_CAPITALIZATION_FIELDS - capitalization_fields
                )
                if missing_capitalization_fields:
                    raise ValuationWorkflowError(
                        f"peer {peer_id} capitalization is missing: "
                        + ", ".join(missing_capitalization_fields)
                    )
                direct_value_fields = sorted(
                    field_name
                    for field_name in ("enterprise_value", "equity_value")
                    if peer.get(field_name) not in (None, "")
                )
                if direct_value_fields:
                    raise ValuationWorkflowError(
                        f"peer {peer_id} cannot mix derived capitalization inputs with direct "
                        + ", ".join(direct_value_fields)
                    )
                for field_name in PEER_CAPITALIZATION_FIELDS:
                    raw_value = peer.get(field_name)
                    if raw_value in (None, ""):
                        continue
                    field_source = (
                        _source(
                            peer.get(f"{field_name}_source"),
                            fallback_as_of=valuation_date,
                        )
                        if peer.get(f"{field_name}_source") is not None
                        else peer_source
                    )
                    if field_name == "share_price":
                        field_unit = f"{currency}_per_share"
                    elif field_name == "fully_diluted_shares":
                        field_unit = share_unit
                    else:
                        field_unit = unit
                    inputs.append(
                        _base_record(
                            input_id=f"peer-{peer_id}-{field_name.replace('_', '-')}",
                            name=f"{peer_metadata['peer_name']} {field_name}",
                            value=_decimal_text(raw_value, f"peer.{field_name}"),
                            source=field_source,
                            period=_text(
                                peer.get(f"{field_name}_period") or valuation_date,
                                f"peer.{field_name}_period",
                                limit=40,
                            ),
                            currency=currency,
                            unit=field_unit,
                            confirm_inputs=confirm_inputs,
                            input_group="trading_comps_capitalization",
                            field=field_name,
                            **peer_metadata,
                        )
                    )
            for field_name in PEER_AMOUNT_FIELDS:
                raw_value = peer.get(field_name)
                if raw_value in (None, ""):
                    continue
                inputs.append(
                    _base_record(
                        input_id=f"peer-{peer_id}-{field_name.replace('_', '-')}",
                        name=f"{peer_metadata['peer_name']} {field_name}",
                        value=_decimal_text(raw_value, f"peer.{field_name}"),
                        source=peer_source,
                        period=_text(
                            peer.get(f"{field_name}_period") or valuation_date,
                            f"peer.{field_name}_period",
                            limit=40,
                        ),
                        currency=currency,
                        unit=unit,
                        confirm_inputs=confirm_inputs,
                        input_group="trading_comps",
                        field=field_name,
                        **peer_metadata,
                    )
                )

    return inputs


def _confirmed_config(inputs: Sequence[Mapping[str, Any]], input_id: str) -> str:
    for item in inputs:
        if item.get("input_id") != input_id:
            continue
        if item.get("status") != "confirmed_input" or item.get("human_confirmed") is not True:
            raise InputGateError(f"{input_id} is not a human-confirmed configuration")
        return _text(item.get("value"), input_id)
    raise ValuationWorkflowError(f"Missing configuration input: {input_id}")


def _model_input(item: Mapping[str, Any]) -> ValuationInput:
    entered = item.get("entered_by") or {}
    reviewed = item.get("reviewed_by") or {}
    return ValuationInput(
        input_id=_text(item.get("input_id"), "input_id", limit=120),
        value=item.get("value"),
        source_id=_text(item.get("source_id"), "source_id", limit=160),
        locator=_text(item.get("locator"), "locator", limit=240),
        period=_text(item.get("period"), "period", limit=80),
        currency=_text(item.get("currency"), "currency", limit=20),
        unit=_text(item.get("unit"), "unit", limit=40),
        as_of=_iso_date(item.get("as_of"), "as_of"),
        entered_by=_text(entered.get("id") or entered, "entered_by", limit=120),
        status=(
            InputStatus.HUMAN_CONFIRMED
            if item.get("status") == "confirmed_input"
            else InputStatus.CANDIDATE
        ),
        reviewed_by=(
            _text(reviewed.get("id") or reviewed, "reviewed_by", limit=120)
            if item.get("status") == "confirmed_input"
            else None
        ),
    )


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, Enum)):
        return value.isoformat() if isinstance(value, date) else value.value
    return value


def _find_model(
    models: Mapping[str, ValuationInput], input_id: str, *, required: bool = True
) -> ValuationInput | None:
    value = models.get(input_id)
    if value is None and required:
        raise ValuationWorkflowError(f"Missing valuation input: {input_id}")
    return value


def _confirmed_timing_text(item: Mapping[str, Any], *, field: str) -> str:
    if item.get("status") != "confirmed_input" or item.get("human_confirmed") is not True:
        raise InputGateError(f"{item.get('input_id')} is not a human-confirmed timing input")
    _text(item.get("source_id"), f"{field}.source_id", limit=160)
    _text(item.get("locator"), f"{field}.locator", limit=240)
    _iso_date(item.get("as_of"), f"{field}.as_of")
    return _text(item.get("value"), field, limit=80)


def _stored_discount_timing(
    stored_inputs: Sequence[Mapping[str, Any]],
    models: Mapping[str, ValuationInput],
    *,
    valuation_date: date,
) -> dict[str, Any]:
    """Revalidate the immutable timing contract immediately before calculation."""

    scenario_rows: dict[str, list[dict[str, Any]]] = {}
    signatures: set[tuple[tuple[str | None, str | None], ...]] = set()
    explicit_scenarios: list[str] = []
    source_input_ids: set[str] = set()
    for scenario_name in SCENARIO_ORDER:
        forecast_indexes = sorted(
            {
                int(item["period_index"])
                for item in stored_inputs
                if item.get("input_group") == "dcf"
                and item.get("scenario") == scenario_name
                and isinstance(item.get("period_index"), int)
            }
        )
        if not forecast_indexes:
            raise ValuationHardFailure(
                "forecast_missing", f"{scenario_name} has no stored DCF forecast periods"
            )
        timing_rows = [
            item
            for item in stored_inputs
            if item.get("input_group") == "dcf_timing"
            and item.get("scenario") == scenario_name
            and isinstance(item.get("period_index"), int)
        ]
        exponent_by_index = {
            int(item["period_index"]): item
            for item in timing_rows
            if item.get("field") == "discount_exponent"
        }
        period_end_by_index = {
            int(item["period_index"]): item
            for item in timing_rows
            if item.get("field") == "period_end"
        }
        if len(exponent_by_index) != sum(
            item.get("field") == "discount_exponent" for item in timing_rows
        ) or len(period_end_by_index) != sum(
            item.get("field") == "period_end" for item in timing_rows
        ):
            raise ValuationHardFailure(
                "duplicate_discount_timing_input",
                f"{scenario_name} contains duplicate DCF timing inputs",
            )
        exponent_indexes = sorted(exponent_by_index)
        period_end_indexes = sorted(period_end_by_index)
        if exponent_indexes and exponent_indexes != forecast_indexes:
            raise ValuationHardFailure(
                "discount_timing_inputs_incomplete",
                f"{scenario_name} must retain one discount exponent per forecast period",
            )
        if period_end_indexes and period_end_indexes != forecast_indexes:
            raise ValuationHardFailure(
                "discount_period_ends_incomplete",
                f"{scenario_name} must retain one structured period end per forecast period",
            )
        if exponent_indexes:
            explicit_scenarios.append(scenario_name)
        rows: list[dict[str, Any]] = []
        prior_exponent: Decimal | None = None
        prior_period_end: date | None = None
        for index in forecast_indexes:
            exponent_item = exponent_by_index.get(index)
            period_end_item = period_end_by_index.get(index)
            exponent: Decimal | None = None
            exponent_input_id: str | None = None
            period_end_value: date | None = None
            period_end_input_id: str | None = None
            if exponent_item is not None:
                exponent_input_id = str(exponent_item["input_id"])
                exponent_model = models.get(exponent_input_id)
                if exponent_model is None:
                    raise ValuationHardFailure(
                        "discount_timing_input_unreadable",
                        f"Missing numeric model input {exponent_input_id}",
                    )
                exponent = exponent_model.value
                if exponent <= 0 or exponent > MAX_DISCOUNT_EXPONENT:
                    raise ValuationHardFailure(
                        "invalid_discount_exponent",
                        "Discount exponents must be greater than zero and no more than 100 years",
                    )
                if prior_exponent is not None and exponent <= prior_exponent:
                    raise ValuationHardFailure(
                        "discount_exponents_not_increasing",
                        "Discount exponents must be strictly increasing in forecast order",
                    )
                prior_exponent = exponent
                source_input_ids.add(exponent_input_id)
            if period_end_item is not None:
                period_end_input_id = str(period_end_item["input_id"])
                period_end_value = date.fromisoformat(
                    _iso_date(
                        _confirmed_timing_text(
                            period_end_item,
                            field=period_end_input_id,
                        ),
                        period_end_input_id,
                    )
                )
                if prior_period_end is not None and period_end_value <= prior_period_end:
                    raise ValuationHardFailure(
                        "discount_period_ends_not_increasing",
                        "Structured DCF period ends must be strictly increasing",
                    )
                prior_period_end = period_end_value
                source_input_ids.add(period_end_input_id)
            rows.append(
                {
                    "period_index": index,
                    "period_end": period_end_value.isoformat() if period_end_value else None,
                    "period_end_input_id": period_end_input_id,
                    "discount_exponent": format(exponent, "f") if exponent is not None else None,
                    "discount_exponent_input_id": exponent_input_id,
                }
            )
        scenario_rows[scenario_name] = rows
        signatures.add(
            tuple(
                (row["period_end"], row["discount_exponent"])
                for row in rows
            )
        )

    if explicit_scenarios and len(explicit_scenarios) != len(SCENARIO_ORDER):
        raise ValuationHardFailure(
            "discount_timing_scenario_conflict",
            "Every DCF scenario must retain the same complete timing contract",
        )
    if len(signatures) != 1:
        raise ValuationHardFailure(
            "discount_timing_scenario_conflict",
            "Base, Downside, and Upside period ends and discount exponents must align",
        )
    if explicit_scenarios:
        basis = "explicit_per_period"
    else:
        rows = scenario_rows[SCENARIO_ORDER[0]]
        expected_period_ends = tuple(
            date(valuation_date.year + index, 12, 31).isoformat()
            for index in range(1, len(rows) + 1)
        )
        actual_period_ends = tuple(row["period_end"] for row in rows)
        if (
            (valuation_date.month, valuation_date.day) != (12, 31)
            or any(value is None for value in actual_period_ends)
            or actual_period_ends != expected_period_ends
        ):
            raise ValuationHardFailure(
                "discount_timing_inputs_missing",
                "Confirmed DCF timing requires a source-bearing discount exponent for every period; positional 1..N compatibility is limited to a December 31 valuation date with consecutive structured December 31 period ends",
            )
        basis = "validated_annual_period_end"
    return {
        "basis": basis,
        "valuation_date": valuation_date.isoformat(),
        "scenarios": scenario_rows,
        "source_input_ids": sorted(source_input_ids),
        "scenario_consistent": True,
    }


def _scenario(
    name: str,
    stored_inputs: Sequence[Mapping[str, Any]],
    models: Mapping[str, ValuationInput],
    *,
    currency: str,
    unit: str,
    discount_convention: DiscountConvention,
) -> DCFScenario:
    period_rows = sorted(
        (
            item
            for item in stored_inputs
            if item.get("input_group") == "dcf"
            and item.get("scenario") == name
            and isinstance(item.get("period_index"), int)
        ),
        key=lambda item: (int(item["period_index"]), str(item.get("field"))),
    )
    indexes = sorted({int(item["period_index"]) for item in period_rows})
    timing_rows = [
        item
        for item in stored_inputs
        if item.get("input_group") == "dcf_timing"
        and item.get("scenario") == name
        and isinstance(item.get("period_index"), int)
    ]
    periods: list[FCFFPeriod] = []
    for index in indexes:
        by_field = {
            str(item["field"]): models[str(item["input_id"])]
            for item in period_rows
            if int(item["period_index"]) == index
        }
        if set(by_field) != {item[0] for item in PERIOD_FIELDS}:
            raise ValuationWorkflowError(f"{name} forecast period {index} is incomplete")
        timing_by_field = {
            str(item["field"]): item
            for item in timing_rows
            if int(item["period_index"]) == index
        }
        exponent_record = timing_by_field.get("discount_exponent")
        period_end_record = timing_by_field.get("period_end")
        periods.append(
            FCFFPeriod(
                period=by_field["ebit"].period,
                ebit=by_field["ebit"],
                tax_rate=by_field["tax_rate"],
                depreciation_amortization=by_field["depreciation_amortization"],
                capex=by_field["capex"],
                change_in_nwc=by_field["change_in_nwc"],
                discount_exponent=(
                    None
                    if exponent_record is None
                    else models[str(exponent_record["input_id"])]
                ),
                period_end=(
                    None
                    if period_end_record is None
                    else date.fromisoformat(
                        _iso_date(period_end_record.get("value"), "period_end")
                    )
                ),
            )
        )
    period_labels = [period.period for period in periods]
    if len(period_labels) != len(set(period_labels)):
        raise ValuationHardFailure(
            "duplicate_forecast_period",
            f"{name} forecast periods must be unique and ordered",
        )
    return DCFScenario(
        name=ScenarioName(name),
        periods=tuple(periods),
        terminal_growth_rate=models[f"{name}-terminal-growth"],
        currency=currency,
        unit=unit,
        discount_convention=discount_convention,
        direct_wacc=models[f"{name}-wacc"],
        terminal_metric=_find_model(models, f"{name}-terminal-metric", required=False),
        exit_multiple=_find_model(models, f"{name}-exit-multiple", required=False),
    )


def _financial_contract(
    stored_inputs: Sequence[Mapping[str, Any]],
    models: Mapping[str, ValuationInput],
    *,
    currency: str,
    unit: str,
) -> FinancialInputContractResult | None:
    rows = [item for item in stored_inputs if item.get("input_group") == "financials"]
    if not rows:
        return None
    if any(not isinstance(item.get("period_index"), int) for item in rows):
        raise ValuationWorkflowError(
            "Every stored financial input must retain an integer period_index"
        )
    expected_fields = {field_name for field_name, _, _ in FINANCIAL_FIELDS}
    periods: list[FinancialStatementPeriod] = []
    period_type_order = {
        FinancialPeriodType.HISTORICAL.value: 0,
        FinancialPeriodType.LTM.value: 1,
        FinancialPeriodType.FORECAST.value: 2,
    }
    keys = sorted(
        {
            (str(item.get("period_type")), int(item.get("period_index")))
            for item in rows
            if isinstance(item.get("period_index"), int)
        },
        key=lambda item: (period_type_order.get(item[0], 99), item[1]),
    )
    if not keys:
        raise ValuationWorkflowError("Stored financial input contract has no period rows")
    for period_type_value, period_index in keys:
        period_rows = [
            item
            for item in rows
            if item.get("period_type") == period_type_value
            and item.get("period_index") == period_index
        ]
        by_field = {str(item.get("field")): models[str(item["input_id"])] for item in period_rows}
        if set(by_field) != expected_fields or len(period_rows) != len(expected_fields):
            raise ValuationWorkflowError(
                f"Stored {period_type_value} financial period {period_index} is incomplete"
            )
        first = period_rows[0]
        try:
            period_type = FinancialPeriodType(period_type_value)
            basis = FinancialBasis(_text(first.get("financial_basis"), "financial_basis"))
        except ValueError as exc:
            raise ValuationWorkflowError("Stored financial period metadata is invalid") from exc
        metadata_matches = all(
            item.get("period_end") == first.get("period_end")
            and item.get("financial_basis") == first.get("financial_basis")
            for item in period_rows
        )
        if not metadata_matches:
            raise ValuationWorkflowError(
                f"Stored {period_type_value} financial period {period_index} metadata conflicts"
            )
        periods.append(
            FinancialStatementPeriod(
                period=by_field["revenue"].period,
                period_end=_iso_date(first.get("period_end"), "financial.period_end"),
                period_type=period_type,
                basis=basis,
                revenue=by_field["revenue"],
                ebitda=by_field["ebitda"],
                ebit=by_field["ebit"],
                tax_rate=by_field["tax_rate"],
                depreciation_amortization=by_field["depreciation_amortization"],
                capex=by_field["capex"],
                change_in_nwc=by_field["change_in_nwc"],
                fcff=by_field["fcff"],
            )
        )
    return validate_financial_input_contract(tuple(periods), currency=currency, unit=unit)


def _derived_peer_value_input(
    *,
    peer_id: str,
    field_name: str,
    value: Decimal,
    capitalization: PeerCapitalization,
    capitalization_result: PeerCapitalizationResult,
    currency: str,
    unit: str,
) -> ValuationInput:
    source_inputs = (
        capitalization.share_price,
        capitalization.fully_diluted_shares,
        *capitalization.cash_like_items,
        *capitalization.debt_like_items,
        *capitalization.non_operating_asset_items,
        *capitalization.other_claim_items,
    )
    return ValuationInput(
        input_id=f"derived-peer-{peer_id}-{field_name.replace('_', '-')}",
        value=value,
        source_id=f"derived:peer:{peer_id}:capitalization",
        locator=(
            capitalization_result.formula
            + "; source inputs: "
            + ", ".join(capitalization_result.input_ids)
        ),
        period=capitalization.share_price.period,
        currency=currency,
        unit=unit,
        as_of=max(item.as_of for item in source_inputs),
        entered_by="deterministic-valuation-engine",
        status=InputStatus.HUMAN_CONFIRMED,
        reviewed_by="derived-from-confirmed-inputs",
    )


def _peer_companies(
    stored_inputs: Sequence[Mapping[str, Any]],
    models: Mapping[str, ValuationInput],
    *,
    currency: str,
    unit: str,
    share_unit: str,
) -> tuple[
    tuple[PeerCompany, ...],
    tuple[tuple[str, str, PeerCapitalizationResult], ...],
]:
    peer_ids = sorted(
        {
            str(item["peer_id"])
            for item in stored_inputs
            if item.get("input_group") in {"trading_comps", "trading_comps_capitalization"}
            and item.get("peer_id")
        }
    )
    peers: list[PeerCompany] = []
    capitalization_results: list[tuple[str, str, PeerCapitalizationResult]] = []
    for peer_id in peer_ids:
        config = {
            str(item.get("field")): item
            for item in stored_inputs
            if item.get("peer_id") == peer_id and item.get("input_group") == "configuration"
        }
        numeric = {
            str(item.get("field")): models[str(item["input_id"])]
            for item in stored_inputs
            if item.get("peer_id") == peer_id and item.get("input_group") == "trading_comps"
        }
        capitalization_numeric = {
            str(item.get("field")): models[str(item["input_id"])]
            for item in stored_inputs
            if item.get("peer_id") == peer_id
            and item.get("input_group") == "trading_comps_capitalization"
        }
        classification = PeerClassification(
            _confirmed_config(stored_inputs, f"peer-{peer_id}-classification")
        )
        rationale = _confirmed_config(stored_inputs, f"peer-{peer_id}-rationale")
        target_flag = _confirmed_config(stored_inputs, f"peer-{peer_id}-target-baseline") == "true"
        name = _text(
            next(iter(config.values())).get("peer_name") if config else peer_id,
            "peer_name",
        )
        capitalization_result: PeerCapitalizationResult | None = None
        if capitalization_numeric:
            missing_fields = sorted(
                REQUIRED_PEER_CAPITALIZATION_FIELDS - set(capitalization_numeric)
            )
            if missing_fields:
                raise ValuationWorkflowError(
                    f"Stored peer {peer_id} capitalization is missing: " + ", ".join(missing_fields)
                )
            capitalization = PeerCapitalization(
                share_price=capitalization_numeric["share_price"],
                fully_diluted_shares=capitalization_numeric["fully_diluted_shares"],
                cash_like_items=(capitalization_numeric["cash_like"],),
                debt_like_items=(capitalization_numeric["debt_like"],),
                non_operating_asset_items=tuple(
                    item
                    for item in (capitalization_numeric.get("non_operating_assets"),)
                    if item is not None
                ),
                other_claim_items=tuple(
                    item
                    for item in (capitalization_numeric.get("other_claims"),)
                    if item is not None
                ),
            )
            capitalization_result = calculate_peer_capitalization(
                capitalization,
                currency=currency,
                amount_unit=unit,
                share_unit=share_unit,
            )
            numeric["enterprise_value"] = _derived_peer_value_input(
                peer_id=peer_id,
                field_name="enterprise_value",
                value=capitalization_result.enterprise_value,
                capitalization=capitalization,
                capitalization_result=capitalization_result,
                currency=currency,
                unit=unit,
            )
            numeric["equity_value"] = _derived_peer_value_input(
                peer_id=peer_id,
                field_name="equity_value",
                value=capitalization_result.equity_value,
                capitalization=capitalization,
                capitalization_result=capitalization_result,
                currency=currency,
                unit=unit,
            )
            capitalization_results.append((peer_id, name, capitalization_result))
        peers.append(
            PeerCompany(
                peer_id=peer_id,
                name=name,
                classification=classification,
                rationale=rationale,
                enterprise_value=numeric.get("enterprise_value"),
                equity_value=numeric.get("equity_value"),
                ltm_revenue=numeric.get("ltm_revenue"),
                ntm_revenue=numeric.get("ntm_revenue"),
                ltm_ebitda=numeric.get("ltm_ebitda"),
                ntm_ebitda=numeric.get("ntm_ebitda"),
                ltm_ebit=numeric.get("ltm_ebit"),
                ltm_net_income=numeric.get("ltm_net_income"),
                is_target_baseline=target_flag,
            )
        )
    return tuple(peers), tuple(capitalization_results)


def calculate_screen_from_version(
    valuation_case: Mapping[str, Any],
    version: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recalculate a screen from stored inputs; caller-provided outputs are ignored."""

    versions = _sequence(valuation_case.get("versions"), "valuation_case.versions")
    active = _mapping(version or versions[-1], "version")
    stored_inputs = [
        _mapping(item, "version.inputs[]")
        for item in _sequence(active.get("inputs"), "version.inputs")
    ]
    business_model = CleanTechBusinessModel(
        _confirmed_config(stored_inputs, "config-business-model")
    )
    discount_convention = DiscountConvention(
        _confirmed_config(stored_inputs, "config-discount-convention")
    )
    selected_methods = {
        _text(item, "valuation_case.methods[]", limit=80)
        for item in _sequence(valuation_case.get("methods"), "valuation_case.methods")
    }
    if not selected_methods:
        raise ValuationWorkflowError("valuation_case.methods must not be empty")
    unsupported_methods = sorted(selected_methods - P0_METHODS)
    if unsupported_methods:
        raise ValuationWorkflowError(
            "Unsupported P0 valuation methods: " + ", ".join(unsupported_methods)
        )
    reviewer = _text(
        (active.get("created_by") or {}).get("id") or "local-fa",
        "version.created_by.id",
    )
    applicability = route_cleantech_valuation(
        business_model,
        human_confirmed=True,
        confirmed_by=reviewer,
    )
    numeric_items = [item for item in stored_inputs if item.get("unit") != "text"]
    models = {str(item["input_id"]): _model_input(item) for item in numeric_items}
    gate = gate_valuation_inputs(models.values(), models)
    if gate.status != "passed":
        raise InputGateError(
            "Only complete, human-confirmed and source-bearing inputs may calculate"
        )
    used_input_ids = ["config-business-model"]
    boundaries = {
        "formal_valuation_opinion_produced": False,
        "fairness_opinion_produced": False,
        "secret_method_weighting_applied": False,
        "agent_can_approve": False,
        "synergy_included_in_standalone_value": False,
        "external_approval_available_in_local_mode": False,
    }
    if not applicability.p0_supported:
        return {
            "engine_version": "valuation-core-1.0",
            "screen_schema_version": SCREEN_SCHEMA_VERSION,
            "authority": "screen_grade_only",
            "formal_valuation_opinion": False,
            "applicability": _json_value(applicability),
            "methods": {},
            "method_ranges": [],
            "hard_failures": [],
            "placeholders": [],
            "warnings": [],
            "calculation_integrity": {
                "status": "passed",
                "failed_check_ids": [],
                "warning_check_ids": [],
            },
            "decision_readiness": {
                "status": "not_ready",
                "blocking_reasons": [applicability.limitation],
                "warnings": [],
                "human_review_required": True,
            },
            "used_input_ids": used_input_ids,
            "input_version_number": active.get("version_number"),
            "input_version_hash": active.get("version_hash"),
            "boundaries": boundaries,
            "not_implemented": [
                "precedent_transactions",
                "project_level_dcf_nav",
                "reverse_dcf",
            ],
        }

    currency = _text(valuation_case.get("base_currency"), "base_currency", limit=3)
    valuation_date = date.fromisoformat(
        _iso_date(valuation_case.get("valuation_date"), "valuation_date")
    )
    provenance_checks: list[ModelCheck] = []
    stale_input_ids = sorted(
        item.input_id for item in models.values() if (valuation_date - item.as_of).days > 365
    )
    future_input_ids = sorted(
        item.input_id for item in models.values() if (item.as_of - valuation_date).days > 31
    )
    if stale_input_ids:
        provenance_checks.append(
            ModelCheck(
                "input_as_of_stale",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                f"{len(stale_input_ids)} valuation inputs are more than 365 days older than the valuation date.",
            )
        )
    if future_input_ids:
        provenance_checks.append(
            ModelCheck(
                "input_as_of_after_valuation_date",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                f"{len(future_input_ids)} valuation inputs are dated more than 31 days after the valuation date.",
            )
        )
    used_input_ids = sorted(
        {
            "config-business-model",
            "config-discount-convention",
            *(
                str(item["input_id"])
                for item in stored_inputs
                if "dcf_fcff" in selected_methods
                and item.get("input_group") in {"dcf", "dcf_timing", "bridge"}
            ),
            *(
                str(item["input_id"])
                for item in stored_inputs
                if "trading_comps" in selected_methods
                and (
                    item.get("input_group") == "trading_comps"
                    or item.get("input_id") == "config-comps-metric"
                    or str(item.get("input_id") or "").startswith("peer-")
                )
            ),
            *(
                str(item["input_id"])
                for item in stored_inputs
                if item.get("input_group") == "financials"
            ),
        }
    )
    amount_units = {
        item.unit
        for item in models.values()
        if item.unit not in {"ratio", "multiple", "shares", "years"}
        and not item.unit.endswith("_shares")
        and not item.unit.endswith("_per_share")
    }
    if len(amount_units) != 1:
        raise ValuationHardFailure(
            "unit_conflict", "All amount inputs in this screen must share one unit"
        )
    unit = next(iter(amount_units))
    if _amount_scale(unit) is None:
        raise ValuationHardFailure(
            "unsupported_amount_unit",
            "Amount unit must identify unscaled, million, or billion currency amounts",
        )
    all_checks: list[ModelCheck] = list(provenance_checks)
    financial_contract = _financial_contract(
        stored_inputs,
        models,
        currency=currency,
        unit=unit,
    )
    if financial_contract is not None:
        all_checks.extend(financial_contract.checks)
    else:
        all_checks.append(
            ModelCheck(
                "financial_input_contract_available",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                "No complete 3-year history, LTM and 3-to-5-year forecast financial "
                "contract was supplied; legacy screen calculations remain available.",
            )
        )
    methods: dict[str, Any] = {}
    method_ranges: list[dict[str, Any]] = []
    if "dcf_fcff" in selected_methods:
        discount_timing = _stored_discount_timing(
            stored_inputs,
            models,
            valuation_date=valuation_date,
        )
        scenarios = tuple(
            _scenario(
                name,
                stored_inputs,
                models,
                currency=currency,
                unit=unit,
                discount_convention=discount_convention,
            )
            for name in SCENARIO_ORDER
        )
        suite = calculate_dcf_suite(scenarios)
        bridge: EVToEquityBridge | None = None
        cash = _find_model(models, "bridge-cash-like", required=False)
        debt = _find_model(models, "bridge-debt-like", required=False)
        if cash is not None or debt is not None:
            bridge = EVToEquityBridge(
                cash_like_items=(cash,) if cash is not None else None,
                debt_like_items=(debt,) if debt is not None else None,
                non_operating_asset_items=tuple(
                    item
                    for item in (
                        _find_model(models, "bridge-non-operating-assets", required=False),
                    )
                    if item is not None
                ),
                other_claim_items=tuple(
                    item
                    for item in (_find_model(models, "bridge-other-claims", required=False),)
                    if item is not None
                ),
            )
        shares = _find_model(models, "bridge-fully-diluted-shares", required=False)
        if shares is not None and shares.unit != _share_unit_for_amount_unit(unit):
            raise ValuationHardFailure(
                "share_unit_conflict",
                "Fully diluted share-count scale must match the amount-unit scale",
            )
        dcf_bridges = {
            result.scenario.value: calculate_ev_to_equity(
                result.enterprise_value_perpetuity,
                currency=currency,
                unit=unit,
                bridge=bridge,
                fully_diluted_shares=shares,
            )
            for result in suite.scenario_results
        }
        base_scenario = next(item for item in scenarios if item.name is ScenarioName.BASE)
        base_result = suite.result_for(ScenarioName.BASE)
        wacc_grid = sorted(
            {
                max(Decimal("0.000001"), base_result.wacc + delta)
                for delta in (
                    Decimal("-0.02"),
                    Decimal("-0.01"),
                    Decimal("0"),
                    Decimal("0.01"),
                    Decimal("0.02"),
                )
            }
        )
        growth_grid = sorted(
            {
                base_result.terminal_growth_rate + delta
                for delta in (
                    Decimal("-0.01"),
                    Decimal("-0.005"),
                    Decimal("0"),
                    Decimal("0.005"),
                    Decimal("0.01"),
                )
            }
        )
        sensitivity = wacc_growth_sensitivity(
            base_scenario,
            wacc_values=wacc_grid,
            terminal_growth_values=growth_grid,
        )
        exit_sensitivity = None
        if base_scenario.exit_multiple is not None:
            exit_multiple = base_scenario.exit_multiple.value
            exit_grid = sorted(
                {
                    max(Decimal("0.01"), exit_multiple + delta)
                    for delta in (
                        Decimal("-2"),
                        Decimal("-1"),
                        Decimal("0"),
                        Decimal("1"),
                        Decimal("2"),
                    )
                }
            )
            exit_sensitivity = wacc_exit_multiple_sensitivity(
                base_scenario,
                wacc_values=wacc_grid,
                exit_multiple_values=exit_grid,
            )
        all_checks.extend(
            (
                *suite.checks,
                *(check for result in suite.scenario_results for check in result.checks),
                *(check for result in dcf_bridges.values() for check in result.checks),
                *sensitivity.checks,
                *(() if exit_sensitivity is None else exit_sensitivity.checks),
            )
        )
        methods["dcf"] = {
            "suite": _json_value(suite),
            "discount_timing": discount_timing,
            "ev_to_equity": _json_value(dcf_bridges),
            "sensitivity": _json_value(sensitivity),
            "sensitivities": {
                "wacc_x_terminal_growth": _json_value(sensitivity),
                "wacc_x_exit_multiple": _json_value(exit_sensitivity),
            },
        }
        method_ranges.append(
            {
                "method": "dcf_fcff",
                "enterprise_value_low": _json_value(
                    suite.result_for(ScenarioName.DOWNSIDE).enterprise_value_perpetuity
                ),
                "enterprise_value_base": _json_value(base_result.enterprise_value_perpetuity),
                "enterprise_value_high": _json_value(
                    suite.result_for(ScenarioName.UPSIDE).enterprise_value_perpetuity
                ),
                "range_basis": "downside_base_upside",
            }
        )
    if "trading_comps" in selected_methods and any(
        item.get("input_id") == "config-comps-metric" for item in stored_inputs
    ):
        metric = MultipleMetric(_confirmed_config(stored_inputs, "config-comps-metric"))
        peer_companies, peer_capitalizations = _peer_companies(
            stored_inputs,
            models,
            currency=currency,
            unit=unit,
            share_unit=_share_unit_for_amount_unit(unit),
        )
        comps = calculate_trading_comps(peer_companies, metric)
        all_checks.extend(comps.checks)
        all_checks.extend(
            check
            for _, _, capitalization in peer_capitalizations
            for check in capitalization.checks
        )
        target_metric = _find_model(models, "target-comps-metric", required=False)
        implied_range: dict[str, Any] | None = None
        target_metric_status = "N/A"
        if target_metric is None:
            all_checks.append(
                ModelCheck(
                    "target_comps_metric_available",
                    CheckScope.READINESS,
                    CheckStatus.WARNING,
                    "Trading Comps statistics are available, but no target metric was supplied for an implied-value range.",
                )
            )
        elif target_metric.value <= TARGET_METRIC_NEAR_ZERO:
            target_metric_status = "N/M"
            all_checks.append(
                ModelCheck(
                    "target_comps_metric_meaningful",
                    CheckScope.READINESS,
                    CheckStatus.WARNING,
                    "Target metric is negative, zero, or near zero; the Trading Comps implied-value range is N/M.",
                )
            )
        elif (
            comps.statistics.reasonable_range_low is not None
            and comps.statistics.reasonable_range_high is not None
        ):
            target_metric_status = "value"
            low = round_decimal(comps.statistics.reasonable_range_low * target_metric.value)
            high = round_decimal(comps.statistics.reasonable_range_high * target_metric.value)
            value_basis = (
                "equity_value" if metric is MultipleMetric.PRICE_EARNINGS else "enterprise_value"
            )
            implied_range = {
                "value_basis": value_basis,
                "value_low": _json_value(low),
                "value_high": _json_value(high),
                f"{value_basis}_low": _json_value(low),
                f"{value_basis}_high": _json_value(high),
                "formula": "peer P25/P75 multiple x human-confirmed target metric",
                "target_metric_input_id": target_metric.input_id,
            }
            method_ranges.append(
                {
                    "method": "trading_comps",
                    **implied_range,
                    "range_basis": comps.statistics.range_method,
                }
            )
        methods["trading_comps"] = {
            "result": _json_value(comps),
            "implied_range": implied_range,
            "target_metric_status": target_metric_status,
            "peer_capitalizations": [
                {
                    "peer_id": peer_id,
                    "peer_name": peer_name,
                    **_json_value(capitalization),
                }
                for peer_id, peer_name, capitalization in peer_capitalizations
            ],
        }
    elif "trading_comps" in selected_methods:
        all_checks.append(
            ModelCheck(
                "trading_comps_inputs_available",
                CheckScope.READINESS,
                CheckStatus.FAILED,
                "Trading Comps was selected for this valuation case, but no confirmed peer set was supplied.",
            )
        )
    status = assess_valuation_status(
        inputs=tuple(models.values()),
        required_input_ids=tuple(models),
        checks=tuple(all_checks),
    )
    hard_failures = sorted(
        {
            check.check_id
            for check in all_checks
            if check.scope is CheckScope.CALCULATION and check.status is CheckStatus.FAILED
        }
    )
    warnings = sorted(
        {check.message for check in all_checks if check.status is CheckStatus.WARNING}
    )
    return {
        "engine_version": "valuation-core-1.0",
        "screen_schema_version": SCREEN_SCHEMA_VERSION,
        "authority": "screen_grade_only",
        "formal_valuation_opinion": False,
        "applicability": _json_value(applicability),
        "financial_input_contract": (
            _json_value(financial_contract)
            if financial_contract is not None
            else {
                "status": "not_provided",
                "limitation": (
                    "Legacy screens remain calculable, but no 3-year history, LTM and "
                    "forecast financial contract was supplied."
                ),
            }
        ),
        "methods": methods,
        "method_ranges": method_ranges,
        "hard_failures": hard_failures,
        "placeholders": [],
        "warnings": warnings,
        "calculation_integrity": _json_value(status.calculation_integrity),
        "decision_readiness": _json_value(status.decision_readiness),
        "used_input_ids": used_input_ids,
        "input_version_number": active.get("version_number"),
        "input_version_hash": active.get("version_hash"),
        "boundaries": boundaries,
        "not_implemented": [
            "precedent_transactions",
            "project_level_dcf_nav",
            "reverse_dcf",
            "revenue_growth_x_ebit_margin_sensitivity",
        ],
    }


def failed_calculation_from_exception(
    valuation_case: Mapping[str, Any],
    version: Mapping[str, Any],
    error: ValuationHardFailure,
) -> dict[str, Any]:
    """Materialize a deterministic hard-failure snapshot without inventing value."""

    return {
        "engine_version": "valuation-core-1.0",
        "screen_schema_version": SCREEN_SCHEMA_VERSION,
        "authority": "screen_grade_only",
        "formal_valuation_opinion": False,
        "methods": {},
        "method_ranges": [],
        "hard_failures": [error.code],
        "placeholders": [],
        "warnings": [],
        "calculation_integrity": {
            "status": "failed",
            "failed_check_ids": [error.code],
            "warning_check_ids": [],
        },
        "decision_readiness": {
            "status": "not_ready",
            "blocking_reasons": [str(error)],
            "warnings": [],
            "human_review_required": True,
        },
        "used_input_ids": sorted(
            str(item.get("input_id"))
            for item in version.get("inputs", [])
            if item.get("status") == "confirmed_input"
        ),
        "input_version_number": version.get("version_number"),
        "input_version_hash": version.get("version_hash"),
        "valuation_id": valuation_case.get("valuation_id"),
        "boundaries": {
            "formal_valuation_opinion_produced": False,
            "fairness_opinion_produced": False,
            "secret_method_weighting_applied": False,
            "agent_can_approve": False,
            "synergy_included_in_standalone_value": False,
            "external_approval_available_in_local_mode": False,
        },
    }


__all__ = [
    "SCREEN_SCHEMA_VERSION",
    "ValuationWorkflowError",
    "calculate_screen_from_version",
    "failed_calculation_from_exception",
    "prepare_screen_inputs",
]
