from __future__ import annotations

import json
from pathlib import Path

from cleantech_finance.onboarding import (
    MATERIAL_CATALOG,
    assessment_plan,
    benchmark_summary,
    build_agent_tasks,
    new_company_case,
    validate_company_case,
)
from cleantech_finance.onboarding_reporting import write_onboarding_artifacts


def _valid_case() -> dict[str, object]:
    case = new_company_case()
    case["case"]["id"] = "demo-distributed-solar"
    case["company"].update(
        {
            "legal_name": "Demo Distributed Solar Services Co., Ltd.",
            "display_name": "Demo Solar",
            "display_name_zh": "示例分布式光伏服务企业",
            "entity_identifier": {"scheme": "cn_uscc", "value": "91310000DEMO00001X"},
            "industry": "distributed-solar-operations",
            "business_model": "asset-light-energy-service",
            "stage": "early_commercial",
            "technology_or_solution": "Solar operations and monitoring service for commercial rooftops.",
            "technology_or_solution_zh": "面向工商业屋顶的光伏运维与监控服务。",
        }
    )
    for material in case["materials"]:
        if material["id"] in MATERIAL_CATALOG:
            material["status"] = "provided"
    case["claims"] = [
        {
            "id": "claim-paid-customers",
            "category": "commercial",
            "text_zh": "企业有三家已回款的付费客户。",
            "text_en": "The company has three paying customers with collected cash.",
            "statement_id": None,
            "critical": True,
            "minimum_evidence_level": "E3",
            "evidence_ids": ["evidence-contracts"],
            "status": "verified",
            "visibility": "internal",
            "subject_scope": "Demo Distributed Solar Services Co., Ltd.",
            "period": "2026-01-01/2026-06-30",
        },
        {
            "id": "claim-market-view",
            "category": "content",
            "text_zh": "创始人认为工商业屋顶运维将从被动维修转向预测性服务。",
            "text_en": "The founder believes commercial rooftop operations will move to predictive service.",
            "statement_id": None,
            "critical": False,
            "minimum_evidence_level": "E1",
            "evidence_ids": [],
            "status": "unverified",
            "visibility": "public_candidate",
            "subject_scope": "Founder opinion",
            "period": "2026",
        },
    ]
    case["evidence"] = [
        {
            "id": "evidence-contracts",
            "level": "E3",
            "source_type": "transaction_document",
            "title": "Redacted contract, invoice and collection package",
            "captured_at": "2026-07-17",
            "visibility": "restricted",
            "review_status": "accepted",
            "raw_artifact": "sources/contracts-and-receipts.pdf",
            "url_or_source_id": "company-provided",
            "sha256": "sha256:demo",
            "agent_run_id": None,
            "claim_ids": ["claim-paid-customers"],
        }
    ]
    return case


def test_template_is_local_first_and_requires_real_intake_data() -> None:
    result = validate_company_case(new_company_case())
    assert not result["passed"]
    assert result["guardrails"]["investment_rating"] is False
    assert {gate["id"] for gate in result["gates"]} == {
        "authorization",
        "identity_scope",
        "minimum_evidence",
        "assessment_eligibility",
        "publication",
    }


def test_valid_case_writes_offline_bilingual_packet(tmp_path: Path) -> None:
    case = _valid_case()
    result = validate_company_case(case)
    assert result["passed"]

    paths = write_onboarding_artifacts(case, tmp_path / "packet")
    assert set(paths) >= {
        "report_html",
        "workbench_html",
        "claim_ledger_csv",
        "agent_tasks_json",
        "benchmark_json",
        "assessment_plan_json",
    }
    report = Path(paths["report_html"]).read_text(encoding="utf-8")
    workbench = Path(paths["workbench_html"]).read_text(encoding="utf-8")
    assert "五道闸门" in report
    assert "本地企业入驻" in report
    assert "Local-only" in workbench
    assert 'id="add-claim"' in workbench
    assert 'id="add-evidence"' in workbench
    assert "fetch(" not in workbench
    assert "cdn" not in workbench.lower()


def test_agent_candidate_cannot_be_auto_accepted_or_upgrade_a_critical_claim() -> None:
    case = _valid_case()
    case["claims"][0]["evidence_ids"] = ["agent-result"]
    case["evidence"] = [
        {
            "id": "agent-result",
            "level": "E1",
            "source_type": "agent_candidate",
            "title": "Registry search result",
            "captured_at": "2026-07-17",
            "visibility": "internal",
            "review_status": "accepted",
            "raw_artifact": "agents/registry-result.html",
            "url_or_source_id": "official_registry",
            "sha256": "sha256:agent",
            "agent_run_id": "run-001",
            "claim_ids": ["claim-paid-customers"],
        }
    ]
    result = validate_company_case(case)
    codes = {item["code"] for item in result["errors"]}
    assert "agent_cannot_auto_accept" in codes
    assert "unproven_verified_claim" in codes


def test_public_claim_requires_explicit_permission_and_verified_status() -> None:
    case = _valid_case()
    case["claims"][1]["visibility"] = "public_approved"
    result = validate_company_case(case)
    codes = {item["code"] for item in result["errors"]}
    assert "public_unverified_claim" in codes
    assert "public_consent_missing" in codes


def test_benchmark_refuses_false_precision_for_small_cohort() -> None:
    case = _valid_case()
    cohort = {
        "industry": case["company"]["industry"],
        "stage": case["company"]["stage"],
        "business_model": case["company"]["business_model"],
        "country": case["company"]["country"],
    }
    case["benchmark_observations"] = [
        {"metric": "gross_margin", "value": value, "cohort": cohort}
        for value in (0.10, 0.20, 0.30, 0.40)
    ]
    summary = benchmark_summary(case)
    assert summary["metrics"][0]["status"] == "insufficient_sample"
    assert summary["metrics"][0]["percentile"] is None


def test_assessment_plan_exposes_truthful_module_boundaries() -> None:
    plan = assessment_plan(_valid_case())
    states = {item["id"]: item["state"] for item in plan["modules"]}
    assert plan["route"] == "sme_evidence_readiness"
    assert states["financial_evidence_core"] == "manifest_required"
    assert states["doe_arl"] == "retrieval_scaffold_only"
    assert plan["guardrails"]["no_aggregate_score"] is True


def test_optional_agent_tasks_are_allowlist_bound(tmp_path: Path) -> None:
    case = _valid_case()
    case["agent_settings"] = {
        "enabled": True,
        "mode": "local_optional",
        "allowed_source_families": ["official_registry", "ip_office"],
        "commercial_provider_authorized": False,
    }
    tasks = build_agent_tasks(case)
    assert [task["id"] for task in tasks] == ["entity-registry", "intellectual-property"]
    payload = tmp_path / "tasks.json"
    payload.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    assert "Candidate evidence only" in payload.read_text(encoding="utf-8")
