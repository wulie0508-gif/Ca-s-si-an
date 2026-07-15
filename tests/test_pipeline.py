from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleantech_finance.audit import run_audit, validate_audit
from cleantech_finance.ingest import ManifestError
from cleantech_finance.reporting import card_html, card_markdown, write_artifacts


@pytest.fixture()
def manifest(tmp_path: Path) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "sample-annual-report.txt"
    source = tmp_path / "annual-report.txt"
    source.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "subject": {
            "organization": "Example Storage Systems",
            "technology": "Grid-scale storage",
            "ticker": None,
        },
        "assessment": {
            "as_of": "2026-03-01",
            "horizon_years": 5,
            "geography": "Global",
            "value_chain_scope": "Consolidated company",
        },
        "sources": [
            {
                "id": "annual-report",
                "path": "annual-report.txt",
                "title": "2025 annual report",
                "url": "https://example.com/annual-report",
                "publisher": "Example Storage Systems",
                "published": "2026-02-01",
                "kind": "audited_financial",
            }
        ],
        "financial_extraction": {
            "enabled": True,
            "source_id": "annual-report",
            "currency": "USD",
            "years": [2025, 2024],
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_auto_extraction_uses_consolidated_statements(manifest: Path) -> None:
    audit = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    extraction = audit["financial_fact_extraction"]
    periods = {period["period"]: period["facts"] for period in extraction["financials"]["periods"]}
    assert periods["FY2025"]["revenue"]["value"] == 120.0
    assert periods["FY2025"]["operating_cost"]["value"] == 78.0
    assert periods["FY2025"]["operating_cash_flow"]["value"] == -12.0
    assert periods["FY2025"]["capex"]["value"] == 3.0
    assert periods["FY2025"]["cash_and_equivalents"]["value"] == 18.0
    assert periods["FY2025"]["net_income"]["value"] == 8.0
    assert all(fact["value"] not in {999.0, 777.0} for fact in periods["FY2025"].values())


def test_formulas_and_negative_cash_runway(manifest: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    metrics = {metric["id"]: metric for metric in audit["financial_analysis"]["metrics"]}
    assert metrics["revenue-growth"]["value"] == pytest.approx(0.2)
    assert metrics["gross-margin"]["value"] == pytest.approx(0.35)
    assert metrics["free-cash-flow"]["value"] == pytest.approx(-15.0)
    assert metrics["net-margin"]["value"] == pytest.approx(0.0667)
    assert metrics["operating-cash-flow-to-capex"]["value"] == pytest.approx(-4.0)
    assert metrics["cash-runway-months"]["value"] == pytest.approx(14.4)
    assert metrics["cash-runway-months"]["signal"] == "observed"


def test_only_dimensions_and_no_automated_rating(manifest: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"profitability-unit-economics"})
    assert [item["id"] for item in audit["finance_evidence"]] == ["profitability-unit-economics"]
    assert audit["adoption_risk_evidence"] == []
    assert audit["finance_evidence"][0]["human_rating"] is None
    assert audit["execution"]["model_calls"] == 0
    assert audit["execution"]["estimated_model_cost"] == 0
    assert audit["validation"]["passed"]


def test_parent_company_evidence_is_excluded(manifest: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"}, top_k=10)
    excerpts = " ".join(
        candidate["excerpt"] for candidate in audit["finance_evidence"][0]["candidates"]
    )
    assert "999.00" not in excerpts
    assert "777.00" not in excerpts


def test_writes_all_artifacts(manifest: Path, tmp_path: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    paths = write_artifacts(audit, tmp_path / "out")
    assert set(paths) == {
        "json",
        "markdown",
        "html",
        "dimension_cards_json",
        "evidence_csv",
        "review_queue_csv",
        "financial_metrics_csv",
    }
    assert all(Path(path).is_file() for path in paths.values())


def test_validation_rejects_automated_human_rating(manifest: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    audit["finance_evidence"][0]["human_rating"] = "low"
    validation = validate_audit(audit)
    assert not validation["passed"]
    assert "automated rating" in validation["errors"][0]


def test_unknown_dimension_fails(manifest: Path) -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        run_audit(str(manifest), only_dimensions={"not-a-real-dimension"})


def test_unknown_financial_source_fails(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["financial_extraction"]["source_id"] = "missing"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError, match="source_id"):
        run_audit(str(manifest), only_dimensions={"cash-runway"})


def test_us_gaap_thousands_three_years_and_parentheses(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "us-gaap-annual-report.txt"
    source = tmp_path / "annual-report.txt"
    source.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "subject": {
            "organization": "Example Solar Systems",
            "technology": "Solar inverters",
            "ticker": "EXAMPLE",
        },
        "assessment": {
            "as_of": "2026-03-01",
            "horizon_years": 5,
            "geography": "Global",
            "value_chain_scope": "Consolidated company",
        },
        "sources": [
            {
                "id": "annual-report",
                "path": "annual-report.txt",
                "title": "2025 Form 10-K",
                "url": "https://example.com/form-10-k",
                "publisher": "Example Solar Systems",
                "published": "2026-02-01",
                "kind": "audited_financial",
            }
        ],
        "financial_extraction": {
            "enabled": True,
            "source_id": "annual-report",
            "currency": "USD",
            "years": [2025, 2024],
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    audit = run_audit(str(path), only_dimensions={"profitability-unit-economics", "cash-runway"})
    extraction = audit["financial_fact_extraction"]
    periods = {period["period"]: period["facts"] for period in extraction["financials"]["periods"]}
    assert periods["FY2025"]["revenue"]["value"] == 1_472_985_000.0
    assert periods["FY2024"]["operating_cost"]["value"] == 701_245_000.0
    assert periods["FY2025"]["operating_cash_flow"]["value"] == 136_540_000.0
    assert periods["FY2025"]["capex"]["value"] == 40_639_000.0
    assert periods["FY2024"]["cash_and_equivalents"]["value"] == 369_110_000.0
    assert periods["FY2025"]["net_income"]["value"] == 172_133_000.0
    assert all(item["unit_scale"] == 1_000.0 for item in extraction["extraction_log"])


def _judgment_context() -> dict[str, object]:
    citation = {"source_id": "annual-report", "locator": "lines 1-20"}

    def dimension(signal: str) -> dict[str, object]:
        return {
            "benchmark": {
                "scope": "Use the company's prior period first and an adjacent-company reference only as context.",
                "observations": [
                    {
                        "entity": "Example Storage Systems",
                        "business_model": "Storage equipment",
                        "metric": "Historical comparison",
                        "period": "FY2025",
                        "value": 1.0,
                        "unit": "ratio",
                        "display_value": "1.00x",
                        "citation": citation,
                    }
                ],
                "limitations": ["No peer percentile or like-for-like benchmark was constructed."],
            },
            "application": {
                "signal": signal,
                "path": "Classify first, compare the company's own trend, then inspect adjacent context.",
                "summary": "The evidence is mixed and remains subject to human review.",
                "basis": [citation],
            },
            "gaps": [
                {
                    "kind": "evidence_gap",
                    "text": "Comparable segment data is missing.",
                    "text_zh": "缺少可比的分部数据。",
                },
                {
                    "kind": "human_judgment",
                    "text": "Assess whether the trend is durable.",
                    "text_zh": "判断该趋势是否可持续。",
                },
                {
                    "kind": "verification",
                    "text": "Confirm consistent accounting scope.",
                    "text_zh": "确认会计口径一致。",
                },
            ],
        }

    return {
        "prepared_by": "test fixture",
        "prepared_at": "2026-07-14",
        "subindustry": {
            "name": "Storage equipment provider",
            "value_chain_position": "Equipment manufacturing",
            "summary": "The company is classified as an equipment provider.",
            "basis": [citation],
        },
        "dimensions": {
            "profitability-unit-economics": dimension("amber"),
            "cash-runway": dimension("red"),
        },
    }


def test_five_cell_cards_lock_framework_and_keep_gaps(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["judgment_context"] = _judgment_context()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    layer = audit["judgment_layer"]
    assert layer["status"] == "generated"
    assert layer["framework_coverage"] == {"locked": 2, "implemented": 2, "ratio": 1.0}
    assert len(layer["structured_stage_trace"]) == 8
    for card in layer["cards"]:
        assert len(card["cells"]) == 5
        framework = card["cells"]["3_judgment_framework"]
        assert framework["locked"] is True
        assert "authored_by" not in framework
        assert "signature" not in framework
        assert framework["methodology_zh"]
        assert framework["basis_zh"]
        assert card["signal_meaning_zh"]
        assert card["disclaimer_zh"]
        gap_kinds = {
            item["kind"]
            for item in card["cells"]["5_gaps_and_human_judgment"]["items"]
        }
        assert gap_kinds == {"evidence_gap", "human_judgment", "verification"}
        rendered = card_markdown(card) + card_html(card)
        assert "判断框架" in rendered
        assert "证据信号" in rendered
        assert "缺口与必须人工判断项" in rendered
        assert "不构成投资建议" in rendered
        assert "Cassian" not in rendered
    assert audit["validation"]["passed"]


def test_judgment_context_cannot_override_locked_framework(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    context = _judgment_context()
    context["dimensions"]["cash-runway"]["framework"] = "Replace the locked framework"
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert not audit["validation"]["passed"]
    assert "override the locked framework" in " ".join(audit["validation"]["errors"])


def test_judgment_context_rejects_cross_subindustry_absolute_threshold(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    context = _judgment_context()
    context["dimensions"]["cash-runway"]["application"]["path"] = (
        "Treat runway below 12 months as red for every clean-energy company."
    )
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert "absolute threshold" in " ".join(audit["validation"]["errors"])


def test_judgment_context_requires_bilingual_gap_text(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    context = _judgment_context()
    del context["dimensions"]["cash-runway"]["gaps"][0]["text_zh"]
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert "require Chinese text" in " ".join(audit["validation"]["errors"])


def test_benchmark_sources_do_not_contaminate_subject_retrieval(
    manifest: Path, tmp_path: Path
) -> None:
    benchmark = tmp_path / "benchmark.txt"
    benchmark.write_text(
        "Gross margin revenue cash flow capital expenditure warranty customers " * 12,
        encoding="utf-8",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["sources"][0]["role"] = "subject"
    payload["sources"].append(
        {
            "id": "benchmark",
            "path": "benchmark.txt",
            "title": "Adjacent benchmark",
            "url": "https://example.com/benchmark",
            "publisher": "Adjacent company",
            "published": "2026-02-01",
            "kind": "audited_financial",
            "role": "benchmark",
        }
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"profitability-unit-economics"}, top_k=10)
    cited_sources = {
        candidate["source_id"] for candidate in audit["finance_evidence"][0]["candidates"]
    }
    assert "benchmark" not in cited_sources
