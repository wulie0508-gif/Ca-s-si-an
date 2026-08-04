from __future__ import annotations

import json
import sys
import threading
import types
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import cleantech_finance.agent_bridge as bridge_module
import cleantech_finance.valuation_workflow as valuation_workflow_module
from cleantech_finance.agent_bridge import create_agent_bridge_server

ROOT = Path(__file__).resolve().parents[1]


def test_valuation_ui_defaults_to_dcf_and_enforces_planned_comps() -> None:
    html = (ROOT / "src/cleantech_finance/web/agent_bridge.html").read_text(
        encoding="utf-8"
    )
    javascript = (ROOT / "src/cleantech_finance/web/agent_bridge.js").read_text(
        encoding="utf-8"
    )

    method_select = html.split('id="valuation-method-plan"', 1)[1].split("</select>", 1)[0]
    assert method_select.index('value="dcf_only"') < method_select.index(
        'value="dcf_and_trading_comps"'
    )
    assert 'elements.valuationCompsMode.value = planned ? "on" : "off";' in javascript
    assert "elements.valuationCompsMode.disabled = true;" in javascript
    assert "const enabled = planned;" in javascript
    assert 'id="valuation-period-count"' in html
    assert 'for (let year = 1; year <= 5; year += 1)' in javascript
    assert "function updateValuationPeriodCount()" in javascript
    assert "input.required = active;" in javascript
    assert "row.hidden = !active;" in javascript
    assert "period_end:" in javascript
    assert "discount_exponent:" in javascript
    assert "企业候选补件不会自动带入或确认" in html
    assert "3 至 5 期 FCFF 输入" in javascript


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    origin: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if origin:
        headers["Origin"] = origin
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _json(response: tuple[int, dict[str, str], bytes]) -> tuple[int, dict[str, Any]]:
    status, _, body = response
    return status, json.loads(body)


@pytest.fixture
def bridge(tmp_path: Path) -> Iterator[tuple[str, Any, str]]:
    catalog = tmp_path / "policy-catalog.xlsx"
    catalog.write_bytes(b"test catalog is not read by these routes")
    workspace_root = tmp_path / "workspace"
    server = create_agent_bridge_server(
        catalog,
        port=0,
        workspace_root=workspace_root,
    )
    case = server.workspace.create_case(
        case_name="Target CleanTech",
        case_type="enterprise",
        files=[("source.txt", b"source-bearing valuation input", "text/plain")],
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url, server, case["case_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ui_deal_valuation_flow_uses_server_identity_and_trusted_calculation(
    bridge: tuple[str, Any, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url, _, case_id = bridge
    prepare_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
    calculate_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def fake_prepare(request: dict[str, Any], valuation: dict[str, Any]) -> list[dict[str, Any]]:
        prepare_calls.append((request, valuation))
        return [
            {
                "input_id": "confirmed-revenue",
                "name": "Confirmed revenue",
                "value": "100",
                "source_id": "artifact-0001",
                "locator": "source.txt",
                "period": "2026A",
                "currency": "USD",
                "unit": "million",
                "as_of": "2026-08-03",
                "status": "confirmed_input",
                "human_confirmed": True,
            }
        ]

    def fake_calculate(valuation: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
        calculate_calls.append((valuation, version))
        return {
            "engine_version": "test-engine-1",
            "authority": "screen_grade_only",
            "formal_valuation_opinion": False,
            "used_input_ids": ["confirmed-revenue"],
            "enterprise_value_range": ["500", "600"],
            "hard_failures": [],
            "placeholders": [],
            "calculation_integrity": {"status": "passed"},
            "decision_readiness": {
                "status": "screen_grade",
                "blocking_reasons": [],
                "warnings": ["FA review has not been recorded."],
                "human_review_required": True,
            },
        }

    monkeypatch.setattr(bridge_module, "prepare_screen_inputs", fake_prepare)
    monkeypatch.setattr(
        valuation_workflow_module,
        "calculate_screen_from_version",
        fake_calculate,
    )

    create_payload = {
        "company_id": case_id,
        "buyer": "Buyer Holdings",
        "target": "Target CleanTech",
        "transaction_scope": "100% equity acquisition",
        "currency": "USD",
        "valuation_date": "2026-08-03",
        "owner": "FA Team",
        "confidentiality_level": "internal_only",
        "reason": "Open a live transaction workstream",
    }
    status, denied = _json(
        _request(
            f"{base_url}/api/ui/deals",
            method="POST",
            origin=base_url,
            idempotency_key="deal-client-actor-denied",
            payload={**create_payload, "actor": {"id": "browser", "role": "admin"}},
        )
    )
    assert status == 403
    assert denied["error"] == "deal_permission_denied"

    status, deal = _json(
        _request(
            f"{base_url}/api/ui/deals",
            method="POST",
            origin=base_url,
            idempotency_key="deal-create-001",
            payload=create_payload,
        )
    )
    assert status == 201
    assert deal["company_id"] == case_id
    assert deal["deal_header"]["confidentiality_level"] == "internal"
    assert deal["audit_trail"][0]["actor"] == {
        "id": "local-fa-ui",
        "role": "deal_lead",
        "type": "human",
    }

    status, listed = _json(_request(f"{base_url}/api/ui/deals"))
    assert status == 200
    assert [item["deal_id"] for item in listed["deals"]] == [deal["deal_id"]]
    status, detail = _json(_request(f"{base_url}/api/ui/deals/{deal['deal_id']}"))
    assert status == 200
    assert detail == deal

    status, staged = _json(
        _request(
            f"{base_url}/api/ui/deals/{deal['deal_id']}/stage",
            method="POST",
            origin=base_url,
            idempotency_key="stage-001",
            payload={
                "stage": "shortlist_and_preliminary_valuation",
                "reason": "Local FA confirmed the live stage",
                "expected_revision": deal["revision"],
                "expected_record_hash": deal["record_hash"],
            },
        )
    )
    assert status == 200
    assert staged["human_confirmed_stage"]["confirmed_by"]["id"] == "local-fa-ui"

    status, valuation = _json(
        _request(
            f"{base_url}/api/ui/deals/{deal['deal_id']}/valuations",
            method="POST",
            origin=base_url,
            idempotency_key="valuation-create-001",
            payload={
                "target_legal_entity": "Target CleanTech Co., Ltd.",
                "transaction_scope": "100% equity acquisition",
                "valuation_date": "2026-08-03",
                "base_currency": "USD",
                "methods": ["trading_comps", "dcf_fcff"],
                "reason": "Start a controlled screen",
                "expected_deal_revision": staged["revision"],
                "expected_deal_hash": staged["record_hash"],
            },
        )
    )
    assert status == 201
    assert valuation["status"] == "draft"

    status, invalid_source = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/inputs",
            method="POST",
            origin=base_url,
            idempotency_key="input-bad-source",
            payload={
                "source": {
                    "source_id": "artifact-9999",
                    "workspace_case_id": case_id,
                    "locator": "missing",
                    "as_of": "2026-08-03",
                },
                "reason": "This reference must fail workspace validation",
                "expected_version_number": 1,
                "expected_version_hash": valuation["current_version_hash"],
            },
        )
    )
    assert status == 400
    assert invalid_source["error"] == "invalid_deal_request"
    assert prepare_calls == []

    status, invalid_nested_source = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/inputs",
            method="POST",
            origin=base_url,
            idempotency_key="input-bad-nested-source",
            payload={
                "source": {
                    "source_id": "artifact-0001",
                    "workspace_case_id": case_id,
                    "locator": "source.txt",
                    "as_of": "2026-08-03",
                },
                "financials": {
                    "ltm": {
                        "revenue_source": {
                            "source_id": "artifact-9999",
                            "locator": "missing nested source",
                            "as_of": "2026-08-03",
                        }
                    }
                },
                "reason": "A nested field source must belong to the workspace",
                "expected_version_number": 1,
                "expected_version_hash": valuation["current_version_hash"],
            },
        )
    )
    assert status == 400
    assert invalid_nested_source["error"] == "invalid_deal_request"
    assert prepare_calls == []

    status, input_version = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/inputs",
            method="POST",
            origin=base_url,
            idempotency_key="input-001",
            payload={
                "source": {
                    "source_id": "artifact-0001",
                    "workspace_case_id": case_id,
                    "locator": "source.txt",
                    "as_of": "2026-08-03",
                },
                "financials": {
                    "ltm": {
                        "revenue_source": {
                            "source_id": "artifact-0001",
                            "locator": "source.txt",
                            "as_of": "2026-08-03",
                        }
                    }
                },
                "reason": "FA confirmed the source-bearing screen inputs",
                "expected_version_number": 1,
                "expected_version_hash": valuation["current_version_hash"],
            },
        )
    )
    assert status == 201
    assert len(prepare_calls) == 1
    assert prepare_calls[0][0]["financials"]["ltm"]["revenue_source"]["source_id"] == (
        "artifact-0001"
    )
    assert input_version["inputs"][0]["entered_by"]["id"] == "local-fa-ui"
    assert input_version["inputs"][0]["status"] == "confirmed_input"

    status, rejected_calculation = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/calculate",
            method="POST",
            origin=base_url,
            idempotency_key="calc-injected",
            payload={
                "calculation": {"enterprise_value": "999999"},
                "reason": "Browser tries to inject a result",
                "expected_version_number": input_version["version_number"],
                "expected_version_hash": input_version["version_hash"],
            },
        )
    )
    assert status == 403
    assert rejected_calculation["error"] == "deal_permission_denied"
    assert calculate_calls == []

    status, calculated = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/calculate",
            method="POST",
            origin=base_url,
            idempotency_key="calc-001",
            payload={
                "reason": "Run the trusted deterministic engine",
                "expected_version_number": input_version["version_number"],
                "expected_version_hash": input_version["version_hash"],
            },
        )
    )
    assert status == 201
    assert len(calculate_calls) == 1
    assert calculate_calls[0][1] == input_version
    assert calculated["calculation"]["engine_version"] == "test-engine-1"
    assert calculated["calculation"]["enterprise_value_range"] == ["500", "600"]

    status, calculation_replay = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/calculate",
            method="POST",
            origin=base_url,
            idempotency_key="calc-001",
            payload={
                "reason": "Run the trusted deterministic engine",
                "expected_version_number": input_version["version_number"],
                "expected_version_hash": input_version["version_hash"],
            },
        )
    )
    assert status == 201
    assert calculation_replay == calculated

    status, reviewed = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/review",
            method="POST",
            origin=base_url,
            idempotency_key="review-001",
            payload={
                "review": {"decision": "accepted", "notes": "Bridge checked"},
                "reason": "Complete FA review",
                "expected_version_number": calculated["version_number"],
                "expected_version_hash": calculated["version_hash"],
            },
        )
    )
    assert status == 201, reviewed
    assert reviewed["status"] == "fa_reviewed"
    assert reviewed["review"]["reviewed_by"]["id"] == "local-fa-ui"

    status, external_denied = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/approve",
            method="POST",
            origin=base_url,
            idempotency_key="approve-external-denied",
            payload={
                "use": "external",
                "reason": "No authenticated external approver exists",
                "expected_version_number": reviewed["version_number"],
                "expected_version_hash": reviewed["version_hash"],
            },
        )
    )
    assert status == 403
    assert external_denied["error"] == "deal_permission_denied"

    status, approved = _json(
        _request(
            f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/approve/internal",
            method="POST",
            origin=base_url,
            idempotency_key="approve-internal-001",
            payload={
                "reason": "Approve for internal discussion only",
                "expected_version_number": reviewed["version_number"],
                "expected_version_hash": reviewed["version_hash"],
            },
        )
    )
    assert status == 201
    assert approved["status"] == "approved_for_internal_use"
    assert approved["approvals"][-1]["approved_by"]["id"] == "local-fa-ui"

    status, stored = _json(_request(f"{base_url}/api/ui/valuations/{valuation['valuation_id']}"))
    assert status == 200
    assert stored["current_version_hash"] == approved["version_hash"]
    status, valuation_list = _json(
        _request(f"{base_url}/api/ui/deals/{deal['deal_id']}/valuations")
    )
    assert status == 200
    assert len(valuation_list["valuations"]) == 1


def test_export_is_lazy_and_agent_manifest_has_no_valuation_approval(
    bridge: tuple[str, Any, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url, server, case_id = bridge
    deal = server.deals.create_deal(
        company_id=case_id,
        buyer="Buyer",
        target="Target",
        transaction_scope="Shares",
        currency="USD",
        valuation_date="2026-08-03",
        owner="FA",
        confidentiality_level="internal",
        actor={"id": "fixture-fa", "role": "fa"},
        reason="Fixture deal",
        idempotency_key="fixture-deal",
    )
    valuation = server.deals.create_valuation_case(
        deal["deal_id"],
        target_legal_entity="Target Ltd.",
        transaction_scope="Shares",
        valuation_date="2026-08-03",
        base_currency="USD",
        methods=["dcf_fcff"],
        actor={"id": "fixture-fa", "role": "fa"},
        reason="Fixture valuation",
        idempotency_key="fixture-valuation",
        expected_deal_revision=deal["revision"],
        expected_deal_hash=deal["record_hash"],
    )
    module_name = "cleantech_finance.valuation_export"
    monkeypatch.setitem(sys.modules, module_name, None)
    status, unavailable = _json(
        _request(f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/export.xlsx")
    )
    assert status == 501
    assert unavailable["error"] == "valuation_export_unavailable"

    captured: dict[str, Any] = {}
    export_module = types.ModuleType(module_name)

    def fake_export(*, deal: dict, valuation: dict, version: dict) -> bytes:
        captured.update(
            {
                "deal_id": deal["deal_id"],
                "valuation_id": valuation["valuation_id"],
                "version_number": version["version_number"],
            }
        )
        return b"PK\x03\x04trusted-workbook"

    export_module.export_valuation_workbook = fake_export  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, export_module.__name__, export_module)

    status, headers, workbook = _request(
        f"{base_url}/api/ui/valuations/{valuation['valuation_id']}/export.xlsx?version_number=1"
    )
    assert status == 200
    assert workbook == b"PK\x03\x04trusted-workbook"
    assert headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert captured == {
        "deal_id": deal["deal_id"],
        "valuation_id": valuation["valuation_id"],
        "version_number": 1,
    }

    status, manifest = _json(_request(f"{base_url}/api/agent/manifest"))
    assert status == 200
    serialized_tools = json.dumps(manifest["tools"], sort_keys=True)
    assert "/api/ui/valuations" not in serialized_tools
    assert "approve_valuation" not in serialized_tools
    assert manifest["boundaries"]["agent_can_approve"] is False

    status, not_found = _json(
        _request(
            f"{base_url}/api/agent/valuations/{valuation['valuation_id']}/approve",
            method="POST",
            payload={},
        )
    )
    assert status == 404
    assert not_found["error"] == "not_found"
