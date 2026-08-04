"""Deterministic, source-gated valuation calculations for FA screening work.

The module deliberately separates arithmetic integrity from decision readiness.
It can calculate auditable screening outputs, but it cannot approve a valuation,
produce a fairness opinion, or silently combine valuation methods.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from enum import Enum
from typing import TypeAlias

DecimalLike: TypeAlias = Decimal | int | str

MONEY_QUANTUM = Decimal("0.01")
MULTIPLE_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.000001")
WEIGHT_TOLERANCE = Decimal("0.000001")
DEFAULT_NEAR_ZERO = Decimal("0.000001")
MIN_COMPARABLE_PERCENTILE_SAMPLE = 5
MAX_INPUT_SIGNIFICANT_DIGITS = 28
MAX_INPUT_ADJUSTED_EXPONENT = 24


class ValuationError(ValueError):
    """Base class for deterministic valuation errors."""


class InputGateError(ValuationError):
    """Raised when a candidate or untraceable input is used in a formula."""


class ValuationHardFailure(ValuationError):
    """Raised when a model must stop instead of manufacturing a result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InputStatus(str, Enum):
    CANDIDATE = "candidate_input"
    HUMAN_CONFIRMED = "human_confirmed"


class FinancialBasis(str, Enum):
    """Disclosed financial-data basis; never inferred from the period label."""

    REPORTED = "reported"
    ADJUSTED = "adjusted"
    MANAGEMENT = "management"
    ANALYST_ESTIMATE = "analyst_estimate"


class FinancialPeriodType(str, Enum):
    HISTORICAL = "historical"
    LTM = "ltm"
    FORECAST = "forecast"


class PeerClassification(str, Enum):
    CORE = "core_peer"
    SECONDARY = "secondary_peer"
    ASPIRATIONAL = "aspirational_peer"
    EXCLUDED = "excluded_peer"


class MultipleMetric(str, Enum):
    EV_LTM_REVENUE = "ev_ltm_revenue"
    EV_NTM_REVENUE = "ev_ntm_revenue"
    EV_LTM_EBITDA = "ev_ltm_ebitda"
    EV_NTM_EBITDA = "ev_ntm_ebitda"
    EV_LTM_EBIT = "ev_ltm_ebit"
    PRICE_EARNINGS = "price_earnings"


class MultipleStatus(str, Enum):
    VALUE = "value"
    NOT_AVAILABLE = "N/A"
    NOT_MEANINGFUL = "N/M"
    EXCLUDED = "excluded"


class DiscountConvention(str, Enum):
    PERIOD_END = "period_end"
    MID_YEAR = "mid_year"


class ScenarioName(str, Enum):
    DOWNSIDE = "downside"
    BASE = "base"
    UPSIDE = "upside"


class CheckScope(str, Enum):
    CALCULATION = "calculation"
    READINESS = "readiness"


class CheckStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class CleanTechBusinessModel(str, Enum):
    MATURE_EQUIPMENT_MANUFACTURING = "mature_equipment_manufacturing"
    SOFTWARE_LIGHT_ASSET_SERVICE = "software_light_asset_service"
    PROJECT_DEVELOPER_OPERATING_ASSET = "project_developer_operating_asset"
    EARLY_COMMERCIAL = "early_commercial"
    PRE_COMMERCIAL_TECHNOLOGY = "pre_commercial_technology"


def _decimal(value: DecimalLike, *, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{label} must be Decimal, int, or string; binary floats are forbidden")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValuationError(f"{label} is not a valid decimal") from exc
    if not result.is_finite():
        raise ValuationError(f"{label} must be finite")
    return result


def round_decimal(value: DecimalLike, quantum: Decimal = MONEY_QUANTUM) -> Decimal:
    """Round deterministically using the disclosed half-up policy."""

    result = _decimal(value, label="value")
    return result.quantize(quantum, rounding=ROUND_HALF_UP)


def _required_text(value: str, *, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValuationError(f"{label} is required")
    return normalized


def _bounded_input_decimal(value: Decimal, *, label: str) -> Decimal:
    if (
        len(value.as_tuple().digits) > MAX_INPUT_SIGNIFICANT_DIGITS
        or abs(value.adjusted() if value else 0) > MAX_INPUT_ADJUSTED_EXPONENT
    ):
        raise ValuationError(f"{label} exceeds the supported input precision or magnitude")
    return value


@dataclass(frozen=True)
class ValuationInput:
    """A raw model input with source and explicit human-confirmation state."""

    input_id: str
    value: DecimalLike
    source_id: str
    locator: str
    period: str
    currency: str
    unit: str
    as_of: date | str
    entered_by: str
    status: InputStatus = InputStatus.CANDIDATE
    reviewed_by: str | None = None

    def __post_init__(self) -> None:
        for attribute in (
            "input_id",
            "source_id",
            "locator",
            "period",
            "currency",
            "unit",
            "entered_by",
        ):
            object.__setattr__(
                self,
                attribute,
                _required_text(getattr(self, attribute), label=attribute),
            )
        object.__setattr__(
            self,
            "value",
            _bounded_input_decimal(
                _decimal(self.value, label=self.input_id),
                label=self.input_id,
            ),
        )
        if isinstance(self.as_of, str):
            try:
                object.__setattr__(self, "as_of", date.fromisoformat(self.as_of))
            except ValueError as exc:
                raise ValuationError(f"{self.input_id}.as_of must be an ISO date") from exc
        elif not isinstance(self.as_of, date):
            raise ValuationError(f"{self.input_id}.as_of must be a date")
        if not isinstance(self.status, InputStatus):
            object.__setattr__(self, "status", InputStatus(self.status))
        if self.reviewed_by is not None:
            object.__setattr__(
                self,
                "reviewed_by",
                _required_text(self.reviewed_by, label="reviewed_by"),
            )
        if self.status is InputStatus.HUMAN_CONFIRMED and not self.reviewed_by:
            raise ValuationError(
                f"{self.input_id} is human_confirmed but does not identify reviewed_by"
            )


@dataclass(frozen=True)
class ModelCheck:
    check_id: str
    scope: CheckScope
    status: CheckStatus
    message: str


@dataclass(frozen=True)
class InputGateResult:
    status: str
    confirmed_input_ids: tuple[str, ...]
    candidate_input_ids: tuple[str, ...]
    missing_input_ids: tuple[str, ...]
    duplicate_input_ids: tuple[str, ...]
    checks: tuple[ModelCheck, ...]


def gate_valuation_inputs(
    inputs: Iterable[ValuationInput],
    required_input_ids: Iterable[str],
) -> InputGateResult:
    """Inspect input readiness without allowing candidates into calculations."""

    seen: dict[str, ValuationInput] = {}
    duplicates: set[str] = set()
    for item in inputs:
        if item.input_id in seen:
            duplicates.add(item.input_id)
        else:
            seen[item.input_id] = item
    required = {_required_text(item, label="required_input_id") for item in required_input_ids}
    missing = sorted(required - set(seen))
    candidates = sorted(
        input_id
        for input_id, item in seen.items()
        if input_id in required and item.status is not InputStatus.HUMAN_CONFIRMED
    )
    confirmed = sorted(
        input_id
        for input_id, item in seen.items()
        if input_id in required and item.status is InputStatus.HUMAN_CONFIRMED
    )
    checks: list[ModelCheck] = []
    checks.append(
        ModelCheck(
            "required_inputs_present",
            CheckScope.READINESS,
            CheckStatus.PASSED if not missing else CheckStatus.FAILED,
            "All required inputs are present."
            if not missing
            else f"Missing required inputs: {', '.join(missing)}",
        )
    )
    checks.append(
        ModelCheck(
            "required_inputs_human_confirmed",
            CheckScope.READINESS,
            CheckStatus.PASSED if not candidates else CheckStatus.FAILED,
            "All required inputs are human-confirmed."
            if not candidates
            else f"Candidate inputs cannot enter the model: {', '.join(candidates)}",
        )
    )
    checks.append(
        ModelCheck(
            "input_ids_unique",
            CheckScope.CALCULATION,
            CheckStatus.PASSED if not duplicates else CheckStatus.FAILED,
            "Input identifiers are unique."
            if not duplicates
            else f"Duplicate input identifiers: {', '.join(sorted(duplicates))}",
        )
    )
    blocked = bool(missing or candidates or duplicates)
    return InputGateResult(
        status="blocked" if blocked else "passed",
        confirmed_input_ids=tuple(confirmed),
        candidate_input_ids=tuple(candidates),
        missing_input_ids=tuple(missing),
        duplicate_input_ids=tuple(sorted(duplicates)),
        checks=tuple(checks),
    )


def _confirmed_value(item: ValuationInput) -> Decimal:
    if item.status is not InputStatus.HUMAN_CONFIRMED:
        raise InputGateError(
            f"{item.input_id} is {item.status.value}; only human_confirmed inputs may calculate"
        )
    return item.value


def _ensure_amount_basis(
    items: Iterable[ValuationInput],
    *,
    currency: str,
    unit: str,
) -> None:
    for item in items:
        if item.currency != currency:
            raise ValuationHardFailure(
                "currency_conflict",
                f"{item.input_id} uses {item.currency}; expected {currency}",
            )
        if item.unit != unit:
            raise ValuationHardFailure(
                "unit_conflict",
                f"{item.input_id} uses {item.unit}; expected {unit}",
            )


@dataclass(frozen=True)
class FinancialStatementPeriod:
    """One source-bearing period in the minimum valuation financial contract."""

    period: str
    period_end: date | str
    period_type: FinancialPeriodType
    basis: FinancialBasis
    revenue: ValuationInput
    ebitda: ValuationInput
    ebit: ValuationInput
    tax_rate: ValuationInput
    depreciation_amortization: ValuationInput
    capex: ValuationInput
    change_in_nwc: ValuationInput
    fcff: ValuationInput

    def __post_init__(self) -> None:
        object.__setattr__(self, "period", _required_text(self.period, label="period"))
        if isinstance(self.period_end, str):
            try:
                object.__setattr__(self, "period_end", date.fromisoformat(self.period_end))
            except ValueError as exc:
                raise ValuationError("period_end must be an ISO date") from exc
        elif not isinstance(self.period_end, date):
            raise ValuationError("period_end must be a date")
        if not isinstance(self.period_type, FinancialPeriodType):
            object.__setattr__(
                self,
                "period_type",
                FinancialPeriodType(self.period_type),
            )
        if not isinstance(self.basis, FinancialBasis):
            object.__setattr__(self, "basis", FinancialBasis(self.basis))

    @property
    def inputs(self) -> tuple[ValuationInput, ...]:
        return (
            self.revenue,
            self.ebitda,
            self.ebit,
            self.tax_rate,
            self.depreciation_amortization,
            self.capex,
            self.change_in_nwc,
            self.fcff,
        )


@dataclass(frozen=True)
class FinancialInputContractResult:
    status: str
    periods: tuple[FinancialStatementPeriod, ...]
    historical_period_count: int
    ltm_period_count: int
    forecast_period_count: int
    bases: tuple[FinancialBasis, ...]
    formula: str
    input_ids: tuple[str, ...]
    checks: tuple[ModelCheck, ...]


def validate_financial_input_contract(
    periods: Sequence[FinancialStatementPeriod],
    *,
    currency: str,
    unit: str,
) -> FinancialInputContractResult:
    """Validate the minimum 3-year history, LTM and forecast input contract.

    This validates source-bearing inputs and the disclosed FCFF arithmetic.  It
    deliberately does not choose a preferred accounting basis or overwrite a
    reported value with a management or analyst adjustment.
    """

    period_rows = tuple(periods)
    currency = _required_text(currency, label="currency")
    unit = _required_text(unit, label="unit")
    historical_count = len(
        {
            item.period_end
            for item in period_rows
            if item.period_type is FinancialPeriodType.HISTORICAL
        }
    )
    ltm_count = len(
        {item.period_end for item in period_rows if item.period_type is FinancialPeriodType.LTM}
    )
    forecast_count = len(
        {
            item.period_end
            for item in period_rows
            if item.period_type is FinancialPeriodType.FORECAST
        }
    )
    checks: list[ModelCheck] = [
        ModelCheck(
            "financial_history_coverage",
            CheckScope.READINESS,
            CheckStatus.PASSED if historical_count >= 3 else CheckStatus.FAILED,
            f"{historical_count} historical periods are supplied; at least 3 are required.",
        ),
        ModelCheck(
            "financial_ltm_coverage",
            CheckScope.READINESS,
            CheckStatus.PASSED if ltm_count == 1 else CheckStatus.FAILED,
            f"{ltm_count} LTM periods are supplied; exactly 1 is required.",
        ),
        ModelCheck(
            "financial_forecast_coverage",
            CheckScope.READINESS,
            CheckStatus.PASSED if 3 <= forecast_count <= 5 else CheckStatus.FAILED,
            f"{forecast_count} forecast periods are supplied; 3 to 5 are required.",
        ),
    ]
    period_keys = [
        (item.period_type.value, item.period_end, item.basis.value) for item in period_rows
    ]
    checks.append(
        ModelCheck(
            "financial_periods_unique",
            CheckScope.CALCULATION,
            CheckStatus.PASSED if len(period_keys) == len(set(period_keys)) else CheckStatus.FAILED,
            "Financial period-type, end-date and basis combinations are unique."
            if len(period_keys) == len(set(period_keys))
            else "Duplicate financial period-type, end-date and basis combinations were supplied.",
        )
    )
    period_labels_match = all(
        model_input.period == row.period for row in period_rows for model_input in row.inputs
    )
    checks.append(
        ModelCheck(
            "financial_input_periods_reconcile",
            CheckScope.CALCULATION,
            CheckStatus.PASSED if period_labels_match else CheckStatus.FAILED,
            "Every financial input carries its parent period label."
            if period_labels_match
            else "At least one financial input period does not match its parent period label.",
        )
    )

    all_inputs = tuple(model_input for row in period_rows for model_input in row.inputs)
    input_gate = gate_valuation_inputs(all_inputs, (item.input_id for item in all_inputs))
    checks.extend(input_gate.checks)
    if input_gate.status == "passed":
        amount_inputs = tuple(
            model_input
            for row in period_rows
            for model_input in (
                row.revenue,
                row.ebitda,
                row.ebit,
                row.depreciation_amortization,
                row.capex,
                row.change_in_nwc,
                row.fcff,
            )
        )
        _ensure_amount_basis(amount_inputs, currency=currency, unit=unit)
        invalid_nonnegative = sorted(
            model_input.input_id
            for row in period_rows
            for model_input in (row.depreciation_amortization, row.capex)
            if _confirmed_value(model_input) < 0
        )
        checks.append(
            ModelCheck(
                "financial_nonnegative_da_and_capex",
                CheckScope.CALCULATION,
                CheckStatus.PASSED if not invalid_nonnegative else CheckStatus.FAILED,
                "D&A and CapEx use non-negative magnitudes."
                if not invalid_nonnegative
                else "Negative D&A or CapEx inputs: " + ", ".join(invalid_nonnegative),
            )
        )
        formula_failures: list[str] = []
        ebitda_warnings: list[str] = []
        for row in period_rows:
            tax_rate = _ratio(row.tax_rate)
            calculated_fcff = _confirmed_value(row.ebit) * (Decimal(1) - tax_rate)
            calculated_fcff += _confirmed_value(row.depreciation_amortization)
            calculated_fcff -= _confirmed_value(row.capex)
            calculated_fcff -= _confirmed_value(row.change_in_nwc)
            if abs(round_decimal(calculated_fcff) - round_decimal(_confirmed_value(row.fcff))) > (
                MONEY_QUANTUM
            ):
                formula_failures.append(row.period)
            ebitda_bridge = _confirmed_value(row.ebit) + _confirmed_value(
                row.depreciation_amortization
            )
            if abs(round_decimal(ebitda_bridge) - round_decimal(_confirmed_value(row.ebitda))) > (
                MONEY_QUANTUM
            ):
                ebitda_warnings.append(row.period)
        checks.extend(
            (
                ModelCheck(
                    "financial_fcff_formula_reconciles",
                    CheckScope.CALCULATION,
                    CheckStatus.PASSED if not formula_failures else CheckStatus.FAILED,
                    "FCFF reconciles to EBIT × (1 − tax) + D&A − CapEx − change in NWC."
                    if not formula_failures
                    else "FCFF formula does not reconcile for: " + ", ".join(formula_failures),
                ),
                ModelCheck(
                    "financial_ebitda_bridge",
                    CheckScope.READINESS,
                    CheckStatus.PASSED if not ebitda_warnings else CheckStatus.WARNING,
                    "EBITDA reconciles to EBIT plus D&A."
                    if not ebitda_warnings
                    else "EBITDA differs from EBIT plus D&A for "
                    + ", ".join(ebitda_warnings)
                    + "; retain the disclosed basis and review adjustments.",
                ),
            )
        )

    has_failed = any(check.status is CheckStatus.FAILED for check in checks)
    has_warning = any(check.status is CheckStatus.WARNING for check in checks)
    return FinancialInputContractResult(
        status="failed" if has_failed else "passed_with_warnings" if has_warning else "passed",
        periods=period_rows,
        historical_period_count=historical_count,
        ltm_period_count=ltm_count,
        forecast_period_count=forecast_count,
        bases=tuple(sorted({item.basis for item in period_rows}, key=lambda item: item.value)),
        formula="FCFF = EBIT × (1 - tax rate) + D&A - CapEx - change in NWC",
        input_ids=tuple(sorted(item.input_id for item in all_inputs)),
        checks=tuple(checks),
    )


@dataclass(frozen=True)
class PeerCapitalization:
    """Source inputs used to derive one listed peer's equity value and EV."""

    share_price: ValuationInput
    fully_diluted_shares: ValuationInput
    cash_like_items: tuple[ValuationInput, ...]
    debt_like_items: tuple[ValuationInput, ...]
    non_operating_asset_items: tuple[ValuationInput, ...] = field(default_factory=tuple)
    other_claim_items: tuple[ValuationInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PeerCapitalizationResult:
    equity_value: Decimal
    enterprise_value: Decimal
    cash_like: Decimal
    debt_like: Decimal
    non_operating_assets: Decimal
    other_claims: Decimal
    formula: str
    input_ids: tuple[str, ...]
    checks: tuple[ModelCheck, ...]


def calculate_peer_capitalization(
    capitalization: PeerCapitalization,
    *,
    currency: str,
    amount_unit: str,
    share_unit: str,
) -> PeerCapitalizationResult:
    """Derive fully diluted equity value and EV from independently sourced inputs."""

    currency = _required_text(currency, label="currency")
    amount_unit = _required_text(amount_unit, label="amount_unit")
    share_unit = _required_text(share_unit, label="share_unit")
    if not capitalization.cash_like_items or not capitalization.debt_like_items:
        raise ValuationHardFailure(
            "peer_capitalization_bridge_incomplete",
            "Peer capitalization requires explicit cash-like and debt-like inputs, including zero.",
        )
    inputs = (
        capitalization.share_price,
        capitalization.fully_diluted_shares,
        *capitalization.cash_like_items,
        *capitalization.debt_like_items,
        *capitalization.non_operating_asset_items,
        *capitalization.other_claim_items,
    )
    gate = gate_valuation_inputs(inputs, (item.input_id for item in inputs))
    if gate.status != "passed":
        raise InputGateError(
            "Peer capitalization requires unique, source-bearing, human-confirmed inputs"
        )
    if capitalization.share_price.currency != currency:
        raise ValuationHardFailure(
            "currency_conflict",
            f"{capitalization.share_price.input_id} uses "
            f"{capitalization.share_price.currency}; expected {currency}",
        )
    expected_price_unit = f"{currency}_per_share"
    if capitalization.share_price.unit != expected_price_unit:
        raise ValuationHardFailure(
            "share_price_unit_conflict",
            f"{capitalization.share_price.input_id} must use unit='{expected_price_unit}'",
        )
    if capitalization.fully_diluted_shares.unit != share_unit:
        raise ValuationHardFailure(
            "share_unit_conflict",
            f"{capitalization.fully_diluted_shares.input_id} must use unit='{share_unit}'",
        )
    bridge_items = (
        *capitalization.cash_like_items,
        *capitalization.debt_like_items,
        *capitalization.non_operating_asset_items,
        *capitalization.other_claim_items,
    )
    _ensure_amount_basis(bridge_items, currency=currency, unit=amount_unit)
    values = {item.input_id: _confirmed_value(item) for item in inputs}
    share_price = values[capitalization.share_price.input_id]
    shares = values[capitalization.fully_diluted_shares.input_id]
    if share_price <= 0:
        raise ValuationHardFailure(
            "invalid_share_price", "Peer share price must be greater than zero"
        )
    if shares <= 0:
        raise ValuationHardFailure(
            "invalid_share_count", "Peer fully diluted shares must be greater than zero"
        )
    negative_bridge_ids = sorted(
        item.input_id for item in bridge_items if values[item.input_id] < 0
    )
    if negative_bridge_ids:
        raise ValuationHardFailure(
            "invalid_bridge_sign",
            "Peer EV bridge uses non-negative magnitudes; negative values: "
            + ", ".join(negative_bridge_ids),
        )
    cash_like = sum((values[item.input_id] for item in capitalization.cash_like_items), Decimal(0))
    debt_like = sum((values[item.input_id] for item in capitalization.debt_like_items), Decimal(0))
    non_operating_assets = sum(
        (values[item.input_id] for item in capitalization.non_operating_asset_items),
        Decimal(0),
    )
    other_claims = sum(
        (values[item.input_id] for item in capitalization.other_claim_items), Decimal(0)
    )
    equity_value = round_decimal(share_price * shares)
    enterprise_value = equity_value + debt_like + other_claims
    enterprise_value -= cash_like + non_operating_assets
    dates_aligned = len({item.as_of for item in inputs}) == 1
    checks = (
        ModelCheck(
            "peer_capitalization_formula",
            CheckScope.CALCULATION,
            CheckStatus.PASSED,
            "Peer equity value and enterprise value use the disclosed capitalization formulas.",
        ),
        ModelCheck(
            "peer_capitalization_as_of_aligned",
            CheckScope.READINESS,
            CheckStatus.PASSED if dates_aligned else CheckStatus.WARNING,
            "Share price, share count, cash and debt inputs use one as-of date."
            if dates_aligned
            else "Peer capitalization inputs use different as-of dates; review date alignment.",
        ),
    )
    return PeerCapitalizationResult(
        equity_value=equity_value,
        enterprise_value=round_decimal(enterprise_value),
        cash_like=round_decimal(cash_like),
        debt_like=round_decimal(debt_like),
        non_operating_assets=round_decimal(non_operating_assets),
        other_claims=round_decimal(other_claims),
        formula=(
            "Equity Value = Share Price × Fully Diluted Shares; "
            "Enterprise Value = Equity Value + Debt-like Items + Other Claims "
            "- Cash-like Items - Non-operating Assets"
        ),
        input_ids=tuple(sorted(values)),
        checks=checks,
    )


@dataclass(frozen=True)
class EVToEquityBridge:
    cash_like_items: tuple[ValuationInput, ...] | None
    debt_like_items: tuple[ValuationInput, ...] | None
    non_operating_asset_items: tuple[ValuationInput, ...] = field(default_factory=tuple)
    other_claim_items: tuple[ValuationInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EVToEquityResult:
    enterprise_value: Decimal
    equity_value: Decimal | None
    per_share_value: Decimal | None
    cash_like: Decimal | None
    debt_like: Decimal | None
    non_operating_assets: Decimal | None
    other_claims: Decimal | None
    status: str
    formula: str
    input_ids: tuple[str, ...]
    checks: tuple[ModelCheck, ...]


def calculate_ev_to_equity(
    enterprise_value: DecimalLike,
    *,
    currency: str,
    unit: str,
    bridge: EVToEquityBridge | None,
    fully_diluted_shares: ValuationInput | None = None,
) -> EVToEquityResult:
    """Apply an explicit EV bridge; preserve EV-only output when the bridge is missing."""

    enterprise_value_decimal = round_decimal(enterprise_value)
    currency = _required_text(currency, label="currency")
    unit = _required_text(unit, label="unit")
    formula = "enterprise_value + cash_like + non_operating_assets - debt_like - other_claims"
    if bridge is None or not bridge.cash_like_items or not bridge.debt_like_items:
        check = ModelCheck(
            "equity_bridge_complete",
            CheckScope.READINESS,
            CheckStatus.FAILED,
            "Enterprise value is available, but confirmed cash-like and debt-like bridge "
            "inputs are required before equity value can be shown.",
        )
        return EVToEquityResult(
            enterprise_value=enterprise_value_decimal,
            equity_value=None,
            per_share_value=None,
            cash_like=None,
            debt_like=None,
            non_operating_assets=None,
            other_claims=None,
            status="enterprise_value_only",
            formula=formula,
            input_ids=(),
            checks=(check,),
        )

    items = (
        *bridge.cash_like_items,
        *bridge.debt_like_items,
        *bridge.non_operating_asset_items,
        *bridge.other_claim_items,
    )
    _ensure_amount_basis(items, currency=currency, unit=unit)
    values = {item.input_id: _confirmed_value(item) for item in items}
    negative_items = sorted(item.input_id for item in items if values[item.input_id] < 0)
    if negative_items:
        raise ValuationHardFailure(
            "invalid_bridge_sign",
            "EV-to-equity bridge inputs use non-negative magnitudes; negative values: "
            + ", ".join(negative_items),
        )
    cash_like = sum((_confirmed_value(item) for item in bridge.cash_like_items), Decimal(0))
    debt_like = sum((_confirmed_value(item) for item in bridge.debt_like_items), Decimal(0))
    non_operating_assets = sum(
        (_confirmed_value(item) for item in bridge.non_operating_asset_items), Decimal(0)
    )
    other_claims = sum((_confirmed_value(item) for item in bridge.other_claim_items), Decimal(0))
    equity_value = enterprise_value_decimal + cash_like + non_operating_assets
    equity_value -= debt_like + other_claims
    equity_value = round_decimal(equity_value)
    per_share_value: Decimal | None = None
    checks: list[ModelCheck] = [
        ModelCheck(
            "equity_bridge_complete",
            CheckScope.READINESS,
            CheckStatus.PASSED,
            "Cash-like and debt-like bridge inputs are confirmed and traceable.",
        ),
        ModelCheck(
            "equity_bridge_formula",
            CheckScope.CALCULATION,
            CheckStatus.PASSED,
            "Equity value reconciles to the disclosed EV-to-equity formula.",
        ),
    ]
    input_ids = set(values)
    if fully_diluted_shares is not None:
        shares = _confirmed_value(fully_diluted_shares)
        if shares <= 0:
            raise ValuationHardFailure(
                "invalid_share_count",
                "Fully diluted shares must be greater than zero for per-share value",
            )
        per_share_value = round_decimal(equity_value / shares)
        input_ids.add(fully_diluted_shares.input_id)
        checks.append(
            ModelCheck(
                "share_count_valid",
                CheckScope.CALCULATION,
                CheckStatus.PASSED,
                "Per-share value uses a positive, human-confirmed fully diluted share count.",
            )
        )
    return EVToEquityResult(
        enterprise_value=enterprise_value_decimal,
        equity_value=equity_value,
        per_share_value=per_share_value,
        cash_like=round_decimal(cash_like),
        debt_like=round_decimal(debt_like),
        non_operating_assets=round_decimal(non_operating_assets),
        other_claims=round_decimal(other_claims),
        status="equity_value_calculated",
        formula=formula,
        input_ids=tuple(sorted(input_ids)),
        checks=tuple(checks),
    )


@dataclass(frozen=True)
class PeerCompany:
    peer_id: str
    name: str
    classification: PeerClassification
    rationale: str
    enterprise_value: ValuationInput | None = None
    equity_value: ValuationInput | None = None
    ltm_revenue: ValuationInput | None = None
    ntm_revenue: ValuationInput | None = None
    ltm_ebitda: ValuationInput | None = None
    ntm_ebitda: ValuationInput | None = None
    ltm_ebit: ValuationInput | None = None
    ltm_net_income: ValuationInput | None = None
    is_target_baseline: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "peer_id", _required_text(self.peer_id, label="peer_id"))
        object.__setattr__(self, "name", _required_text(self.name, label="name"))
        object.__setattr__(
            self,
            "rationale",
            _required_text(self.rationale, label="peer rationale"),
        )
        if not isinstance(self.classification, PeerClassification):
            object.__setattr__(
                self,
                "classification",
                PeerClassification(self.classification),
            )
        if self.is_target_baseline and self.classification is PeerClassification.EXCLUDED:
            raise ValuationError("A target baseline cannot also be an excluded peer")


@dataclass(frozen=True)
class MultipleObservation:
    peer_id: str
    peer_name: str
    classification: PeerClassification
    rationale: str
    status: MultipleStatus
    value: Decimal | None
    display_value: str
    reason: str | None
    is_target_baseline: bool
    included_in_statistics: bool


@dataclass(frozen=True)
class ComparableStatistics:
    sample_count: int
    median: Decimal | None
    p25: Decimal | None
    p75: Decimal | None
    mean: Decimal | None
    outlier_peer_ids: tuple[str, ...]
    reasonable_range_low: Decimal | None
    reasonable_range_high: Decimal | None
    range_method: str


@dataclass(frozen=True)
class TradingCompsResult:
    metric: MultipleMetric
    observations: tuple[MultipleObservation, ...]
    statistics: ComparableStatistics
    selected_peer_classes: tuple[PeerClassification, ...]
    checks: tuple[ModelCheck, ...]
    boundary: str = "Target trading data is baseline only; no method weighting is applied."


_MULTIPLE_FIELDS: dict[MultipleMetric, tuple[str, str]] = {
    MultipleMetric.EV_LTM_REVENUE: ("enterprise_value", "ltm_revenue"),
    MultipleMetric.EV_NTM_REVENUE: ("enterprise_value", "ntm_revenue"),
    MultipleMetric.EV_LTM_EBITDA: ("enterprise_value", "ltm_ebitda"),
    MultipleMetric.EV_NTM_EBITDA: ("enterprise_value", "ntm_ebitda"),
    MultipleMetric.EV_LTM_EBIT: ("enterprise_value", "ltm_ebit"),
    MultipleMetric.PRICE_EARNINGS: ("equity_value", "ltm_net_income"),
}


def _percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        raise ValuationError("Cannot calculate a percentile from an empty sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * percentile
    lower_index = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _multiple_observation(
    peer: PeerCompany,
    metric: MultipleMetric,
    *,
    selected_classes: set[PeerClassification],
    near_zero_threshold: Decimal,
) -> MultipleObservation:
    if peer.classification is PeerClassification.EXCLUDED:
        return MultipleObservation(
            peer.peer_id,
            peer.name,
            peer.classification,
            peer.rationale,
            MultipleStatus.EXCLUDED,
            None,
            "Excluded",
            peer.rationale,
            peer.is_target_baseline,
            False,
        )
    numerator_name, denominator_name = _MULTIPLE_FIELDS[metric]
    numerator = getattr(peer, numerator_name)
    denominator = getattr(peer, denominator_name)
    selected = peer.classification in selected_classes and not peer.is_target_baseline
    if numerator is None or denominator is None:
        missing = [
            name
            for name, item in ((numerator_name, numerator), (denominator_name, denominator))
            if item is None
        ]
        return MultipleObservation(
            peer.peer_id,
            peer.name,
            peer.classification,
            peer.rationale,
            MultipleStatus.NOT_AVAILABLE,
            None,
            MultipleStatus.NOT_AVAILABLE.value,
            f"Missing {', '.join(missing)}",
            peer.is_target_baseline,
            False,
        )
    numerator_value = _confirmed_value(numerator)
    denominator_value = _confirmed_value(denominator)
    _ensure_amount_basis(
        (numerator, denominator),
        currency=numerator.currency,
        unit=numerator.unit,
    )
    if denominator_value <= near_zero_threshold:
        return MultipleObservation(
            peer.peer_id,
            peer.name,
            peer.classification,
            peer.rationale,
            MultipleStatus.NOT_MEANINGFUL,
            None,
            MultipleStatus.NOT_MEANINGFUL.value,
            "The denominator is negative, zero, or below the near-zero threshold.",
            peer.is_target_baseline,
            False,
        )
    value = round_decimal(numerator_value / denominator_value, MULTIPLE_QUANTUM)
    return MultipleObservation(
        peer.peer_id,
        peer.name,
        peer.classification,
        peer.rationale,
        MultipleStatus.VALUE,
        value,
        f"{value}x",
        None,
        peer.is_target_baseline,
        selected,
    )


def calculate_trading_comps(
    peers: Sequence[PeerCompany],
    metric: MultipleMetric,
    *,
    selected_peer_classes: Sequence[PeerClassification] = (
        PeerClassification.CORE,
        PeerClassification.SECONDARY,
    ),
    near_zero_threshold: DecimalLike = DEFAULT_NEAR_ZERO,
) -> TradingCompsResult:
    """Calculate unweighted peer statistics and a non-extreme interquartile range."""

    if not isinstance(metric, MultipleMetric):
        metric = MultipleMetric(metric)
    selected_classes = {
        item if isinstance(item, PeerClassification) else PeerClassification(item)
        for item in selected_peer_classes
    }
    if PeerClassification.EXCLUDED in selected_classes:
        raise ValuationError("excluded_peer cannot be selected for statistics")
    threshold = _decimal(near_zero_threshold, label="near_zero_threshold")
    if threshold < 0:
        raise ValuationError("near_zero_threshold cannot be negative")
    observations = tuple(
        _multiple_observation(
            peer,
            metric,
            selected_classes=selected_classes,
            near_zero_threshold=threshold,
        )
        for peer in peers
    )
    selected = [
        observation
        for observation in observations
        if observation.included_in_statistics and observation.value is not None
    ]
    values = [observation.value for observation in selected if observation.value is not None]
    if len(values) >= MIN_COMPARABLE_PERCENTILE_SAMPLE:
        raw_p25 = _percentile(values, Decimal("0.25"))
        raw_p75 = _percentile(values, Decimal("0.75"))
        iqr = raw_p75 - raw_p25
        lower_fence = raw_p25 - Decimal("1.5") * iqr
        upper_fence = raw_p75 + Decimal("1.5") * iqr
        outlier_ids = tuple(
            observation.peer_id
            for observation in selected
            if observation.value is not None
            and (observation.value < lower_fence or observation.value > upper_fence)
        )
        defensible_values = [
            observation.value
            for observation in selected
            if observation.value is not None and observation.peer_id not in outlier_ids
        ]
        if not defensible_values:
            defensible_values = values
        statistics = ComparableStatistics(
            sample_count=len(values),
            median=round_decimal(_percentile(values, Decimal("0.5")), MULTIPLE_QUANTUM),
            p25=round_decimal(raw_p25, MULTIPLE_QUANTUM),
            p75=round_decimal(raw_p75, MULTIPLE_QUANTUM),
            mean=round_decimal(sum(values, Decimal(0)) / Decimal(len(values)), MULTIPLE_QUANTUM),
            outlier_peer_ids=tuple(sorted(outlier_ids)),
            reasonable_range_low=round_decimal(
                _percentile(defensible_values, Decimal("0.25")), MULTIPLE_QUANTUM
            ),
            reasonable_range_high=round_decimal(
                _percentile(defensible_values, Decimal("0.75")), MULTIPLE_QUANTUM
            ),
            range_method="p25_to_p75_after_iqr_outlier_exclusion",
        )
    elif values:
        statistics = ComparableStatistics(
            sample_count=len(values),
            median=round_decimal(_percentile(values, Decimal("0.5")), MULTIPLE_QUANTUM),
            p25=None,
            p75=None,
            mean=round_decimal(sum(values, Decimal(0)) / Decimal(len(values)), MULTIPLE_QUANTUM),
            outlier_peer_ids=(),
            reasonable_range_low=None,
            reasonable_range_high=None,
            range_method="unavailable_fewer_than_five_valid_selected_external_peers",
        )
    else:
        statistics = ComparableStatistics(
            sample_count=0,
            median=None,
            p25=None,
            p75=None,
            mean=None,
            outlier_peer_ids=(),
            reasonable_range_low=None,
            reasonable_range_high=None,
            range_method="unavailable_no_valid_selected_external_peers",
        )
    target_in_stats = any(
        observation.is_target_baseline and observation.included_in_statistics
        for observation in observations
    )
    checks: list[ModelCheck] = [
        ModelCheck(
            "target_baseline_excluded_from_peer_statistics",
            CheckScope.CALCULATION,
            CheckStatus.FAILED if target_in_stats else CheckStatus.PASSED,
            "Target baseline is excluded from external peer statistics."
            if not target_in_stats
            else "Target baseline was incorrectly included in peer statistics.",
        )
    ]
    if statistics.sample_count == 0:
        checks.append(
            ModelCheck(
                "selected_peer_sample_available",
                CheckScope.READINESS,
                CheckStatus.FAILED,
                "No valid selected external peer multiple is available.",
            )
        )
    elif statistics.sample_count < MIN_COMPARABLE_PERCENTILE_SAMPLE:
        checks.append(
            ModelCheck(
                "selected_peer_sample_size",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                f"Only {statistics.sample_count} valid selected external peers; "
                "percentiles and implied range are unavailable until at least five are confirmed.",
            )
        )
    else:
        checks.append(
            ModelCheck(
                "selected_peer_sample_size",
                CheckScope.READINESS,
                CheckStatus.PASSED,
                f"{statistics.sample_count} valid selected external peers support the statistics.",
            )
        )
    return TradingCompsResult(
        metric=metric,
        observations=observations,
        statistics=statistics,
        selected_peer_classes=tuple(sorted(selected_classes, key=lambda item: item.value)),
        checks=tuple(checks),
    )


def calculate_implied_enterprise_value(
    selected_multiple: ValuationInput,
    target_metric: ValuationInput,
) -> Decimal:
    """Apply a human-confirmed selected multiple without adding hidden weights."""

    multiple = _confirmed_value(selected_multiple)
    metric = _confirmed_value(target_metric)
    if selected_multiple.unit != "multiple":
        raise ValuationHardFailure(
            "unit_conflict",
            f"{selected_multiple.input_id} must use unit='multiple'",
        )
    if multiple < 0:
        raise ValuationHardFailure(
            "invalid_selected_multiple", "Selected multiple cannot be negative"
        )
    if metric <= DEFAULT_NEAR_ZERO:
        raise ValuationHardFailure(
            "target_metric_not_meaningful",
            "Target metric must be positive and above the near-zero threshold",
        )
    return round_decimal(multiple * metric)


@dataclass(frozen=True)
class WACCComponents:
    risk_free_rate: ValuationInput
    beta: ValuationInput
    equity_risk_premium: ValuationInput
    size_premium: ValuationInput
    country_risk_premium: ValuationInput
    pre_tax_cost_of_debt: ValuationInput
    equity_weight: ValuationInput
    debt_weight: ValuationInput
    tax_rate: ValuationInput


@dataclass(frozen=True)
class WACCResult:
    wacc: Decimal
    cost_of_equity: Decimal | None
    method: str
    formula: str
    input_ids: tuple[str, ...]


def _ratio(item: ValuationInput, *, minimum: Decimal = Decimal(0)) -> Decimal:
    value = _confirmed_value(item)
    if item.unit != "ratio":
        raise ValuationHardFailure(
            "unit_conflict",
            f"{item.input_id} must use unit='ratio'",
        )
    if value < minimum or value >= 1:
        raise ValuationHardFailure(
            "invalid_rate",
            f"{item.input_id} must be in [{minimum}, 1)",
        )
    return value


def _weight(item: ValuationInput) -> Decimal:
    value = _confirmed_value(item)
    if item.unit != "ratio":
        raise ValuationHardFailure(
            "unit_conflict",
            f"{item.input_id} must use unit='ratio'",
        )
    if value < 0 or value > 1:
        raise ValuationHardFailure(
            "invalid_weight",
            f"{item.input_id} must be in [0, 1]",
        )
    return value


def _terminal_growth(item: ValuationInput) -> Decimal:
    value = _confirmed_value(item)
    if item.unit != "ratio":
        raise ValuationHardFailure(
            "unit_conflict",
            f"{item.input_id} must use unit='ratio'",
        )
    if value <= -1 or value >= 1:
        raise ValuationHardFailure(
            "invalid_terminal_growth",
            f"{item.input_id} must be in (-1, 1)",
        )
    return value


def calculate_wacc(
    *,
    direct_wacc: ValuationInput | None = None,
    components: WACCComponents | None = None,
) -> WACCResult:
    """Resolve either an explicitly sourced direct WACC or its disclosed components."""

    if (direct_wacc is None) == (components is None):
        raise ValuationHardFailure(
            "wacc_method_ambiguous",
            "Provide exactly one of direct_wacc or WACC components",
        )
    if direct_wacc is not None:
        wacc = _ratio(direct_wacc, minimum=Decimal("0.000001"))
        return WACCResult(
            round_decimal(wacc, RATE_QUANTUM),
            None,
            "direct_confirmed_wacc",
            "direct human-confirmed WACC",
            (direct_wacc.input_id,),
        )
    assert components is not None
    risk_free = _ratio(components.risk_free_rate)
    beta = _confirmed_value(components.beta)
    if components.beta.unit != "multiple" or beta < 0:
        raise ValuationHardFailure(
            "invalid_beta",
            "Beta must be a non-negative input with unit='multiple'",
        )
    equity_risk_premium = _ratio(components.equity_risk_premium)
    size_premium = _ratio(components.size_premium)
    country_risk_premium = _ratio(components.country_risk_premium)
    pre_tax_cost_of_debt = _ratio(components.pre_tax_cost_of_debt)
    equity_weight = _weight(components.equity_weight)
    debt_weight = _weight(components.debt_weight)
    tax_rate = _ratio(components.tax_rate)
    if abs(equity_weight + debt_weight - Decimal(1)) > WEIGHT_TOLERANCE:
        raise ValuationHardFailure(
            "capital_structure_weights_do_not_sum_to_one",
            "Target equity and debt weights must sum to one",
        )
    cost_of_equity = risk_free + beta * equity_risk_premium + size_premium + country_risk_premium
    wacc = equity_weight * cost_of_equity
    wacc += debt_weight * pre_tax_cost_of_debt * (Decimal(1) - tax_rate)
    if wacc <= 0 or wacc >= 1:
        raise ValuationHardFailure("invalid_wacc", "Calculated WACC must be in (0, 1)")
    input_ids = tuple(
        item.input_id
        for item in (
            components.risk_free_rate,
            components.beta,
            components.equity_risk_premium,
            components.size_premium,
            components.country_risk_premium,
            components.pre_tax_cost_of_debt,
            components.equity_weight,
            components.debt_weight,
            components.tax_rate,
        )
    )
    return WACCResult(
        round_decimal(wacc, RATE_QUANTUM),
        round_decimal(cost_of_equity, RATE_QUANTUM),
        "component_wacc",
        "E/(D+E)*CoE + D/(D+E)*CoD*(1-tax rate)",
        input_ids,
    )


@dataclass(frozen=True)
class FCFFPeriod:
    period: str
    ebit: ValuationInput
    tax_rate: ValuationInput
    depreciation_amortization: ValuationInput
    capex: ValuationInput
    change_in_nwc: ValuationInput

    def __post_init__(self) -> None:
        object.__setattr__(self, "period", _required_text(self.period, label="period"))


@dataclass(frozen=True)
class FCFFProjection:
    period: str
    fcff: Decimal
    discount_exponent: Decimal
    present_value: Decimal
    formula: str
    input_ids: tuple[str, ...]


def calculate_fcff(period: FCFFPeriod, *, currency: str, unit: str) -> Decimal:
    """Calculate FCFF with positive CapEx representing a cash outflow."""

    amount_inputs = (
        period.ebit,
        period.depreciation_amortization,
        period.capex,
        period.change_in_nwc,
    )
    _ensure_amount_basis(amount_inputs, currency=currency, unit=unit)
    ebit = _confirmed_value(period.ebit)
    tax_rate = _ratio(period.tax_rate)
    depreciation_amortization = _confirmed_value(period.depreciation_amortization)
    capex = _confirmed_value(period.capex)
    change_in_nwc = _confirmed_value(period.change_in_nwc)
    if depreciation_amortization < 0 or capex < 0:
        raise ValuationHardFailure(
            "invalid_fcff_sign_convention",
            "D&A and CapEx must be non-negative magnitudes; Change in NWC may be signed",
        )
    fcff = ebit * (Decimal(1) - tax_rate)
    fcff += depreciation_amortization - capex - change_in_nwc
    return round_decimal(fcff)


@dataclass(frozen=True)
class DCFScenario:
    name: ScenarioName
    periods: tuple[FCFFPeriod, ...]
    terminal_growth_rate: ValuationInput
    currency: str
    unit: str
    discount_convention: DiscountConvention = DiscountConvention.PERIOD_END
    direct_wacc: ValuationInput | None = None
    wacc_components: WACCComponents | None = None
    terminal_metric: ValuationInput | None = None
    exit_multiple: ValuationInput | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, ScenarioName):
            object.__setattr__(self, "name", ScenarioName(self.name))
        if not isinstance(self.discount_convention, DiscountConvention):
            object.__setattr__(
                self,
                "discount_convention",
                DiscountConvention(self.discount_convention),
            )
        object.__setattr__(self, "currency", _required_text(self.currency, label="currency"))
        object.__setattr__(self, "unit", _required_text(self.unit, label="unit"))
        object.__setattr__(self, "periods", tuple(self.periods))


@dataclass(frozen=True)
class DCFResult:
    scenario: ScenarioName
    discount_convention: DiscountConvention
    wacc: Decimal
    terminal_growth_rate: Decimal
    projections: tuple[FCFFProjection, ...]
    present_value_explicit_fcff: Decimal
    terminal_value_perpetuity: Decimal
    present_value_terminal: Decimal
    enterprise_value_perpetuity: Decimal
    terminal_value_share_of_ev: Decimal | None
    terminal_value_exit_multiple: Decimal | None
    enterprise_value_exit_multiple: Decimal | None
    exit_cross_check_difference: Decimal | None
    formulas: tuple[str, ...]
    input_ids: tuple[str, ...]
    checks: tuple[ModelCheck, ...]


def _discount_denominator(
    rate: Decimal,
    period_index: int,
    convention: DiscountConvention,
) -> tuple[Decimal, Decimal]:
    base = Decimal(1) + rate
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_UP
        if convention is DiscountConvention.PERIOD_END:
            exponent = Decimal(period_index)
            denominator = base**period_index
        else:
            exponent = Decimal(period_index) - Decimal("0.5")
            denominator = (base ** (period_index - 1)) * base.sqrt(context)
    return denominator, exponent


def _effective_rate(
    value: DecimalLike | None,
    fallback: Decimal,
    *,
    label: str,
    allow_negative: bool = False,
) -> Decimal:
    if value is None:
        return fallback
    result = _decimal(value, label=label)
    invalid = result <= -1 if allow_negative else result < 0
    if invalid or result >= 1:
        interval = "(-1, 1)" if allow_negative else "[0, 1)"
        raise ValuationHardFailure("invalid_rate", f"{label} must be in {interval}")
    return result


def calculate_dcf_scenario(
    scenario: DCFScenario,
    *,
    wacc_override: DecimalLike | None = None,
    terminal_growth_override: DecimalLike | None = None,
    exit_multiple_override: DecimalLike | None = None,
) -> DCFResult:
    """Calculate an FCFF DCF using perpetuity growth and optional exit cross-check."""

    if not scenario.periods:
        raise ValuationHardFailure("forecast_missing", "DCF requires at least one forecast period")
    wacc_result = calculate_wacc(
        direct_wacc=scenario.direct_wacc,
        components=scenario.wacc_components,
    )
    confirmed_growth = _terminal_growth(scenario.terminal_growth_rate)
    wacc = _effective_rate(wacc_override, wacc_result.wacc, label="wacc_override")
    terminal_growth = _effective_rate(
        terminal_growth_override,
        confirmed_growth,
        label="terminal_growth_override",
        allow_negative=True,
    )
    if wacc <= terminal_growth:
        raise ValuationHardFailure(
            "wacc_not_above_terminal_growth",
            "WACC must be strictly greater than terminal growth",
        )
    projections: list[FCFFProjection] = []
    present_value_explicit_raw = Decimal(0)
    final_fcff = Decimal(0)
    for index, period in enumerate(scenario.periods, start=1):
        fcff = calculate_fcff(period, currency=scenario.currency, unit=scenario.unit)
        denominator, exponent = _discount_denominator(
            wacc,
            index,
            scenario.discount_convention,
        )
        present_value_raw = fcff / denominator
        present_value_explicit_raw += present_value_raw
        final_fcff = fcff
        projections.append(
            FCFFProjection(
                period=period.period,
                fcff=fcff,
                discount_exponent=exponent,
                present_value=round_decimal(present_value_raw),
                formula="EBIT*(1-tax rate)+D&A-CapEx-Change in NWC",
                input_ids=(
                    period.ebit.input_id,
                    period.tax_rate.input_id,
                    period.depreciation_amortization.input_id,
                    period.capex.input_id,
                    period.change_in_nwc.input_id,
                ),
            )
        )
    terminal_fcff = final_fcff * (Decimal(1) + terminal_growth)
    terminal_value_raw = terminal_fcff / (wacc - terminal_growth)
    terminal_denominator, _ = _discount_denominator(
        wacc,
        len(scenario.periods),
        scenario.discount_convention,
    )
    present_value_terminal_raw = terminal_value_raw / terminal_denominator
    enterprise_value_raw = present_value_explicit_raw + present_value_terminal_raw
    enterprise_value = round_decimal(enterprise_value_raw)
    terminal_share = None
    if enterprise_value_raw != 0:
        terminal_share = round_decimal(
            present_value_terminal_raw / enterprise_value_raw,
            RATE_QUANTUM,
        )
    effective_exit_multiple: Decimal | None = None
    if exit_multiple_override is not None:
        effective_exit_multiple = _decimal(
            exit_multiple_override,
            label="exit_multiple_override",
        )
    elif scenario.exit_multiple is not None:
        effective_exit_multiple = _confirmed_value(scenario.exit_multiple)
        if scenario.exit_multiple.unit != "multiple":
            raise ValuationHardFailure(
                "unit_conflict",
                f"{scenario.exit_multiple.input_id} must use unit='multiple'",
            )
    if (scenario.terminal_metric is None) != (effective_exit_multiple is None):
        raise ValuationHardFailure(
            "exit_cross_check_incomplete",
            "Exit-multiple cross-check requires both terminal metric and exit multiple",
        )
    exit_terminal_value: Decimal | None = None
    exit_enterprise_value: Decimal | None = None
    exit_difference: Decimal | None = None
    checks: list[ModelCheck] = [
        ModelCheck(
            "wacc_above_terminal_growth",
            CheckScope.CALCULATION,
            CheckStatus.PASSED,
            "WACC is strictly greater than terminal growth.",
        ),
        ModelCheck(
            "fcff_formula_reconciled",
            CheckScope.CALCULATION,
            CheckStatus.PASSED,
            "Every forecast FCFF uses the disclosed deterministic formula.",
        ),
    ]
    input_ids = {
        scenario.terminal_growth_rate.input_id,
        *wacc_result.input_ids,
        *(item for projection in projections for item in projection.input_ids),
    }
    if scenario.terminal_metric is not None and effective_exit_multiple is not None:
        _ensure_amount_basis(
            (scenario.terminal_metric,),
            currency=scenario.currency,
            unit=scenario.unit,
        )
        terminal_metric = _confirmed_value(scenario.terminal_metric)
        if effective_exit_multiple <= 0 or terminal_metric <= 0:
            checks.append(
                ModelCheck(
                    "exit_multiple_cross_check_meaningful",
                    CheckScope.READINESS,
                    CheckStatus.WARNING,
                    "Exit cross-check is N/M because the terminal metric or multiple is non-positive.",
                )
            )
        else:
            exit_terminal_raw = terminal_metric * effective_exit_multiple
            exit_enterprise_raw = present_value_explicit_raw + (
                exit_terminal_raw / terminal_denominator
            )
            exit_terminal_value = round_decimal(exit_terminal_raw)
            exit_enterprise_value = round_decimal(exit_enterprise_raw)
            if enterprise_value_raw != 0:
                exit_difference = round_decimal(
                    (exit_enterprise_raw - enterprise_value_raw) / abs(enterprise_value_raw),
                    RATE_QUANTUM,
                )
            checks.append(
                ModelCheck(
                    "exit_multiple_cross_check_available",
                    CheckScope.READINESS,
                    CheckStatus.PASSED,
                    "Perpetuity-growth and exit-multiple enterprise values are both available.",
                )
            )
        input_ids.add(scenario.terminal_metric.input_id)
        if scenario.exit_multiple is not None:
            input_ids.add(scenario.exit_multiple.input_id)
    else:
        checks.append(
            ModelCheck(
                "exit_multiple_cross_check_available",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                "Perpetuity-growth DCF calculated without an exit-multiple cross-check.",
            )
        )
    if terminal_share is not None and terminal_share > Decimal("0.75"):
        checks.append(
            ModelCheck(
                "terminal_value_concentration",
                CheckScope.READINESS,
                CheckStatus.WARNING,
                f"Present value of terminal value is {terminal_share} of enterprise value.",
            )
        )
    return DCFResult(
        scenario=scenario.name,
        discount_convention=scenario.discount_convention,
        wacc=round_decimal(wacc, RATE_QUANTUM),
        terminal_growth_rate=round_decimal(terminal_growth, RATE_QUANTUM),
        projections=tuple(projections),
        present_value_explicit_fcff=round_decimal(present_value_explicit_raw),
        terminal_value_perpetuity=round_decimal(terminal_value_raw),
        present_value_terminal=round_decimal(present_value_terminal_raw),
        enterprise_value_perpetuity=enterprise_value,
        terminal_value_share_of_ev=terminal_share,
        terminal_value_exit_multiple=exit_terminal_value,
        enterprise_value_exit_multiple=exit_enterprise_value,
        exit_cross_check_difference=exit_difference,
        formulas=(
            "FCFF=EBIT*(1-tax rate)+D&A-CapEx-Change in NWC",
            "Terminal value=FCFF(n+1)/(WACC-terminal growth)",
            "Enterprise value=PV(explicit FCFF)+PV(terminal value)",
        ),
        input_ids=tuple(sorted(input_ids)),
        checks=tuple(checks),
    )


@dataclass(frozen=True)
class DCFSuiteResult:
    scenario_results: tuple[DCFResult, ...]
    checks: tuple[ModelCheck, ...]

    def result_for(self, scenario: ScenarioName) -> DCFResult:
        for result in self.scenario_results:
            if result.scenario is scenario:
                return result
        raise KeyError(scenario)


def calculate_dcf_suite(
    scenarios: Sequence[DCFScenario],
    *,
    directionality_explanations: Mapping[str, str] | None = None,
) -> DCFSuiteResult:
    """Calculate exactly Base, Downside, and Upside without combining the methods."""

    by_name: dict[ScenarioName, DCFScenario] = {}
    for scenario in scenarios:
        if scenario.name in by_name:
            raise ValuationHardFailure(
                "duplicate_dcf_scenario",
                f"Duplicate DCF scenario: {scenario.name.value}",
            )
        by_name[scenario.name] = scenario
    required = {ScenarioName.DOWNSIDE, ScenarioName.BASE, ScenarioName.UPSIDE}
    missing = required - set(by_name)
    if missing:
        raise ValuationHardFailure(
            "dcf_scenarios_missing",
            "DCF suite requires Base, Downside, and Upside; missing "
            + ", ".join(sorted(item.value for item in missing)),
        )
    results = {
        name: calculate_dcf_scenario(by_name[name])
        for name in (ScenarioName.DOWNSIDE, ScenarioName.BASE, ScenarioName.UPSIDE)
    }
    explanations = directionality_explanations or {}
    checks: list[ModelCheck] = []
    comparisons = (
        (
            "downside_not_above_base",
            results[ScenarioName.DOWNSIDE].enterprise_value_perpetuity
            <= results[ScenarioName.BASE].enterprise_value_perpetuity,
            "downside_above_base",
            "Downside enterprise value should not exceed Base.",
        ),
        (
            "upside_not_below_base",
            results[ScenarioName.UPSIDE].enterprise_value_perpetuity
            >= results[ScenarioName.BASE].enterprise_value_perpetuity,
            "upside_below_base",
            "Upside enterprise value should not be below Base.",
        ),
    )
    for check_id, passed, explanation_key, message in comparisons:
        explanation = str(explanations.get(explanation_key) or "").strip()
        if passed:
            status = CheckStatus.PASSED
            scope = CheckScope.CALCULATION
        elif explanation:
            status = CheckStatus.WARNING
            scope = CheckScope.READINESS
            message += f" Explicit explanation: {explanation}"
        else:
            status = CheckStatus.FAILED
            scope = CheckScope.CALCULATION
        checks.append(ModelCheck(check_id, scope, status, message))
    return DCFSuiteResult(
        scenario_results=tuple(results[name] for name in ScenarioName),
        checks=tuple(checks),
    )


@dataclass(frozen=True)
class SensitivityCell:
    row_value: Decimal
    column_value: Decimal
    enterprise_value: Decimal | None
    hard_failure_code: str | None = None


@dataclass(frozen=True)
class SensitivityRow:
    row_value: Decimal
    cells: tuple[SensitivityCell, ...]


@dataclass(frozen=True)
class SensitivityTable:
    row_driver: str
    column_driver: str
    column_values: tuple[Decimal, ...]
    rows: tuple[SensitivityRow, ...]
    checks: tuple[ModelCheck, ...]


def _sensitivity_values(values: Sequence[DecimalLike], *, label: str) -> tuple[Decimal, ...]:
    normalized = tuple(sorted({_decimal(value, label=label) for value in values}))
    if len(normalized) < 2:
        raise ValuationError(f"{label} requires at least two distinct values")
    return normalized


def _sensitivity_direction_checks(
    rows: tuple[SensitivityRow, ...],
    *,
    row_check_id: str,
    column_check_id: str,
    row_message: str,
    column_message: str,
) -> tuple[ModelCheck, ...]:
    invalid_cells = [cell for row in rows for cell in row.cells if cell.enterprise_value is None]
    row_direction_passed = True
    column_direction_passed = True
    if not invalid_cells:
        for column_index in range(len(rows[0].cells)):
            column = [row.cells[column_index].enterprise_value for row in rows]
            row_direction_passed &= all(
                current is not None and prior is not None and current < prior
                for prior, current in zip(column, column[1:], strict=False)
            )
        for row in rows:
            values = [cell.enterprise_value for cell in row.cells]
            column_direction_passed &= all(
                current is not None and prior is not None and current > prior
                for prior, current in zip(values, values[1:], strict=False)
            )
    else:
        row_direction_passed = False
        column_direction_passed = False
    checks = [
        ModelCheck(
            "sensitivity_cells_valid",
            CheckScope.CALCULATION,
            CheckStatus.PASSED if not invalid_cells else CheckStatus.FAILED,
            "All sensitivity cells calculated."
            if not invalid_cells
            else f"{len(invalid_cells)} sensitivity cells hit a hard failure.",
        ),
        ModelCheck(
            row_check_id,
            CheckScope.CALCULATION,
            CheckStatus.PASSED if row_direction_passed else CheckStatus.FAILED,
            row_message,
        ),
        ModelCheck(
            column_check_id,
            CheckScope.CALCULATION,
            CheckStatus.PASSED if column_direction_passed else CheckStatus.FAILED,
            column_message,
        ),
    ]
    return tuple(checks)


def wacc_growth_sensitivity(
    scenario: DCFScenario,
    *,
    wacc_values: Sequence[DecimalLike],
    terminal_growth_values: Sequence[DecimalLike],
) -> SensitivityTable:
    """Build a deterministic WACC-by-terminal-growth enterprise-value grid."""

    rows_values = _sensitivity_values(wacc_values, label="wacc_values")
    columns = _sensitivity_values(
        terminal_growth_values,
        label="terminal_growth_values",
    )
    rows: list[SensitivityRow] = []
    for wacc in rows_values:
        cells: list[SensitivityCell] = []
        for growth in columns:
            try:
                result = calculate_dcf_scenario(
                    scenario,
                    wacc_override=wacc,
                    terminal_growth_override=growth,
                )
                cells.append(SensitivityCell(wacc, growth, result.enterprise_value_perpetuity))
            except ValuationHardFailure as exc:
                cells.append(SensitivityCell(wacc, growth, None, exc.code))
        rows.append(SensitivityRow(wacc, tuple(cells)))
    materialized = tuple(rows)
    checks = _sensitivity_direction_checks(
        materialized,
        row_check_id="wacc_up_value_down",
        column_check_id="terminal_growth_up_value_up",
        row_message="Enterprise value decreases as WACC increases.",
        column_message="Enterprise value increases as terminal growth increases.",
    )
    return SensitivityTable(
        "wacc",
        "terminal_growth_rate",
        columns,
        materialized,
        checks,
    )


def wacc_exit_multiple_sensitivity(
    scenario: DCFScenario,
    *,
    wacc_values: Sequence[DecimalLike],
    exit_multiple_values: Sequence[DecimalLike],
) -> SensitivityTable:
    """Build a WACC-by-exit-multiple cross-check grid."""

    if scenario.terminal_metric is None:
        raise ValuationHardFailure(
            "terminal_metric_missing",
            "WACC/exit-multiple sensitivity requires a terminal metric",
        )
    rows_values = _sensitivity_values(wacc_values, label="wacc_values")
    columns = _sensitivity_values(exit_multiple_values, label="exit_multiple_values")
    rows: list[SensitivityRow] = []
    for wacc in rows_values:
        cells: list[SensitivityCell] = []
        for multiple in columns:
            try:
                result = calculate_dcf_scenario(
                    scenario,
                    wacc_override=wacc,
                    exit_multiple_override=multiple,
                )
                cells.append(
                    SensitivityCell(
                        wacc,
                        multiple,
                        result.enterprise_value_exit_multiple,
                    )
                )
            except ValuationHardFailure as exc:
                cells.append(SensitivityCell(wacc, multiple, None, exc.code))
        rows.append(SensitivityRow(wacc, tuple(cells)))
    materialized = tuple(rows)
    checks = _sensitivity_direction_checks(
        materialized,
        row_check_id="wacc_up_exit_value_down",
        column_check_id="exit_multiple_up_value_up",
        row_message="Exit-multiple enterprise value decreases as WACC increases.",
        column_message="Exit-multiple enterprise value increases as exit multiple increases.",
    )
    return SensitivityTable(
        "wacc",
        "exit_multiple",
        columns,
        materialized,
        checks,
    )


@dataclass(frozen=True)
class ApplicabilityRoute:
    business_model: CleanTechBusinessModel
    status: str
    recommended_methods: tuple[str, ...]
    important_supplements: tuple[str, ...]
    p0_supported: bool
    limitation: str | None
    confirmed_by: str | None


_APPLICABILITY_ROUTES: dict[
    CleanTechBusinessModel,
    tuple[tuple[str, ...], tuple[str, ...], bool, str | None],
] = {
    CleanTechBusinessModel.MATURE_EQUIPMENT_MANUFACTURING: (
        ("trading_comps", "corporate_fcff_dcf"),
        ("capex", "working_capital", "capacity_utilization", "warranty", "cycle_adjustment"),
        True,
        None,
    ),
    CleanTechBusinessModel.SOFTWARE_LIGHT_ASSET_SERVICE: (
        ("revenue_ebitda_comps", "corporate_fcff_dcf"),
        ("arr", "retention", "gross_margin", "customer_concentration", "cash_conversion"),
        True,
        None,
    ),
    CleanTechBusinessModel.PROJECT_DEVELOPER_OPERATING_ASSET: (
        ("project_level_dcf_nav",),
        ("cod", "ppa", "load_factor", "subsidy", "project_debt", "remaining_term"),
        False,
        "P0 corporate FCFF does not replace project-level DCF/NAV; method is not applicable here.",
    ),
    CleanTechBusinessModel.EARLY_COMMERCIAL: (
        ("revenue_kpi_comps", "scenario_fcff_dcf"),
        ("order_quality", "capacity_ramp", "yield", "unit_economics", "funding_gap"),
        True,
        "Scenario DCF is screen-grade until forecasts and ramp assumptions are human-verified.",
    ),
    CleanTechBusinessModel.PRE_COMMERCIAL_TECHNOLOGY: (
        ("milestone_scenarios", "replacement_cost", "precedent_transactions"),
        ("technical_milestones", "financing_need", "commercialization_evidence"),
        False,
        "Traditional revenue DCF and EV/EBITDA are not applicable to unverified remote forecasts.",
    ),
}


def route_cleantech_valuation(
    business_model: CleanTechBusinessModel,
    *,
    human_confirmed: bool,
    confirmed_by: str | None = None,
) -> ApplicabilityRoute:
    """Route methods only after a human confirms the business-model classification."""

    if not isinstance(business_model, CleanTechBusinessModel):
        business_model = CleanTechBusinessModel(business_model)
    methods, supplements, supported, limitation = _APPLICABILITY_ROUTES[business_model]
    if not human_confirmed:
        return ApplicabilityRoute(
            business_model,
            "human_confirmation_required",
            (),
            supplements,
            False,
            "Agent classification is only a candidate; no valuation method is activated.",
            None,
        )
    reviewer = _required_text(confirmed_by or "", label="confirmed_by")
    return ApplicabilityRoute(
        business_model,
        "applicable" if supported else "not_applicable_in_p0",
        methods,
        supplements,
        supported,
        limitation,
        reviewer,
    )


@dataclass(frozen=True)
class CalculationIntegrity:
    status: str
    failed_check_ids: tuple[str, ...]
    warning_check_ids: tuple[str, ...]


@dataclass(frozen=True)
class DecisionReadiness:
    status: str
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    human_review_required: bool


@dataclass(frozen=True)
class ValuationModelStatus:
    calculation_integrity: CalculationIntegrity
    decision_readiness: DecisionReadiness
    boundaries: Mapping[str, bool]


def assess_valuation_status(
    *,
    inputs: Sequence[ValuationInput],
    required_input_ids: Sequence[str],
    checks: Sequence[ModelCheck],
    fa_reviewed_by: str | None = None,
    approved_for_internal_use_by: str | None = None,
) -> ValuationModelStatus:
    """Report mechanical integrity and human decision readiness independently."""

    gate = gate_valuation_inputs(inputs, required_input_ids)
    all_checks = (*gate.checks, *checks)
    calculation_failures = tuple(
        item.check_id
        for item in all_checks
        if item.scope is CheckScope.CALCULATION and item.status is CheckStatus.FAILED
    )
    calculation_warnings = tuple(
        item.check_id
        for item in all_checks
        if item.scope is CheckScope.CALCULATION and item.status is CheckStatus.WARNING
    )
    integrity_status = "failed" if calculation_failures else "passed"
    readiness_failures = [
        item.message
        for item in all_checks
        if item.scope is CheckScope.READINESS and item.status is CheckStatus.FAILED
    ]
    readiness_warnings = [item.message for item in all_checks if item.status is CheckStatus.WARNING]
    if approved_for_internal_use_by and not fa_reviewed_by:
        readiness_failures.append("Internal approval cannot precede identified FA review.")
    if calculation_failures:
        readiness_failures.append("Calculation integrity has failed checks.")
    if readiness_failures:
        readiness_status = "not_ready"
    elif approved_for_internal_use_by:
        readiness_status = "approved_for_internal_use"
    elif fa_reviewed_by:
        readiness_status = "fa_reviewed_with_caveats" if readiness_warnings else "fa_reviewed"
    else:
        readiness_status = "screen_grade"
        readiness_warnings.append("FA review has not been recorded.")
    return ValuationModelStatus(
        calculation_integrity=CalculationIntegrity(
            integrity_status,
            tuple(sorted(set(calculation_failures))),
            tuple(sorted(set(calculation_warnings))),
        ),
        decision_readiness=DecisionReadiness(
            readiness_status,
            tuple(readiness_failures),
            tuple(readiness_warnings),
            readiness_status not in {"fa_reviewed", "approved_for_internal_use"},
        ),
        boundaries={
            "formal_valuation_opinion_produced": False,
            "fairness_opinion_produced": False,
            "secret_method_weighting_applied": False,
            "agent_can_approve": False,
            "synergy_included_in_standalone_value": False,
        },
    )


__all__ = [
    "ApplicabilityRoute",
    "CalculationIntegrity",
    "CheckScope",
    "CheckStatus",
    "CleanTechBusinessModel",
    "ComparableStatistics",
    "DCFResult",
    "DCFScenario",
    "DCFSuiteResult",
    "DecisionReadiness",
    "DiscountConvention",
    "EVToEquityBridge",
    "EVToEquityResult",
    "FinancialBasis",
    "FinancialInputContractResult",
    "FinancialPeriodType",
    "FinancialStatementPeriod",
    "FCFFPeriod",
    "FCFFProjection",
    "InputGateError",
    "InputGateResult",
    "InputStatus",
    "ModelCheck",
    "MultipleMetric",
    "MultipleObservation",
    "MultipleStatus",
    "PeerClassification",
    "PeerCapitalization",
    "PeerCapitalizationResult",
    "PeerCompany",
    "ScenarioName",
    "SensitivityCell",
    "SensitivityRow",
    "SensitivityTable",
    "TradingCompsResult",
    "ValuationError",
    "ValuationHardFailure",
    "ValuationInput",
    "ValuationModelStatus",
    "WACCComponents",
    "WACCResult",
    "assess_valuation_status",
    "calculate_dcf_scenario",
    "calculate_dcf_suite",
    "calculate_ev_to_equity",
    "calculate_fcff",
    "calculate_implied_enterprise_value",
    "calculate_peer_capitalization",
    "calculate_trading_comps",
    "calculate_wacc",
    "gate_valuation_inputs",
    "round_decimal",
    "route_cleantech_valuation",
    "validate_financial_input_contract",
    "wacc_exit_multiple_sensitivity",
    "wacc_growth_sensitivity",
]
