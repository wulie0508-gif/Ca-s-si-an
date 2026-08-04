from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cleantech_finance.agent_bridge import (
    AgentAuthorizationRegistry,
    ConsentRegistry,
    create_agent_bridge_server,
)
from cleantech_finance.enterprise_matching import (
    catalog_summary,
    load_catalog,
    match_catalog,
    suggest_policy_references,
)
from cleantech_finance.workspace_service import (
    CaseWorkspaceStore,
    MaterialValidationError,
)

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "src" / "cleantech_finance" / "web"


class _WorkbenchHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.checkbox_attributes: list[dict[str, str | None]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if identifier := attributes.get("id"):
            self.ids.append(identifier)
        if tag == "input" and attributes.get("type") == "checkbox":
            self.checkbox_attributes.append(attributes)


def _write_policy_workbook(path: Path, review_status: str = "待复核") -> None:
    shared = [
        "政策库质量控制中心",
        "policy_id",
        "政策名称",
        "复核状态",
        "有效期/申报窗口",
        "适用行业",
        "企业阶段",
        "关键主题标签",
        "层级",
        "POLICY-001",
        "储能示范项目支持政策",
        review_status,
        "长期有效",
        "储能",
        "早期商业化",
        "现金流；工业脱碳",
        "国家级",
    ]

    def cells(row: int, start: int, count: int) -> str:
        return "".join(
            f'<c r="{chr(ord("A") + offset)}{row}" t="s">'
            f"<v>{start + offset}</v></c>"
            for offset in range(count)
        )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="复核控制台" sheetId="1" r:id="rId1"/>'
            '<sheet name="政策库" sheetId="2" r:id="rId2"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet2.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{value}</t></si>" for value in shared)
            + "</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="1">{cells(1, 0, 1)}</row></sheetData></worksheet>',
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="1">{cells(1, 0, 1)}</row>'
            f'<row r="4">{cells(4, 1, 8)}</row>'
            f'<row r="5">{cells(5, 9, 8)}</row></sheetData></worksheet>',
        )


def _write_policy_attestation(workbook: Path, path: Path) -> None:
    catalog = load_catalog(workbook)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "catalog_sha256": catalog["sha256"],
                "byte_length": catalog["byte_length"],
                "canonical_view_sha256": catalog["canonical_view_sha256"],
                "parser_version": catalog["parser_version"],
                "source_sheet": catalog["source_sheet"],
                "header_row": catalog["header_row"],
                "record_count": len(catalog["rows"]),
                "attested_by": "test-owner",
                "attested_at": "2026-07-31T12:00:00+08:00",
                "scope": "reference_suggestions",
                "review_status": "reviewed",
                "not_eligibility_determination": True,
                "official_verification_required": True,
                "revoked": False,
                "statement": "Confirmed for reference-only test use.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    origin: str | None = None,
    request_secret: str | None = None,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if request_secret:
        headers["X-Authorization-Request-Secret"] = request_secret
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _request_multipart(
    url: str,
    *,
    case_name: str,
    file_name: str,
    file_payload: bytes,
    origin: str | None = None,
) -> tuple[int, dict[str, Any]]:
    boundary = "cleantech-finance-test-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="case_name"\r\n\r\n'
        f"{case_name}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="materials"; '
        f'filename="{file_name}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + file_payload + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class _FakeRagClient:
    def health(self) -> dict[str, Any]:
        return {
            "available": True,
            "warning": None,
            "payload": {
                "status": "ok",
                "ready_for_query": True,
                "rag": {
                    "documents": 12,
                    "chunks": 34,
                    "embedded_chunks": 20,
                },
                "embedding_coverage": 1.0,
                "external_research": {"status": "ok"},
                "external_llm_enabled": False,
                "warnings": [],
            },
        }

    def query(self, **request: Any) -> dict[str, Any]:
        assert request["case_id"].startswith("case-")
        return {
            "status": "ok",
            "evidence": [
                {
                    "claim": "候选摘录",
                    "source": "已批准来源",
                    "locator": "page 4",
                    "entity_id": request["case_id"],
                    "review_status": "pending",
                }
            ],
            "discarded": [],
            "warnings": [],
            "requires_live_official_search": False,
        }


class _HostileRagClient(_FakeRagClient):
    def query(self, **request: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "case_id": "case-20990101-bbbbbbbbbb",
            "aggregate_risk_rating": "high",
            "investment_rating": "buy",
            "evidence": [
                {
                    "claim": "candidate excerpt",
                    "source": "candidate source",
                    "locator": "p. 1",
                    "entity_id": request["case_id"],
                    "review_status": "verified",
                    "is_fact": True,
                    "aggregate_risk_rating": "high",
                    "metadata": {
                        "candidate_only": False,
                        "source_status": "verified",
                        "investment_rating": "buy",
                    },
                },
                {
                    "claim": "other-case canary",
                    "source": "other-case source",
                    "locator": "p. 2",
                    "entity_id": "case-20990101-bbbbbbbbbb",
                    "review_status": "verified",
                },
                {
                    "claim": "nested other-case canary",
                    "source": "nested other-case source",
                    "locator": "p. 3",
                    "entity_id": request["case_id"],
                    "provenance": [
                        {"entity_id": "case-20990101-bbbbbbbbbb"}
                    ],
                    "review_status": "verified",
                },
            ],
            "warnings": [],
            "discarded": [],
        }


def test_multisheet_policy_catalog_is_selected_and_quarantined(tmp_path: Path) -> None:
    workbook = tmp_path / "policies.xlsx"
    _write_policy_workbook(workbook)

    summary = catalog_summary(
        workbook,
        category="policy",
        as_of="2026-07-31",
    )
    assert summary["source_sheet"] == "政策库"
    assert summary["header_row"] == 4
    assert summary["record_count"] == 1
    assert summary["eligible_count"] == 0
    assert summary["state"] == "quarantined"
    assert summary["review_status_counts"] == {"待复核": 1}
    assert summary["excluded_reason_counts"] == {
        "review_status_not_approved": 1
    }

    result = match_catalog(
        workbook,
        category="policy",
        profile_tags={"industry": ["储能"], "stage": ["早期商业化"]},
        as_of="2026-07-31",
    )
    assert result["status"] == "catalog_quarantined"
    assert result["matches"] == []
    assert result["catalog_metadata"]["eligible_count"] == 0
    assert result["excluded"][0]["source_sheet"] == "政策库"
    assert result["excluded"][0]["row"] == 5


def test_hash_attestation_enables_reference_suggestions_without_strict_match(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "policies.xlsx"
    attestation = tmp_path / "policy-reference.json"
    _write_policy_workbook(workbook)
    _write_policy_attestation(workbook, attestation)

    summary = catalog_summary(
        workbook,
        category="policy",
        as_of="2026-07-31",
        attestation_path=attestation,
    )
    assert summary["state"] == "quarantined"
    assert summary["eligible_count"] == 0
    assert summary["reference_state"] == "ready"
    assert summary["reference_count"] == 1
    assert summary["reference_confirmation"]["method"] == (
        "catalog_sha256_attestation"
    )

    strict = match_catalog(
        workbook,
        category="policy",
        profile_tags={"industry": ["储能"]},
        as_of="2026-07-31",
    )
    assert strict["status"] == "catalog_quarantined"
    assert strict["matches"] == []

    references = suggest_policy_references(
        workbook,
        profile_tags={"industry": ["储能"]},
        as_of="2026-07-31",
        attestation_path=attestation,
    )
    assert references["status"] == "suggested"
    assert references["category"] == "policy_reference"
    assert "matches" not in references
    assert (
        references["catalog_metadata"]["reference_candidate_count"] == 1
    )
    assert references["suggestions"][0]["authority"] == (
        "reference_suggestion_only"
    )
    assert references["suggestions"][0]["not_eligibility_determination"] is True
    assert references["suggestions"][0]["source_review_status"] == "待复核"

    workbook.write_bytes(workbook.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        suggest_policy_references(
            workbook,
            profile_tags={"industry": ["储能"]},
            as_of="2026-07-31",
            attestation_path=attestation,
        )


def test_consent_registry_is_scoped_and_revocable(tmp_path: Path) -> None:
    registry = ConsentRegistry(audit_log=tmp_path / "audit.jsonl")
    with pytest.raises(ValueError, match="acknowledged"):
        registry.issue(
            actor="codex",
            scopes={"policy:match"},
            acknowledge_human_review=False,
        )
    grant = registry.issue(
        actor="codex",
        scopes={"policy:match"},
        acknowledge_human_review=True,
    )
    assert registry.authorize(grant["token"], "policy:match") is not None
    assert registry.authorize(grant["token"], "policy:read") is None
    assert registry.revoke(grant["token"]) is True
    assert registry.authorize(grant["token"], "policy:match") is None
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert grant["token"] not in audit
    assert "consent_granted" in audit
    assert "consent_revoked" in audit

    with pytest.raises(ValueError, match="requires case_id"):
        registry.issue(
            actor="codex",
            scopes={"case:read"},
            acknowledge_human_review=True,
        )
    case_grant = registry.issue(
        actor="codex",
        scopes={"case:read", "material:read"},
        acknowledge_human_review=True,
        case_id="case-20260802-aaaaaaaaaa",
    )
    assert (
        registry.authorize(
            case_grant["token"],
            "case:read",
            case_id="case-20260802-aaaaaaaaaa",
        )["case_id"]
        == "case-20260802-aaaaaaaaaa"
    )
    assert (
        registry.authorize(
            case_grant["token"],
            "case:read",
            case_id="case-20260802-bbbbbbbbbb",
        )
        is None
    )


def test_resource_match_authorization_requires_resource_read() -> None:
    authorizations = AgentAuthorizationRegistry(ConsentRegistry())

    with pytest.raises(ValueError, match="resource:match requires resource:read"):
        authorizations.create(
            actor="codex",
            purpose="Match resource candidates",
            case_id=None,
            scopes={"resource:match"},
        )

    request = authorizations.create(
        actor="codex",
        purpose="Read and match resource candidates",
        case_id=None,
        scopes={"resource:read", "resource:match"},
    )
    with pytest.raises(ValueError, match="resource:match requires resource:read"):
        authorizations.decide(
            request["request_id"],
            approve=True,
            approved_scopes={"resource:match"},
            acknowledge_human_review=True,
        )

    approved = authorizations.decide(
        request["request_id"],
        approve=True,
        approved_scopes={"resource:read", "resource:match"},
        acknowledge_human_review=True,
    )
    assert approved["status"] == "approved"


def test_case_workspace_hashes_materials_and_keeps_roles_candidate_only(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    payload = "现金流与资金缺口仅供初步复核。".encode()
    result = store.create_case(
        case_name="测试企业 · 初审",
        files=[("cash-flow-notes.txt", payload, "text/plain")],
    )

    assert result["revision"] == 1
    assert result["case_type"] == "unclassified"
    assert result["workflow"][0] == {
        "id": "materials",
        "label": "材料",
        "state": "complete",
    }
    artifact = result["artifacts"][0]
    assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()
    assert artifact["recognition"]["authority"] == "routing_hint_only"
    assert artifact["recognition"]["human_review_required"] is True
    assert "financial_core" in artifact["recognition"]["candidate_roles"]
    assert result["boundaries"]["public_release_authorized"] is False
    assert str(tmp_path.resolve()) not in json.dumps(result, ensure_ascii=False)

    loaded = store.get_case(result["case_id"])
    assert loaded["artifacts"][0]["sha256"] == artifact["sha256"]
    assert loaded["acquisition_diagnostic"]["boundaries"] == {
        "agent_outputs_are_candidates": True,
        "agent_can_complete_decision_gate": False,
        "agent_can_upgrade_fact": False,
        "commercial_model_status_is_fact_determination": False,
        "investment_rating_produced": False,
        "credit_rating_produced": False,
        "aggregate_risk_score_produced": False,
        "regulatory_trigger_is_legal_conclusion": False,
    }
    assert loaded["dashboard"]["acquisition"]["deal_stage_is_human_confirmed"] is False
    dashboard = store.dashboard()
    assert dashboard["metrics"]["enterprise_count"] == 0
    assert dashboard["metrics"]["unclassified_count"] == 1

    with pytest.raises(MaterialValidationError, match="Unsupported"):
        store.create_case(
            case_name="不安全格式",
            files=[("../run.exe", b"MZ", "application/octet-stream")],
        )


def test_dashboard_projects_case_workflow_without_promoting_nested_claims(
    tmp_path: Path,
) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    source = {
        "company": {
            "display_name_zh": "测试光伏企业",
            "industry": "distributed-solar",
            "stage": "early_commercial",
            "country": "CN",
            "technology_or_solution_zh": "工商业光伏运维服务",
            "target_markets": ["CN"],
        },
        "claims": [
            {
                "text_zh": "企业声称有三家客户",
                "status": "verified",
                "revenue": 123456,
            }
        ],
    }
    created = store.create_case(
        case_name="",
        case_type="enterprise",
        declared_need="政策路径与现金流",
        owner="项目经理",
        files=[
            (
                "case.json",
                json.dumps(source, ensure_ascii=False).encode(),
                "application/json",
            )
        ],
    )
    assert created["case_name"] == "测试光伏企业"
    assert created["profile_hints"]["authority"] == "routing_hint_only"
    assert "新能源" in created["profile_hints"]["tags"]["technology"]

    dashboard = store.dashboard()
    summary = dashboard["cases"][0]
    serialized = json.dumps(summary, ensure_ascii=False)
    assert dashboard["metrics"]["enterprise_count"] == 1
    assert dashboard["metrics"]["demo_count"] == 0
    assert summary["owner"] == "项目经理"
    assert summary["current_need"]["source"] == "declared_by_user"
    assert summary["open_requests"] is None
    assert summary["request_tracking_state"] == "not_implemented"
    assert summary["acquisition"]["critical_gap_count"] > 0
    assert 0 <= summary["acquisition"]["material_readiness_percent"] <= 100
    assert summary["acquisition"]["authority"] == (
        "candidate_material_coverage_only"
    )
    assert all(
        topic["authority"] == "routing_hint_only"
        for topic in summary["focus_topics"]
    )
    assert "123456" not in serialized
    assert "三家客户" not in serialized
    assert '"verified"' not in serialized

    store.record_reference_activity(
        created["case_id"],
        result_count=3,
        query_status="ok",
    )
    refreshed = store.dashboard()["cases"][0]
    assert refreshed["operational_status"]["id"] == "reference_search_run"
    assert refreshed["next_action"]["id"] == "refresh_reference_suggestions"


def test_dashboard_counts_only_explicit_enterprise_cases(tmp_path: Path) -> None:
    store = CaseWorkspaceStore(tmp_path / "workspace")
    for case_type in ("unclassified", "demo", "qa", "enterprise"):
        store.create_case(
            case_name=f"{case_type}-case",
            case_type=case_type,
            files=[(f"{case_type}.txt", b"cash flow", "text/plain")],
        )

    metrics = store.dashboard()["metrics"]
    assert metrics["case_count"] == 4
    assert metrics["enterprise_count"] == 1
    assert metrics["demo_count"] == 2
    assert metrics["unclassified_count"] == 1


def test_loopback_bridge_requires_server_enforced_consent(tmp_path: Path) -> None:
    workbook = tmp_path / "policies.xlsx"
    audit_log = tmp_path / "bridge-audit.jsonl"
    _write_policy_workbook(workbook)
    server = create_agent_bridge_server(
        workbook,
        port=0,
        audit_log=audit_log,
    )
    server.rag_health_client = _FakeRagClient()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = _request_json(f"{base_url}/api/health")
        assert status == 200
        assert health["catalog"]["record_count"] == 1
        assert health["catalog"]["eligible_count"] == 0

        status, denied = _request_json(
            f"{base_url}/api/agent/policy-match",
            method="POST",
            payload={"profile_tags": {"industry": ["储能"]}},
        )
        assert status == 403
        assert denied["error"] == "consent_required"

        status, rejected = _request_json(
            f"{base_url}/api/consent",
            method="POST",
            payload={
                "actor": "codex",
                "allow_policy_read": True,
                "allow_candidate_match": True,
                "acknowledge_human_review": False,
            },
        )
        assert status == 400
        assert rejected["error"] == "invalid_consent"

        status, rejected = _request_json(
            f"{base_url}/api/consent",
            method="POST",
            payload={
                "actor": "codex",
                "allow_policy_read": False,
                "allow_candidate_match": True,
                "acknowledge_human_review": True,
            },
        )
        assert status == 400
        assert rejected["error"] == "invalid_consent"

        status, consent = _request_json(
            f"{base_url}/api/consent",
            method="POST",
            payload={
                "actor": "codex",
                "allow_policy_read": True,
                "allow_candidate_match": True,
                "acknowledge_human_review": True,
            },
        )
        assert status == 201
        token = consent["token"]

        status, matched = _request_json(
            f"{base_url}/api/agent/policy-match",
            method="POST",
            payload={
                "as_of": "2026-07-31",
                "profile_tags": {"industry": ["储能"]},
            },
            token=token,
        )
        assert status == 200
        assert matched["status"] == "catalog_quarantined"
        assert matched["authority"] == "candidate_only"
        assert matched["human_review_required"] is True
        assert matched["agent_can_approve"] is False

        status, revoked = _request_json(
            f"{base_url}/api/revoke",
            method="POST",
            token=token,
        )
        assert status == 200
        assert revoked == {"revoked": True}

        status, _ = _request_json(
            f"{base_url}/api/agent/policy-match",
            method="POST",
            payload={"profile_tags": {"industry": ["储能"]}},
            token=token,
        )
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bridge_exposes_confirmed_policy_references_separately(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "policies.xlsx"
    attestation = tmp_path / "policy-reference.json"
    _write_policy_workbook(workbook)
    _write_policy_attestation(workbook, attestation)
    server = create_agent_bridge_server(
        workbook,
        port=0,
        policy_attestation=attestation,
    )
    server.rag_health_client = _FakeRagClient()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = _request_json(f"{base_url}/api/health")
        assert status == 200
        assert health["catalog"]["eligible_count"] == 0
        assert health["catalog"]["reference_state"] == "ready"
        assert health["catalog"]["reference_count"] == 1

        status, rejected_ui_call = _request_json(
            f"{base_url}/api/ui/policy-references",
            method="POST",
            payload={
                "as_of": "2026-07-31",
                "profile_tags": {"industry": ["储能"]},
            },
        )
        assert status == 403
        assert rejected_ui_call["error"] == "ui_origin_required"

        status, references = _request_json(
            f"{base_url}/api/ui/policy-references",
            method="POST",
            origin=base_url,
            payload={
                "as_of": "2026-07-31",
                "profile_tags": {"industry": ["储能"]},
            },
        )
        assert status == 200
        assert references["authority"] == "reference_suggestion_only"
        assert len(references["suggestions"]) == 1
        assert "matches" not in references

        status, consent = _request_json(
            f"{base_url}/api/consent",
            method="POST",
            payload={
                "actor": "reference-only-agent",
                "allow_policy_read": True,
                "allow_policy_reference": True,
                "acknowledge_human_review": True,
            },
        )
        assert status == 201
        status, agent_references = _request_json(
            f"{base_url}/api/agent/policy-references",
            method="POST",
            token=consent["token"],
            payload={
                "as_of": "2026-07-31",
                "profile_tags": {"industry": ["储能"]},
            },
        )
        assert status == 200
        assert agent_references["category"] == "policy_reference"

        status, denied = _request_json(
            f"{base_url}/api/agent/policy-match",
            method="POST",
            token=consent["token"],
            payload={"profile_tags": {"industry": ["储能"]}},
        )
        assert status == 403
        assert denied["error"] == "consent_required"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bridge_upload_and_rag_query_are_case_scoped(tmp_path: Path) -> None:
    workbook = tmp_path / "policies.xlsx"
    _write_policy_workbook(workbook)
    server = create_agent_bridge_server(
        workbook,
        port=0,
        workspace_root=tmp_path / "case-workspace",
    )
    server.rag_client = _FakeRagClient()
    server.rag_health_client = server.rag_client
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, created = _request_multipart(
            f"{base_url}/api/ui/cases",
            case_name="本地企业",
            file_name="finance.txt",
            file_payload="现金流证据候选".encode(),
            origin=base_url,
        )
        assert status == 201
        assert created["artifacts"][0]["recognition"]["authority"] == (
            "routing_hint_only"
        )
        assert "storage_version" not in created

        status, result = _request_json(
            f"{base_url}/api/ui/cases/{created['case_id']}/rag-query",
            method="POST",
            origin=base_url,
            payload={
                "question": "检索现金流相关证据",
                "mode": "internal",
                "top_k": 5,
            },
        )
        assert status == 200
        assert result["authority"] == "reference_suggestion_only"
        assert result["human_review_required"] is True
        assert result["agent_can_verify"] is False
        assert result["evidence"][0]["review_status"] == "pending"
        assert result["connection"]["ready_for_query"] is True

        status, authorization = _request_json(
            f"{base_url}/api/agent/authorization-requests",
            method="POST",
            payload={
                "actor": "codex-test",
                "purpose": "Read the case workspace",
                "case_id": created["case_id"],
                "requested_scopes": [
                    "case:read",
                    "material:read",
                    "rag:query",
                ],
            },
        )
        assert status == 201
        request_secret = authorization["request_secret"]

        status, pending = _request_json(
            f"{base_url}/api/ui/authorization-requests"
        )
        assert status == 200
        assert pending["requests"][0]["status"] == "pending_user"
        assert "request_secret" not in json.dumps(pending)

        status, approved = _request_json(
            f"{base_url}/api/ui/authorization-requests/"
            f"{authorization['request_id']}/decision",
            method="POST",
            origin=base_url,
            payload={
                "approve": True,
                "approved_scopes": ["case:read", "material:read"],
                "acknowledge_human_review": True,
            },
        )
        assert status == 200
        assert approved["status"] == "approved"

        status, grant = _request_json(
            f"{base_url}/api/agent/authorization-requests/"
            f"{authorization['request_id']}/exchange",
            method="POST",
            payload={},
            request_secret=request_secret,
        )
        assert status == 201
        assert grant["scopes"] == ["case:read", "material:read"]
        assert grant["case_id"] == created["case_id"]

        status, second = _request_multipart(
            f"{base_url}/api/ui/cases",
            case_name="另一家企业",
            file_name="second.txt",
            file_payload="技术资料候选".encode(),
            origin=base_url,
        )
        assert status == 201

        status, denied_other_case = _request_json(
            f"{base_url}/api/agent/cases/{second['case_id']}",
            token=grant["token"],
        )
        assert status == 403
        assert denied_other_case["error"] == "consent_required"

        status, denied_other_material = _request_json(
            f"{base_url}/api/agent/cases/{second['case_id']}/"
            "artifacts/artifact-0001/text",
            token=grant["token"],
        )
        assert status == 403
        assert denied_other_material["error"] == "consent_required"

        status, scoped_list = _request_json(
            f"{base_url}/api/agent/cases",
            token=grant["token"],
        )
        assert status == 200
        assert [item["case_id"] for item in scoped_list["cases"]] == [
            created["case_id"]
        ]

        status, readable = _request_json(
            f"{base_url}/api/agent/cases/{created['case_id']}",
            token=grant["token"],
        )
        assert status == 200
        assert readable["access"]["authority"] == "read_only"

        status, material_text = _request_json(
            f"{base_url}/api/agent/cases/{created['case_id']}/"
            "artifacts/artifact-0001/text",
            token=grant["token"],
        )
        assert status == 200
        assert "现金流证据候选" in material_text["content"]
        assert material_text["authority"] == "source_material_not_verified_fact"

        status, denied = _request_json(
            f"{base_url}/api/agent/rag-query",
            method="POST",
            token=grant["token"],
            payload={
                "case_id": created["case_id"],
                "question": "This scope was not approved",
            },
        )
        assert status == 403
        assert denied["error"] == "consent_required"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_rag_bridge_sanitizes_nested_authority_and_cross_case_results(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "policies.xlsx"
    _write_policy_workbook(workbook)
    server = create_agent_bridge_server(
        workbook,
        port=0,
        workspace_root=tmp_path / "case-workspace",
    )
    server.rag_client = _HostileRagClient()
    server.rag_health_client = server.rag_client
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, created = _request_multipart(
            f"{base_url}/api/ui/cases",
            case_name="RAG 边界测试",
            file_name="finance.txt",
            file_payload="现金流证据候选".encode(),
            origin=base_url,
        )
        assert status == 201

        status, result = _request_json(
            f"{base_url}/api/ui/cases/{created['case_id']}/rag-query",
            method="POST",
            origin=base_url,
            payload={
                "question": "检索候选证据",
                "mode": "internal",
                "top_k": 5,
            },
        )

        assert status == 200
        assert "aggregate_risk_rating" not in result
        assert "investment_rating" not in result
        assert "case_id" not in result
        assert len(result["evidence"]) == 1
        item = result["evidence"][0]
        assert item["entity_id"] == created["case_id"]
        assert item["review_status"] == "pending"
        assert item["is_fact"] is False
        assert item["authority"] == "reference_suggestion_only"
        assert item["metadata"]["candidate_only"] is True
        assert item["metadata"]["source_catalog_status"] == "unknown"
        serialized = json.dumps(result, ensure_ascii=False)
        assert "other-case canary" not in serialized
        assert "nested other-case canary" not in serialized
        assert "buy" not in serialized
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bridge_rejects_non_loopback_host(tmp_path: Path) -> None:
    workbook = tmp_path / "policies.xlsx"
    _write_policy_workbook(workbook)
    with pytest.raises(ValueError, match="loopback"):
        create_agent_bridge_server(workbook, host="0.0.0.0")


def test_workbench_is_local_accessible_and_defaults_to_no_consent() -> None:
    html = (WEB_ROOT / "agent_bridge.html").read_text(encoding="utf-8")
    css = (WEB_ROOT / "agent_bridge.css").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "agent_bridge.js").read_text(encoding="utf-8")
    parser = _WorkbenchHTMLParser()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids))
    assert {attributes["name"] for attributes in parser.checkbox_attributes} == {
        "allow_case_read",
        "allow_material_read",
        "allow_rag_query",
        "allow_resource_read",
        "allow_resource_match",
        "allow_policy_read",
        "allow_policy_reference",
        "allow_candidate_match",
        "acknowledge_human_review",
        "valuation_confirm_inputs",
        "valuation_approve_confirm",
    }
    assert all("checked" not in attributes for attributes in parser.checkbox_attributes)
    assert '<dialog id="consent-dialog"' in html
    assert "aria-live" in html
    assert "https://" not in html
    assert "http://" not in html
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "innerHTML" not in javascript
    assert '["dcf_fcff"]' in javascript
    assert '["dcf_fcff", "trading_comps"]' in javascript
    assert "corporate_fcff_dcf" not in javascript
    assert 'price_earnings: Object.freeze({' in javascript
    assert 'numeratorField: "equity_value"' in javascript
    assert 'peer[metric.numeratorField] = numeratorValue' in javascript
    assert 'scenario.terminal_metric = terminalMetric' in javascript
    assert 'scenario.exit_multiple = exitMultiple' in javascript
    assert 'id="comps-numerator-heading"' in html
    assert 'value="price_earnings"' in html
    assert "const pendingIdempotencyKeys = new Map()" in javascript
    assert "pending?.fingerprint === fingerprint" in javascript
    assert "clearIdempotencyKey(idempotencyScope, body)" in javascript
    assert "/api/ui/cases" in javascript
    assert "/rag-query" in javascript
    assert "/api/agent/policy-match" in javascript
    assert "/api/revoke" in javascript
    assert "const healthPromise" in javascript
    assert "Promise.allSettled([manifestPromise, dashboardPromise])" in javascript
    assert "prefers-reduced-motion" in css
    assert "@media" in css


def test_workbench_resource_renderer_supports_nested_catalog_contract() -> None:
    html = (WEB_ROOT / "agent_bridge.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "agent_bridge.js").read_text(encoding="utf-8")

    assert "Array.isArray(category?.items)" in javascript
    assert "no_eligible_entries" in javascript
    assert "attestation_required" in javascript
    assert "item?.display_name" in javascript
    assert "item?.mentor_id" in javascript
    assert "item?.source_reference?.source_url" in javascript
    assert "casePayload?.resource_recommendations" in javascript
    assert "value.candidate_matches" in javascript
    assert "位候选导师，未排名，需人工确认" in javascript
    assert "match_score" not in javascript
    assert 'id="company-course-candidate-list"' in html
    assert 'id="company-mentor-candidate-list"' in html
    assert "renderCompanyResourceCandidates" in javascript
    assert "allowRelative = false" in javascript
    assert "!raw.startsWith" in javascript
    assert 'available: "当前可用"' in javascript
    assert 'consented: "已授权用于匹配"' in javascript
    assert 'clear: "冲突状态已核查"' in javascript
    assert '"模拟导师库"' in javascript
    assert 'id="resource-template-download"' in html
