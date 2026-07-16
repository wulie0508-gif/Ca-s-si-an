"""Accounting-scope selection for facts that can control rule branches."""

from __future__ import annotations

from typing import Any

VALID_OPERATIONS_SCOPES = {"total_operations", "continuing_operations"}
VALID_ATTRIBUTIONS = {"consolidated", "attributable_to_parent", "not_applicable"}


def statement_scope(fact: dict[str, Any], fact_id: str) -> dict[str, str]:
    scope = fact.get("statement_scope")
    if not isinstance(scope, dict):
        raise ValueError(f"Financial fact '{fact_id}' requires statement_scope metadata")
    operations = scope.get("operations")
    attribution = scope.get("attribution")
    if operations not in VALID_OPERATIONS_SCOPES:
        raise ValueError(
            f"Financial fact '{fact_id}' has unsupported operations scope '{operations}'"
        )
    if attribution not in VALID_ATTRIBUTIONS:
        raise ValueError(
            f"Financial fact '{fact_id}' has unsupported attribution '{attribution}'"
        )
    return {"operations": operations, "attribution": attribution}


def margin_operations_scope(period: dict[str, Any]) -> str:
    facts = period["facts"]
    component_id = "gross_profit" if "gross_profit" in facts else "operating_cost"
    revenue_scope = statement_scope(facts["revenue"], "revenue")["operations"]
    component_scope = statement_scope(facts[component_id], component_id)["operations"]
    if revenue_scope != component_scope:
        raise ValueError(
            f"Financial period '{period['period']}' mixes revenue '{revenue_scope}' with "
            f"{component_id} '{component_scope}'"
        )
    return revenue_scope


def cash_operations_scope(period: dict[str, Any]) -> str:
    return statement_scope(
        period["facts"]["operating_cash_flow"], "operating_cash_flow"
    )["operations"]


def select_net_income_fact(
    period: dict[str, Any], operations_scope: str
) -> tuple[str, dict[str, Any], dict[str, str]]:
    matches: list[tuple[str, dict[str, Any], dict[str, str]]] = []
    for fact_id in ("net_income", "net_income_continuing"):
        fact = period.get("facts", {}).get(fact_id)
        if fact is None:
            continue
        scope = statement_scope(fact, fact_id)
        if scope["operations"] == operations_scope:
            matches.append((fact_id, fact, scope))
    if len(matches) != 1:
        raise ValueError(
            f"Financial period '{period['period']}' requires exactly one net-income fact "
            f"for operations scope '{operations_scope}', found {len(matches)}"
        )
    return matches[0]

