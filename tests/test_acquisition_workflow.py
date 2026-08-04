from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cleantech_finance.acquisition_workflow import (
    DEFAULT_CONFIG_PATH,
    REQUIREMENT_CANDIDATE_SCHEMA_VERSION,
    RULE_VERSION,
    acquisition_workflow_definition,
    diagnose_acquisition_readiness,
    load_acquisition_workflow_config,
)

ROOT = Path(__file__).resolve().parents[1]


def test_default_acquisition_config_is_packaged_and_matches_operator_copy() -> None:
    packaged = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    operator_copy = json.loads(
        (ROOT / "config" / "acquisition-workflow.default.json").read_text(
            encoding="utf-8"
        )
    )

    assert packaged == operator_copy


def _artifact(
    artifact_id: str,
    *roles: str,
    profile_hints: dict[str, list[str]] | None = None,
    recognition_status: str = "candidate_ready",
    requirement_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "status": "ready",
        "recognition": {
            "status": recognition_status,
            "candidate_roles": list(roles),
            "requirement_candidates": {
                "schema_version": REQUIREMENT_CANDIDATE_SCHEMA_VERSION,
                "rule_version": RULE_VERSION,
                "requirement_ids": list(requirement_ids),
            },
            "profile_hints": profile_hints or {},
            "authority": "routing_hint_only",
            "human_review_required": True,
        },
    }


def test_definition_locks_eight_stages_and_five_cross_cutting_workstreams() -> None:
    definition = acquisition_workflow_definition()

    assert [stage["name_zh"] for stage in definition["stages"]] == [
        "收购战略与委托确认",
        "产业研究与 Longlist",
        "Shortlist 与初步估值",
        "初步接触与 NDA",
        "IOI / LOI 与排他",
        "尽调与交易结构",
        "签约、审批与交割",
        "并购后整合",
    ]
    assert [stage["decision_gate"]["question_zh"] for stage in definition["stages"]] == [
        "是否正式启动",
        "哪些进入初筛",
        "是否接触",
        "是否继续",
        "是否进入全面尽调",
        "投资委员会是否批准",
        "是否完成交割",
        "是否兑现交易价值",
    ]
    assert [item["name_zh"] for item in definition["workstreams"]] == [
        "商业与行业研究",
        "财务、估值与融资",
        "法律、税务与监管",
        "技术、IP、质量与EHS",
        "项目管理、沟通与并购后整合",
    ]
    for stage in definition["stages"]:
        assert stage["materials"]
        assert stage["fields"]
        assert stage["criticality"] == "stage_gate_critical"
        assert stage["responsible_roles"]
        assert stage["requirements"]
        assert stage["conditional_regulatory_triggers"]
        assert stage["decision_gate"]["authority"] == "human_only"
        assert stage["decision_gate"]["agent_may_decide"] is False


def test_empty_input_is_zero_insufficient_and_candidate_only() -> None:
    result = diagnose_acquisition_readiness([])

    assert result["schema_version"] == "1.0.0"
    assert result["completeness"]["ratio"] == 0
    assert result["completeness"]["percent"] == 0
    assert result["business_model_interview_readiness"]["status"] == "insufficient"
    assert result["business_model_interview_readiness"]["label_zh"] == "尚不足"
    assert result["critical_gaps"]
    assert 1 <= len(result["interview_questions"]) <= 8
    assert all(question["basis"]["missing_requirement"] for question in result["interview_questions"])
    assert result["boundaries"] == {
        "agent_outputs_are_candidates": True,
        "agent_can_complete_decision_gate": False,
        "agent_can_upgrade_fact": False,
        "commercial_model_status_is_fact_determination": False,
        "investment_rating_produced": False,
        "credit_rating_produced": False,
        "aggregate_risk_score_produced": False,
        "regulatory_trigger_is_legal_conclusion": False,
    }
    assert all(
        stage["decision_gate"]["status"] == "human_pending"
        for stage in result["stage_diagnostics"]
    )


def test_partial_input_is_deterministic_and_questions_cite_missing_requirements() -> None:
    materials = [
        _artifact(
            "company-pack",
            "company_identity",
            profile_hints={"industry": ["氢能"], "geography": ["中国"]},
            requirement_ids=("target_business_profile",),
        )
    ]
    profile_hints = {"tags": {"technology": ["电解槽"]}}

    first = diagnose_acquisition_readiness(materials, profile_hints=profile_hints)
    second = diagnose_acquisition_readiness(copy.deepcopy(materials), profile_hints=profile_hints)

    assert first == second
    assert 0 < first["completeness"]["ratio"] < 1
    assert first["business_model_interview_readiness"]["status"] == "insufficient"
    assert len(first["interview_questions"]) <= 8
    missing_ids = {
        requirement["id"]
        for stage in first["stage_diagnostics"]
        for requirement in stage["requirements"]
        if requirement["status"] != "candidate_covered"
    }
    assert all(
        question["gap_requirement_id"] in missing_ids
        for question in first["interview_questions"]
    )


def test_key_material_candidates_can_make_interview_schedulable_without_fact_claim() -> None:
    entry_and_coverage_ids = tuple(
        requirement["id"]
        for stage in acquisition_workflow_definition()["stages"][:4]
        for requirement in stage["requirements"]
    )
    materials = [
        _artifact(
            "identity",
            "company_identity",
            requirement_ids=entry_and_coverage_ids,
        ),
        _artifact("financial", "financial_core"),
        _artifact("commercial", "market_export"),
        _artifact("technology", "technology_arl"),
    ]
    profile_hints = {
        "tags": {
            "industry": ["氢能"],
            "stage": ["早期商业化"],
            "technology": ["电解槽"],
            "geography": ["中国", "美国"],
            "market": ["工业客户"],
            "need": ["跨境收购"],
        }
    }
    materials[0]["recognition"]["profile_hints"] = profile_hints["tags"]

    result = diagnose_acquisition_readiness(materials, profile_hints=profile_hints)
    readiness = result["business_model_interview_readiness"]

    assert readiness["status"] == "interview_schedulable"
    assert readiness["label_zh"] == "可安排访谈"
    assert readiness["missing_entry_requirement_ids"] == []
    assert readiness["authority"] == "workflow_readiness_not_fact_verification"
    assert "不表示商业模式成立" in readiness["basis_zh"]
    assert result["boundaries"]["agent_can_upgrade_fact"] is False


def test_all_coarse_roles_cannot_cover_concrete_requirements() -> None:
    roles = (
        "company_identity",
        "financial_core",
        "esg_impact",
        "technology_arl",
        "market_export",
        "policy_resource",
        "governance_legal",
        "generic_supporting",
    )
    hints = {
        "industry": ["氢能"],
        "stage": ["规模化"],
        "technology": ["电解槽"],
        "geography": ["中国", "美国"],
        "market": ["工业"],
        "need": ["并购"],
    }
    materials = [_artifact(f"all-{index}", *roles, profile_hints=hints) for index in range(20)]

    result = diagnose_acquisition_readiness(materials)

    assert result["completeness"]["ratio"] == 0
    assert result["completeness"]["percent"] == 0
    assert result["critical_gaps"]
    late_stage_ids = {
        "ioi_loi_and_exclusivity",
        "diligence_and_transaction_structure",
        "signing_approval_and_closing",
        "post_merger_integration",
    }
    late_stages = [
        stage for stage in result["stage_diagnostics"] if stage["id"] in late_stage_ids
    ]
    assert len(late_stages) == 4
    assert all(stage["completeness_ratio"] == 0 for stage in late_stages)
    assert all(
        stage["coverage_status"] != "candidate_coverage_complete"
        for stage in late_stages
    )


def test_versioned_requirement_candidates_can_cover_without_exceeding_one() -> None:
    requirement_ids = tuple(
        requirement["id"]
        for stage in acquisition_workflow_definition()["stages"]
        for requirement in stage["requirements"]
    )
    materials = [
        _artifact("explicit-candidates", requirement_ids=requirement_ids),
    ]

    result = diagnose_acquisition_readiness(materials)

    assert result["completeness"]["ratio"] == 1
    assert result["completeness"]["percent"] == 100
    assert result["completeness"]["earned_weight"] <= result["completeness"]["total_weight"]
    assert result["critical_gaps"] == []


def test_exact_duplicate_identity_is_deduplicated() -> None:
    item = _artifact("same-artifact", "company_identity")

    baseline = diagnose_acquisition_readiness([item])
    duplicate = diagnose_acquisition_readiness([item, copy.deepcopy(item)])

    assert duplicate["completeness"] == baseline["completeness"]
    assert duplicate["input_summary"]["accepted_artifact_count"] == 1
    assert duplicate["input_summary"]["duplicate_artifact_count"] == 1


def test_conflicting_duplicate_identity_fails_closed() -> None:
    materials = [
        _artifact("same-artifact", "company_identity"),
        _artifact("same-artifact", "financial_core"),
    ]

    with pytest.raises(ValueError, match="conflicting duplicate artifact identity"):
        diagnose_acquisition_readiness(materials)


@pytest.mark.parametrize(
    "recognition_status",
    ["awaiting_human", "not_applicable", "unknown", "", None],
)
def test_only_candidate_ready_recognition_can_contribute_coverage(
    recognition_status: str | None,
) -> None:
    material = _artifact(
        "unusable-recognition",
        "company_identity",
        recognition_status=recognition_status,  # type: ignore[arg-type]
    )

    result = diagnose_acquisition_readiness([material])

    assert result["completeness"]["ratio"] == 0
    assert result["input_summary"]["accepted_artifact_count"] == 0
    assert result["input_summary"]["ignored_artifact_count"] == 1


def test_missing_recognition_status_and_missing_identity_fail_closed() -> None:
    missing_status = _artifact("missing-status", "company_identity")
    missing_status["recognition"].pop("status")
    missing_identity = _artifact("placeholder", "financial_core")
    missing_identity.pop("id")

    result = diagnose_acquisition_readiness([missing_status, missing_identity])

    assert result["completeness"]["ratio"] == 0
    assert result["input_summary"]["accepted_artifact_count"] == 0
    assert result["input_summary"]["missing_identity_artifact_count"] == 1
    assert result["input_summary"]["ignored_recognition_statuses"] == [
        "<missing-or-null>"
    ]


def test_awaiting_human_and_unknown_roles_do_not_inflate_coverage() -> None:
    materials = [
        _artifact("not-ready", "company_identity", recognition_status="awaiting_human"),
        _artifact("unknown", "made_up_decision_role"),
        "malformed",
    ]

    result = diagnose_acquisition_readiness(materials)  # type: ignore[arg-type]

    assert result["completeness"]["ratio"] == 0
    assert result["input_summary"]["ignored_artifact_count"] == 2
    assert result["input_summary"]["ignored_candidate_roles"] == ["made_up_decision_role"]


def test_external_routing_profile_hints_do_not_inflate_material_coverage() -> None:
    materials = [_artifact("identity", "company_identity")]
    baseline = diagnose_acquisition_readiness(materials)
    routed = diagnose_acquisition_readiness(
        materials,
        profile_hints={
            "tags": {
                "industry": ["synthetic-industry"],
                "stage": ["synthetic-stage"],
                "technology": ["synthetic-technology"],
                "geography": ["synthetic-geography"],
                "market": ["synthetic-market"],
                "need": ["synthetic-need"],
            }
        },
    )

    assert routed["completeness"] == baseline["completeness"]
    assert routed["business_model_interview_readiness"] == (
        baseline["business_model_interview_readiness"]
    )
    assert routed["input_summary"]["profile_hints"]


def test_generic_supporting_material_never_covers_a_specific_requirement() -> None:
    result = diagnose_acquisition_readiness(
        [_artifact("unrelated-text", "generic_supporting")]
    )

    assert result["completeness"]["ratio"] == 0
    assert all(
        requirement["status"] == "missing"
        for stage in result["stage_diagnostics"]
        for requirement in stage["requirements"]
    )


def test_specific_nda_candidate_covers_only_nda_requirement() -> None:
    result = diagnose_acquisition_readiness(
        [
            _artifact(
                "nda-only",
                "governance_legal",
                requirement_ids=("nda_record",),
            )
        ]
    )
    statuses = {
        requirement["id"]: requirement["status"]
        for stage in result["stage_diagnostics"]
        for requirement in stage["requirements"]
    }

    assert statuses["nda_record"] == "candidate_covered"
    assert statuses["spa_and_disclosure"] != "candidate_covered"
    assert statuses["closing_checklist"] != "candidate_covered"
    assert statuses["hundred_day_plan"] != "candidate_covered"


def test_unversioned_requirement_candidates_fail_closed() -> None:
    material = _artifact("stale-candidate", "governance_legal")
    material["recognition"]["requirement_candidates"] = {
        "schema_version": REQUIREMENT_CANDIDATE_SCHEMA_VERSION,
        "rule_version": "acquisition-workflow-stale",
        "requirement_ids": ["nda_record"],
    }

    result = diagnose_acquisition_readiness([material])

    assert result["completeness"]["ratio"] == 0
    assert result["input_summary"][
        "ignored_requirement_candidate_contract_count"
    ] == 1


def test_config_rejects_more_than_eight_interview_questions() -> None:
    config = load_acquisition_workflow_config()
    config["interview"]["maximum_questions"] = 9

    with pytest.raises(ValueError, match="from 1 to 8"):
        diagnose_acquisition_readiness([], config=config)


def test_definition_is_defensively_copied() -> None:
    first = acquisition_workflow_definition()
    first["stages"][0]["name_zh"] = "mutated"

    second = acquisition_workflow_definition()

    assert second["stages"][0]["name_zh"] == "收购战略与委托确认"
