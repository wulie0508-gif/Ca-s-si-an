from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from cleantech_finance.audit import run_audit, validate_audit
from cleantech_finance.reporting import html_report, markdown_report
from cleantech_finance.rules import PRE_COMMERCIAL_TECHNOLOGY_SCOPE

ROOT = Path(__file__).parents[1]
MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8")
)


def _fact(
    value: float,
    *,
    attribution: str = "not_applicable",
) -> dict[str, object]:
    return {
        "value": value,
        "source_id": "subject-filing",
        "locator": "audited statements",
        "statement_scope": {
            "operations": "total_operations",
            "attribution": attribution,
        },
    }


def _payload() -> dict[str, object]:
    def period(
        fiscal_year: int,
        *,
        net_income: float,
        operating_cash_flow: float,
        capex: float,
        cash: float,
    ) -> dict[str, object]:
        return {
            "period": f"FY{fiscal_year}",
            "fiscal_year": fiscal_year,
            "period_type": "annual",
            "start_date": f"{fiscal_year}-01-01",
            "end_date": f"{fiscal_year}-12-31",
            "duration_days": 366 if fiscal_year == 2024 else 365,
            "facts": {
                "net_income": _fact(net_income, attribution="consolidated"),
                "operating_cash_flow": _fact(operating_cash_flow),
                "capex": {
                    "value": capex,
                    "source_id": "subject-filing",
                    "locator": "audited cash-flow statement",
                },
                "cash_and_equivalents": {
                    "value": cash,
                    "source_id": "subject-filing",
                    "locator": "audited balance sheet",
                },
            },
        }

    citation = {"source_id": "subject-filing", "locator": "business and financial review"}
    cash_dimension = {
        "benchmark": {
            "scope": "Use the subject's own cash-use direction; no peer threshold is used.",
            "scope_zh": "仅使用主体自身现金消耗方向，不使用同业绝对阈值。",
            "observations": [
                {
                    "comparison_type": "subject_history",
                    "entity": "Illustrative Technology Developer",
                    "business_model": "Pre-commercial technology development",
                    "metric": "Operating cash use",
                    "period": "FY2025",
                    "value": -40.0,
                    "unit": "USD",
                    "display_value": "USD -40.0",
                    "citation": citation,
                }
            ],
            "limitations": ["No forward financing schedule is treated as verified."],
            "limitations_zh": ["尚未把前瞻融资计划视为已核实事实。"],
        },
        "gaps": [
            {
                "kind": "evidence_gap",
                "text": "A forward funding schedule is missing.",
                "text_zh": "缺少前瞻资金计划。",
            },
            {
                "kind": "human_judgment",
                "text": "Assess whether planned milestones are financeable.",
                "text_zh": "判断计划里程碑是否具备融资可行性。",
            },
            {
                "kind": "verification",
                "text": "Verify cash commitments after the reporting date.",
                "text_zh": "核验报告日后的现金承诺。",
            },
        ],
    }
    return {
        "subject": {
            "organization": "Illustrative Technology Developer",
            "technology": "Solid-state lithium-metal battery platform",
            "ticker": "TEST",
        },
        "assessment": {
            "as_of": "2026-01-15",
            "horizon_years": 5,
            "geography": "Global",
            "value_chain_scope": "Technology development and licensing",
        },
        "sources": [
            {
                "id": "subject-filing",
                "path": "subject.txt",
                "title": "Audited annual filing",
                "url": "https://example.com/subject-filing",
                "publisher": "Illustrative Technology Developer",
                "published": "2026-01-10",
                "kind": "audited_financial",
                "role": "subject",
            }
        ],
        "financials": {
            "currency": "USD",
            "periods": [
                period(
                    2024,
                    net_income=-70.0,
                    operating_cash_flow=-50.0,
                    capex=10.0,
                    cash=150.0,
                ),
                period(
                    2025,
                    net_income=-80.0,
                    operating_cash_flow=-40.0,
                    capex=12.0,
                    cash=180.0,
                ),
            ],
        },
        "applicability_context": {
            "contract_version": "1.0.0",
            "commercialization_stage": {
                "state": "pre_commercial",
                "as_of": "2025-12-31",
                "basis": [citation],
            },
            "recognized_operating_revenue": {
                "state": "none_recognized",
                "periods": ["FY2024", "FY2025"],
                "basis": [citation],
            },
        },
        "judgment_context": {
            "contract_version": "0.3.0",
            "prepared_by": "test fixture",
            "prepared_at": "2026-01-15",
            "subindustry": {
                "scope_id": PRE_COMMERCIAL_TECHNOLOGY_SCOPE,
                "name": "Pre-commercial solid-state battery technology developer",
                "name_zh": "预商业化固态电池技术开发商",
                "value_chain_position": "Technology development and licensing",
                "value_chain_position_zh": "技术开发与许可",
                "summary": "Subject evidence supports the exact pre-commercial scope.",
                "summary_zh": "主体证据支持精确的预商业化业务范围。",
                "basis": [citation],
            },
            "dimensions": {"cash-runway": cash_dimension},
        },
    }


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "subject.txt").write_text(
        "Audited subject evidence describes pre-commercial technology development, "
        "no recognized operating revenue, operating losses, cash use, and capital spending.",
        encoding="utf-8",
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _run(tmp_path: Path, payload: dict[str, object]) -> dict[str, object]:
    return run_audit(
        str(_write_manifest(tmp_path, payload)),
        only_dimensions={"profitability-unit-economics", "cash-runway"},
    )


def test_precommercial_profitability_is_not_yet_applicable_and_cash_is_independent(
    tmp_path: Path,
) -> None:
    payload = _payload()
    schema_errors = list(
        Draft202012Validator(
            MANIFEST_SCHEMA, format_checker=FormatChecker()
        ).iter_errors(payload)
    )
    assert not schema_errors

    audit = _run(tmp_path, payload)

    assert audit["validation"]["passed"], audit["validation"]["errors"]
    outcomes = {
        item["dimension_id"]: item
        for item in audit["judgment_layer"]["dimension_outcomes"]
    }
    profitability = outcomes["profitability-unit-economics"]
    assert profitability["status"] == "not_yet_applicable"
    assert profitability["signal"] is None
    assert profitability["reason_code"] == (
        "pre_commercial_no_recognized_operating_revenue"
    )
    assert profitability["reason"] and profitability["reason_zh"]
    assert profitability["policy_id"]
    assert profitability["policy_version"] == "1.0.0"
    assert profitability["policy_digest"].startswith("sha256:")
    assert profitability["inputs_digest"].startswith("sha256:")
    assert {item["role"] for item in profitability["basis"]} == {"subject"}

    cards = {
        item["dimension_id"]: item for item in audit["judgment_layer"]["cards"]
    }
    assert cards["cash-runway"]["signal"] == "amber"
    metric_ids = {item["id"] for item in audit["financial_analysis"]["metrics"]}
    assert {
        "revenue-growth",
        "gross-margin",
        "operating-margin",
        "net-margin",
        "capex-to-revenue",
    }.isdisjoint(metric_ids)
    assert {
        "free-cash-flow",
        "operating-cash-flow-to-capex",
        "cash-runway-months",
    }.issubset(metric_ids)
    rendered = markdown_report(audit) + html_report(audit)
    assert "Not yet applicable" in rendered
    assert "暂不适用" in rendered
    assert profitability["reason_code"] in rendered
    assert profitability["policy_digest"] in rendered
    assert profitability["inputs_digest"] in rendered


def test_applicability_digest_does_not_depend_on_company_identity_or_display_text(
    tmp_path: Path,
) -> None:
    baseline = _run(tmp_path / "baseline", _payload())
    renamed_payload = _payload()
    renamed_payload["subject"]["organization"] = "Renamed Display Company"
    renamed_payload["subject"]["ticker"] = "RENAMED"
    renamed_payload["judgment_context"]["subindustry"]["name"] = "Renamed scope label"
    renamed_payload["judgment_context"]["subindustry"]["summary"] = (
        "Different display prose with the same evidence inputs."
    )
    renamed = _run(tmp_path / "renamed", renamed_payload)

    def profitability(audit: dict[str, object]) -> dict[str, object]:
        return next(
            item
            for item in audit["judgment_layer"]["dimension_outcomes"]
            if item["dimension_id"] == "profitability-unit-economics"
        )

    assert profitability(renamed)["policy_digest"] == profitability(baseline)[
        "policy_digest"
    ]
    assert profitability(renamed)["inputs_digest"] == profitability(baseline)[
        "inputs_digest"
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda payload: payload["applicability_context"][
                "recognized_operating_revenue"
            ].update({"basis": []}),
            "basis must contain at least one citation",
        ),
        (
            lambda payload: payload["applicability_context"][
                "recognized_operating_revenue"
            ].update({"periods": ["FY2025"]}),
            "must cover all financial periods",
        ),
        (
            lambda payload: payload["applicability_context"][
                "commercialization_stage"
            ].update({"as_of": "2026-01-16"}),
            "cannot be later than assessment.as_of",
        ),
    ],
)
def test_missing_or_misaligned_applicability_evidence_fails_validation_without_blocking_cash(
    tmp_path: Path,
    mutation: object,
    expected_error: str,
) -> None:
    payload = _payload()
    mutation(payload)
    audit = _run(tmp_path, payload)

    assert not audit["validation"]["passed"]
    assert expected_error in " ".join(audit["validation"]["errors"])
    assert not any(
        item["status"] == "not_yet_applicable"
        for item in audit["judgment_layer"]["dimension_outcomes"]
    )
    assert {item["dimension_id"] for item in audit["judgment_layer"]["cards"]} == {
        "cash-runway"
    }


def test_applicability_basis_rejects_non_subject_source_without_blocking_cash(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["sources"].append(
        {
            "id": "benchmark-report",
            "path": "benchmark.txt",
            "title": "Benchmark report",
            "url": "https://example.com/benchmark",
            "publisher": "Benchmark publisher",
            "published": "2026-01-10",
            "kind": "industry_report",
            "role": "benchmark",
        }
    )
    (tmp_path / "benchmark.txt").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmark.txt").write_text(
        "External benchmark material cannot establish the subject's commercialization stage.",
        encoding="utf-8",
    )
    payload["applicability_context"]["commercialization_stage"]["basis"] = [
        {"source_id": "benchmark-report", "locator": "p.1"}
    ]
    audit = _run(tmp_path, payload)

    assert not audit["validation"]["passed"]
    assert "same-subject role=subject sources only" in " ".join(
        audit["validation"]["errors"]
    )
    assert {item["dimension_id"] for item in audit["judgment_layer"]["cards"]} == {
        "cash-runway"
    }


def test_near_scope_and_ordinary_missing_revenue_fail_closed(tmp_path: Path) -> None:
    for index, scope_id in enumerate(
        (
            PRE_COMMERCIAL_TECHNOLOGY_SCOPE + "-adjacent",
            "storage-equipment",
        )
    ):
        payload = _payload()
        payload["judgment_context"]["subindustry"]["scope_id"] = scope_id
        audit = _run(tmp_path / str(index), payload)
        assert not audit["validation"]["passed"]
        assert not any(
            item["status"] == "not_yet_applicable"
            for item in audit["judgment_layer"]["dimension_outcomes"]
        )
        cash_cards = {
            item["dimension_id"] for item in audit["judgment_layer"]["cards"]
        }
        assert cash_cards == (set() if index == 0 else {"cash-runway"})


@pytest.mark.parametrize("forbidden", ["outcome", "signal", "reason"])
def test_manifest_schema_and_runtime_forbid_applicability_outcomes(
    tmp_path: Path, forbidden: str
) -> None:
    payload = _payload()
    payload["applicability_context"][forbidden] = "agent-authored override"
    errors = list(
        Draft202012Validator(
            MANIFEST_SCHEMA, format_checker=FormatChecker()
        ).iter_errors(payload)
    )
    assert errors
    audit = _run(tmp_path, payload)
    assert not audit["validation"]["passed"]
    assert "cannot provide policy-owned fields" in " ".join(
        audit["validation"]["errors"]
    )
    assert not any(
        item["status"] == "not_yet_applicable"
        for item in audit["judgment_layer"]["dimension_outcomes"]
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("source_id", "unknown-source", "Unknown applicability-outcome source"),
        ("locator", "", "missing a locator or URL"),
        ("url", "", "missing a locator or URL"),
    ],
)
def test_audit_validation_checks_applicability_outcome_citations(
    tmp_path: Path,
    field: str,
    value: str,
    expected: str,
) -> None:
    audit = _run(tmp_path, _payload())
    tampered = copy.deepcopy(audit)
    outcome = next(
        item
        for item in tampered["judgment_layer"]["dimension_outcomes"]
        if item["status"] == "not_yet_applicable"
    )
    outcome["basis"][0][field] = value
    validation = validate_audit(tampered)
    assert not validation["passed"]
    assert expected in " ".join(validation["errors"])
