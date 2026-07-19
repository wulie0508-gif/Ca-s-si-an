from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleantech_finance.audit import run_audit, validate_audit
from cleantech_finance.financials import validate_period_contract
from cleantech_finance.ingest import ManifestError
from cleantech_finance.reporting import card_html, card_markdown, html_report, write_artifacts


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
            "fiscal_year_end": "12-31",
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
    assert audit["financial_analysis"]["period_contract"]["status"] == "comparable_annual"


def test_non_calendar_fiscal_year_preserves_period_identity(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["financial_extraction"]["fiscal_year_end"] = "09-30"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    periods = audit["financial_fact_extraction"]["financials"]["periods"]

    assert [(item["start_date"], item["end_date"]) for item in periods] == [
        ("2023-10-01", "2024-09-30"),
        ("2024-10-01", "2025-09-30"),
    ]
    assert [item["duration_days"] for item in periods] == [366, 365]
    assert audit["financial_analysis"]["period_contract"]["uses_sec_frame"] is False


def test_transition_period_cannot_drive_annual_trend() -> None:
    periods = [
        {
            "period": "FY2025",
            "fiscal_year": 2025,
            "period_type": "annual",
            "start_date": "2025-07-01",
            "end_date": "2025-12-31",
            "duration_days": 184,
        }
    ]
    with pytest.raises(ManifestError, match="transition or non-annual"):
        validate_period_contract(periods)


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


def test_html_report_contains_mobile_overflow_guards(manifest: Path) -> None:
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    rendered = html_report(audit)

    assert "overflow-x:clip" in rendered
    assert ".cell>div{min-width:0}" in rendered
    assert "a,code,blockquote,.retrieval li{overflow-wrap:anywhere" in rendered


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


def test_financial_extraction_rejects_benchmark_source(manifest: Path, tmp_path: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    benchmark = tmp_path / "benchmark.txt"
    benchmark.write_text(
        (Path(__file__).parent / "fixtures" / "sample-annual-report.txt").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    payload["sources"].append(
        {
            "id": "benchmark",
            "path": "benchmark.txt",
            "title": "Benchmark filing",
            "url": "https://example.com/benchmark",
            "publisher": "Benchmark Company",
            "published": "2026-02-01",
            "kind": "audited_financial",
            "role": "benchmark",
        }
    )
    payload["financial_extraction"]["source_id"] = "benchmark"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError, match="subject source"):
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
            "fiscal_year_end": "12-31",
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

    def dimension() -> dict[str, object]:
        return {
            "benchmark": {
                "scope": "Use the company's prior period first and an adjacent-company reference only as context.",
                "scope_zh": "优先比较公司自身上期，相邻公司只作背景。",
                "observations": [
                    {
                        "comparison_type": "subject_history",
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
                "limitations_zh": ["未构建同业百分位或完全同口径基准。"],
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
        "contract_version": "0.3.0",
        "prepared_by": "test fixture",
        "prepared_at": "2026-07-14",
        "subindustry": {
            "scope_id": "storage-equipment",
            "name": "Storage equipment provider",
            "name_zh": "储能设备提供商",
            "value_chain_position": "Equipment manufacturing",
            "value_chain_position_zh": "设备制造",
            "summary": "The company is classified as an equipment provider.",
            "summary_zh": "该公司被归类为设备提供商。",
            "basis": [citation],
        },
        "dimensions": {
            "profitability-unit-economics": dimension(),
            "cash-runway": dimension(),
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
    assert layer["framework_coverage"] == {
        "locked": 2,
        "implemented": 2,
        "not_applicable": 0,
        "requested": 2,
        "ratio": 1.0,
    }
    assert len(layer["structured_stage_trace"]) == 8
    assert {card["dimension_id"]: card["signal"] for card in layer["cards"]} == {
        "profitability-unit-economics": "green",
        "cash-runway": "red",
    }
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
        application = card["cells"]["4_framework_application"]
        provenance = application["rule_provenance"]
        assert application["label"] == "deterministic_rule_output"
        assert application["path_zh"]
        assert application["summary_zh"]
        assert provenance["deterministic"] is True
        assert provenance["rule_status"] == "validated"
        assert provenance["rule_digest"].startswith("sha256:")
        assert provenance["inputs_digest"].startswith("sha256:")
        gap_kinds = {item["kind"] for item in card["cells"]["5_gaps_and_human_judgment"]["items"]}
        assert gap_kinds == {"evidence_gap", "human_judgment", "verification"}
        rendered = card_markdown(card) + card_html(card)
        assert "判断框架" in rendered
        assert "证据信号" in rendered
        assert "缺口与必须人工判断项" in rendered
        assert "不构成投资建议" in rendered
        assert "Cassian" not in rendered
    assert audit["validation"]["passed"]
    signal_stages = [
        item for item in layer["structured_stage_trace"] if item["stage"] == "deterministic_signal"
    ]
    assert len(signal_stages) == 2
    assert all(item["actor"] == "deterministic_rule_engine" for item in signal_stages)
    assert all(item["sources"] for item in layer["structured_stage_trace"])


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
    context["dimensions"]["cash-runway"]["benchmark"]["limitations"] = [
        "Treat runway below 12 months as red for every clean-energy company."
    ]
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert "absolute threshold" in " ".join(audit["validation"]["errors"])


def test_judgment_context_cannot_override_deterministic_signal(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    context = _judgment_context()
    context["dimensions"]["cash-runway"]["application"] = {
        "signal": "green",
        "path": "External override",
        "summary": "External override",
        "basis": [{"source_id": "annual-report", "locator": "lines 1-20"}],
    }
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert audit["judgment_layer"]["cards"][0]["signal"] == "red"
    assert "cannot provide deterministic application fields" in " ".join(
        audit["validation"]["errors"]
    )


def test_company_identity_and_benchmark_labels_do_not_change_signal(manifest: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["judgment_context"] = _judgment_context()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    baseline = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    baseline_signals = {
        card["dimension_id"]: card["signal"] for card in baseline["judgment_layer"]["cards"]
    }

    payload["subject"]["organization"] = "Renamed Generic Company"
    payload["subject"]["ticker"] = "RENAMED"
    for dimension in payload["judgment_context"]["dimensions"].values():
        for observation in dimension["benchmark"]["observations"]:
            observation["entity"] = "Arbitrary Display Label"
            observation["value"] = 999999.0
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    renamed = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    renamed_signals = {
        card["dimension_id"]: card["signal"] for card in renamed["judgment_layer"]["cards"]
    }
    assert renamed_signals == baseline_signals


def test_subindustry_classification_rejects_benchmark_citation(
    manifest: Path, tmp_path: Path
) -> None:
    benchmark = tmp_path / "benchmark.txt"
    benchmark.write_text("Benchmark evidence " * 30, encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["sources"].append(
        {
            "id": "benchmark",
            "path": "benchmark.txt",
            "title": "Benchmark source",
            "url": "https://example.com/benchmark",
            "publisher": "Benchmark Company",
            "published": "2026-02-01",
            "kind": "industry_report",
            "role": "benchmark",
        }
    )
    context = _judgment_context()
    context["subindustry"]["basis"] = [{"source_id": "benchmark", "locator": "lines 1-2"}]
    payload["judgment_context"] = context
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    audit = run_audit(str(manifest), only_dimensions={"cash-runway"})
    assert audit["judgment_layer"]["status"] == "invalid"
    assert "subject sources only" in " ".join(audit["validation"]["errors"])


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


def test_optional_auxiliary_source_warns_without_changing_signal_or_retrieval(
    manifest: Path, tmp_path: Path
) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["judgment_context"] = _judgment_context()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    baseline = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    baseline_signals = [card["signal"] for card in baseline["judgment_layer"]["cards"]]

    auxiliary = tmp_path / "regulator-facts.json"
    auxiliary.write_text('{"source":"public regulator facts"}', encoding="utf-8")
    segment = tmp_path / "segment-release.txt"
    segment.write_text("Segment revenue 80.0", encoding="utf-8")
    payload["sources"].append(
        {
            "id": "regulator-facts",
            "path": "regulator-facts.json",
            "title": "Public regulator facts",
            "url": "https://data.example.gov/companyfacts.json",
            "publisher": "Example regulator",
            "published": "2026-02-02",
            "kind": "regulator",
            "role": "auxiliary",
        }
    )
    payload["sources"].append(
        {
            "id": "segment-release",
            "path": "segment-release.txt",
            "title": "Company segment release",
            "url": "https://example.com/segment-release",
            "publisher": "Example Storage Systems",
            "published": "2026-02-02",
            "kind": "company_results",
            "role": "auxiliary",
        }
    )
    payload["auxiliary_validation"] = {
        "enabled": True,
        "selected_source_ids": ["regulator-facts"],
        "relative_tolerance": 0,
        "absolute_tolerance": 0,
        "facts": [
            {
                "period": "FY2025",
                "period_end": "2025-12-31",
                "fact_id": "revenue",
                "unit": "USD",
                "currency": "USD",
                "accounting_scope": "consolidated",
                "value": 120.0,
                "source_id": "regulator-facts",
                "locator": "RevenueFromContractWithCustomerExcludingAssessedTax FY2025",
            },
            {
                "period": "FY2025",
                "period_end": "2025-12-31",
                "fact_id": "capex",
                "unit": "USD",
                "currency": "USD",
                "accounting_scope": "consolidated",
                "value": 4.0,
                "source_id": "regulator-facts",
                "locator": "PaymentsToAcquirePropertyPlantAndEquipment FY2025",
            },
            {
                "period": "FY2025",
                "period_end": "2025-12-31",
                "fact_id": "revenue",
                "unit": "USD",
                "currency": "USD",
                "accounting_scope": "segment:storage",
                "value": 80.0,
                "source_id": "segment-release",
                "locator": "Storage segment revenue FY2025",
            },
        ],
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    checked = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )

    auxiliary_result = checked["auxiliary_validation"]
    assert auxiliary_result["enabled_by_user"] is True
    assert auxiliary_result["status"] == "warning"
    assert auxiliary_result["affects_signal"] is False
    assert {item["status"] for item in auxiliary_result["checks"]} == {
        "matched",
        "mismatch",
    }
    assert auxiliary_result["summary_zh"]
    assert auxiliary_result["available_source_ids"] == [
        "regulator-facts",
        "segment-release",
    ]
    assert auxiliary_result["selected_source_ids"] == ["regulator-facts"]
    assert auxiliary_result["ignored_source_ids"] == ["segment-release"]
    assert [card["signal"] for card in checked["judgment_layer"]["cards"]] == baseline_signals
    assert checked["metrics"]["chunk_count"] == baseline["metrics"]["chunk_count"]

    payload["auxiliary_validation"]["selected_source_ids"] = ["segment-release"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    segment_checked = run_audit(
        str(manifest), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    segment_result = segment_checked["auxiliary_validation"]
    assert segment_result["status"] == "warning"
    assert [item["status"] for item in segment_result["checks"]] == ["not_comparable"]
    assert segment_result["checks"][0]["semantic_mismatches"][0]["field"] == (
        "accounting_scope"
    )
    assert [card["signal"] for card in segment_checked["judgment_layer"]["cards"]] == (
        baseline_signals
    )
