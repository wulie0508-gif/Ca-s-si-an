"""Deterministic financial calculations with input-level provenance."""

from __future__ import annotations

from datetime import date
from typing import Any

from .fact_semantics import margin_operations_scope, select_net_income_fact, statement_scope
from .ingest import ManifestError


def validate_period_contract(periods: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate annual period identity before any trend calculation."""

    labels: set[str] = set()
    end_dates: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for period in periods:
        for key in (
            "period",
            "fiscal_year",
            "period_type",
            "start_date",
            "end_date",
            "duration_days",
        ):
            if key not in period:
                raise ManifestError(f"Financial period missing '{key}'")
        if period["period_type"] != "annual":
            raise ManifestError(
                f"Financial period '{period['period']}' is not an annual period"
            )
        if period["period"] != f"FY{period['fiscal_year']}":
            raise ManifestError(
                f"Financial period label '{period['period']}' does not match fiscal_year "
                f"{period['fiscal_year']}"
            )
        try:
            start = date.fromisoformat(period["start_date"])
            end = date.fromisoformat(period["end_date"])
        except (TypeError, ValueError) as exc:
            raise ManifestError(
                f"Financial period '{period['period']}' has invalid start/end dates"
            ) from exc
        if end < start:
            raise ManifestError(
                f"Financial period '{period['period']}' ends before it starts"
            )
        actual_duration = (end - start).days + 1
        if period["duration_days"] != actual_duration:
            raise ManifestError(
                f"Financial period '{period['period']}' duration_days must be "
                f"{actual_duration}, found {period['duration_days']}"
            )
        if not 350 <= actual_duration <= 380:
            raise ManifestError(
                f"Financial period '{period['period']}' is {actual_duration} days; "
                "transition or non-annual periods cannot drive an annual trend"
            )
        if period["period"] in labels or period["end_date"] in end_dates:
            raise ManifestError("Financial periods require unique labels and end dates")
        labels.add(period["period"])
        end_dates.add(period["end_date"])
        normalized.append(
            {
                "period": period["period"],
                "fiscal_year": period["fiscal_year"],
                "start_date": period["start_date"],
                "end_date": period["end_date"],
                "duration_days": actual_duration,
            }
        )

    normalized.sort(key=lambda item: item["end_date"])
    if len(normalized) >= 2:
        prior, latest = normalized[-2:]
        duration_delta = abs(latest["duration_days"] - prior["duration_days"])
        if duration_delta > 7:
            raise ManifestError(
                "Latest and prior annual periods differ by more than 7 days and are not "
                "comparable without human normalization"
            )
    else:
        duration_delta = None
    return {
        "status": "comparable_annual" if len(normalized) >= 2 else "single_annual_period",
        "label_basis": "fiscal year ending year",
        "uses_sec_frame": False,
        "duration_delta_days": duration_delta,
        "periods": normalized,
    }


def _fact(period: dict[str, Any], name: str, source_ids: set[str]) -> dict[str, Any] | None:
    raw = period.get("facts", {}).get(name)
    if raw is None:
        return None
    for key in ("value", "source_id", "locator"):
        if key not in raw:
            raise ManifestError(
                f"Financial fact '{name}' in {period.get('period')} missing '{key}'"
            )
    if not isinstance(raw["value"], (int, float)):
        raise ManifestError(f"Financial fact '{name}' must have a numeric value")
    if raw["source_id"] not in source_ids:
        raise ManifestError(f"Financial fact '{name}' cites unknown source id '{raw['source_id']}'")
    if name in {
        "revenue",
        "operating_cost",
        "gross_profit",
        "net_income",
        "net_income_continuing",
        "operating_cash_flow",
    }:
        try:
            statement_scope(raw, name)
        except ValueError as exc:
            raise ManifestError(str(exc)) from exc
    selection = raw.get("selection")
    if selection is not None:
        for key in ("concept", "method", "basis", "basis_zh", "excluded_candidates"):
            if key not in selection:
                raise ManifestError(
                    f"Financial fact '{name}' selection metadata missing '{key}'"
                )
        reconciliation = selection.get("reconciliation")
        if reconciliation is not None and reconciliation.get("passed") is not True:
            raise ManifestError(
                f"Financial fact '{name}' failed statement-identity reconciliation"
            )
    return raw


def _input(name: str, period: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    item = {
        "name": name,
        "period": period["period"],
        "value": fact["value"],
        "source_id": fact["source_id"],
        "locator": fact["locator"],
    }
    if "selection" in fact:
        item["selection"] = fact["selection"]
    if "statement_scope" in fact:
        item["statement_scope"] = fact["statement_scope"]
    if "accounting_scope" in fact:
        item["accounting_scope"] = fact["accounting_scope"]
    return item


def derive_financial_metrics(
    financials: dict[str, Any] | None,
    source_ids: set[str],
    inapplicable_dimensions: set[str] | None = None,
    applicability_outcomes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not financials:
        return {
            "currency": None,
            "periods": [],
            "metrics": [],
            "status": "not_provided",
            "note": "Add cited structured financial facts to enable deterministic ratios.",
        }
    periods = financials.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ManifestError("'financials.periods' must be a non-empty list")
    period_contract = validate_period_contract(periods)
    periods = sorted(periods, key=lambda period: period["end_date"])
    latest = periods[-1]
    prior = periods[-2] if len(periods) > 1 else None
    currency = financials.get("currency", "USD")
    metrics: list[dict[str, Any]] = []
    screening_notes: list[dict[str, Any]] = []
    inapplicable_dimensions = inapplicable_dimensions or set()
    applicability_outcomes = applicability_outcomes or {}
    profitability_applicable = (
        "profitability-unit-economics" not in inapplicable_dimensions
    )

    def add(
        metric_id: str,
        name: str,
        value: float,
        unit: str,
        formula: str,
        inputs: list[dict[str, Any]],
        signal: str = "observed",
    ) -> None:
        metrics.append(
            {
                "id": metric_id,
                "name": name,
                "period": latest["period"],
                "value": round(value, 4),
                "unit": unit,
                "formula": formula,
                "inputs": inputs,
                "signal": signal,
            }
        )

    revenue = _fact(latest, "revenue", source_ids) if profitability_applicable else None
    prior_revenue = (
        _fact(prior, "revenue", source_ids)
        if profitability_applicable and prior
        else None
    )
    if revenue and prior_revenue and prior_revenue["value"]:
        value = (revenue["value"] - prior_revenue["value"]) / abs(prior_revenue["value"])
        add(
            "revenue-growth",
            "Revenue growth",
            value,
            "ratio",
            "(latest revenue - prior revenue) / abs(prior revenue)",
            [_input("revenue", latest, revenue), _input("revenue", prior, prior_revenue)],
        )

    gross_profit = (
        _fact(latest, "gross_profit", source_ids) if profitability_applicable else None
    )
    operating_cost = (
        _fact(latest, "operating_cost", source_ids) if profitability_applicable else None
    )
    if profitability_applicable and revenue and gross_profit and revenue["value"]:
        value = gross_profit["value"] / revenue["value"]
        add(
            "gross-margin",
            "Gross margin",
            value,
            "ratio",
            "gross profit / revenue",
            [_input("gross_profit", latest, gross_profit), _input("revenue", latest, revenue)],
            "attention" if value < 0 else "observed",
        )
    elif profitability_applicable and revenue and operating_cost and revenue["value"]:
        value = (revenue["value"] - operating_cost["value"]) / revenue["value"]
        add(
            "gross-margin",
            "Gross margin",
            value,
            "ratio",
            "(revenue - operating cost) / revenue",
            [
                _input("revenue", latest, revenue),
                _input("operating_cost", latest, operating_cost),
            ],
            "attention" if value < 0 else "observed",
        )

    operating_income = (
        _fact(latest, "operating_income", source_ids) if profitability_applicable else None
    )
    if revenue and operating_income and revenue["value"]:
        value = operating_income["value"] / revenue["value"]
        add(
            "operating-margin",
            "Operating margin",
            value,
            "ratio",
            "operating income / revenue",
            [
                _input("operating_income", latest, operating_income),
                _input("revenue", latest, revenue),
            ],
            "attention" if value < 0 else "observed",
        )

    net_income = None
    net_income_id = "net_income"
    if profitability_applicable and revenue and (gross_profit or operating_cost):
        try:
            target_scope = margin_operations_scope(latest)
            net_income_id, _, _ = select_net_income_fact(latest, target_scope)
            net_income = _fact(latest, net_income_id, source_ids)
        except ValueError as exc:
            raise ManifestError(str(exc)) from exc
    if revenue and net_income and revenue["value"]:
        value = net_income["value"] / revenue["value"]
        add(
            "net-margin",
            "Net margin",
            value,
            "ratio",
            "net income / revenue",
            [
                _input(net_income_id, latest, net_income),
                _input("revenue", latest, revenue),
            ],
            "attention" if value < 0 else "observed",
        )
    if not profitability_applicable:
        applicability = applicability_outcomes.get("profitability-unit-economics", {})
        screening_notes.append(
            {
                "id": "profitability-unit-economics-not-applicable",
                "status": applicability.get("status", "not_applicable"),
                "reason_code": applicability.get("reason_code"),
                "text": applicability.get("reason")
                or (
                    "Revenue and margin calculations were suppressed because the classified "
                    "business-model scope is not applicable."
                ),
                "text_zh": applicability.get("reason_zh"),
            }
        )

    operating_cash_flow = _fact(latest, "operating_cash_flow", source_ids)
    capex = _fact(latest, "capex", source_ids)
    free_cash_flow: float | None = None
    free_cash_inputs: list[dict[str, Any]] = []
    if operating_cash_flow and capex:
        free_cash_flow = operating_cash_flow["value"] - abs(capex["value"])
        free_cash_inputs = [
            _input("operating_cash_flow", latest, operating_cash_flow),
            _input("capex", latest, capex),
        ]
        add(
            "free-cash-flow",
            "Free cash flow",
            free_cash_flow,
            currency,
            "operating cash flow - abs(capex)",
            free_cash_inputs,
            "attention" if free_cash_flow < 0 else "observed",
        )
        if capex["value"]:
            add(
                "operating-cash-flow-to-capex",
                "Operating cash flow to capex",
                operating_cash_flow["value"] / abs(capex["value"]),
                "ratio",
                "operating cash flow / abs(capex)",
                [
                    _input("operating_cash_flow", latest, operating_cash_flow),
                    _input("capex", latest, capex),
                ],
                "attention" if operating_cash_flow["value"] < abs(capex["value"]) else "observed",
            )

    cash = _fact(latest, "cash_and_equivalents", source_ids)
    if cash and free_cash_flow is not None and free_cash_flow < 0:
        months = cash["value"] / abs(free_cash_flow) * 12
        add(
            "cash-runway-months",
            "Simple cash runway",
            months,
            "months",
            "cash and equivalents / abs(annual free cash flow) * 12",
            [_input("cash_and_equivalents", latest, cash), *free_cash_inputs],
            "observed",
        )
        screening_notes.append(
            {
                "id": "runway-relative-review",
                "status": "human_review",
                "text": (
                    "Runway is reported as an observed calculation without a universal "
                    "red/amber/green threshold. Classify the business model and compare financing "
                    "cycle, commitments, and genuinely comparable companies before interpretation."
                ),
            }
        )
    elif free_cash_flow is not None and free_cash_flow >= 0:
        screening_notes.append(
            {
                "id": "runway-not-applicable",
                "status": "human_review",
                "text": (
                    "Simple cash runway is not calculated because observed annual free cash flow "
                    "is non-negative. This does not prove future funding sufficiency; review forward "
                    "capex, working capital, commitments, and downside scenarios."
                ),
            }
        )

    debt = _fact(latest, "total_debt", source_ids)
    if cash and debt:
        net_cash = cash["value"] - debt["value"]
        add(
            "net-cash",
            "Net cash",
            net_cash,
            currency,
            "cash and equivalents - total debt",
            [_input("cash_and_equivalents", latest, cash), _input("total_debt", latest, debt)],
            "attention" if net_cash < 0 else "observed",
        )

    if capex and revenue and revenue["value"]:
        value = abs(capex["value"]) / abs(revenue["value"])
        add(
            "capex-to-revenue",
            "Capex to revenue",
            value,
            "ratio",
            "abs(capex) / abs(revenue)",
            [_input("capex", latest, capex), _input("revenue", latest, revenue)],
        )

    backlog = _fact(latest, "backlog", source_ids)
    if backlog and revenue and revenue["value"]:
        value = backlog["value"] / abs(revenue["value"])
        add(
            "backlog-to-revenue",
            "Backlog to annual revenue",
            value,
            "ratio",
            "backlog / abs(revenue)",
            [_input("backlog", latest, backlog), _input("revenue", latest, revenue)],
        )

    return {
        "currency": currency,
        "periods": [period["period"] for period in periods],
        "period_contract": period_contract,
        "metrics": metrics,
        "screening_notes": screening_notes,
        "status": "calculated",
        "note": "Signals are deterministic screening rules, not investment recommendations.",
    }
