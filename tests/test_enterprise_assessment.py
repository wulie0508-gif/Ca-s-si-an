from __future__ import annotations

import json
import urllib.error
import zipfile
from pathlib import Path
from typing import Any

import pytest

from cleantech_finance.enterprise_assessment import EnterpriseAssessmentEngine
from cleantech_finance.enterprise_evidence import (
    NexSidecarClient,
    evaluate_claim_burden,
    normalize_evidence,
)
from cleantech_finance.enterprise_matching import match_catalog
from cleantech_finance.enterprise_reporting import (
    build_enterprise_report,
    write_enterprise_report,
)
from cleantech_finance.enterprise_store import AssessmentStore

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "enterprise-assessment"


def _create_case(
    store: AssessmentStore,
    profile: dict[str, Any],
    *,
    name: str = "Fictional CleanTech",
) -> str:
    company_id = store.upsert_company(
        canonical_name=name,
        legal_name=f"{name} Ltd.",
        jurisdiction="CN",
        registry_id=f"FICTIONAL:{name}",
    )
    return store.create_case(
        company_id=company_id,
        stage="early_commercial",
        as_of="2026-07-30",
        profile=profile,
        owner="tester",
    )


def _complete_profile() -> dict[str, Any]:
    return {
        "technology": ["thermal storage"],
        "business_model": "equipment + service",
        "stage": ["early_commercial"],
        "geography": ["China", "EU"],
        "target_market": ["industrial decarbonization"],
        "industry": ["energy storage", "industrial heat"],
        "needs": ["cash flow", "EU market entry"],
        "tags": {
            "industry": ["energy storage", "industrial heat"],
            "stage": ["early_commercial"],
            "need": ["cash flow", "EU market entry"],
            "technology": ["thermal storage"],
            "geography": ["China", "EU"],
            "market": ["industrial decarbonization"],
        },
    }


def _add_complete_nonfinancial_evidence(store: AssessmentStore, case_id: str) -> None:
    store.add_evidence(
        case_id,
        {
            "evidence_key": "owner-revenue",
            "claim": "Founder stated H1 revenue was CNY 12 million.",
            "source": "interview.txt",
            "locator": "00:08:13-00:08:31",
            "entity_id": case_id,
            "source_level": "L4",
            "type": "owner_statement",
            "confidence": "medium",
            "review_status": "pending",
            "metadata": {
                "input_module": "interview",
                "topic": "2026H1_revenue",
                "normalized_value": 12000000,
            },
        },
    )
    store.add_evidence(
        case_id,
        {
            "evidence_key": "public-revenue",
            "claim": "Reviewed accounts show H1 revenue of CNY 12 million.",
            "source": "reviewed-accounts.pdf",
            "locator": "p.4 revenue table",
            "entity_id": case_id,
            "source_level": "L1",
            "type": "fact",
            "confidence": "high",
            "review_status": "verified",
            "metadata": {
                "input_module": "public",
                "topic": "2026H1_revenue",
                "normalized_value": 12000000,
            },
        },
    )


def test_unified_evidence_rejects_missing_locator() -> None:
    with pytest.raises(ValueError, match="locator"):
        normalize_evidence(
            {
                "claim": "A claim",
                "source": "A source",
                "locator": "",
                "entity_id": "case-1",
                "source_level": "L1",
                "type": "fact",
                "confidence": "high",
                "review_status": "verified",
            }
        )


def test_store_enforces_case_owned_evidence_and_decision_workflow(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    case_id = _create_case(store, _complete_profile())
    with pytest.raises(ValueError, match="entity_id"):
        store.add_evidence(
            case_id,
            {
                "claim": "Wrong-case evidence",
                "source": "source",
                "locator": "p.1",
                "entity_id": "another-case",
                "source_level": "L1",
                "type": "fact",
                "confidence": "high",
                "review_status": "verified",
            },
        )
    store.create_draft_decision(
        case_id,
        recommendation="补充信息后再议",
        reasons=["Missing evidence"],
        human_confirmation=["Financial evidence"],
        actor="analyst",
    )
    with pytest.raises(ValueError, match="Invalid decision transition"):
        store.transition_decision(case_id, "approved", actor="leader")
    store.transition_decision(case_id, "pending_review", actor="analyst")
    rejected = store.transition_decision(
        case_id,
        "rejected",
        actor="leader",
        rejection_reason="Revenue basis needs correction",
        eval_dir=tmp_path / "eval_cases",
    )
    snapshot = Path(str(rejected["evaluation_snapshot"]))
    assert snapshot.is_file()
    assert json.loads(snapshot.read_text(encoding="utf-8"))["decisions"][-1][
        "rejection_reason"
    ] == "Revenue basis needs correction"


def test_company_master_fails_closed_on_identity_conflicts(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "identity.sqlite")
    store.upsert_company(
        canonical_name="Alpha Storage",
        registry_id="FICTIONAL:ALPHA",
    )
    store.upsert_company(
        canonical_name="Beta Storage",
        registry_id="FICTIONAL:BETA",
    )
    with pytest.raises(ValueError, match="identity conflict"):
        store.upsert_company(
            canonical_name="Alpha Storage",
            registry_id="FICTIONAL:BETA",
        )
    with pytest.raises(ValueError, match="human confirmation"):
        store.upsert_company(
            canonical_name="Alpha Storage Renamed",
            registry_id="FICTIONAL:ALPHA",
        )


def test_claim_burden_never_uses_owner_or_l3_l4_as_proof() -> None:
    reference_only = [
        {
            "source": "interview",
            "source_url": None,
            "source_level": "L4",
            "type": "owner_statement",
            "review_status": "pending",
        },
        {
            "source": "industry blog",
            "source_url": "https://example.invalid/blog",
            "source_level": "L3",
            "type": "fact",
            "review_status": "verified",
        },
    ]
    assert evaluate_claim_burden(reference_only)["status"] == "not_supported"
    l2_pair = [
        {
            "source": "Association A",
            "source_url": "https://a.example.invalid",
            "source_level": "L2",
            "type": "fact",
            "review_status": "verified",
        },
        {
            "source": "Media B",
            "source_url": "https://b.example.invalid",
            "source_level": "L2",
            "type": "fact",
            "review_status": "verified",
        },
    ]
    assert evaluate_claim_burden(l2_pair)["status"] == "supported"


def test_policy_hard_filters_are_always_applied() -> None:
    result = match_catalog(
        EXAMPLES / "policies.csv",
        category="policy",
        profile_tags={
            "industry": ["energy storage", "industrial heat"],
            "stage": ["early_commercial"],
            "need": ["cash flow", "EU market entry"],
            "technology": ["thermal storage"],
            "geography": ["China", "EU"],
            "market": ["industrial decarbonization"],
        },
        as_of="2026-07-30",
    )
    assert [item["item_id"] for item in result["matches"]] == ["POLICY-001"]
    assert {item["reason"] for item in result["excluded"]} == {
        "expired",
        "review_status_not_approved",
    }


def test_xlsx_catalog_is_read_without_optional_excel_dependencies(tmp_path: Path) -> None:
    workbook = tmp_path / "courses.xlsx"
    shared = [
        "course_id",
        "title",
        "industry_tags",
        "stage_tags",
        "need_tags",
        "technology_tags",
        "geography_tags",
        "market_tags",
        "XLSX-001",
        "Thermal Storage Commercialization",
        "energy storage",
        "early_commercial",
        "cash flow",
        "thermal storage",
        "EU",
        "industrial decarbonization",
    ]
    cells = []
    for row_number, start in ((1, 0), (2, 8)):
        for offset in range(8):
            column = chr(ord("A") + offset)
            cells.append(
                f'<c r="{column}{row_number}" t="s"><v>{start + offset}</v></c>'
            )
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Courses" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
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
            f"<sheetData><row r=\"1\">{''.join(cells[:8])}</row>"
            f"<row r=\"2\">{''.join(cells[8:])}</row></sheetData></worksheet>",
        )
    result = match_catalog(
        workbook,
        category="course",
        profile_tags={
            "industry": ["energy storage"],
            "stage": ["early_commercial"],
            "need": ["cash flow"],
            "technology": ["thermal storage"],
            "geography": ["EU"],
            "market": ["industrial decarbonization"],
        },
        as_of="2026-07-30",
    )
    assert result["status"] == "matched"
    assert result["matches"][0]["item_id"] == "XLSX-001"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_sidecar_hit_converts_only_traceable_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "citations": [
            {
                "title": "Official solar register",
                "snippet": "Solar capacity is listed as 12 MW.",
                "locator": "CSV row 44",
                "source_url": "https://example.gov.au/register",
                "publication_date": "2026-06-01",
                "source_kind": "official_registry",
                "retrieval_score": 0.8,
            },
            {
                "title": "Untraceable result",
                "snippet": "Solar capacity might be 99 MW.",
                "locator": "",
            },
        ],
        "warnings": [],
        "confidence": "medium",
        "data_freshness": "2026-06-01",
    }
    monkeypatch.setattr(
        "cleantech_finance.enterprise_evidence.urllib.request.urlopen",
        lambda *args, **kwargs: _FakeResponse(payload),
    )
    result = NexSidecarClient().query(
        question="solar capacity",
        case_id="case-1",
        top_k=5,
    )
    assert result["status"] == "ok"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["source_level"] == "L1"
    assert result["evidence"][0]["review_status"] == "pending"
    assert result["discarded"] == [{"index": 1, "reason": "missing_locator"}]


def test_sidecar_unavailable_is_an_explicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        "cleantech_finance.enterprise_evidence.urllib.request.urlopen",
        fail,
    )
    result = NexSidecarClient(timeout_seconds=0.1).query(
        question="company official filings",
        case_id="case-1",
    )
    assert result["status"] == "sidecar_unavailable"
    assert result["evidence"] == []
    assert result["requires_live_official_search"] is True
    assert "本地缓存未使用" in result["warnings"][0]


def test_complete_fictional_company_runs_full_flow(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "complete.sqlite")
    case_id = _create_case(store, _complete_profile(), name="Qinglan Demo")
    _add_complete_nonfinancial_evidence(store, case_id)
    audit = json.loads(
        (EXAMPLES / "complete-financial-audit.json").read_text(encoding="utf-8")
    )
    assessment = EnterpriseAssessmentEngine(store).run(
        case_id,
        financial_audit=audit,
        course_catalog=EXAMPLES / "courses.csv",
        policy_catalog=EXAMPLES / "policies.csv",
        sidecar_status={"status": "ok", "warnings": []},
        actor="analyst",
    )
    assert assessment["dimensions"]["financial_evidence_sufficiency"]["status"] == "sufficient"
    assert (
        assessment["dimensions"]["information_consistency"]["status"]
        == "consistent_on_available_evidence"
    )
    assert assessment["dimensions"]["data_completeness"]["status"] == "complete"
    assert assessment["recommendation"] == "进"
    assert assessment["guardrails"]["aggregate_score"] is False
    assert [item["item_id"] for item in assessment["matching"]["policy"]["matches"]] == [
        "POLICY-001"
    ]
    report = build_enterprise_report(store, assessment)
    assert report["decision"]["status"] == "draft"
    assert all(item["source"] and item["locator"] for item in report["evidence"])
    paths = write_enterprise_report(store, assessment, tmp_path / "report")
    assert all(Path(path).is_file() for path in paths.values())
    assert "没有总分" in Path(paths["report_html"]).read_text(encoding="utf-8")


def test_sparse_fictional_company_honestly_downgrades(tmp_path: Path) -> None:
    store = AssessmentStore(tmp_path / "sparse.sqlite")
    case_id = _create_case(
        store,
        {"technology": ["bio-based material"], "stage": ["research_development"]},
        name="Mosslight Demo",
    )
    assessment = EnterpriseAssessmentEngine(store).run(
        case_id,
        sidecar_status={
            "status": "sidecar_unavailable",
            "warnings": ["本地缓存未使用"],
        },
    )
    assert assessment["recommendation"] == "补充信息后再议"
    assert assessment["dimensions"]["financial_evidence_sufficiency"]["status"] == "insufficient"
    assert assessment["dimensions"]["information_consistency"]["status"] == "unassessable"
    assert assessment["dimensions"]["data_completeness"]["status"] == "sparse"
    gap_ids = {gap["gap_id"] for gap in assessment["gaps"]}
    assert {
        "financial-profitability-unit-economics",
        "financial-cash-runway",
        "nex-sidecar-unavailable",
        "course-catalog-not-supplied",
        "policy-catalog-not-supplied",
    } <= gap_ids
    assert assessment["matching"]["course"]["status"] == "catalog_not_supplied"
