from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from cleantech_finance.cli import main
from cleantech_finance.qa_diagnostics import (
    QA_CASE_SCHEMA_PATH,
    build_company_profile,
    new_qa_case,
    next_qa_question,
    next_qa_question_status,
    validate_qa_case,
)
from cleantech_finance.qa_loop import (
    _reject_company_specific_qa_rules,
    preflight_qa_registry,
    run_qa_registry,
    selection_digest,
    selection_material_report,
)
from cleantech_finance.qa_reporting import write_qa_artifacts

ROOT = Path(__file__).parents[1]


def test_qa_case_schema_is_packaged_and_matches_operator_copy() -> None:
    assert json.loads(QA_CASE_SCHEMA_PATH.read_text(encoding="utf-8")) == json.loads(
        (ROOT / "schemas" / "qa-case.schema.json").read_text(encoding="utf-8")
    )


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_documented_qa_loop_script_can_be_invoked_directly() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_qa_loop.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--selection-digest-only" in result.stdout


def _entity(case: dict[str, object]) -> dict[str, str]:
    company = case["company"]
    stable_identifier = company["stable_identifier"]
    return {
        "scheme": stable_identifier["scheme"],
        "value": stable_identifier["value"],
        "legal_name": company["legal_name"],
    }


def _set_profile_only_waiver(case: dict[str, object]) -> None:
    source = case["sources"][0]
    case["financial_evidence"] = {
        "annual_report_status": "not_available",
        "manifest": None,
        "ground_truth": None,
        "card_ground_truth": None,
        "review": None,
        "profile_only_waiver": {
            "approval_id": "contract-fixture-waiver",
            "status": "approved",
            "actor_type": "human",
            "scope": "profile_only_annual_report_waiver",
            "approved_by": "contract-test-author",
            "approved_at": "2026-07-18T09:30:00+08:00",
            "entity": _entity(case),
            "reason_code": "annual_report_not_available_to_run",
            "rationale": "This non-delivery contract fixture has no annual-report input.",
            "basis_evidence_refs": [
                {
                    "source_id": source["id"],
                    "quote": source["excerpt"],
                }
            ],
        },
    }


def _subject_source_hashes(manifest_path: Path) -> list[dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return sorted(
        [
            {
                "source_id": source["id"],
                "sha256": _file_sha256((manifest_path.parent / source["path"]).resolve()),
            }
            for source in manifest["sources"]
            if source.get("role", "subject") == "subject"
        ],
        key=lambda item: item["source_id"],
    )


def _all_source_hashes(manifest_path: Path) -> list[dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return sorted(
        [
            {
                "source_id": source["id"],
                "role": source.get("role", "subject"),
                "sha256": _file_sha256((manifest_path.parent / source["path"]).resolve()),
            }
            for source in manifest["sources"]
        ],
        key=lambda item: (item["source_id"], item["role"]),
    )


def _set_financial_contract(
    case: dict[str, object],
    manifest_path: Path,
    ground_path: Path,
    card_ground_path: Path,
) -> None:
    case["financial_evidence"] = {
        "annual_report_status": "available",
        "manifest": str(manifest_path.resolve()),
        "ground_truth": str(ground_path.resolve()),
        "card_ground_truth": str(card_ground_path.resolve()),
        "review": {
            "approval_id": "contract-fixture-finance-review",
            "status": "approved",
            "actor_type": "human",
            "scope": "financial_ground_truth_and_entity_binding",
            "reviewed_by": "contract-test-author",
            "reviewed_at": "2026-07-18T09:30:00+08:00",
            "entity": _entity(case),
            "manifest_sha256": _file_sha256(manifest_path),
            "ground_truth_sha256": _file_sha256(ground_path),
            "card_ground_truth_sha256": _file_sha256(card_ground_path),
            "subject_sources": _subject_source_hashes(manifest_path),
            "all_sources": _all_source_hashes(manifest_path),
        },
        "profile_only_waiver": None,
    }


def _configure_local_sungrow_financial_case(
    registry_path: Path,
    tmp_path: Path,
) -> dict[str, Path]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    row = registry["cases"][0]
    case_path = tmp_path / row["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["company"]["legal_name"] = "Sungrow Power Supply Co., Ltd."
    case["company"]["stable_identifier"] = {
        "scheme": "ticker",
        "value": "300274.SZ",
    }
    _bind_case_entities(case)

    original_manifest_path = Path.cwd() / "examples/sungrow/manifest.auto.json"
    manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    subject_source_path: Path | None = None
    for index, source in enumerate(manifest["sources"]):
        original_source = (original_manifest_path.parent / source["path"]).resolve()
        if source.get("role", "subject") == "subject" and subject_source_path is None:
            subject_source_path = tmp_path / f"subject-source-{index}{original_source.suffix}"
            shutil.copyfile(original_source, subject_source_path)
            source["path"] = str(subject_source_path)
        else:
            source["path"] = str(original_source)
    assert subject_source_path is not None
    manifest_path = tmp_path / "financial-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    ground_path = tmp_path / "financial-ground-truth.json"
    card_ground_path = tmp_path / "card-ground-truth.json"
    shutil.copyfile(Path.cwd() / "evals/sungrow-2025.json", ground_path)
    shutil.copyfile(Path.cwd() / "evals/sungrow-cards-v0.2.json", card_ground_path)
    _set_financial_contract(case, manifest_path, ground_path, card_ground_path)
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    row["company"] = case["company"]["legal_name"]
    row["entity_scheme"] = "ticker"
    row["entity_id"] = "300274.SZ"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return {
        "case": case_path,
        "manifest": manifest_path,
        "ground_truth": ground_path,
        "card_ground_truth": card_ground_path,
        "subject_source": subject_source_path,
    }


def _answer(
    answer_id: str, question_id: str, statement: str, response: dict[str, object]
) -> dict[str, object]:
    return {
        "id": answer_id,
        "question_id": question_id,
        "statement": statement,
        "response": response,
        "response_assertions": [
            {"field": field, "value": value, "quote": statement}
            for field, value in response.items()
        ],
        "respondent_entity": {
            "scheme": "provided_case_id",
            "value": "human-selected-001",
            "legal_name": "Human Selected CleanTech Co., Ltd.",
        },
        "answered_at": "2026-07-18T09:00:00+08:00",
        "answer_origin": "company_statement",
    }


def _bind_answer_response(answer: dict[str, object]) -> None:
    answer["response_assertions"] = [
        {"field": field, "value": value, "quote": answer["statement"]}
        for field, value in answer["response"].items()
    ]


def _bind_case_entities(case: dict[str, object]) -> None:
    entity = _entity(case)
    for source in case["sources"]:
        source.pop("subject_entity_id", None)
        source["subject_entity"] = entity.copy()
    for answer in case["qa_session"]["answers"]:
        answer["respondent_entity"] = entity.copy()


def _bind_profile_answer_assertions(case: dict[str, object]) -> None:
    answers = {item["id"]: item for item in case["qa_session"]["answers"]}
    for candidate in case["profile_candidates"]:
        for ref in candidate["evidence_refs"]:
            answer = answers.get(ref["source_id"])
            if answer is None:
                continue
            assertion = next(
                item
                for item in answer["response_assertions"]
                if item["field"] == candidate["field"]
            )
            assertion["quote"] = ref["quote"]


def _complete_case() -> dict[str, object]:
    case = new_qa_case()
    case["case"]["id"] = "human-selected-demo"
    case["company"] = {
        "legal_name": "Human Selected CleanTech Co., Ltd.",
        "display_name": "Human Selected CleanTech",
        "display_name_zh": "人工指定清洁技术企业",
        "stable_identifier": {"scheme": "provided_case_id", "value": "human-selected-001"},
    }
    case["sources"] = [
        {
            "id": "public-product-page",
            "kind": "public_source",
            "title": "Company product page",
            "excerpt": "The company supplies modular industrial heat-pump systems for food factories.",
            "locator": "Product overview, paragraph 1",
            "captured_at": "2026-07-18",
            "url_or_source_id": "https://example.invalid/product",
            "subject_entity": {
                "scheme": "provided_case_id",
                "value": "human-selected-001",
                "legal_name": "Human Selected CleanTech Co., Ltd.",
            },
            "sha256": None,
            "selection_origin": "human_supplied",
            "field_assertions": [
                {
                    "field": "subindustry",
                    "value": "industrial-heat-pump-systems",
                    "quote": "modular industrial heat-pump systems for food factories",
                }
            ],
        }
    ]
    case["qa_session"]["answers"] = [
        _answer(
            "answer-product",
            "product-core",
            "我们向食品工厂销售模块化工业热泵系统，替代部分燃气蒸汽供热。",
            {
                "product_technology": "模块化工业热泵系统",
                "customer_problem": "食品工厂燃气蒸汽供热成本与排放",
                "subindustry": "industrial-heat-pump-systems",
            },
        ),
        _answer(
            "answer-market",
            "market-core",
            "德国食品加工客户是首个目标市场，依据是客户访谈和当地工业脱碳需求。",
            {
                "target_markets": ["DE"],
                "customer_segments": ["food-processing"],
                "market_basis": "客户访谈和当地工业脱碳需求",
            },
        ),
        _answer(
            "answer-stage",
            "export-stage",
            "企业已向德国客户完成一笔付费样机交付，目前属于早期商业化。",
            {"export_stage": "early_commercial"},
        ),
        _answer(
            "answer-commercial",
            "commercial-proof",
            "已有付费样机合同和收款记录，但尚未形成复购，重复性仍需验证。",
            {
                "customer_evidence": "付费样机合同和收款记录",
                "repeatability_evidence": "尚无复购，待验证",
            },
        ),
        _answer(
            "answer-gap",
            "gap-core",
            "最大缺口是德国市场所需产品认证，当前尚无完整测试报告。",
            {
                "core_gaps": [
                    {
                        "category": "certification",
                        "description": "缺少德国市场产品认证和完整测试报告",
                    }
                ]
            },
        ),
        _answer(
            "answer-resource",
            "resource-core",
            "需要认证专家和测试实验室资源，以便在十二个月内完成首轮认证。",
            {
                "resource_needs": [
                    {
                        "category": "certification_expert",
                        "description": "认证专家和测试实验室",
                    }
                ],
                "expected_milestone": "十二个月内完成首轮认证",
            },
        ),
    ]
    case["profile_candidates"] = [
        {
            "field": "product_technology",
            "value": "模块化工业热泵系统",
            "conclusion_type": "source_statement",
            "evidence_refs": [
                {
                    "source_id": "answer-product",
                    "quote": "我们向食品工厂销售模块化工业热泵系统",
                }
            ],
        },
        {
            "field": "subindustry",
            "value": "industrial-heat-pump-systems",
            "conclusion_type": "inference",
            "rationale": "Normalized from the stated product and customer use case.",
            "evidence_refs": [
                {
                    "source_id": "public-product-page",
                    "quote": "modular industrial heat-pump systems for food factories",
                }
            ],
        },
        {
            "field": "target_markets",
            "value": ["DE"],
            "conclusion_type": "source_statement",
            "evidence_refs": [
                {
                    "source_id": "answer-market",
                    "quote": "德国食品加工客户是首个目标市场",
                }
            ],
        },
        {
            "field": "export_stage",
            "value": "early_commercial",
            "conclusion_type": "inference",
            "rationale": "Mapped from the completed paid delivery, not the company's aspiration.",
            "evidence_refs": [
                {
                    "source_id": "answer-stage",
                    "quote": "已向德国客户完成一笔付费样机交付",
                }
            ],
        },
        {
            "field": "core_gaps",
            "value": [
                {
                    "category": "certification",
                    "description": "缺少德国市场产品认证和完整测试报告",
                }
            ],
            "conclusion_type": "source_statement",
            "evidence_refs": [
                {
                    "source_id": "answer-gap",
                    "quote": "最大缺口是德国市场所需产品认证",
                }
            ],
        },
        {
            "field": "resource_needs",
            "value": [
                {
                    "category": "certification_expert",
                    "description": "认证专家和测试实验室",
                }
            ],
            "conclusion_type": "source_statement",
            "evidence_refs": [
                {
                    "source_id": "answer-resource",
                    "quote": "需要认证专家和测试实验室资源",
                }
            ],
        },
    ]
    _bind_profile_answer_assertions(case)
    _bind_case_entities(case)
    _set_profile_only_waiver(case)
    return case


def _five_case_registry(tmp_path: Path) -> Path:
    rows = []
    for iteration in range(1, 6):
        case = _complete_case()
        case_id = f"human-case-{iteration}"
        case["case"]["id"] = case_id
        case["company"]["legal_name"] = f"Human Selected CleanTech {iteration} Co., Ltd."
        case["company"]["stable_identifier"]["value"] = f"human-selected-{iteration:03d}"
        _bind_case_entities(case)
        _set_profile_only_waiver(case)
        case_path = tmp_path / f"{case_id}.json"
        case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        rows.append(
            {
                "iteration": iteration,
                "id": case_id,
                "entity_scheme": case["company"]["stable_identifier"]["scheme"],
                "entity_id": case["company"]["stable_identifier"]["value"],
                "company": case["company"]["legal_name"],
                "input": case_path.name,
                "input_sha256": None,
                "profile_ground_truth": None,
                "profile_ground_truth_sha256": None,
                "selection_origin": "human_supplied",
            }
        )
    registry = {
        "schema_version": "1.0.0",
        "run_mode": "contract_test",
        "selection_policy": "human_supplied_only",
        "selection_attestation": None,
        "cases": rows,
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return path


def _write_profile_ground_truth(case: dict[str, object], path: Path) -> None:
    validation = validate_qa_case(case)
    assert validation["passed"]
    payload = {
        "schema_version": "1.0.0",
        "case_id": case["case"]["id"],
        "entity": _entity(case),
        "review": {
            "actor_type": "human",
            "reviewed_by": "synthetic-negative-test-reviewer",
            "reviewed_at": "2026-07-18T10:00:00+08:00",
            "scope": "field_value_quote_and_entity_binding",
        },
        "fields": [
            {
                "field": field["id"],
                "accepted": True,
                "value": field["value"],
                "conclusion_type": field["conclusion_type"],
                "evidence_refs": [
                    {"source_id": ref["source_id"], "quote": ref["quote"]}
                    for ref in field["evidence_refs"]
                ],
            }
            for field in validation["profile"]["fields"]
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _delivery_registry_for_negative_test(
    tmp_path: Path,
    *,
    include_financial_case: bool = True,
) -> Path:
    registry_path = _five_case_registry(tmp_path)
    if include_financial_case:
        _configure_local_sungrow_financial_case(registry_path, tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["run_mode"] = "qa_delivery"
    for row in registry["cases"]:
        case_path = tmp_path / row["input"]
        case = json.loads(case_path.read_text(encoding="utf-8"))
        review_path = tmp_path / f"{row['id']}-profile-ground-truth.json"
        _write_profile_ground_truth(case, review_path)
        row["input_sha256"] = _file_sha256(case_path)
        row["profile_ground_truth"] = review_path.name
        row["profile_ground_truth_sha256"] = _file_sha256(review_path)
    registry["selection_attestation"] = {
        "actor_type": "human",
        "confirmed_by": "synthetic-negative-test-selector",
        "confirmed_at": "2026-07-18T10:10:00+08:00",
        "selection_batch_id": "synthetic-negative-test-batch",
        "case_set_sha256": "0" * 64,
        "statement": (
            "I selected these five companies and supplied their case inputs; "
            "the Evidence Agent did not discover or choose them."
        ),
    }
    registry["selection_attestation"]["case_set_sha256"] = selection_digest(
        registry,
        registry_path,
    )
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_path


def test_selection_material_report_bootstraps_all_ten_hashes_without_attesting(
    tmp_path: Path,
) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["selection_attestation"] = None
    for row in registry["cases"]:
        row["input_sha256"] = None
        row["profile_ground_truth_sha256"] = None
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    first = selection_material_report(
        registry,
        registry_path,
        project_root=ROOT,
    )

    assert not first["ready_for_human_attestation"]
    assert first["creates_human_attestation"] is False
    assert first["case_set_sha256"]
    assert len(first["cases"]) == 5
    assert all(item["input_sha256"] for item in first["cases"])
    assert all(item["profile_ground_truth_sha256"] for item in first["cases"])
    assert first["unconfirmed_attestation_template"]["confirmed_at"].startswith(
        "REPLACE_"
    )
    update_codes = [
        item["code"]
        for item in first["issues"]
        if item["code"].endswith("hash_update_required")
    ]
    assert len(update_codes) == 10

    actual_by_id = {item["id"]: item for item in first["cases"]}
    for row in registry["cases"]:
        actual = actual_by_id[row["id"]]
        row["input_sha256"] = actual["input_sha256"]
        row["profile_ground_truth_sha256"] = actual[
            "profile_ground_truth_sha256"
        ]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    second = selection_material_report(
        registry,
        registry_path,
        project_root=ROOT,
    )

    assert second["ready_for_human_attestation"]
    assert second["issues"] == []
    assert second["case_set_sha256"] == selection_digest(registry, registry_path)


def test_delivery_preflight_uses_disposable_storage_only(tmp_path: Path) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    intended_output = tmp_path / "formal-output-not-created"

    result = preflight_qa_registry(
        registry_path,
        project_root=ROOT,
        intended_output_dir=intended_output,
    )

    assert result["passed"]
    assert result["mode"] == "qa_delivery_preflight"
    assert result["completed_execution_count"] == 5
    assert result["human_attestation_assurance"] == {
        "status": "unsigned_claim_only",
        "cryptographic_identity_verified": False,
        "meaning": (
            "Hashes bind the declared selection material but do not verify the "
            "identity of a claimed human reviewer."
        ),
    }
    assert result["formal_output_created"] is False
    assert result["formal_history_created"] is False
    assert result["temporary_artifacts_retained"] is False
    assert not intended_output.exists()


def test_dynamic_question_router_follows_previous_answer() -> None:
    case = new_qa_case()
    assert next_qa_question(case)["id"] == "product-core"

    case["qa_session"]["answers"] = [
        _answer(
            "answer-product",
            "product-core",
            "我们销售工业热泵。",
            {"product_technology": "工业热泵"},
        )
    ]
    follow_up = next_qa_question(case)
    assert follow_up["id"] == "product-clarification"
    assert follow_up["missing_fields"] == ["customer_problem", "subindustry"]


def test_dynamic_router_allows_repeated_clarification_until_complete() -> None:
    case = _complete_case()
    original_answers = case["qa_session"]["answers"]
    case["qa_session"]["answers"] = [
        _answer(
            "answer-product",
            "product-core",
            "我们向食品工厂销售模块化工业热泵系统。",
            {"product_technology": "模块化工业热泵系统"},
        ),
        _answer(
            "answer-product-clarify-1",
            "product-clarification",
            "客户问题是食品工厂燃气蒸汽供热成本与排放。",
            {"customer_problem": "食品工厂燃气蒸汽供热成本与排放"},
        ),
        _answer(
            "answer-product-clarify-2",
            "product-clarification",
            "最准确的子行业是 industrial-heat-pump-systems。",
            {"subindustry": "industrial-heat-pump-systems"},
        ),
        *original_answers[1:],
    ]
    _bind_case_entities(case)
    _bind_profile_answer_assertions(case)

    result = validate_qa_case(case)

    assert result["passed"]
    assert result["qa"]["next_question"] is None
    assert "duplicate_question_answer" not in {
        item["code"] for item in result["errors"]
    }


@pytest.mark.parametrize(
    ("stage", "expected_question"),
    [
        ("exploring", "early-stage-proof"),
        ("pilot", "pilot-proof"),
        ("early_commercial", "commercial-proof"),
    ],
)
def test_export_stage_selects_dynamic_branch(
    stage: str,
    expected_question: str,
) -> None:
    case = _complete_case()
    case["qa_session"]["answers"] = case["qa_session"]["answers"][:3]
    case["qa_session"]["answers"][2]["response"]["export_stage"] = stage
    _bind_answer_response(case["qa_session"]["answers"][2])
    question = next_qa_question(case)
    assert question["id"] == expected_question
    assert question["reason_code"] == f"export_stage_branch_{stage}"


def test_complete_profile_requires_exact_traceable_quotes() -> None:
    case = _complete_case()
    result = validate_qa_case(case)
    assert result["passed"]
    assert result["qa"]["next_question"] is None
    assert all(field["status"] == "supported" for field in result["profile"]["fields"])
    assert all(field["evidence_refs"] for field in result["profile"]["fields"])
    selected = {route["line"] for route in result["triage"]["routes"] if route["selected"]}
    assert selected == {"expert", "map", "radar"}
    selected_reasons = [
        reason
        for route in result["triage"]["routes"]
        if route["selected"]
        for reason in route["reasons"]
    ]
    assert all(reason["evidence_refs"] for reason in selected_reasons)
    assert "score" not in result["profile"]
    assert "confidence" not in result["profile"]
    assert result["profile"]["guardrails"]["company_statement_is_not_verified_fact"] is True


def test_untraceable_profile_value_fails_closed_into_gap_queue() -> None:
    case = _complete_case()
    case["profile_candidates"][0]["evidence_refs"][0]["quote"] = "这句话不在原始回答中"
    profile = build_company_profile(case)
    assert not profile["passed"]
    field = next(item for item in profile["fields"] if item["id"] == "product_technology")
    assert field["status"] == "gap"
    assert field["value"] is None
    assert field["candidate_value"] == "模块化工业热泵系统"
    assert "profile_quote_mismatch" in {item["code"] for item in field["errors"]}
    assert "product_technology" in {item["field"] for item in profile["gap_queue"]}


def test_inference_needs_rationale_even_with_a_source() -> None:
    case = _complete_case()
    case["profile_candidates"][1]["rationale"] = ""
    result = validate_qa_case(case)
    assert not result["passed"]
    assert "inference_rationale_missing" in {item["code"] for item in result["errors"]}


def test_dynamic_qa_replay_rejects_reversed_and_unknown_answers() -> None:
    reversed_case = _complete_case()
    reversed_case["qa_session"]["answers"].reverse()
    assert next_qa_question(reversed_case)["id"] == "product-core"
    reversed_result = validate_qa_case(reversed_case)
    assert not reversed_result["passed"]
    assert not reversed_result["qa"]["complete"]
    assert "qa_answer_out_of_order" in {item["code"] for item in reversed_result["errors"]}
    assert reversed_result["triage"]["eligible"] is False
    assert reversed_result["triage"]["upstream_validation"]["passed"] is False
    assert not any(route["selected"] for route in reversed_result["triage"]["routes"])

    unknown_case = _complete_case()
    unknown_case["qa_session"]["answers"].insert(
        1,
        _answer(
            "answer-agent-invented",
            "agent-invented-question",
            "This question was never issued by the router.",
            {"product_technology": "unsupported"},
        ),
    )
    unknown_result = validate_qa_case(unknown_case)
    assert next_qa_question(unknown_case)["id"] == "market-core"
    assert not unknown_result["passed"]
    assert "unknown_qa_question" in {item["code"] for item in unknown_result["errors"]}


def test_next_question_status_fails_closed_on_replay_errors() -> None:
    case = _complete_case()
    case["qa_session"]["answers"][0]["response_assertions"] = []

    status = next_qa_question_status(case)

    assert status["status"] == "blocked_by_replay_errors"
    assert status["complete"] is False
    assert status["next_question"] is None
    assert "answer_response_assertion_count" in {
        item["code"] for item in status["errors"]
    }
    assert next_qa_question(case)["id"] == "product-core"


def test_dynamic_qa_rejects_unbound_or_non_text_evidence_and_reversed_timestamps() -> None:
    unbound_case = _complete_case()
    commercial = next(
        item
        for item in unbound_case["qa_session"]["answers"]
        if item["question_id"] == "commercial-proof"
    )
    commercial["statement"] = "unrelated statement"
    commercial["response"] = {
        "customer_evidence": "fabricated",
        "repeatability_evidence": "fabricated",
    }
    unbound_result = validate_qa_case(unbound_case)
    assert not unbound_result["passed"]
    assert "answer_response_assertion_value_mismatch" in {
        item["code"] for item in unbound_result["errors"]
    }
    assert not any(route["selected"] for route in unbound_result["triage"]["routes"])

    typed_case = _complete_case()
    commercial = next(
        item
        for item in typed_case["qa_session"]["answers"]
        if item["question_id"] == "commercial-proof"
    )
    commercial["statement"] = "customer evidence and repeatability are not supplied"
    commercial["response"] = {"customer_evidence": True, "repeatability_evidence": 1}
    _bind_answer_response(commercial)
    typed_result = validate_qa_case(typed_case)
    assert not typed_result["passed"]
    assert typed_result["qa"]["next_question"]["id"] == "commercial-proof-clarification"
    assert typed_result["triage"]["eligible"] is False

    timestamp_case = _complete_case()
    timestamp_case["qa_session"]["answers"][1]["answered_at"] = "2026-07-18T08:59:00+08:00"
    timestamp_result = validate_qa_case(timestamp_case)
    assert not timestamp_result["passed"]
    assert "answer_timestamp_out_of_order" in {item["code"] for item in timestamp_result["errors"]}


def test_profile_values_must_bind_to_answer_or_source_assertion() -> None:
    answer_case = _complete_case()
    answer_case["profile_candidates"][0]["value"] = "perpetual-motion reactor"
    answer_result = validate_qa_case(answer_case)
    assert not answer_result["passed"]
    assert "profile_answer_value_mismatch" in {item["code"] for item in answer_result["errors"]}

    source_case = _complete_case()
    source_case["profile_candidates"][1]["value"] = "banana-farming"
    source_result = validate_qa_case(source_case)
    assert not source_result["passed"]
    assert "profile_source_assertion_mismatch" in {item["code"] for item in source_result["errors"]}


def test_profile_answer_quote_must_match_its_response_assertion() -> None:
    case = _complete_case()
    product_answer = next(
        item for item in case["qa_session"]["answers"] if item["id"] == "answer-product"
    )
    product_assertion = next(
        item
        for item in product_answer["response_assertions"]
        if item["field"] == "product_technology"
    )
    product_assertion["quote"] = product_answer["statement"]
    result = validate_qa_case(case)
    assert not result["passed"]
    product = next(
        item for item in result["profile"]["fields"] if item["id"] == "product_technology"
    )
    assert product["status"] == "gap"
    assert "profile_answer_assertion_mismatch" in {item["code"] for item in product["errors"]}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("placeholder_scheme", "stable_identifier_missing"),
        ("invalid_http_url", "source_url_invalid"),
        ("invalid_sha256", "source_sha256_invalid"),
    ],
)
def test_identity_and_source_metadata_fail_closed(
    mutation: str,
    expected_code: str,
) -> None:
    case = _complete_case()
    if mutation == "placeholder_scheme":
        case["company"]["stable_identifier"]["scheme"] = "replace"
        _bind_case_entities(case)
        _set_profile_only_waiver(case)
    elif mutation == "invalid_http_url":
        case["sources"][0]["url_or_source_id"] = "https://"
    else:
        case["sources"][0]["sha256"] = "not-a-sha256"
    result = validate_qa_case(case)
    assert not result["passed"]
    assert expected_code in {item["code"] for item in result["errors"]}
    if mutation != "placeholder_scheme":
        subindustry = next(
            item for item in result["profile"]["fields"] if item["id"] == "subindustry"
        )
        assert subindustry["status"] == "gap"


@pytest.mark.parametrize(
    "url",
    ["https://[::1", "https://exa mple.com", "https://example.com:99999"],
)
def test_malformed_http_urls_return_structured_gaps(url: str) -> None:
    case = _complete_case()
    case["sources"][0]["url_or_source_id"] = url
    result = validate_qa_case(case)
    assert not result["passed"]
    assert "source_url_invalid" in {item["code"] for item in result["errors"]}
    subindustry = next(item for item in result["profile"]["fields"] if item["id"] == "subindustry")
    assert subindustry["status"] == "gap"


@pytest.mark.parametrize(
    ("candidate_index", "invalid_value"),
    [(4, [{}]), (4, [{"foo": "bar"}]), (5, [""])],
)
def test_gap_and_resource_candidates_reject_empty_items(
    candidate_index: int,
    invalid_value: list[object],
) -> None:
    case = _complete_case()
    case["profile_candidates"][candidate_index]["value"] = invalid_value
    result = validate_qa_case(case)
    assert not result["passed"]
    assert "invalid_profile_value" in {item["code"] for item in result["errors"]}


def test_source_contract_binds_complete_source_to_case_entity() -> None:
    mismatch_case = _complete_case()
    mismatch_case["sources"][0]["subject_entity"] = {
        "scheme": "provided_case_id",
        "value": "different-company",
        "legal_name": "Different Company Co., Ltd.",
    }
    mismatch_result = validate_qa_case(mismatch_case)
    assert not mismatch_result["passed"]
    assert "source_subject_mismatch" in {item["code"] for item in mismatch_result["errors"]}
    subindustry = next(
        item for item in mismatch_result["profile"]["fields"] if item["id"] == "subindustry"
    )
    assert subindustry["status"] == "gap"
    assert "invalid_profile_source" in {item["code"] for item in subindustry["errors"]}

    answer_case = _complete_case()
    answer_case["qa_session"]["answers"][0]["respondent_entity"]["scheme"] = "lei"
    answer_result = validate_qa_case(answer_case)
    assert not answer_result["passed"]
    assert "answer_subject_mismatch" in {item["code"] for item in answer_result["errors"]}
    product = next(
        item for item in answer_result["profile"]["fields"] if item["id"] == "product_technology"
    )
    assert product["status"] == "gap"

    incomplete_case = _complete_case()
    incomplete_case["sources"][0].pop("title")
    incomplete_result = validate_qa_case(incomplete_case)
    assert not incomplete_result["passed"]
    codes = {item["code"] for item in incomplete_result["errors"]}
    assert "qa_schema_validation" in codes
    assert "source_title_missing" in codes


def test_standalone_qa_rejects_non_human_company_and_sources() -> None:
    case = _complete_case()
    case["case"]["selection_origin"] = "agent_selected"
    case["sources"][0]["selection_origin"] = "agent_selected"
    result = validate_qa_case(case)
    assert not result["passed"]
    codes = {item["code"] for item in result["errors"]}
    assert "company_not_human_selected" in codes
    assert "source_not_human_supplied" in codes
    assert result["triage"]["eligible"] is False
    assert not any(route["selected"] for route in result["triage"]["routes"])


def test_qa_schema_validates_complete_case() -> None:
    schema = json.loads(Path("schemas/qa-case.schema.json").read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(_complete_case())
    )
    assert errors == []


def test_report_packet_exposes_profile_triage_and_gaps(tmp_path: Path) -> None:
    paths = write_qa_artifacts(_complete_case(), tmp_path / "qa-output")
    assert set(paths) == {
        "case_json",
        "validation_json",
        "profile_json",
        "triage_json",
        "gap_queue_json",
        "next_question_json",
        "report_markdown",
        "report_html",
    }
    report = Path(paths["report_html"]).read_text(encoding="utf-8")
    assert "画像卡 / Profile card" in report
    assert "Stub only" in report
    assert "Evidence / 出处" in report
    assert "answer-product @ qa_session.answers[answer-product]" in report
    assert 'href="https://example.invalid/product"' in report
    markdown = Path(paths["report_markdown"]).read_text(encoding="utf-8")
    assert "https://example.invalid/product" in markdown
    assert "不构成投资" in report
    assert "fetch(" not in report
    assert "cdn" not in report.lower()
    validation = json.loads(Path(paths["validation_json"]).read_text(encoding="utf-8"))
    assert validation["passed"]


def test_cli_exposes_next_question_and_validation(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "qa-case.json"
    path.write_text(
        json.dumps(_complete_case(), ensure_ascii=False),
        encoding="utf-8",
    )
    assert main(["qa", "next", str(path)]) == 0
    next_payload = json.loads(capsys.readouterr().out)
    assert next_payload == {"complete": True, "next_question": None}
    assert main(["qa", "validate", str(path)]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["passed"]


def test_cli_next_returns_structured_replay_errors(
    tmp_path: Path,
    capsys: object,
) -> None:
    case = _complete_case()
    case["qa_session"]["answers"][0]["response_assertions"] = []
    path = tmp_path / "qa-case-with-replay-error.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    assert main(["qa", "next", str(path)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "blocked_by_replay_errors"
    assert payload["complete"] is False
    assert payload["next_question"] is None
    assert "answer_response_assertion_count" in {
        item["code"] for item in payload["errors"]
    }


def test_contract_fixture_exercises_five_cases_but_never_counts_as_delivery(
    tmp_path: Path,
) -> None:
    registry = _five_case_registry(tmp_path)
    result = run_qa_registry(
        registry,
        tmp_path / "output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not result["passed"]
    assert result["execution_passed"]
    assert not result["delivery_eligible"]
    assert result["deliverable_status"] == "contract_fixture_only"
    assert result["human_attestation_assurance"]["status"] == (
        "not_applicable_contract_fixture"
    )
    assert not result["human_attestation_assurance"][
        "cryptographic_identity_verified"
    ]
    assert result["completed_execution_count"] == 5
    assert result["completed_case_count"] == 0
    assert all(item["selection_origin"] == "human_supplied" for item in result["cases"])
    assert all(item["execution_passed"] and not item["passed"] for item in result["cases"])
    assert all(
        item["profile_review"]["contract_check_passed"] and not item["profile_review"]["passed"]
        for item in result["cases"]
    )
    assert all(item["financial"]["status"] == "profile_only_waived" for item in result["cases"])
    assert all(
        item["financial"]["contract_check_passed"] and not item["financial"]["passed"]
        for item in result["cases"]
    )
    assert all(not any(route["selected"] for route in item["triage"]) for item in result["cases"])
    assert not any((tmp_path / "output").rglob("financial"))
    assert result["financial_summary"]["audited_case_count"] == 0
    assert result["financial_summary"]["contract_checks_passed"]
    assert not result["financial_summary"]["passed"]
    report = Path(result["artifacts"]["report_markdown"]).read_text(encoding="utf-8")
    assert "五家公司自迭代报告" in report
    assert "不构成投资" in report
    assert "answer-product @ qa_session.answers[answer-product]" in report
    assert "contract_fixture_only" in report
    assert "https://example.invalid/product" in report
    html_report = Path(result["artifacts"]["report_html"]).read_text(encoding="utf-8")
    assert 'href="https://example.invalid/product"' in html_report
    assert 'id="responsive-safety"' in html_report
    assert "overflow-wrap:anywhere" in html_report


def test_synthetic_delivery_contract_reaches_all_gates_but_is_not_real_evidence(
    tmp_path: Path,
) -> None:
    """Prove the delivery code path only; this is not the user's five-company evidence."""
    registry = _delivery_registry_for_negative_test(tmp_path)
    result = run_qa_registry(
        registry,
        tmp_path / "synthetic-delivery-output",
        project_root=Path.cwd(),
    )
    assert result["passed"]
    assert result["execution_passed"]
    assert result["completed_execution_count"] == 5
    assert result["completed_case_count"] == 5
    assert result["human_attestation_assurance"]["status"] == (
        "unsigned_claim_only"
    )
    assert not result["human_attestation_assurance"][
        "cryptographic_identity_verified"
    ]
    assert all(item["passed"] for item in result["cases"])
    assert all(item["profile_review"]["passed"] for item in result["cases"])
    assert all(item["financial"]["passed"] for item in result["cases"])
    report = json.loads(Path(result["artifacts"]["report_json"]).read_text(encoding="utf-8"))
    assert report["cases"]
    assert all({"profile", "triage", "gaps", "financial"} <= set(item) for item in report["cases"])
    assert {"frequent_gap_fields", "generalization_issues", "financial_summary"} <= set(report)
    assert "Human attestation assurance: unsigned_claim_only" in Path(
        result["artifacts"]["report_markdown"]
    ).read_text(encoding="utf-8")
    qa_validation = json.loads(
        Path(result["cases"][0]["qa_artifacts"]["validation_json"]).read_text(encoding="utf-8")
    )
    assert qa_validation["delivery_eligible"]
    assert qa_validation["delivery_gate"]["passed"]


def test_delivery_cannot_claim_financial_traceability_without_an_audited_case(
    tmp_path: Path,
) -> None:
    registry = _delivery_registry_for_negative_test(
        tmp_path,
        include_financial_case=False,
    )

    result = run_qa_registry(
        registry,
        tmp_path / "all-profile-only-delivery",
        project_root=ROOT,
    )

    assert result["execution_passed"]
    assert result["delivery_eligible"]
    assert not result["passed"]
    assert result["deliverable_status"] == "failed"
    assert result["financial_summary"]["status"] == "financial_not_exercised"
    assert result["financial_summary"]["audited_case_count"] == 0
    assert result["financial_summary"]["traceability_percent"] is None
    assert result["financial_summary"]["passed"] is False


def test_history_binds_the_complete_run_artifact_tree(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "artifact-history-output"
    result = run_qa_registry(
        registry,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    history = json.loads((output / "qa-loop-history.json").read_text(encoding="utf-8"))
    assert history["schema_version"] == "2.0.0"
    entry = history["runs"][0]
    assert not Path(entry["run_output"]).is_absolute()
    manifest_paths = {item["path"] for item in entry["artifact_manifest"]}
    assert {
        "qa-loop-report.json",
        "qa-loop-report.md",
        "qa-loop-report.html",
    } <= manifest_paths

    validation_path = Path(result["cases"][0]["qa_artifacts"]["validation_json"])
    validation_path.write_text('{"tampered": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="artifact manifest is invalid"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )


def test_report_failure_does_not_commit_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "report-failure-output"

    def fail_report(_result: dict[str, object]) -> str:
        raise RuntimeError("synthetic renderer failure")

    monkeypatch.setattr("cleantech_finance.qa_loop._html_report", fail_report)
    with pytest.raises(RuntimeError, match="synthetic renderer failure"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert not (output / "qa-loop-history.json").exists()
    assert any((output / "runs" / ".staging").iterdir())


def test_input_drift_during_execution_does_not_commit_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    first_case_path = tmp_path / registry_payload["cases"][0]["input"]
    output = tmp_path / "input-drift-output"
    from cleantech_finance import qa_loop

    real_html_report = qa_loop._html_report

    def mutate_input_after_render(result: dict[str, object]) -> str:
        rendered = real_html_report(result)
        case = json.loads(first_case_path.read_text(encoding="utf-8"))
        case["company"]["display_name"] = "Changed during execution"
        first_case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return rendered

    monkeypatch.setattr("cleantech_finance.qa_loop._html_report", mutate_input_after_render)
    with pytest.raises(ValueError, match="inputs changed during execution"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert not (output / "qa-loop-history.json").exists()


def test_registry_snapshot_uses_the_bytes_that_were_parsed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "registry-snapshot-output"
    from cleantech_finance import qa_loop

    real_runtime_manifest = qa_loop._runtime_input_manifest
    call_count = 0

    def mutate_before_first_manifest(
        registry_payload: dict[str, object],
        registry_path: Path,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            registry_path.write_text(
                registry_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        return real_runtime_manifest(registry_payload, registry_path, **kwargs)

    monkeypatch.setattr(
        "cleantech_finance.qa_loop._runtime_input_manifest",
        mutate_before_first_manifest,
    )
    with pytest.raises(ValueError, match="inputs changed during execution"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert not (output / "qa-loop-history.json").exists()


def test_loop_rejects_an_existing_process_lock(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "locked-output"
    output.mkdir()
    lock = output / ".qa-loop.lock"
    lock.write_text('{"pid": 123}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="locked by another or interrupted run"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert lock.is_file()


def test_delivery_history_rejects_changed_input_batch(tmp_path: Path) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    output = tmp_path / "immutable-delivery-output"
    first = run_qa_registry(registry_path, output, project_root=Path.cwd())
    assert first["passed"]

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    row = registry["cases"][0]
    case_path = tmp_path / row["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["company"]["display_name"] = "Changed after immutable selection"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    row["input_sha256"] = _file_sha256(case_path)
    registry["selection_attestation"]["case_set_sha256"] = selection_digest(registry, registry_path)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="different immutable inputs"):
        run_qa_registry(registry_path, output, project_root=Path.cwd())


def test_delivery_history_binds_the_human_selection_attestation(tmp_path: Path) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    output = tmp_path / "attestation-lock-output"
    first = run_qa_registry(registry_path, output, project_root=Path.cwd())
    assert first["passed"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["selection_attestation"]["confirmed_by"] = "different-human-reviewer"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="different human selection attestation"):
        run_qa_registry(registry_path, output, project_root=Path.cwd())


def test_contract_and_delivery_histories_require_separate_outputs(tmp_path: Path) -> None:
    contract_registry = _five_case_registry(tmp_path)
    output = tmp_path / "mode-isolation-output"
    run_qa_registry(
        contract_registry,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    delivery_registry = _delivery_registry_for_negative_test(tmp_path)
    with pytest.raises(ValueError, match="separate output directories"):
        run_qa_registry(delivery_registry, output, project_root=Path.cwd())


def test_five_case_loop_stops_on_first_traceability_failure(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    first_case_path = tmp_path / payload["cases"][0]["input"]
    first_case = json.loads(first_case_path.read_text(encoding="utf-8"))
    first_case["profile_candidates"][0]["evidence_refs"][0]["quote"] = "not in source"
    first_case_path.write_text(json.dumps(first_case, ensure_ascii=False), encoding="utf-8")

    result = run_qa_registry(
        registry,
        tmp_path / "failed-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not result["passed"]
    assert result["completed_case_count"] == 0
    assert len(result["cases"]) == 1
    assert result["cases"][0]["financial"]["status"] == "not_run_due_to_upstream_failure"
    assert result["frequent_gap_fields"][0]["field"] == "product_technology"
    assert result["frequent_gap_fields"][0]["count"] == 1
    assert result["frequent_gap_fields"][0]["recommended_question"]["question_id"] == "product-core"


def test_mixed_financial_pass_and_upstream_skip_is_not_ground_truth_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    second_case_path = tmp_path / payload["cases"][1]["input"]
    second_case = json.loads(second_case_path.read_text(encoding="utf-8"))
    second_case["profile_candidates"][0]["evidence_refs"][0]["quote"] = "not in source"
    second_case_path.write_text(json.dumps(second_case, ensure_ascii=False), encoding="utf-8")

    def financial_pass(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "status": "passed",
            "passed": True,
            "extraction_evaluation": {"passed_checks": 28, "total_checks": 28},
            "card_evaluation": {"passed_checks": 27, "total_checks": 27},
        }

    monkeypatch.setattr("cleantech_finance.qa_loop._run_financial_evidence", financial_pass)
    result = run_qa_registry(
        registry,
        tmp_path / "mixed-financial-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert len(result["cases"]) == 2
    assert result["financial_summary"]["status"] == ("financial_not_run_or_contract_failure")
    assert result["financial_summary"]["status"] != "financial_ground_truth_failure"


def test_human_supplied_annual_report_uses_existing_financial_ground_truth(
    tmp_path: Path,
) -> None:
    registry = _five_case_registry(tmp_path)
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    first_row = registry_payload["cases"][0]
    first_case_path = tmp_path / first_row["input"]
    first_case = json.loads(first_case_path.read_text(encoding="utf-8"))
    first_case["company"]["legal_name"] = "Sungrow Power Supply Co., Ltd."
    first_case["company"]["stable_identifier"] = {
        "scheme": "ticker",
        "value": "300274.SZ",
    }
    _bind_case_entities(first_case)
    manifest_path = Path.cwd() / "examples/sungrow/manifest.auto.json"
    ground_path = Path.cwd() / "evals/sungrow-2025.json"
    card_ground_path = Path.cwd() / "evals/sungrow-cards-v0.2.json"
    _set_financial_contract(
        first_case,
        manifest_path,
        ground_path,
        card_ground_path,
    )
    first_case_path.write_text(
        json.dumps(first_case, ensure_ascii=False),
        encoding="utf-8",
    )
    first_row["company"] = "Sungrow Power Supply Co., Ltd."
    first_row["entity_scheme"] = "ticker"
    first_row["entity_id"] = "300274.SZ"
    registry.write_text(
        json.dumps(registry_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_qa_registry(
        registry,
        tmp_path / "financial-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not result["passed"]
    assert result["execution_passed"]
    assert result["deliverable_status"] == "contract_fixture_only"
    financial = result["cases"][0]["financial"]
    assert financial["status"] == "passed"
    assert financial["contract_check_passed"]
    assert not financial["passed"]
    assert financial["extraction_evaluation"]["passed_checks"] == 29
    assert financial["card_evaluation"]["passed_checks"] == 27
    assert financial["model_calls"] == 0
    assert financial["network_calls"] == 0
    assert result["financial_summary"]["audited_case_count"] == 1
    assert result["financial_summary"]["passed_checks"] == 56
    assert result["financial_summary"]["total_checks"] == 56
    assert result["financial_summary"]["traceability_percent"] == 100.0
    assert result["financial_summary"]["status"] == ("all_supplied_financial_cases_traceable")
    assert result["financial_summary"]["contract_checks_passed"]
    assert not result["financial_summary"]["passed"]


def test_financial_origin_aba_executes_only_captured_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    origins = _configure_local_sungrow_financial_case(registry, tmp_path)
    original_bytes = {name: path.read_bytes() for name, path in origins.items()}
    from cleantech_finance import qa_loop

    real_financial = qa_loop._run_financial_evidence
    captured_snapshot_root: Path | None = None

    def mutate_origins_during_financial(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal captured_snapshot_root
        snapshot = kwargs["runtime_snapshot"]
        captured_snapshot_root = snapshot.root
        for path in origins.values():
            assert not path.is_relative_to(snapshot.root)
        origins["manifest"].write_text("{}", encoding="utf-8")
        origins["ground_truth"].write_text("{}", encoding="utf-8")
        origins["card_ground_truth"].write_text("{}", encoding="utf-8")
        origins["subject_source"].write_bytes(b"attacker bytes that must never be consumed")
        try:
            return real_financial(*args, **kwargs)
        finally:
            for name, path in origins.items():
                path.write_bytes(original_bytes[name])

    monkeypatch.setattr(
        "cleantech_finance.qa_loop._run_financial_evidence",
        mutate_origins_during_financial,
    )
    result = run_qa_registry(
        registry,
        tmp_path / "origin-aba-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    financial = result["cases"][0]["financial"]
    assert financial["status"] == "passed"
    assert financial["extraction_evaluation"]["passed_checks"] == 29
    assert financial["card_evaluation"]["passed_checks"] == 27
    assert financial["runtime_input_snapshot"]["retained"] is False
    assert all(path.read_bytes() == original_bytes[name] for name, path in origins.items())
    assert captured_snapshot_root is not None and not captured_snapshot_root.exists()
    retained_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(result["artifacts"]["run_output"]).rglob("*")
        if path.is_file()
    )
    assert "cleantech-qa-runtime-inputs-" not in retained_text
    for origin in origins.values():
        assert str(origin) not in retained_text
        assert origin.as_posix() not in retained_text


def test_snapshot_source_digest_and_extraction_use_the_same_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    _configure_local_sungrow_financial_case(registry, tmp_path)
    from cleantech_finance import audit as audit_module

    real_load_manifest = audit_module.load_manifest
    real_ingest_sources = audit_module.ingest_sources
    mutated_path: Path | None = None
    original_payload: bytes | None = None

    def load_then_mutate(*args: object, **kwargs: object) -> tuple[object, ...]:
        nonlocal mutated_path, original_payload
        loaded = real_load_manifest(*args, **kwargs)
        subject = next(source for source in loaded[1] if source.role == "subject")
        mutated_path = Path(subject.path)
        original_payload = mutated_path.read_bytes()
        mutated_path.write_bytes(b"not the bytes represented by the captured source digest")
        return loaded

    def ingest_then_restore(*args: object, **kwargs: object) -> list[object]:
        try:
            return real_ingest_sources(*args, **kwargs)
        finally:
            assert mutated_path is not None and original_payload is not None
            mutated_path.write_bytes(original_payload)

    monkeypatch.setattr(audit_module, "load_manifest", load_then_mutate)
    monkeypatch.setattr(audit_module, "ingest_sources", ingest_then_restore)
    result = run_qa_registry(
        registry,
        tmp_path / "single-read-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert result["cases"][0]["financial"]["status"] == "passed"
    assert result["financial_summary"]["traceability_percent"] == 100.0


def test_runtime_snapshot_tampering_aborts_without_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "snapshot-tamper-output"
    from cleantech_finance import qa_loop

    real_runner = qa_loop._run_qa_registry_unlocked
    captured_root: Path | None = None

    def tamper_before_execution(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal captured_root
        snapshot = kwargs["runtime_snapshot"]
        captured_root = snapshot.root
        snapshot.files["case:human-case-1"].write_text("{}", encoding="utf-8")
        return real_runner(*args, **kwargs)

    monkeypatch.setattr(
        "cleantech_finance.qa_loop._run_qa_registry_unlocked",
        tamper_before_execution,
    )
    with pytest.raises(ValueError, match="runtime input snapshot changed"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert not (output / "qa-loop-history.json").exists()
    assert not (output / ".qa-loop.lock").exists()
    assert captured_root is not None and not captured_root.exists()


def test_runtime_snapshot_refuses_a_temp_root_inside_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "unsafe-temp-output"
    monkeypatch.setattr(
        "cleantech_finance.qa_loop.tempfile.gettempdir",
        lambda: str(Path.cwd()),
    )
    with pytest.raises(ValueError, match="temporary directory is inside the QA project tree"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert not (output / "qa-loop-history.json").exists()
    assert not (output / ".qa-loop.lock").exists()


def test_snapshot_cleanup_failure_prevents_history_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _five_case_registry(tmp_path)
    output = tmp_path / "cleanup-failure-output"
    from cleantech_finance import qa_loop

    real_cleanup = qa_loop._RuntimeInputSnapshot.cleanup
    call_count = 0

    def fail_first_cleanup(snapshot: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("synthetic private snapshot cleanup failure")
        real_cleanup(snapshot)

    monkeypatch.setattr(qa_loop._RuntimeInputSnapshot, "cleanup", fail_first_cleanup)
    with pytest.raises(OSError, match="synthetic private snapshot cleanup failure"):
        run_qa_registry(
            registry,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )
    assert call_count == 2
    assert not (output / "qa-loop-history.json").exists()
    assert not (output / ".qa-loop.lock").exists()


def test_case_input_bundle_binds_non_subject_financial_sources() -> None:
    from cleantech_finance import qa_loop

    case = _complete_case()
    case["financial_evidence"] = {
        "annual_report_status": "available",
        "review": {
            "manifest_sha256": "1" * 64,
            "ground_truth_sha256": "2" * 64,
            "card_ground_truth_sha256": "3" * 64,
            "subject_sources": [{"source_id": "subject", "sha256": "4" * 64}],
            "all_sources": [
                {"source_id": "subject", "role": "subject", "sha256": "4" * 64},
                {"source_id": "benchmark", "role": "benchmark", "sha256": "5" * 64},
            ],
        },
    }
    row = {
        "entity_scheme": "provided_case_id",
        "entity_id": "human-selected-001",
        "company": "Human Selected CleanTech Co., Ltd.",
        "profile_ground_truth_sha256": None,
    }
    first = qa_loop._input_bundle_material(
        row,
        case,
        Path("unused.json"),
        case_sha256="a" * 64,
    )
    case["financial_evidence"]["review"]["all_sources"][1]["sha256"] = "6" * 64
    second = qa_loop._input_bundle_material(
        row,
        case,
        Path("unused.json"),
        case_sha256="a" * 64,
    )
    assert qa_loop._canonical_sha256(first) != qa_loop._canonical_sha256(second)


def test_runtime_snapshot_rejects_duplicate_manifest_source_ids(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    paths = _configure_local_sungrow_financial_case(registry, tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert len(manifest["sources"]) >= 2
    manifest["sources"][1]["id"] = manifest["sources"][0]["id"]
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    case = json.loads(paths["case"].read_text(encoding="utf-8"))
    _set_financial_contract(
        case,
        paths["manifest"],
        paths["ground_truth"],
        paths["card_ground_truth"],
    )
    paths["case"].write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate manifest source id"):
        run_qa_registry(
            registry,
            tmp_path / "duplicate-source-output",
            project_root=Path.cwd(),
            allow_contract_test=True,
        )


def test_runtime_snapshot_rejects_unc_sources_before_network_access(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    paths = _configure_local_sungrow_financial_case(registry, tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["sources"][0]["path"] = r"\\server\share\untrusted-report.pdf"
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    case = json.loads(paths["case"].read_text(encoding="utf-8"))
    case["financial_evidence"]["review"]["manifest_sha256"] = _file_sha256(paths["manifest"])
    paths["case"].write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="reject UNC and device paths"):
        run_qa_registry(
            registry,
            tmp_path / "unc-source-output",
            project_root=Path.cwd(),
            allow_contract_test=True,
        )


def test_runtime_snapshot_rejects_two_source_ids_for_one_physical_file(
    tmp_path: Path,
) -> None:
    registry = _five_case_registry(tmp_path)
    paths = _configure_local_sungrow_financial_case(registry, tmp_path)
    hardlink_path = tmp_path / f"subject-hardlink{paths['subject_source'].suffix}"
    try:
        os.link(paths["subject_source"], hardlink_path)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable in this test environment: {exc}")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["sources"][1]["path"] = str(hardlink_path)
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    case = json.loads(paths["case"].read_text(encoding="utf-8"))
    _set_financial_contract(
        case,
        paths["manifest"],
        paths["ground_truth"],
        paths["card_ground_truth"],
    )
    paths["case"].write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="one physical file"):
        run_qa_registry(
            registry,
            tmp_path / "hardlink-source-output",
            project_root=Path.cwd(),
            allow_contract_test=True,
        )


def test_loop_rejects_agent_selected_company_registry(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["selection_policy"] = "agent_selected"
    payload["cases"][0]["selection_origin"] = "agent_selected"
    registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid QA registry"):
        run_qa_registry(
            registry,
            tmp_path / "rejected-output",
            project_root=Path.cwd(),
            allow_contract_test=True,
        )


def test_company_specific_rule_scan_covers_imported_helper_modules(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    registry_path = _five_case_registry(inputs)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    project_root = tmp_path / "project"
    package_root = project_root / "src" / "cleantech_finance"
    package_root.mkdir(parents=True)
    (package_root / "company_helper.py").write_text(
        "def route(entity_id):\n"
        "    if entity_id == 'human-selected-001':\n"
        "        return 'special-case'\n"
        "    return 'general-rule'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="company_helper.py"):
        _reject_company_specific_qa_rules(registry, project_root)


def test_financial_ground_truth_entity_must_match_qa_company(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    first_case_path = tmp_path / payload["cases"][0]["input"]
    first_case = json.loads(first_case_path.read_text(encoding="utf-8"))
    _set_financial_contract(
        first_case,
        Path.cwd() / "examples/sungrow/manifest.auto.json",
        Path.cwd() / "evals/sungrow-2025.json",
        Path.cwd() / "evals/sungrow-cards-v0.2.json",
    )
    first_case_path.write_text(
        json.dumps(first_case, ensure_ascii=False),
        encoding="utf-8",
    )
    result = run_qa_registry(
        registry,
        tmp_path / "mismatch-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not result["passed"]
    assert len(result["cases"]) == 1
    assert result["cases"][0]["financial"]["status"] == "invalid_financial_ground_truth"


def test_loop_preserves_schema_failure_instead_of_crashing(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    first_case_path = tmp_path / payload["cases"][0]["input"]
    first_case = json.loads(first_case_path.read_text(encoding="utf-8"))
    first_case.pop("qa_session")
    first_case_path.write_text(json.dumps(first_case, ensure_ascii=False), encoding="utf-8")
    result = run_qa_registry(
        registry,
        tmp_path / "schema-failure-output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not result["passed"]
    assert len(result["cases"]) == 1
    row = result["cases"][0]
    assert row["case_schema_errors"]
    assert row["financial"]["status"] == "not_run_due_to_upstream_failure"
    assert Path(row["qa_artifacts"]["validation_json"]).is_file()


def test_final_loop_report_preserves_historical_missing_source_frequency(
    tmp_path: Path,
) -> None:
    registry = _five_case_registry(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    output = tmp_path / "historical-gap-output"

    def set_target_quote(case_path: Path, quote: str) -> str:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        candidate = next(
            item for item in case["profile_candidates"] if item["field"] == "target_markets"
        )
        original = candidate["evidence_refs"][0]["quote"]
        candidate["evidence_refs"][0]["quote"] = quote
        case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return original

    first_path = tmp_path / payload["cases"][0]["input"]
    first_quote = set_target_quote(first_path, "missing target-market quote")
    first_run = run_qa_registry(
        registry,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not first_run["execution_passed"]

    set_target_quote(first_path, first_quote)
    second_path = tmp_path / payload["cases"][1]["input"]
    second_quote = set_target_quote(second_path, "missing target-market quote")
    second_run = run_qa_registry(
        registry,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not second_run["execution_passed"]
    assert second_run["cases"][0]["execution_passed"]
    assert not second_run["cases"][1]["execution_passed"]

    set_target_quote(second_path, second_quote)
    result = run_qa_registry(
        registry,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert result["execution_passed"]
    assert not result["passed"]
    assert result["run_number"] == 3
    assert [(item["field"], item["count"]) for item in result["frequent_gap_fields"]] == [
        ("target_markets", 2)
    ]
    assert result["frequent_gap_fields"][0]["recommended_question"]["question_id"] == "market-core"
    report = Path(result["artifacts"]["report_html"]).read_text(encoding="utf-8")
    assert "高频出处缺口" in report
    assert "target_markets: 2" in report
    history = json.loads(Path(result["artifacts"]["history_json"]).read_text(encoding="utf-8"))
    assert len(history["runs"]) == 3
    assert history["runs"][-1]["previous_run_hash"] == history["runs"][-2]["run_hash"]


def test_contract_fixture_is_rejected_without_explicit_test_flag(tmp_path: Path) -> None:
    registry = _five_case_registry(tmp_path)
    with pytest.raises(ValueError, match="cannot be run as a delivery"):
        run_qa_registry(
            registry,
            tmp_path / "output",
            project_root=Path.cwd(),
        )


def test_delivery_selection_attestation_must_bind_all_five_inputs(
    tmp_path: Path,
) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["selection_attestation"]["case_set_sha256"] = "f" * 64
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="attestation does not match"):
        run_qa_registry(
            registry_path,
            tmp_path / "output",
            project_root=Path.cwd(),
        )


def test_delivery_fails_when_human_profile_ground_truth_disagrees(
    tmp_path: Path,
) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    first_row = registry["cases"][0]
    review_path = tmp_path / first_row["profile_ground_truth"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["fields"][0]["value"] = "tampered human review value"
    review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    first_row["profile_ground_truth_sha256"] = _file_sha256(review_path)
    registry["selection_attestation"]["case_set_sha256"] = selection_digest(
        registry,
        registry_path,
    )
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_qa_registry(
        registry_path,
        tmp_path / "output",
        project_root=Path.cwd(),
    )
    assert not result["passed"]
    assert result["delivery_eligible"]
    assert result["cases"][0]["profile_review"]["status"] == "failed"
    assert result["cases"][0]["financial"]["status"] == "not_run_due_to_upstream_failure"
    triage = json.loads(
        Path(result["cases"][0]["qa_artifacts"]["triage_json"]).read_text(encoding="utf-8")
    )
    assert triage["eligible"] is False
    assert not any(route["selected"] for route in triage["routes"])


def test_profile_only_requires_a_human_waiver() -> None:
    case = _complete_case()
    case["financial_evidence"]["profile_only_waiver"] = None
    result = validate_qa_case(case)
    assert not result["passed"]
    assert "qa_schema_validation" in {item["code"] for item in result["errors"]}


def test_empty_financial_ground_truth_cannot_greenlight_a_real_audit(
    tmp_path: Path,
) -> None:
    registry_path = _five_case_registry(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    row = registry["cases"][0]
    case_path = tmp_path / row["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["company"]["legal_name"] = "Sungrow Power Supply Co., Ltd."
    case["company"]["stable_identifier"] = {
        "scheme": "ticker",
        "value": "300274.SZ",
    }
    _bind_case_entities(case)
    bad_ground = json.loads((Path.cwd() / "evals/sungrow-2025.json").read_text(encoding="utf-8"))
    bad_ground["facts"] = []
    bad_ground["metrics"] = {}
    bad_ground_path = tmp_path / "empty-ground-truth.json"
    bad_ground_path.write_text(
        json.dumps(bad_ground, ensure_ascii=False),
        encoding="utf-8",
    )
    _set_financial_contract(
        case,
        Path.cwd() / "examples/sungrow/manifest.auto.json",
        bad_ground_path,
        Path.cwd() / "evals/sungrow-cards-v0.2.json",
    )
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    row["company"] = case["company"]["legal_name"]
    row["entity_scheme"] = "ticker"
    row["entity_id"] = "300274.SZ"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_qa_registry(
        registry_path,
        tmp_path / "output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    financial = result["cases"][0]["financial"]
    assert financial["status"] == "invalid_financial_ground_truth"
    assert "facts" in financial["reason"]


def test_rule_change_requires_note_and_replays_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = _five_case_registry(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    case_path = tmp_path / registry["cases"][0]["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    product = next(
        item for item in case["profile_candidates"] if item["field"] == "product_technology"
    )
    original_quote = product["evidence_refs"][0]["quote"]
    product["evidence_refs"][0]["quote"] = "missing product quote"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "output"
    first = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert not first["execution_passed"]

    case = json.loads(case_path.read_text(encoding="utf-8"))
    product = next(
        item for item in case["profile_candidates"] if item["field"] == "product_technology"
    )
    product["evidence_refs"][0]["quote"] = original_quote
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        "cleantech_finance.qa_loop._qa_rule_bundle_digest",
        lambda _project_root: "b" * 64,
    )
    monkeypatch.setattr(
        "cleantech_finance.qa_loop.IMPORTED_QA_RULE_BUNDLE_DIGEST",
        "b" * 64,
    )
    with pytest.raises(ValueError, match="requires bilingual change notes"):
        run_qa_registry(
            registry_path,
            output,
            project_root=Path.cwd(),
            allow_contract_test=True,
        )

    second = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
        change_note="General traceability rule fix; no company-name branch.",
        change_note_zh="通用可追溯规则修复；未增加公司名分支。",
    )
    assert second["execution_passed"]
    assert second["run_number"] == 2
    assert second["generalization_issues"] == []
    assert second["input_corrections"][0]["case_id"] == "human-case-1"
    assert second["input_corrections"][0]["classification"] == "input_changed_not_general_rule_fix"


def test_rule_change_regression_evidence_exposes_failed_and_missing_prior_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = _five_case_registry(tmp_path)
    output = tmp_path / "observed-regression-output"
    real_validate = validate_qa_case

    def fail_third_under_old_rule(case: dict[str, object]) -> dict[str, object]:
        result = deepcopy(real_validate(case))
        if case["case"]["id"] == "human-case-3":
            result["passed"] = False
            result["errors"].append(
                {
                    "code": "synthetic_third_case_failure",
                    "text": "Synthetic third-case failure.",
                    "text_zh": "Synthetic third-case failure.",
                    "field": "",
                    "subject": "",
                }
            )
        return result

    monkeypatch.setattr(
        "cleantech_finance.qa_loop.validate_qa_case",
        fail_third_under_old_rule,
    )
    first = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert [row["id"] for row in first["cases"]] == [
        "human-case-1",
        "human-case-2",
        "human-case-3",
    ]
    assert [row["id"] for row in first["cases"] if row["execution_passed"]] == [
        "human-case-1",
        "human-case-2",
    ]

    def regress_first_under_new_rule(case: dict[str, object]) -> dict[str, object]:
        result = deepcopy(real_validate(case))
        if case["case"]["id"] == "human-case-1":
            result["passed"] = False
            result["errors"].append(
                {
                    "code": "synthetic_prior_pass_regression",
                    "text": "Synthetic regression of a prior pass.",
                    "text_zh": "Synthetic regression of a prior pass.",
                    "field": "",
                    "subject": "",
                }
            )
        return result

    monkeypatch.setattr(
        "cleantech_finance.qa_loop.validate_qa_case",
        regress_first_under_new_rule,
    )
    monkeypatch.setattr(
        "cleantech_finance.qa_loop._qa_rule_bundle_digest",
        lambda _project_root: "d" * 64,
    )
    monkeypatch.setattr(
        "cleantech_finance.qa_loop.IMPORTED_QA_RULE_BUNDLE_DIGEST",
        "d" * 64,
    )
    second = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
        change_note="Synthetic general rule change.",
        change_note_zh="Synthetic general rule change.",
    )

    evidence = second["regression_evidence"]
    assert evidence["required"] is True
    assert evidence["complete"] is False
    assert evidence["status"] == "incomplete_failed_or_missing"
    assert evidence["required_case_ids"] == ["human-case-1", "human-case-2"]
    assert evidence["executed_case_ids"] == ["human-case-1"]
    assert evidence["passed_case_ids"] == []
    assert evidence["failed_case_ids"] == ["human-case-1"]
    assert evidence["missing_case_ids"] == ["human-case-2"]
    assert evidence["input_changed_case_ids"] == []
    markdown_report = Path(second["artifacts"]["report_markdown"]).read_text(
        encoding="utf-8"
    )
    html_report = Path(second["artifacts"]["report_html"]).read_text(
        encoding="utf-8"
    )
    assert "Regression evidence: incomplete_failed_or_missing" in markdown_report
    assert "Regression: incomplete_failed_or_missing" in html_report
    history = json.loads(
        Path(second["artifacts"]["history_json"]).read_text(encoding="utf-8")
    )
    assert history["runs"][-1]["regression_evidence"] == evidence

    monkeypatch.setattr("cleantech_finance.qa_loop.validate_qa_case", real_validate)
    third = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert third["regression_evidence"]["required"] is True
    assert third["regression_evidence"]["complete"] is True
    assert third["regression_evidence"]["status"] == "complete"
    assert third["regression_evidence"]["passed_case_ids"] == [
        "human-case-1",
        "human-case-2",
    ]


def test_same_input_delivery_failure_then_rule_fix_is_generalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = _delivery_registry_for_negative_test(tmp_path)
    output = tmp_path / "generalization-output"
    real_validate = validate_qa_case

    def fail_under_old_rule(case: dict[str, object]) -> dict[str, object]:
        result = deepcopy(real_validate(case))
        result["passed"] = False
        result["errors"].append(
            {
                "code": "synthetic_general_rule_failure",
                "text": "Synthetic old-rule failure.",
                "text_zh": "模拟旧规则失败。",
                "field": "",
                "subject": "",
            }
        )
        return result

    monkeypatch.setattr("cleantech_finance.qa_loop.validate_qa_case", fail_under_old_rule)
    first = run_qa_registry(registry_path, output, project_root=Path.cwd())
    assert not first["execution_passed"]

    monkeypatch.setattr("cleantech_finance.qa_loop.validate_qa_case", real_validate)
    monkeypatch.setattr(
        "cleantech_finance.qa_loop._qa_rule_bundle_digest",
        lambda _project_root: "c" * 64,
    )
    monkeypatch.setattr(
        "cleantech_finance.qa_loop.IMPORTED_QA_RULE_BUNDLE_DIGEST",
        "c" * 64,
    )
    second = run_qa_registry(
        registry_path,
        output,
        project_root=Path.cwd(),
        change_note="General validation fix; no company-specific branch.",
        change_note_zh="通用校验修复；未增加公司特例。",
    )
    assert second["passed"]
    assert second["input_corrections"] == []
    assert second["generalization_issues"][0]["case_id"] == "human-case-1"
    assert second["generalization_issues"][0]["failure_codes"] == ["synthetic_general_rule_failure"]
    assert second["generalization_issues"][0]["regression_complete"] is False
    assert second["generalization_issues"][0]["regression_status"] == (
        "not_established_no_prior_passes"
    )


def test_financial_review_detects_subject_report_file_replacement(
    tmp_path: Path,
) -> None:
    registry_path = _five_case_registry(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    row = registry["cases"][0]
    case_path = tmp_path / row["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["company"]["legal_name"] = "Sungrow Power Supply Co., Ltd."
    case["company"]["stable_identifier"] = {
        "scheme": "ticker",
        "value": "300274.SZ",
    }
    _bind_case_entities(case)

    original_manifest_path = Path.cwd() / "examples/sungrow/manifest.auto.json"
    manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        source["path"] = str((original_manifest_path.parent / source["path"]).resolve())
    source_copy = tmp_path / "subject-report.pdf"
    source_copy.write_bytes(Path(manifest["sources"][0]["path"]).read_bytes())
    manifest["sources"][0]["path"] = str(source_copy)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    _set_financial_contract(
        case,
        manifest_path,
        Path.cwd() / "evals/sungrow-2025.json",
        Path.cwd() / "evals/sungrow-cards-v0.2.json",
    )
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    row["company"] = case["company"]["legal_name"]
    row["entity_scheme"] = "ticker"
    row["entity_id"] = "300274.SZ"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )
    source_copy.write_bytes(source_copy.read_bytes() + b"tampered-after-review")

    result = run_qa_registry(
        registry_path,
        tmp_path / "output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    financial = result["cases"][0]["financial"]
    assert financial["status"] == "invalid_financial_ground_truth"
    assert "subject_sources" in financial["reason"]


def test_manifest_identity_requires_scheme_value_and_legal_name_match(
    tmp_path: Path,
) -> None:
    registry_path = _five_case_registry(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    row = registry["cases"][0]
    case_path = tmp_path / row["input"]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["company"]["legal_name"] = "Sungrow Power Supply Co., Ltd."
    case["company"]["stable_identifier"] = {
        "scheme": "ticker",
        "value": "0000000001",
    }
    _bind_case_entities(case)
    expected_entity = _entity(case)

    original_manifest_path = Path.cwd() / "examples/sungrow/manifest.auto.json"
    manifest = json.loads(original_manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        source["path"] = str((original_manifest_path.parent / source["path"]).resolve())
    manifest["subject"]["identity"] = {
        "entity_id": "sec-cik-0000000001",
        "scheme": "sec_cik",
        "value": "0000000001",
        "legal_name": "Sungrow Power Supply Co., Ltd.",
        "display_name": "Sungrow Power Supply Co., Ltd.",
        "display_name_zh": "阳光电源股份有限公司",
        "legal_name_citation": {
            "source_id": manifest["sources"][0]["id"],
            "locator": "Cover page",
        },
        "aliases": [],
    }
    manifest_path = tmp_path / "identity-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    ground = json.loads((Path.cwd() / "evals/sungrow-2025.json").read_text(encoding="utf-8"))
    cards = json.loads((Path.cwd() / "evals/sungrow-cards-v0.2.json").read_text(encoding="utf-8"))
    ground["entity"] = expected_entity
    cards["entity"] = expected_entity
    ground_path = tmp_path / "ground.json"
    cards_path = tmp_path / "cards.json"
    ground_path.write_text(json.dumps(ground, ensure_ascii=False), encoding="utf-8")
    cards_path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    _set_financial_contract(case, manifest_path, ground_path, cards_path)
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    row["company"] = case["company"]["legal_name"]
    row["entity_scheme"] = "ticker"
    row["entity_id"] = "0000000001"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_qa_registry(
        registry_path,
        tmp_path / "output",
        project_root=Path.cwd(),
        allow_contract_test=True,
    )
    assert result["cases"][0]["financial"]["status"] == "financial_entity_mismatch"
