from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from cleantech_finance.audit import run_audit
from cleantech_finance.ingest import ManifestError
from cleantech_finance.rules import derive_rule_inputs

ROOT = Path(__file__).parents[1]
CASES = json.loads((ROOT / "evals" / "company-loops-v0.3.json").read_text(encoding="utf-8"))
MANIFESTS = sorted((ROOT / "examples").rglob("manifest*.json"))
MANIFEST_SCHEMA = json.loads(
    (ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("manifest_path", MANIFESTS, ids=lambda path: str(path.relative_to(ROOT)))
def test_example_manifest_matches_v03_schema(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            MANIFEST_SCHEMA, format_checker=FormatChecker()
        ).iter_errors(manifest)
    )
    assert not errors, [f"{error.json_path}: {error.message}" for error in errors]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_new_company_loop(case: dict[str, object]) -> None:
    audit = run_audit(
        str(ROOT / case["manifest"]),
        only_dimensions={"profitability-unit-economics", "cash-runway"},
    )
    assert audit["validation"]["passed"], audit["validation"]["errors"]
    cards = {card["dimension_id"]: card for card in audit["judgment_layer"]["cards"]}
    expected_signals = case["expected_signals"]
    assert {dimension: card["signal"] for dimension, card in cards.items()} == {
        dimension: signal
        for dimension, signal in expected_signals.items()
        if signal is not None
    }
    not_applicable = {
        item["dimension_id"]
        for item in audit["judgment_layer"]["dimension_outcomes"]
        if item["status"] == "not_applicable"
    }
    assert not_applicable == {
        dimension for dimension, signal in expected_signals.items() if signal is None
    }
    assert {
        card["cells"]["4_framework_application"]["rule_provenance"]["subindustry_scope"]
        for card in cards.values()
    } == {case["scope_id"]}
    assert audit["auxiliary_validation"]["status"] == case["expected_auxiliary_status"]
    assert audit["auxiliary_validation"]["affects_signal"] is False
    assert audit["execution"]["model_calls"] == 0


def test_albemarle_auxiliary_source_choice_cannot_change_core_signal(
    tmp_path: Path,
) -> None:
    original = ROOT / "examples/company-loops/albemarle/manifest.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        source["path"] = str((original.parent / source["path"]).resolve())
    payload["auxiliary_validation"]["selected_source_ids"] = [
        "albemarle-2025-results"
    ]
    alternate = tmp_path / "manifest.json"
    alternate.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    baseline = run_audit(
        str(original),
        only_dimensions={"profitability-unit-economics", "cash-runway"},
    )
    selected = run_audit(
        str(alternate),
        only_dimensions={"profitability-unit-economics", "cash-runway"},
    )

    assert selected["auxiliary_validation"]["status"] == "warning"
    assert {item["status"] for item in selected["auxiliary_validation"]["checks"]} == {
        "matched",
        "not_comparable",
    }
    segment = next(
        item
        for item in selected["auxiliary_validation"]["checks"]
        if item["fact_id"] == "revenue"
    )
    assert [item["field"] for item in segment["semantic_mismatches"]] == [
        "accounting_scope"
    ]
    assert [card["signal"] for card in selected["judgment_layer"]["cards"]] == [
        card["signal"] for card in baseline["judgment_layer"]["cards"]
    ]
    assert [
        card["cells"]["4_framework_application"]["rule_provenance"]["rule_digest"]
        for card in selected["judgment_layer"]["cards"]
    ] == [
        card["cells"]["4_framework_application"]["rule_provenance"]["rule_digest"]
        for card in baseline["judgment_layer"]["cards"]
    ]


def test_tpi_selects_net_income_matching_each_dimension_scope() -> None:
    path = ROOT / "examples/company-loops/tpi-composites/manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    profitability = derive_rule_inputs(
        "profitability-unit-economics", payload["financials"]
    )
    cash = derive_rule_inputs("cash-runway", payload["financials"])

    assert profitability["operations_scope"] == "continuing_operations"
    assert profitability["latest_net_income_fact_id"] == "net_income_continuing"
    assert profitability["net_income_attribution"] == "attributable_to_parent"
    assert cash["operations_scope"] == "total_operations"
    assert cash["latest_net_income_fact_id"] == "net_income"
    assert cash["net_income_attribution"] == "attributable_to_parent"

    del payload["financials"]["periods"][-1]["facts"]["net_income_continuing"]
    with pytest.raises(ValueError, match="requires exactly one net-income fact"):
        derive_rule_inputs("profitability-unit-economics", payload["financials"])


def test_clearway_suppresses_inapplicable_manufacturing_margin() -> None:
    path = ROOT / "examples/company-loops/clearway-energy/manifest.json"
    audit = run_audit(
        str(path), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )

    assert [card["dimension_id"] for card in audit["judgment_layer"]["cards"]] == [
        "cash-runway"
    ]
    outcome = next(
        item
        for item in audit["judgment_layer"]["dimension_outcomes"]
        if item["dimension_id"] == "profitability-unit-economics"
    )
    assert outcome["status"] == "not_applicable"
    metric_ids = {item["id"] for item in audit["financial_analysis"]["metrics"]}
    assert "gross-margin" not in metric_ids
    assert "net-margin" not in metric_ids
    assert "operating-cash-flow-to-capex" in metric_ids


def test_nextpower_resolves_old_and_new_names_by_stable_cik(tmp_path: Path) -> None:
    original = ROOT / "examples/company-loops/nextpower/manifest.json"
    audit = run_audit(
        str(original), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )

    identity = audit["identity_resolution"]
    assert identity["status"] == "passed"
    assert identity["entity_id"] == "sec-cik-0001852131"
    assert identity["match_method"] == "stable_identifier"
    assert {item["name"] for item in identity["aliases"]} == {"Nextracker Inc."}
    assert {
        (item["publisher"], item["subject_entity_id"])
        for item in identity["source_bindings"]
    } >= {
        ("Nextpower Inc.", "sec-cik-0001852131"),
        ("Nextracker Inc.", "sec-cik-0001852131"),
    }

    payload = json.loads(original.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        source["path"] = str((original.parent / source["path"]).resolve())
        if source["publisher"] == "Nextracker Inc.":
            source["subject_entity_id"] = "sec-cik-0000000001"
    conflicting = tmp_path / "manifest.json"
    conflicting.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ManifestError, match="belongs to.*not"):
        run_audit(
            str(conflicting),
            only_dimensions={"profitability-unit-economics", "cash-runway"},
        )


def test_shoals_normalizes_cash_effect_polarity_without_changing_signal(
    tmp_path: Path,
) -> None:
    original = ROOT / "examples/company-loops/shoals/manifest.json"
    baseline = run_audit(
        str(original), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    context = baseline["cash_conversion_context"]

    assert context["status"] == "passed"
    assert context["affects_signal"] is False
    assert context["polarity_policy_version"] == "1.0.0"
    effects = {
        (item["period"], item["driver_id"]): item["normalized_cash_effect"]
        for item in context["items"]
    }
    assert effects[("FY2025", "accounts_receivable_change")] == -50_612_000
    assert effects[("FY2025", "inventory_change")] == -35_107_000
    assert effects[("FY2025", "accounts_payable_change")] == 43_320_000
    assert effects[("FY2025", "contract_liability_change")] == 18_294_000
    assert effects[("FY2025", "warranty_claim_payments")] == -40_965_000
    assert effects[("FY2024", "accounts_receivable_change")] == 28_937_000
    totals = {item["period"]: item for item in context["totals_by_period"]}
    assert totals["FY2025"]["net_effect"] == -65_070_000
    assert totals["FY2024"]["net_effect"] == -3_884_000

    cards = {card["dimension_id"]: card for card in baseline["judgment_layer"]["cards"]}
    cash_rule = cards["cash-runway"]["cells"]["4_framework_application"][
        "rule_provenance"
    ]
    assert cards["cash-runway"]["signal"] == "red"
    assert cash_rule["rule_id"] == "cash-profitable-not-covered"
    assert cash_rule["inputs"]["latest_ocf_to_capex"] == 0.516509

    payload = json.loads(original.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        source["path"] = str((original.parent / source["path"]).resolve())
    payload["auxiliary_validation"]["enabled"] = False
    payload["auxiliary_validation"]["selected_source_ids"] = []
    payload["cash_conversion_context"]["enabled"] = False
    disabled_path = tmp_path / "manifest.json"
    disabled_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    disabled = run_audit(
        str(disabled_path),
        only_dimensions={"profitability-unit-economics", "cash-runway"},
    )
    assert disabled["cash_conversion_context"]["status"] == "disabled"
    assert [card["signal"] for card in disabled["judgment_layer"]["cards"]] == [
        card["signal"] for card in baseline["judgment_layer"]["cards"]
    ]
    for key in ("rule_digest", "inputs_digest"):
        assert [
            card["cells"]["4_framework_application"]["rule_provenance"][key]
            for card in disabled["judgment_layer"]["cards"]
        ] == [
            card["cells"]["4_framework_application"]["rule_provenance"][key]
            for card in baseline["judgment_layer"]["cards"]
        ]


def test_shoals_cash_context_semantic_mismatch_fails_closed(tmp_path: Path) -> None:
    original = ROOT / "examples/company-loops/shoals/manifest.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        source["path"] = str((original.parent / source["path"]).resolve())
    payload["cash_conversion_context"]["facts"][0]["period_end"] = "2025-12-30"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    audit = run_audit(
        str(path), only_dimensions={"profitability-unit-economics", "cash-runway"}
    )
    assert not audit["validation"]["passed"]
    assert any("period_end" in error for error in audit["validation"]["errors"])
    assert audit["cash_conversion_context"]["items"] == [] or all(
        item["driver_id"] != "accounts_receivable_change"
        or item["period"] != "FY2025"
        for item in audit["cash_conversion_context"]["items"]
    )
