from __future__ import annotations

import hashlib
import inspect
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest

from cleantech_finance.deal_service import DealStore
from cleantech_finance.valuation_export import (
    PRECEDENTS_P0_STATUS,
    REQUIRED_SHEETS,
    export_valuation_workbook,
    validate_valuation_workbook,
)
from cleantech_finance.valuation_workflow import (
    prepare_screen_inputs,
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _version_hash(version: dict[str, object]) -> str:
    payload = {key: value for key, value in version.items() if key != "version_hash"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _records() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    deal: dict[str, object] = {
        "deal_id": "deal-shanghai-h2-001",
        "deal_header": {
            "buyer": "Strategic Buyer (illustrative)",
            "target": "Shanghai Hydrogen Systems Co., Ltd.",
            "transaction_scope": "Standalone target screening",
            "currency": "CNY",
            "valuation_date": "2026-07-31",
            "owner": "deal-team",
            "confidentiality_level": "internal",
        },
    }
    financials = []
    scenario_values = {
        "downside": ("0.115", "0.020", "7.0", "120"),
        "base": ("0.100", "0.030", "8.0", "150"),
        "upside": ("0.090", "0.035", "9.0", "180"),
    }
    for scenario, scale in (("downside", 80), ("base", 100), ("upside", 120)):
        for period_index, period in enumerate(("FY2027", "FY2028", "FY2029"), start=1):
            financials.append(
                {
                    "scenario": scenario,
                    "period": period,
                    "revenue": str(scale * period_index * 10),
                    "ebitda": str(scale * period_index * 2),
                    "ebit": str(scale * period_index * 15 / 10),
                    "tax_rate": "0.25",
                    "depreciation_amortization": str(scale * period_index / 2),
                    "capex": str(scale * period_index * 6 / 10),
                    "change_in_nwc": str(scale * period_index * 2 / 10),
                    "source_id": "SRC-MGMT-PLAN",
                    "input_status": "confirmed",
                }
            )
    calculation: dict[str, object] = {
        "calculation_integrity": {"status": "passed"},
        "decision_readiness": {"status": "screen_grade"},
        "authority": {
            "screen_grade_only": True,
            "formal_valuation_opinion": False,
        },
        "financials": financials,
        "trading_comps": {
            "observations": [
                {
                    "peer_id": f"peer-{index}",
                    "peer_name": f"Comparable {index}",
                    "classification": "selected external peer",
                    "rationale": "Comparable hydrogen equipment exposure",
                    "metric": "EV/EBITDA",
                    "status": "available",
                    "value": str(value),
                    "included_in_statistics": True,
                    "source_id": f"SRC-PEER-{index}",
                }
                for index, value in enumerate((7.0, 8.0, 9.0, 10.0), start=1)
            ]
            + [
                {
                    "peer_id": "target-baseline",
                    "peer_name": "Target baseline",
                    "classification": "target",
                    "rationale": "Visible baseline; excluded from external-peer statistics",
                    "metric": "EV/EBITDA",
                    "status": "N/M",
                    "included_in_statistics": False,
                    "source_id": "SRC-TARGET",
                }
            ]
        },
        "dcf": {
            "discount_convention": "period_end",
            "bridge": {
                "cash_like": "120",
                "non_operating_assets": "20",
                "debt_like": "250",
                "other_claims": "15",
                "fully_diluted_shares": "100",
            },
            "scenarios": [
                {
                    "name": name,
                    "wacc": values[0],
                    "terminal_growth": values[1],
                    "exit_multiple": values[2],
                    "terminal_metric": values[3],
                }
                for name, values in scenario_values.items()
            ],
        },
        "sensitivities": [
            {
                "name": "Base EV — WACC / terminal growth",
                "row_driver": "WACC",
                "column_driver": "Terminal growth",
                "column_values": ["0.02", "0.03", "0.04"],
                "rows": [
                    {
                        "row_value": "0.09",
                        "cells": ["1800", "2050", "2400"],
                    },
                    {
                        "row_value": "0.10",
                        "cells": ["1550", "1750", "2000"],
                    },
                    {
                        "row_value": "0.11",
                        "cells": ["1350", "1500", "1680"],
                    },
                ],
            }
        ],
        "sources": [
            {
                "source_id": "SRC-MGMT-PLAN",
                "title": '=HYPERLINK("https://example.invalid", "not a formula")',
                "locator": "Management plan, worksheet Forecast",
                "as_of": "2026-07-20",
                "currency": "CNY",
                "unit": "CNY million",
                "review_status": "reviewed",
                "reviewed_by": "analyst-01",
                "url": "https://example.invalid/source",
                "notes": "Illustrative source register entry.",
            }
        ],
        "assumptions": [
            {
                "assumption_id": "ASM-WACC-BASE",
                "name": "Base WACC",
                "value": "0.10",
                "unit": "%",
                "source_id": "SRC-WACC-MEMO",
                "status": "confirmed",
                "owner": "valuation-team",
            }
        ],
        "checks": [
            {
                "check_id": "source_registry_present",
                "scope": "readiness",
                "status": "passed",
                "message": "A source registry is present for the selected version.",
            }
        ],
        "hard_failures": [],
    }
    version: dict[str, object] = {
        "version_id": "valuation-version-001",
        "version_number": 1,
        "status": "reviewed",
        "operation": "calculate",
        "inputs": [],
        "inputs_hash": hashlib.sha256(b"confirmed-inputs").hexdigest(),
        "calculation": calculation,
        "calculation_hash": hashlib.sha256(b"calculation").hexdigest(),
        "review": {"status": "reviewed", "reviewed_by": "reviewer-01"},
        "approvals": [],
        "previous_version_hash": None,
        "created_by": "analyst-01",
        "created_at": "2026-07-31T08:00:00Z",
        "reason": "Initial screen-grade valuation",
    }
    version["version_hash"] = _version_hash(version)
    valuation: dict[str, object] = {
        "valuation_id": "valuation-001",
        "deal_id": deal["deal_id"],
        "target_legal_entity": "Shanghai Hydrogen Systems Co., Ltd.",
        "transaction_scope": "Standalone target screening",
        "valuation_date": "2026-07-31",
        "base_currency": "CNY",
        "unit": "CNY million",
        "methods": ["dcf", "trading_comps"],
        "status": "reviewed",
        "current_version_number": 1,
        "current_version_hash": version["version_hash"],
        "versions": [deepcopy(version)],
        "boundaries": {
            "screen_grade_only": True,
            "formal_valuation_opinion": False,
        },
    }
    return deal, valuation, version


def _workflow_screen() -> dict[str, object]:
    scenario_assumptions = {
        "downside": (("80", "90", "100"), "0.12", "0.02", "110", "7"),
        "base": (("100", "110", "120"), "0.10", "0.03", "130", "8"),
        "upside": (("120", "135", "150"), "0.09", "0.035", "160", "9"),
    }
    scenarios = {}
    for scenario, values in scenario_assumptions.items():
        ebit_values, wacc, growth, terminal_metric, exit_multiple = values
        scenarios[scenario] = {
            "wacc": wacc,
            "terminal_growth": growth,
            "terminal_metric": terminal_metric,
            "exit_multiple": exit_multiple,
            "periods": [
                {
                    "period": f"FY{2026 + index}",
                    "ebit": ebit,
                    "tax_rate": "0.25",
                    "depreciation_amortization": "10",
                    "capex": "22" if index == 1 else "20",
                    "change_in_nwc": "7" if index == 1 else "5",
                }
                for index, ebit in enumerate(ebit_values, start=1)
            ],
        }
    def financial_row(
        period: str,
        period_end: str,
        basis: str,
        *,
        ebit: int,
    ) -> dict[str, object]:
        depreciation = 10
        capex = 20
        change_in_nwc = 5
        tax_rate = "0.25"
        fcff = ebit * 3 / 4 + depreciation - capex - change_in_nwc
        return {
            "period": period,
            "period_end": period_end,
            "basis": basis,
            "revenue": str(ebit * 5),
            "ebitda": str(ebit + depreciation),
            "ebit": str(ebit),
            "tax_rate": tax_rate,
            "depreciation_amortization": str(depreciation),
            "capex": str(capex),
            "change_in_nwc": str(change_in_nwc),
            "fcff": format(fcff, ".2f"),
        }

    return {
        "confirm_inputs": True,
        "business_model": "mature_equipment_manufacturing",
        "discount_convention": "period_end",
        "unit": "USDm",
        "source": {
            "source_id": "management-model-v3",
            "locator": "Forecast and bridge tabs; reviewed 2026-08-03",
            "as_of": "2026-08-03",
        },
        "financials": {
            "historical": [
                financial_row("FY2023A", "2023-12-31", "reported", ebit=50),
                financial_row("FY2024A", "2024-12-31", "reported", ebit=60),
                financial_row("FY2025A", "2025-12-31", "reported", ebit=70),
            ],
            "ltm": financial_row("LTM Jun-2026", "2026-06-30", "adjusted", ebit=80),
            "forecast": [
                financial_row("FY2027E", "2027-12-31", "management", ebit=100),
                financial_row("FY2028E", "2028-12-31", "management", ebit=110),
                financial_row("FY2029E", "2029-12-31", "management", ebit=120),
            ],
        },
        "scenarios": scenarios,
        "bridge": {
            "cash_like": "100",
            "debt_like": "200",
            "non_operating_assets": "10",
            "other_claims": "5",
            "fully_diluted_shares": "50",
        },
        "trading_comps": {
            "metric": "ev_ltm_ebitda",
            "target_metric": "100",
            "target_metric_period": "LTM 2026-06-30",
            "peers": [
                {
                    "peer_id": f"peer-{index}",
                    "name": f"External Peer {index}",
                    "classification": (
                        "core_peer" if index < 5 else "secondary_peer"
                    ),
                    "rationale": "Comparable equipment mix and maturity.",
                    "enterprise_value": str(multiple * 100),
                    "ltm_ebitda": "100",
                    "ltm_ebitda_period": "LTM 2026-06-30",
                }
                for index, multiple in enumerate((6, 7, 8, 9, 30), start=1)
            ],
        },
    }


def _read_part(payload: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read(name)


def _worksheet_root(payload: bytes, sheet_number: int) -> ElementTree.Element:
    return ElementTree.fromstring(
        _read_part(payload, f"xl/worksheets/sheet{sheet_number}.xml")
    )


def _worksheet_text(payload: bytes, sheet_number: int) -> str:
    root = _worksheet_root(payload, sheet_number)
    return " ".join(text for text in root.itertext() if text)


def test_public_export_interface_is_keyword_only_and_returns_xlsx_bytes() -> None:
    deal, valuation, version = _records()

    payload = export_valuation_workbook(
        deal=deal,
        valuation=valuation,
        version=version,
    )

    assert payload.startswith(b"PK")
    assert inspect.signature(export_valuation_workbook).parameters["deal"].default is None
    with pytest.raises(TypeError):
        export_valuation_workbook(deal, valuation, version)  # type: ignore[misc]


def test_workbook_has_required_visible_sheet_order_and_dashboard_first() -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)

    workbook = ElementTree.fromstring(_read_part(payload, "xl/workbook.xml"))
    sheets = workbook.findall(f".//{{{_MAIN_NS}}}sheet")

    assert tuple(sheet.attrib["name"] for sheet in sheets) == REQUIRED_SHEETS
    assert all(sheet.attrib.get("state") == "visible" for sheet in sheets)
    assert b'activeTab="0"' in _read_part(payload, "xl/workbook.xml")


def test_generated_workbook_passes_structural_validation_from_bytes_and_path(
    tmp_path: Path,
) -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)
    output = tmp_path / "valuation.xlsx"
    output.write_bytes(payload)

    bytes_result = validate_valuation_workbook(payload)
    path_result = validate_valuation_workbook(output)

    assert bytes_result.valid, bytes_result.issues
    assert path_result.valid, path_result.issues
    assert bytes_result.sheet_names == REQUIRED_SHEETS
    assert bytes_result.formula_count >= 40


def test_package_contains_no_macros_external_links_or_hidden_placeholders() -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = tuple(archive.namelist())
        assert "xl/vbaProject.bin" not in names
        assert not any(name.startswith("xl/externalLinks/") for name in names)
        for name in names:
            if name.endswith((".xml", ".rels")):
                root = ElementTree.fromstring(archive.read(name))
                if name.endswith(".rels"):
                    assert all(
                        node.attrib.get("TargetMode") != "External" for node in root
                    )
        for sheet_number in range(1, len(REQUIRED_SHEETS) + 1):
            root = _worksheet_root(payload, sheet_number)
            assert not root.findall(f".//{{{_MAIN_NS}}}row[@hidden='1']")
            assert not root.findall(f".//{{{_MAIN_NS}}}col[@hidden='1']")


def test_financials_and_dcf_formulas_have_cached_values_and_no_broken_refs() -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)

    financials = _worksheet_root(payload, 2)
    dcf = _worksheet_root(payload, 5)
    financial_formulas = financials.findall(f".//{{{_MAIN_NS}}}f")
    dcf_formulas = dcf.findall(f".//{{{_MAIN_NS}}}f")

    assert any("*(1-F" in (formula.text or "") for formula in financial_formulas)
    assert any("'Financials'!J" in (formula.text or "") for formula in dcf_formulas)
    assert any("-$D$" in (formula.text or "") for formula in dcf_formulas)
    assert all(
        cell.find(f"{{{_MAIN_NS}}}v") is not None
        for cell in financials.findall(f".//{{{_MAIN_NS}}}c")
        if cell.find(f"{{{_MAIN_NS}}}f") is not None
    )
    assert "#REF!" not in " ".join(formula.text or "" for formula in dcf_formulas)


def test_precedents_boundary_and_version_hash_are_auditable() -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)

    precedents_text = _worksheet_text(payload, 4)
    versions = _worksheet_root(payload, 9)
    versions_text = " ".join(versions.itertext())
    hash_match_cell = versions.find(f".//{{{_MAIN_NS}}}c[@r='B7']")

    assert PRECEDENTS_P0_STATUS in precedents_text
    assert version["version_hash"] in versions_text
    assert hash_match_cell is not None
    assert hash_match_cell.find(f"{{{_MAIN_NS}}}f").text == "B5=B6"
    assert hash_match_cell.find(f"{{{_MAIN_NS}}}v").text == "1"


def test_formula_like_user_text_remains_plain_inline_string() -> None:
    deal, valuation, version = _records()
    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)
    sources = _worksheet_root(payload, 7)

    source_title = sources.find(f".//{{{_MAIN_NS}}}c[@r='B5']")

    assert source_title is not None
    assert source_title.attrib["t"] == "inlineStr"
    assert source_title.find(f"{{{_MAIN_NS}}}f") is None
    assert "=HYPERLINK" in " ".join(source_title.itertext())


def test_export_is_byte_deterministic_and_input_changes_change_the_package() -> None:
    deal, valuation, version = _records()

    first = export_valuation_workbook(deal=deal, valuation=valuation, version=version)
    second = export_valuation_workbook(deal=deal, valuation=valuation, version=version)
    changed_version = deepcopy(version)
    changed_version["reason"] = "Updated audit reason"
    changed_version["version_hash"] = _version_hash(changed_version)
    changed_valuation = deepcopy(valuation)
    changed_valuation["versions"] = [deepcopy(changed_version)]
    changed = export_valuation_workbook(
        deal=deal,
        valuation=changed_valuation,
        version=changed_version,
    )

    assert first == second
    assert hashlib.sha256(first).hexdigest() != hashlib.sha256(changed).hexdigest()


def test_failed_incomplete_version_exports_audit_information_without_fake_dcf() -> None:
    version: dict[str, object] = {
        "version_id": "failed-version-001",
        "version_number": 2,
        "status": "failed",
        "operation": "calculate",
        "created_by": "agent",
        "created_at": "2026-08-01T00:00:00Z",
        "reason": "Required forecast evidence is absent",
        "calculation": {
            "calculation_integrity": {"status": "failed"},
            "decision_readiness": {"status": "not_ready"},
            "hard_failures": [
                {
                    "code": "missing_confirmed_forecast",
                    "message": "Confirmed forecast evidence is required.",
                }
            ],
            "dcf": {
                "scenarios": [
                    {
                        "name": "base",
                        "wacc": "0.03",
                        "terminal_growth": "0.04",
                    }
                ]
            },
        },
    }
    version["version_hash"] = _version_hash(version)
    valuation: dict[str, object] = {
        "valuation_id": "valuation-failed",
        "deal_id": "deal-failed",
        "target_legal_entity": "Incomplete Target",
        "transaction_scope": "Standalone target screening",
        "valuation_date": "2026-08-01",
        "base_currency": "CNY",
        "versions": [deepcopy(version)],
    }

    payload = export_valuation_workbook(deal=None, valuation=valuation, version=version)
    validation = validate_valuation_workbook(payload)

    assert validation.valid, validation.issues
    assert "missing_confirmed_forecast" in _worksheet_text(payload, 8)
    assert "Confirmed forecast evidence is required" in _worksheet_text(payload, 1)
    assert "No financial forecast records supplied" in _worksheet_text(payload, 2)
    assert "WACC <= terminal growth" not in _worksheet_text(payload, 5)


def test_hash_mismatch_is_exported_as_failed_check_instead_of_silently_repaired() -> None:
    deal, valuation, version = _records()
    version["version_hash"] = "f" * 64
    valuation["versions"] = [deepcopy(version)]

    payload = export_valuation_workbook(deal=deal, valuation=valuation, version=version)

    assert "valuation_version_hash_matches_record" in _worksheet_text(payload, 8)
    versions = _worksheet_root(payload, 9)
    assert versions.find(f".//{{{_MAIN_NS}}}c[@r='B7']/{{{_MAIN_NS}}}v").text == "0"
    assert "not_ready" in _worksheet_text(payload, 1)


def test_real_dealstore_workflow_shape_exports_formula_model_not_empty_shell(
    tmp_path: Path,
) -> None:
    actor = {"id": "fa-export-integration", "role": "fa"}
    store = DealStore(tmp_path / "deals")
    deal = store.create_deal(
        company_id="company-export-target",
        buyer="Buyer Holdings",
        target="Workflow Target",
        transaction_scope="100% equity acquisition",
        currency="USD",
        valuation_date="2026-08-03",
        owner="FA Team",
        confidentiality_level="confidential",
        actor=actor,
        reason="Create export integration deal",
        idempotency_key="create-export-integration-deal",
    )
    valuation = store.create_valuation_case(
        deal["deal_id"],
        target_legal_entity="Workflow Target Co., Ltd.",
        transaction_scope="100% equity acquisition",
        valuation_date="2026-08-03",
        base_currency="USD",
        methods=["trading_comps", "dcf_fcff"],
        actor=actor,
        reason="Open export integration valuation",
        idempotency_key="create-export-integration-valuation",
        expected_deal_revision=deal["revision"],
        expected_deal_hash=deal["record_hash"],
    )
    opening_version = valuation["versions"][-1]
    inputs = prepare_screen_inputs(_workflow_screen(), valuation)
    store.update_valuation_inputs(
        valuation["valuation_id"],
        inputs=inputs,
        actor=actor,
        reason="Confirm source-bearing workflow inputs",
        idempotency_key="update-export-integration-inputs",
        expected_version_number=opening_version["version_number"],
        expected_version_hash=opening_version["version_hash"],
    )
    valuation = store.get_valuation(valuation["valuation_id"])
    input_version = valuation["versions"][-1]
    store.calculate_valuation(
        valuation["valuation_id"],
        actor=actor,
        reason="Calculate trusted screen for export",
        idempotency_key="calculate-export-integration",
        expected_version_number=input_version["version_number"],
        expected_version_hash=input_version["version_hash"],
    )
    valuation = store.get_valuation(valuation["valuation_id"])
    calculated_version = valuation["versions"][-1]

    payload = export_valuation_workbook(
        deal=deal,
        valuation=valuation,
        version=calculated_version,
    )
    validation = validate_valuation_workbook(payload)

    assert validation.valid, validation.issues
    assert validation.formula_count >= 40
    assert "No financial forecast records supplied" not in _worksheet_text(payload, 2)
    assert "FY2027" in _worksheet_text(payload, 2)
    assert "historical" in _worksheet_text(payload, 2)
    assert "adjusted" in _worksheet_text(payload, 2)
    assert "ev_ltm_ebitda" in _worksheet_text(payload, 3)
    assert "Wacc X Terminal Growth" in _worksheet_text(payload, 6)
    assert "management-model-v3" in _worksheet_text(payload, 7)
    assert "wacc_above_terminal_growth" in _worksheet_text(payload, 8)
    dcf_formulas = _worksheet_root(payload, 5).findall(f".//{{{_MAIN_NS}}}f")
    assert sum("'Financials'!J" in (formula.text or "") for formula in dcf_formulas) == 9
