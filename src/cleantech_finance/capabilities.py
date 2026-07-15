"""Truthful product-completion matrix for public claims and report labels."""

from __future__ import annotations

from typing import Any

from .finance_framework import FINANCE_DIMENSIONS
from .framework import DIMENSIONS

VALIDATED_FINANCE = {
    "profitability-unit-economics",
    "cash-runway",
}


def capability_matrix() -> dict[str, Any]:
    finance = []
    for dimension in FINANCE_DIMENSIONS:
        validated = dimension.id in VALIDATED_FINANCE
        finance.append(
            {
                "id": dimension.id,
                "name": dimension.name,
                "status": "validated_end_to_end" if validated else "framework_ready_unvalidated",
                "public_cases": ["Sungrow 2025", "Enphase 2025"] if validated else [],
                "judgment_card": "implemented_and_validated" if validated else "not_implemented",
                "claim_boundary": (
                    "Audited facts, calculations, five-cell card structure, citations, and gaps are regression-tested."
                    if validated
                    else "Lexical retrieval lens exists; extraction and judgment output are not publicly validated."
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
            "validated_adoption_dimensions": 0,
            "total_adoption_dimensions": len(DIMENSIONS),
        },
        "public_claim": (
            "The 29/29 and 28/28 checks validate extraction, page locators, formulas, "
            "citation integrity, and guardrails for two dimensions. They do not validate "
            "investment, credit, or risk judgments."
        ),
    }
