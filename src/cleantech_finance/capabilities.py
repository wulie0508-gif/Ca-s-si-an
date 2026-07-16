"""Truthful product-completion matrix for public claims and report labels."""

from __future__ import annotations

from typing import Any

from .finance_framework import FINANCE_DIMENSIONS
from .framework import DIMENSIONS
from .rules import rule_status_for_dimension

VALIDATED_FINANCE = {
    "profitability-unit-economics",
    "cash-runway",
}


def capability_matrix() -> dict[str, Any]:
    finance = []
    for dimension in FINANCE_DIMENSIONS:
        validated = dimension.id in VALIDATED_FINANCE
        rule_status = rule_status_for_dimension(dimension.id)
        finance.append(
            {
                "id": dimension.id,
                "name": dimension.name,
                "status": "validated_end_to_end" if validated else "framework_ready_unvalidated",
                "rule_status": rule_status,
                "public_cases": ["Sungrow 2025", "Enphase 2025"] if validated else [],
                "judgment_card": "implemented_and_validated" if validated else "not_implemented",
                "claim_boundary": (
                    "Audited facts, calculations, five-cell card structure, citations, and gaps are regression-tested."
                    if validated
                    else "A scoped rule input contract is authored, but extraction, signal branches, and judgment output are not publicly validated."
                ),
            }
        )
    adoption = [
        {
            "id": dimension.id,
            "name": dimension.name,
            "status": "framework_ready_unvalidated",
            "public_cases": [],
            "judgment_card": "not_implemented",
            "claim_boundary": "Retrieval cues exist; no validated risk conclusion or ARL score is produced.",
        }
        for dimension in DIMENSIONS
    ]
    return {
        "finance": finance,
        "adoption_risk": adoption,
        "summary": {
            "validated_finance_dimensions": len(VALIDATED_FINANCE),
            "total_finance_dimensions": len(FINANCE_DIMENSIONS),
            "validated_rule_dimensions": sum(
                rule_status_for_dimension(item.id) == "validated" for item in FINANCE_DIMENSIONS
            ),
            "authored_only_rule_dimensions": sum(
                rule_status_for_dimension(item.id) == "authored" for item in FINANCE_DIMENSIONS
            ),
            "validated_adoption_dimensions": 0,
            "total_adoption_dimensions": len(DIMENSIONS),
        },
        "public_claim": (
            "Two finance dimensions have deterministic rule branches and ordered public-case "
            "regression. Four additional dimensions have authored input contracts only. The "
            "29/29 and 28/28 extraction checks and 27/27 card checks do not validate "
            "investment, credit, or aggregate risk judgments."
        ),
    }
