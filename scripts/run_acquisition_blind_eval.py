"""Run reproducible synthetic black-box checks against acquisition diagnostics.

The generated inputs are deliberately synthetic.  They exercise public contracts and
metamorphic invariants; they are not company facts and never assert a transaction,
investment, credit, or aggregate-risk conclusion.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from cleantech_finance.acquisition_workflow import (
    REQUIREMENT_CANDIDATE_SCHEMA_VERSION,
    RULE_VERSION,
    acquisition_workflow_definition,
    diagnose_acquisition_readiness,
)

SYNTHETIC_NOTICE = (
    "SYNTHETIC BLIND EVALUATION INPUT; no company, transaction, person, or source is real."
)
ROLES = (
    "company_identity",
    "financial_core",
    "esg_impact",
    "technology_arl",
    "market_export",
    "policy_resource",
    "governance_legal",
)
PROFILE_FIELDS = (
    "industry",
    "stage",
    "technology",
    "geography",
    "market",
    "need",
)
REQUIREMENT_IDS = tuple(
    requirement["id"]
    for stage in acquisition_workflow_definition()["stages"]
    for requirement in stage["requirements"]
)
INVALID_RECOGNITION_STATUSES: tuple[Any, ...] = (
    "awaiting_human",
    "not_applicable",
    "verified",
    "rejected",
    "",
    None,
    True,
    1,
)
EXPECTED_BOUNDARIES = {
    "agent_outputs_are_candidates": True,
    "agent_can_complete_decision_gate": False,
    "agent_can_upgrade_fact": False,
    "commercial_model_status_is_fact_determination": False,
    "investment_rating_produced": False,
    "credit_rating_produced": False,
    "aggregate_risk_score_produced": False,
    "regulatory_trigger_is_legal_conclusion": False,
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _artifact(
    artifact_id: str,
    roles: list[str],
    *,
    recognition_status: Any = "candidate_ready",
    artifact_status: Any = "ready",
    profile_hints: dict[str, list[str]] | None = None,
    requirement_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "sha256": hashlib.sha256(artifact_id.encode("utf-8")).hexdigest(),
        "kind": "uploaded_material",
        "status": artifact_status,
        "synthetic": True,
        "synthetic_notice": SYNTHETIC_NOTICE,
        "recognition": {
            "status": recognition_status,
            "candidate_roles": roles,
            "requirement_candidates": {
                "schema_version": REQUIREMENT_CANDIDATE_SCHEMA_VERSION,
                "rule_version": RULE_VERSION,
                "requirement_ids": list(requirement_ids or []),
            },
            "profile_hints": copy.deepcopy(profile_hints or {}),
            "authority": "routing_hint_only",
            "human_review_required": True,
        },
    }


def _coverage_view(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "completeness": result["completeness"],
        "interview_readiness": result["business_model_interview_readiness"],
        "requirements": [
            {
                "id": requirement["id"],
                "status": requirement["status"],
                "sources": requirement["source_artifact_ids"],
            }
            for stage in result["stage_diagnostics"]
            for requirement in stage["requirements"]
        ],
        "critical_gaps": [
            gap["requirement_id"] for gap in result["critical_gaps"]
        ],
        "supplements": [
            supplement["requirement_id"]
            for supplement in result["suggested_supplements"]
        ],
        "questions": [
            question["gap_requirement_id"]
            for question in result["interview_questions"]
        ],
        "gates": [
            stage["decision_gate"] for stage in result["stage_diagnostics"]
        ],
        "boundaries": result["boundaries"],
    }


def _random_profile(rng: random.Random, seed: int) -> dict[str, list[str]]:
    count = rng.randint(0, len(PROFILE_FIELDS))
    fields = rng.sample(list(PROFILE_FIELDS), count)
    return {field: [f"synthetic-{field}-{seed}"] for field in fields}


def _random_materials(rng: random.Random, seed: int) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for index in range(rng.randint(0, 8)):
        roles = rng.sample(list(ROLES), rng.randint(1, min(3, len(ROLES))))
        materials.append(
            _artifact(
                f"synthetic-{seed}-{index}",
                roles,
                profile_hints=_random_profile(rng, seed * 100 + index),
                requirement_ids=rng.sample(REQUIREMENT_IDS, rng.randint(1, 3)),
            )
        )
    return materials


def _global_failures(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    stages = result.get("stage_diagnostics") or []
    if [stage.get("order") for stage in stages] != list(range(1, 9)):
        failures.append("O01_eight_stage_order")
    if any(
        stage.get("decision_gate")
        != {
            "question_zh": stage.get("decision_gate", {}).get("question_zh"),
            "status": "human_pending",
            "authority": "human_only",
            "agent_may_decide": False,
        }
        for stage in stages
    ):
        failures.append("O02_human_only_decision_gates")
    if result.get("boundaries") != EXPECTED_BOUNDARIES:
        failures.append("O03_authority_boundaries")

    requirements = [
        requirement
        for stage in stages
        for requirement in stage.get("requirements", [])
    ]
    earned = sum(
        float(requirement["weight"])
        for requirement in requirements
        if requirement.get("status") == "candidate_covered"
    )
    total = sum(float(requirement["weight"]) for requirement in requirements)
    completeness = result.get("completeness") or {}
    expected_ratio = min(1.0, earned / total) if total else 0.0
    if abs(float(completeness.get("earned_weight", -1)) - earned) > 1e-6:
        failures.append("O04_earned_weight_recomputes")
    if abs(float(completeness.get("total_weight", -1)) - total) > 1e-6:
        failures.append("O05_total_weight_recomputes")
    if abs(float(completeness.get("ratio", -1)) - round(expected_ratio, 4)) > 1e-6:
        failures.append("O06_ratio_recomputes")
    if not 0 <= float(completeness.get("ratio", -1)) <= 1:
        failures.append("O07_ratio_bounded")

    missing_ids = {
        requirement["id"]
        for requirement in requirements
        if requirement.get("status") != "candidate_covered"
    }
    missing_critical_ids = {
        requirement["id"]
        for requirement in requirements
        if requirement.get("status") != "candidate_covered"
        and requirement.get("criticality") == "critical"
    }
    if {gap.get("requirement_id") for gap in result.get("critical_gaps", [])} != (
        missing_critical_ids
    ):
        failures.append("O08_critical_gaps_exact")
    if {
        supplement.get("requirement_id")
        for supplement in result.get("suggested_supplements", [])
    } != missing_ids:
        failures.append("O09_supplements_exact")
    if any(
        not requirement.get("source_artifact_ids")
        for requirement in requirements
        if requirement.get("status") == "candidate_covered"
    ):
        failures.append("O10_covered_requirements_have_sources")

    questions = result.get("interview_questions") or []
    if len(questions) > 8 or len({item.get("id") for item in questions}) != len(
        questions
    ):
        failures.append("O11_question_cap_and_identity")
    if any(
        question.get("gap_requirement_id") not in missing_ids
        for question in questions
    ):
        failures.append("O12_questions_reference_missing")
    return failures


def _run(materials: list[dict[str, Any]], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    return diagnose_acquisition_readiness(
        copy.deepcopy(materials),
        profile_hints=copy.deepcopy(profile),
    )


def _evaluate_seed(seed: int, repeats: int) -> tuple[dict[str, Any], int]:
    rng = random.Random(seed)
    materials = _random_materials(rng, seed)
    baseline_runs = [_run(materials) for _ in range(repeats)]
    api_calls = repeats
    failures = _global_failures(baseline_runs[0])
    if len({_digest(item) for item in baseline_runs}) != 1:
        failures.append("M01_same_process_determinism")
    baseline = baseline_runs[0]
    baseline_view = _coverage_view(baseline)

    shuffled = copy.deepcopy(materials)
    rng.shuffle(shuffled)
    if _coverage_view(_run(shuffled)) != baseline_view:
        failures.append("M02_input_order_invariance")
    api_calls += 1

    exact_duplicate = copy.deepcopy(materials)
    if materials:
        exact_duplicate.append(copy.deepcopy(materials[0]))
    if _coverage_view(_run(exact_duplicate)) != baseline_view:
        failures.append("M03_exact_duplicate_invariance")
    api_calls += 1

    external_profile = {
        "tags": {
            field: [f"synthetic-external-{field}-{seed}"]
            for field in PROFILE_FIELDS
        },
        "authority": "routing_hint_only",
        "synthetic": True,
    }
    if _coverage_view(_run(materials, profile=external_profile)) != baseline_view:
        failures.append("M04_external_profile_does_not_cover_materials")
    api_calls += 1

    generic = _artifact(f"synthetic-generic-{seed}", ["generic_supporting"])
    if _coverage_view(_run([*materials, generic])) != baseline_view:
        failures.append("M05_generic_supporting_invariance")
    api_calls += 1

    invalid = _artifact(
        f"synthetic-invalid-{seed}",
        [rng.choice(ROLES)],
        recognition_status=rng.choice(INVALID_RECOGNITION_STATUSES),
        profile_hints=_random_profile(rng, seed + 50_000),
    )
    if _coverage_view(_run([*materials, invalid])) != baseline_view:
        failures.append("M06_invalid_recognition_invariance")
    api_calls += 1

    not_ready = _artifact(
        f"synthetic-not-ready-{seed}",
        [rng.choice(ROLES)],
        artifact_status="not_applicable",
        profile_hints=_random_profile(rng, seed + 60_000),
    )
    if _coverage_view(_run([*materials, not_ready])) != baseline_view:
        failures.append("M07_non_ready_artifact_invariance")
    api_calls += 1

    unknown_role = _artifact(
        f"synthetic-unknown-role-{seed}",
        [f"synthetic-unknown-role-{seed}"],
    )
    if _coverage_view(_run([*materials, unknown_role])) != baseline_view:
        failures.append("M08_unknown_role_invariance")
    api_calls += 1

    uncovered_ids = [
        requirement["id"]
        for stage in baseline["stage_diagnostics"]
        for requirement in stage["requirements"]
        if requirement["status"] != "candidate_covered"
    ]
    addition = _artifact(
        f"synthetic-valid-addition-{seed}",
        [rng.choice(ROLES)],
        profile_hints=_random_profile(rng, seed + 70_000),
        requirement_ids=uncovered_ids[:1],
    )
    added = _run([*materials, addition])
    api_calls += 1
    if uncovered_ids and added["completeness"]["ratio"] <= baseline["completeness"]["ratio"]:
        failures.append("M09_valid_addition_monotonic")

    if materials:
        conflict = copy.deepcopy(materials[0])
        conflict["recognition"]["candidate_roles"] = [
            role
            for role in ROLES
            if role not in conflict["recognition"]["candidate_roles"]
        ][:1] or ["generic_supporting"]
        try:
            _run([*materials, conflict])
        except ValueError as exc:
            if "conflicting duplicate artifact identity" not in str(exc):
                failures.append("M10_conflicting_identity_error_contract")
        else:
            failures.append("M10_conflicting_identity_fails_closed")
        api_calls += 1

    return (
        {
            "synthetic": True,
            "seed": seed,
            "material_count": len(materials),
            "baseline_digest": _digest(baseline),
            "rule_version": baseline["rule_version"],
            "completeness_ratio": baseline["completeness"]["ratio"],
            "readiness": baseline["business_model_interview_readiness"]["status"],
            "failures": sorted(set(failures)),
        },
        api_calls,
    )


def evaluate(*, seed_start: int, seed_count: int, repeats: int) -> dict[str, Any]:
    if seed_count < 1 or repeats < 2:
        raise ValueError("seed_count must be positive and repeats must be at least 2")
    definition = acquisition_workflow_definition()
    records: list[dict[str, Any]] = []
    api_calls = 0
    for seed in range(seed_start, seed_start + seed_count):
        record, seed_calls = _evaluate_seed(seed, repeats)
        records.append(record)
        api_calls += seed_calls
    failed = [record for record in records if record["failures"]]
    return {
        "synthetic": True,
        "synthetic_notice": SYNTHETIC_NOTICE,
        "definition_digest": definition["definition_digest"],
        "seed_start": seed_start,
        "seed_count": seed_count,
        "repeats": repeats,
        "api_call_count": api_calls,
        "passed_seed_count": seed_count - len(failed),
        "failed_seed_count": len(failed),
        "passed": not failed,
        "failed_records": failed,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible synthetic acquisition-workflow blind checks."
    )
    parser.add_argument("--seed-start", type=int, default=30_001)
    parser.add_argument("--seed-count", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(
        seed_start=args.seed_start,
        seed_count=args.seed_count,
        repeats=args.repeats,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in report.items() if key != "records"}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
