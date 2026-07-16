from __future__ import annotations

from typing import Any

from scripts.collect_sec_case import _select_facts


def _annual(value: float) -> list[dict[str, Any]]:
    return [
        {
            "val": value,
            "start": "2025-01-01",
            "end": "2025-12-31",
            "form": "10-K",
            "accn": "0000000000-26-000001",
            "filed": "2026-02-09",
        }
    ]


def _concept(value: float) -> dict[str, Any]:
    return {"units": {"USD": _annual(value)}}


def test_statement_identity_selects_consolidated_revenue_and_cost() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": _concept(2_023_994_000),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    2_001_614_000
                ),
                "CostOfRevenue": _concept(1_436_594_000),
                "CostOfGoodsAndServicesSold": _concept(18_000_000),
                "GrossProfit": _concept(587_400_000),
                "ProfitLoss": _concept(-87_140_000),
                "NetCashProvidedByUsedInOperatingActivities": _concept(113_949_000),
                "PaymentsToAcquirePropertyPlantAndEquipment": _concept(56_759_000),
                "CashAndCashEquivalentsAtCarryingValue": _concept(2_454_108_000),
            }
        }
    }

    selected = _select_facts(
        companyfacts,
        "2025-12-31",
        "0000000000-26-000001",
        "USD",
    )

    assert selected["revenue"]["concept"] == "Revenues"
    assert selected["operating_cost"]["concept"] == "CostOfRevenue"
    assert selected["gross_profit"]["concept"] == "GrossProfit"
    assert selected["revenue"]["selection"]["reconciliation"] == {
        "equation": "revenue - operating_cost = gross_profit",
        "difference": 0.0,
        "unit": "USD",
        "passed": True,
    }
    excluded = selected["revenue"]["selection"]["excluded_candidates"]
    assert {item["concept"] for item in excluded} == {
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    }

