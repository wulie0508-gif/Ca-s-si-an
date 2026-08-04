"""Traceable QA diagnostics, company profiles, and downstream triage stubs.

This layer deliberately does not verify a company assertion, issue a score, or
run Expert/Map/Radar.  It turns human-provided answers and source excerpts into
candidate profile fields, then fails closed when a field cannot point to an
exact source quote.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

QA_SCHEMA_VERSION = "1.0.0"
QA_RULE_VERSION = "qa-diagnostic-1.0.0"
QA_RULE_DIGEST = sha256(Path(__file__).read_bytes()).hexdigest()
QA_CASE_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "qa-case.schema.json"

PROFILE_FIELDS = (
    "product_technology",
    "subindustry",
    "target_markets",
    "export_stage",
    "core_gaps",
    "resource_needs",
)

PROFILE_LABELS = {
    "product_technology": ("Product / technology", "产品 / 技术"),
    "subindustry": ("Subindustry", "子行业"),
    "target_markets": ("Target markets", "目标市场"),
    "export_stage": ("Export stage", "出海阶段"),
    "core_gaps": ("Core gaps", "核心缺口"),
    "resource_needs": ("Resource needs", "资源需求"),
}

EXPORT_STAGES = {
    "domestic_only",
    "exploring",
    "market_validation",
    "pilot",
    "early_commercial",
    "scaling",
    "established",
}

CONCLUSION_TYPES = {"source_statement", "inference"}
SOURCE_KINDS = {"public_source", "company_document", "provided_case_material"}
QA_QUESTION_IDS = {
    "product-core",
    "product-clarification",
    "market-core",
    "market-clarification",
    "export-stage",
    "export-stage-clarification",
    "early-stage-proof",
    "early-stage-proof-clarification",
    "pilot-proof",
    "pilot-proof-clarification",
    "commercial-proof",
    "commercial-proof-clarification",
    "gap-core",
    "gap-clarification",
    "resource-core",
    "resource-clarification",
}
REPEATABLE_QA_QUESTION_IDS = {
    question_id for question_id in QA_QUESTION_IDS if question_id.endswith("-clarification")
}


def new_qa_case() -> dict[str, Any]:
    """Return a local starter case without choosing a company for the user."""
    return {
        "schema_version": QA_SCHEMA_VERSION,
        "case": {
            "id": "replace-with-human-selected-case-id",
            "created_at": date.today().isoformat(),
            "purpose": "company_entry_diagnostic",
            "selection_origin": "human_supplied",
        },
        "company": {
            "legal_name": "Replace with the human-selected legal entity",
            "stable_identifier": {"scheme": "replace", "value": "replace"},
        },
        "sources": [],
        "qa_session": {"answers": []},
        "profile_candidates": [],
        "financial_evidence": {
            "annual_report_status": "undetermined",
            "manifest": None,
            "ground_truth": None,
            "card_ground_truth": None,
            "review": None,
            "profile_only_waiver": None,
        },
    }


def _issue(
    code: str,
    text: str,
    text_zh: str,
    *,
    field: str = "",
    subject: str = "",
) -> dict[str, str]:
    return {
        "code": code,
        "text": text,
        "text_zh": text_zh,
        "field": field,
        "subject": subject,
    }


def _answers(case: dict[str, Any]) -> list[dict[str, Any]]:
    session = case.get("qa_session")
    if not isinstance(session, dict):
        return []
    answers = session.get("answers")
    if not isinstance(answers, list):
        return []
    return [item for item in answers if isinstance(item, dict)]


def _answers_for(case: dict[str, Any], *question_ids: str) -> list[dict[str, Any]]:
    accepted = set(question_ids)
    return [item for item in _answers(case) if item.get("question_id") in accepted]


def _merged_response(case: dict[str, Any], *question_ids: str) -> dict[str, Any]:
    response: dict[str, Any] = {}
    for answer in _answers_for(case, *question_ids):
        item = answer.get("response")
        if isinstance(item, dict):
            response.update(item)
    return response


def _structured_text_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_structured_text_present(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(
            isinstance(key, str) and bool(key.strip()) and _structured_text_present(item)
            for key, item in value.items()
        )
    return False


def _gap_resource_value_present(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            (isinstance(item, str) and bool(item.strip()))
            or (
                isinstance(item, dict)
                and isinstance(item.get("category"), str)
                and bool(item["category"].strip())
                and isinstance(item.get("description"), str)
                and bool(item["description"].strip())
            )
            for item in value
        )
    )


def _response_field_present(field: str, value: Any) -> bool:
    if field in {"target_markets", "customer_segments"}:
        return (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and bool(item.strip()) for item in value)
        )
    if field in {"core_gaps", "resource_needs"}:
        return _gap_resource_value_present(value)
    return _structured_text_present(value)


def _json_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(
            left,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) == json.dumps(
            right,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return False


def _case_entity(case: dict[str, Any]) -> dict[str, str]:
    company = case.get("company") if isinstance(case.get("company"), dict) else {}
    stable = (
        company.get("stable_identifier")
        if isinstance(company.get("stable_identifier"), dict)
        else {}
    )
    return {
        "scheme": str(stable.get("scheme", "")).strip(),
        "value": str(stable.get("value", "")).strip(),
        "legal_name": str(company.get("legal_name", "")).strip(),
    }


def _answer_assertion_issues(
    answer: dict[str, Any],
) -> list[dict[str, str]]:
    """Bind every supplied structured response value to an exact statement quote."""
    answer_id = str(answer.get("id", "")).strip()
    statement = answer.get("statement")
    response = answer.get("response")
    assertions = answer.get("response_assertions")
    if not isinstance(response, dict) or not isinstance(assertions, list):
        return []
    issues: list[dict[str, str]] = []
    by_field: dict[str, list[dict[str, Any]]] = {}
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        field = str(assertion.get("field", "")).strip()
        by_field.setdefault(field, []).append(assertion)
        if field not in response:
            issues.append(
                _issue(
                    "answer_response_assertion_unknown_field",
                    "A response assertion must target a field present in response.",
                    "回答断言必须指向 response 中实际存在的字段。",
                    field=field,
                    subject=answer_id,
                )
            )
    for field, value in response.items():
        matches = by_field.get(str(field), [])
        if len(matches) != 1:
            issues.append(
                _issue(
                    "answer_response_assertion_count",
                    "Every supplied response field needs exactly one field/value/quote assertion.",
                    "每个已提供的 response 字段都必须有且仅有一条字段—值—原话断言。",
                    field=str(field),
                    subject=answer_id,
                )
            )
            continue
        assertion = matches[0]
        if not _json_equal(assertion.get("value"), value):
            issues.append(
                _issue(
                    "answer_response_assertion_value_mismatch",
                    "The response assertion value must exactly equal response[field].",
                    "回答断言的值必须与 response[field] 完全一致。",
                    field=str(field),
                    subject=answer_id,
                )
            )
        quote = assertion.get("quote")
        if (
            not isinstance(statement, str)
            or not isinstance(quote, str)
            or not quote.strip()
            or quote not in statement
        ):
            issues.append(
                _issue(
                    "answer_response_assertion_quote_mismatch",
                    "The response assertion quote must be an exact non-empty substring of the company statement.",
                    "回答断言的原话必须是企业陈述中的非空精确子串。",
                    field=str(field),
                    subject=answer_id,
                )
            )
    return issues


def _question(
    question_id: str,
    topic: str,
    text: str,
    text_zh: str,
    required_response_fields: list[str],
    reason_code: str,
    *,
    triggered_by: str | None = None,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": question_id,
        "topic": topic,
        "text": text,
        "text_zh": text_zh,
        "required_response_fields": required_response_fields,
        "reason_code": reason_code,
        "triggered_by": triggered_by,
        "missing_fields": missing_fields or [],
        "answer_contract": {
            "statement": "The company's exact words; do not paraphrase here.",
            "response": "Structured fields extracted from that statement.",
            "profile_candidates": "Any normalized profile value remains a candidate with exact quote references.",
        },
    }


def _route_next_qa_question(case: dict[str, Any]) -> dict[str, Any] | None:
    """Choose the next question from prior structured answers.

    The router is deterministic.  It asks targeted clarification questions for
    missing response fields and branches on the declared export stage.
    """
    if not _answers_for(case, "product-core"):
        return _question(
            "product-core",
            "product_technology",
            "What exactly does the customer buy, which costly problem does it solve, and which subindustry best describes it?",
            "客户实际购买的是什么、解决了什么昂贵问题、最准确的子行业是什么？请用具体产品或服务说明。",
            ["product_technology", "customer_problem", "subindustry"],
            "start_with_product",
        )
    product = _merged_response(case, "product-core", "product-clarification")
    product_missing = [
        field
        for field in ("product_technology", "customer_problem", "subindustry")
        if not _response_field_present(field, product.get(field))
    ]
    if product_missing:
        return _question(
            "product-clarification",
            "product_technology",
            "Clarify the missing product fields with one concrete customer example.",
            "请用一个具体客户案例补清产品、客户问题或子行业中仍缺失的部分。",
            product_missing,
            "product_answer_incomplete",
            triggered_by="product-core",
            missing_fields=product_missing,
        )

    if not _answers_for(case, "market-core"):
        return _question(
            "market-core",
            "target_markets",
            "Which countries and customer segments are real targets, and what evidence supports choosing them?",
            "真正准备进入哪些国家和客户群？选择这些市场的依据是什么？",
            ["target_markets", "customer_segments", "market_basis"],
            "product_is_clear_enough_for_market_question",
            triggered_by="product-core",
        )
    market = _merged_response(case, "market-core", "market-clarification")
    market_missing = [
        field
        for field in ("target_markets", "customer_segments", "market_basis")
        if not _response_field_present(field, market.get(field))
    ]
    if market_missing:
        return _question(
            "market-clarification",
            "target_markets",
            "Separate desired markets from evidence-backed target markets and fill the missing fields.",
            "请区分“想去的市场”和“有依据的目标市场”，并补齐缺失字段。",
            market_missing,
            "market_answer_incomplete",
            triggered_by="market-core",
            missing_fields=market_missing,
        )

    if not _answers_for(case, "export-stage"):
        return _question(
            "export-stage",
            "export_stage",
            "Which export stage describes completed actions, not aspirations?",
            "按已经完成的动作而不是愿望判断，企业目前处于哪个出海阶段？",
            ["export_stage"],
            "market_answer_sets_stage_context",
            triggered_by="market-core",
        )
    stage = _merged_response(
        case,
        "export-stage",
        "export-stage-clarification",
    ).get("export_stage")
    if stage not in EXPORT_STAGES:
        return _question(
            "export-stage-clarification",
            "export_stage",
            "Choose one supported export-stage value and cite the completed action behind it.",
            "请选择一个受支持的出海阶段，并说明支撑该阶段的已完成动作。",
            ["export_stage", "completed_action"],
            "unknown_export_stage",
            triggered_by="export-stage",
            missing_fields=["export_stage"],
        )

    if stage in {"domestic_only", "exploring"}:
        branch_id = "early-stage-proof"
        required = ["selection_basis", "next_12_month_milestone"]
        text = "What evidence supports the first target market, and what milestone would justify entry within 12 months?"
        text_zh = "首个目标市场的依据是什么？未来12个月达到什么里程碑才值得进入？"
    elif stage in {"market_validation", "pilot"}:
        branch_id = "pilot-proof"
        required = ["validation_evidence", "conversion_criteria"]
        text = "What customer validation or pilot evidence exists, and what converts it into commercial business?"
        text_zh = "已有何种客户验证或试点证据？达到什么条件才会转成商业订单？"
    else:
        branch_id = "commercial-proof"
        required = ["customer_evidence", "repeatability_evidence"]
        text = "What paying-customer evidence exists, and what shows exports can repeat rather than remain one-off?"
        text_zh = "已有何种付费客户证据？什么能证明出海业务可以重复，而不是一次性订单？"
    if not _answers_for(case, branch_id):
        return _question(
            branch_id,
            "export_stage",
            text,
            text_zh,
            required,
            f"export_stage_branch_{stage}",
            triggered_by="export-stage",
        )
    branch = _merged_response(case, branch_id, f"{branch_id}-clarification")
    branch_missing = [
        field for field in required if not _response_field_present(field, branch.get(field))
    ]
    if branch_missing:
        return _question(
            f"{branch_id}-clarification",
            "export_stage",
            "Fill the missing stage evidence without upgrading an aspiration into a completed action.",
            "请补齐阶段证据；不得把愿望或计划升级为已经完成的动作。",
            branch_missing,
            "stage_branch_answer_incomplete",
            triggered_by=branch_id,
            missing_fields=branch_missing,
        )

    if not _answers_for(case, "gap-core"):
        return _question(
            "gap-core",
            "core_gaps",
            "What is the single largest blocker, which category is it, and what evidence would resolve the uncertainty?",
            "当前最大的单一阻塞是什么、属于哪类缺口、需要什么证据才能消除不确定性？",
            ["core_gaps"],
            "stage_evidence_exposes_gaps",
            triggered_by=branch_id,
        )
    gaps = _merged_response(case, "gap-core", "gap-clarification")
    if not _response_field_present("core_gaps", gaps.get("core_gaps")):
        return _question(
            "gap-clarification",
            "core_gaps",
            "Name at least one concrete gap or explicitly explain why no current gap is claimed.",
            "请至少列出一个具体缺口；若认为没有缺口，必须明确说明依据。",
            ["core_gaps"],
            "gap_answer_incomplete",
            triggered_by="gap-core",
            missing_fields=["core_gaps"],
        )

    if not _answers_for(case, "resource-core"):
        return _question(
            "resource-core",
            "resource_needs",
            "Which external resources are needed, for what milestone, and by when?",
            "需要哪些外部资源、用于哪个里程碑、希望何时到位？",
            ["resource_needs", "expected_milestone"],
            "gaps_determine_resource_question",
            triggered_by="gap-core",
        )
    resources = _merged_response(case, "resource-core", "resource-clarification")
    resource_missing = [
        field
        for field in ("resource_needs", "expected_milestone")
        if not _response_field_present(field, resources.get(field))
    ]
    if resource_missing:
        return _question(
            "resource-clarification",
            "resource_needs",
            "Tie every requested resource to a concrete milestone and timing.",
            "请把每项资源需求对应到具体里程碑和时间。",
            resource_missing,
            "resource_answer_incomplete",
            triggered_by="resource-core",
            missing_fields=resource_missing,
        )
    return None


def _schema_issues(case: dict[str, Any]) -> list[dict[str, str]]:
    """Validate the standalone case against the same schema used by the loop."""
    try:
        schema = json.loads(QA_CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            _issue(
                "qa_schema_unavailable",
                f"QA case schema could not be loaded: {exc}",
                f"无法加载 QA 案例 Schema：{exc}",
            )
        ]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[dict[str, str]] = []
    for error in sorted(
        validator.iter_errors(case),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        issues.append(
            _issue(
                "qa_schema_validation",
                f"{location}: {error.message}",
                f"{location}：不符合 QA 案例 Schema（{error.message}）",
                subject=location,
            )
        )
    return issues


def _replay_qa_session(
    case: dict[str, Any],
) -> tuple[dict[str, Any] | None, set[str], list[dict[str, str]]]:
    """Replay answers in order and accept only questions the router issued."""
    replay_case = deepcopy(case)
    replay_case["qa_session"] = {"answers": []}
    accepted_answer_ids: set[str] = set()
    errors: list[dict[str, str]] = []
    replay_answers = replay_case["qa_session"]["answers"]
    previous_answered_at: datetime | None = None
    for position, answer in enumerate(_answers(case)):
        expected = _route_next_qa_question(replay_case)
        question_id = str(answer.get("question_id", "")).strip()
        answer_id = str(answer.get("id", "")).strip()
        answered_at = answer.get("answered_at")
        try:
            if not isinstance(answered_at, str):
                raise ValueError
            answered_at_value = datetime.fromisoformat(answered_at)
            if answered_at_value.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append(
                _issue(
                    "answer_timestamp_invalid",
                    "The router replay requires a valid answered_at date-time.",
                    "路由重放要求回答包含有效的 answered_at 日期时间。",
                    subject=answer_id or f"answers[{position}]",
                )
            )
            break
        if previous_answered_at is not None and answered_at_value < previous_answered_at:
            errors.append(
                _issue(
                    "answer_timestamp_out_of_order",
                    "QA answer timestamps must be non-decreasing in router order.",
                    "QA 回答时间必须按路由顺序单调不减。",
                    subject=answer_id or f"answers[{position}]",
                )
            )
            break
        if expected is None:
            errors.append(
                _issue(
                    "qa_answer_after_completion",
                    "The QA graph was already complete; an additional answer was not issued by the router.",
                    "QA 问题图已经完成；额外回答并非由路由器发出。",
                    subject=answer_id or f"answers[{position}]",
                )
            )
            break
        if question_id != expected["id"]:
            code = (
                "unknown_qa_question"
                if question_id not in QA_QUESTION_IDS
                else "qa_answer_out_of_order"
            )
            errors.append(
                _issue(
                    code,
                    f"Answer {position} targets '{question_id}', but the router issued '{expected['id']}'.",
                    f"第 {position + 1} 条回答对应“{question_id}”，但路由器实际发出的是“{expected['id']}”。",
                    subject=answer_id or f"answers[{position}]",
                )
            )
            break
        assertion_issues = _answer_assertion_issues(answer)
        if assertion_issues:
            errors.extend(assertion_issues)
            break
        replay_answers.append(answer)
        previous_answered_at = answered_at_value
        if answer_id:
            accepted_answer_ids.add(answer_id)
    return _route_next_qa_question(replay_case), accepted_answer_ids, errors


def next_qa_question(case: dict[str, Any]) -> dict[str, Any] | None:
    """Return the next actually issuable question after replaying answer order."""
    next_question, _, _ = _replay_qa_session(case)
    return next_question


def next_qa_question_status(case: dict[str, Any]) -> dict[str, Any]:
    """Return a fail-closed routing status with replay errors exposed."""
    next_question, _, replay_errors = _replay_qa_session(case)
    if replay_errors:
        return {
            "status": "blocked_by_replay_errors",
            "complete": False,
            "next_question": None,
            "errors": replay_errors,
        }
    complete = next_question is None
    return {
        "status": "complete" if complete else "next_question_available",
        "complete": complete,
        "next_question": next_question,
        "errors": [],
    }


def _source_index(
    case: dict[str, Any],
    errors: list[dict[str, str]],
    *,
    accepted_answer_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    expected_entity = _case_entity(case)
    sources = case.get("sources")
    if not isinstance(sources, list):
        errors.append(
            _issue("invalid_sources", "sources must be an array.", "sources 必须是数组。")
        )
        sources = []
    for source in sources:
        if not isinstance(source, dict):
            errors.append(
                _issue("invalid_source", "Each source must be an object.", "每条来源必须是对象。")
            )
            continue
        source_error_start = len(errors)
        source_id = str(source.get("id", "")).strip()
        if not source_id or source_id in index:
            errors.append(
                _issue(
                    "duplicate_source_id",
                    "Each source needs a unique id.",
                    "每条来源都需要唯一 ID。",
                    subject=source_id,
                )
            )
            continue
        text = source.get("excerpt")
        if not isinstance(text, str) or not text.strip():
            errors.append(
                _issue(
                    "source_excerpt_missing",
                    "A source needs a non-empty excerpt.",
                    "来源必须包含非空原文摘录。",
                    subject=source_id,
                )
            )
            text = ""
        if not str(source.get("locator", "")).strip():
            errors.append(
                _issue(
                    "source_locator_missing",
                    "A source needs a page, section, or line locator.",
                    "来源必须包含页码、章节或行号定位。",
                    subject=source_id,
                )
            )
        kind = source.get("kind")
        if kind not in SOURCE_KINDS:
            errors.append(
                _issue(
                    "source_kind_invalid",
                    "A source needs a supported kind.",
                    "来源必须使用受支持的类型。",
                    subject=source_id,
                )
            )
        if not str(source.get("title", "")).strip():
            errors.append(
                _issue(
                    "source_title_missing",
                    "A source needs a non-empty title.",
                    "来源必须包含非空标题。",
                    subject=source_id,
                )
            )
        captured_at = source.get("captured_at")
        try:
            if not isinstance(captured_at, str):
                raise ValueError
            date.fromisoformat(captured_at)
        except ValueError:
            errors.append(
                _issue(
                    "source_captured_at_invalid",
                    "A source needs a valid captured_at date.",
                    "来源必须包含有效的 captured_at 日期。",
                    subject=source_id,
                )
            )
        url_or_source_id = str(source.get("url_or_source_id", "")).strip()
        if not url_or_source_id:
            errors.append(
                _issue(
                    "source_url_or_id_missing",
                    "A source needs a URL or stable source id.",
                    "来源必须包含 URL 或稳定来源 ID。",
                    subject=source_id,
                )
            )
        elif url_or_source_id.lower().startswith(("http://", "https://")):
            try:
                parsed_url = urlparse(url_or_source_id)
                hostname = parsed_url.hostname
                _ = parsed_url.port
                valid_http_url = bool(
                    parsed_url.scheme.lower() in {"http", "https"}
                    and hostname
                    and not any(character.isspace() for character in url_or_source_id)
                )
            except ValueError:
                valid_http_url = False
            if not valid_http_url:
                errors.append(
                    _issue(
                        "source_url_invalid",
                        "A source claiming an HTTP(S) URL needs a valid host.",
                        "声明为 HTTP(S) URL 的来源必须包含有效主机名。",
                        subject=source_id,
                    )
                )
        source_sha256 = source.get("sha256")
        if source_sha256 is not None and not (
            isinstance(source_sha256, str) and re.fullmatch(r"[a-f0-9]{64}", source_sha256)
        ):
            errors.append(
                _issue(
                    "source_sha256_invalid",
                    "A supplied source sha256 must be 64 lowercase hexadecimal characters.",
                    "来源 sha256 必须是 64 位小写十六进制字符串。",
                    subject=source_id,
                )
            )
        if source.get("subject_entity") != expected_entity:
            errors.append(
                _issue(
                    "source_subject_mismatch",
                    "The source subject_entity must exactly match the QA company scheme, value, and legal name.",
                    "来源 subject_entity 必须与 QA 企业的标识方案、值和法定名称完全一致。",
                    subject=source_id,
                )
            )
        if source.get("selection_origin") != "human_supplied":
            errors.append(
                _issue(
                    "source_not_human_supplied",
                    "QA sources must be selected and supplied by a human.",
                    "QA 来源必须由人工选择并提供。",
                    subject=source_id,
                )
            )
        assertions = source.get("field_assertions")
        if not isinstance(assertions, list):
            errors.append(
                _issue(
                    "source_field_assertions_invalid",
                    "field_assertions must be an array.",
                    "field_assertions 必须是数组。",
                    subject=source_id,
                )
            )
            assertions = []
        valid_assertions: list[dict[str, Any]] = []
        for assertion in assertions:
            if not isinstance(assertion, dict):
                errors.append(
                    _issue(
                        "source_field_assertion_invalid",
                        "Each field assertion must be an object.",
                        "每条字段断言必须是对象。",
                        subject=source_id,
                    )
                )
                continue
            assertion_field = str(assertion.get("field", ""))
            assertion_quote = assertion.get("quote")
            if assertion_field not in PROFILE_FIELDS:
                errors.append(
                    _issue(
                        "source_field_assertion_unknown",
                        "A field assertion targets an unsupported profile field.",
                        "字段断言指向不受支持的画像字段。",
                        field=assertion_field,
                        subject=source_id,
                    )
                )
                continue
            if not _valid_profile_value(assertion_field, assertion.get("value")):
                errors.append(
                    _issue(
                        "source_field_assertion_value_invalid",
                        "A field assertion has an invalid field value.",
                        "字段断言包含无效的字段值。",
                        field=assertion_field,
                        subject=source_id,
                    )
                )
                continue
            if (
                not isinstance(assertion_quote, str)
                or not assertion_quote.strip()
                or assertion_quote not in text
            ):
                errors.append(
                    _issue(
                        "source_field_assertion_quote_mismatch",
                        "A field assertion quote must be an exact non-empty substring of the source excerpt.",
                        "字段断言引文必须是来源摘录中的非空精确子串。",
                        field=assertion_field,
                        subject=source_id,
                    )
                )
                continue
            valid_assertions.append(assertion)
        index[source_id] = {
            **source,
            "text": text,
            "field_assertions": valid_assertions,
            "traceability_valid": len(errors) == source_error_start,
        }

    answer_ids: set[str] = set()
    question_ids: set[str] = set()
    for answer in _answers(case):
        answer_error_start = len(errors)
        answer_id = str(answer.get("id", "")).strip()
        question_id = str(answer.get("question_id", "")).strip()
        if not answer_id or answer_id in answer_ids or answer_id in index:
            errors.append(
                _issue(
                    "duplicate_answer_id",
                    "Each QA answer needs a unique id that does not collide with a source id.",
                    "每条 QA 回答需要唯一且不与来源冲突的 ID。",
                    subject=answer_id,
                )
            )
            continue
        answer_ids.add(answer_id)
        if not question_id or (
            question_id in question_ids and question_id not in REPEATABLE_QA_QUESTION_IDS
        ):
            errors.append(
                _issue(
                    "duplicate_question_answer",
                    "Each non-clarification question may have at most one controlling answer.",
                    "每个非澄清问题最多只能有一条控制性回答。",
                    subject=question_id,
                )
            )
        question_ids.add(question_id)
        statement = answer.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            errors.append(
                _issue(
                    "answer_statement_missing",
                    "A QA answer needs the company's exact statement.",
                    "QA 回答必须保留企业原话。",
                    subject=answer_id,
                )
            )
            statement = ""
        if not isinstance(answer.get("response"), dict):
            errors.append(
                _issue(
                    "answer_response_missing",
                    "A QA answer needs a structured response object.",
                    "QA 回答必须包含结构化 response 对象。",
                    subject=answer_id,
                )
            )
        if answer.get("answer_origin") != "company_statement":
            errors.append(
                _issue(
                    "answer_origin_invalid",
                    "A QA answer must be explicitly recorded as a company statement.",
                    "QA 回答必须明确记录为企业陈述。",
                    subject=answer_id,
                )
            )
        if answer.get("respondent_entity") != expected_entity:
            errors.append(
                _issue(
                    "answer_subject_mismatch",
                    "The answer respondent_entity must exactly match the QA company scheme, value, and legal name.",
                    "回答 respondent_entity 必须与 QA 企业的标识方案、值和法定名称完全一致。",
                    subject=answer_id,
                )
            )
        errors.extend(_answer_assertion_issues(answer))
        answered_at = answer.get("answered_at")
        try:
            if not isinstance(answered_at, str):
                raise ValueError
            answered_at_value = datetime.fromisoformat(answered_at)
            if answered_at_value.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append(
                _issue(
                    "answer_timestamp_invalid",
                    "A QA answer needs a valid answered_at date-time.",
                    "QA 回答必须包含有效的 answered_at 日期时间。",
                    subject=answer_id,
                )
            )
        if accepted_answer_ids is not None and answer_id not in accepted_answer_ids:
            continue
        index[answer_id] = {
            "id": answer_id,
            "kind": "company_statement",
            "title": f"QA answer: {question_id}",
            "locator": f"qa_session.answers[{answer_id}]",
            "url_or_source_id": None,
            "text": statement,
            "response": answer.get("response") if isinstance(answer.get("response"), dict) else {},
            "response_assertions": (
                answer.get("response_assertions")
                if isinstance(answer.get("response_assertions"), list)
                else []
            ),
            "traceability_valid": len(errors) == answer_error_start,
        }
    return index


def _valid_profile_value(field: str, value: Any) -> bool:
    if field in {"product_technology", "subindustry"}:
        return isinstance(value, str) and bool(value.strip())
    if field == "export_stage":
        return value in EXPORT_STAGES
    if field == "target_markets":
        return (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
        )
    if field in {"core_gaps", "resource_needs"}:
        return _gap_resource_value_present(value)
    return False


def build_company_profile(case: dict[str, Any]) -> dict[str, Any]:
    """Validate candidate profile fields against exact source excerpts."""
    errors: list[dict[str, str]] = []
    _, accepted_answer_ids, replay_errors = _replay_qa_session(case)
    errors.extend(replay_errors)
    sources = _source_index(
        case,
        errors,
        accepted_answer_ids=accepted_answer_ids,
    )
    candidates = case.get("profile_candidates")
    if not isinstance(candidates, list):
        errors.append(
            _issue(
                "invalid_profile_candidates",
                "profile_candidates must be an array.",
                "profile_candidates 必须是数组。",
            )
        )
        candidates = []
    by_field: dict[str, list[dict[str, Any]]] = {field: [] for field in PROFILE_FIELDS}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append(
                _issue(
                    "invalid_profile_candidate",
                    "Each profile candidate must be an object.",
                    "每个画像候选必须是对象。",
                )
            )
            continue
        field = str(candidate.get("field", ""))
        if field not in by_field:
            errors.append(
                _issue(
                    "unknown_profile_field",
                    "Profile field is not supported.",
                    "画像字段不受支持。",
                    field=field,
                )
            )
            continue
        by_field[field].append(candidate)

    fields: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for field in PROFILE_FIELDS:
        label, label_zh = PROFILE_LABELS[field]
        rows = by_field[field]
        field_errors: list[dict[str, str]] = []
        if not rows:
            field_errors.append(
                _issue(
                    "profile_field_missing",
                    f"Profile field '{field}' has no candidate.",
                    f"画像字段“{label_zh}”没有候选值。",
                    field=field,
                )
            )
            candidate: dict[str, Any] = {}
        elif len(rows) > 1:
            field_errors.append(
                _issue(
                    "profile_field_conflict",
                    f"Profile field '{field}' has multiple unresolved candidates.",
                    f"画像字段“{label_zh}”存在多个未解决候选。",
                    field=field,
                )
            )
            candidate = rows[0]
        else:
            candidate = rows[0]

        value = candidate.get("value")
        if rows and not _valid_profile_value(field, value):
            field_errors.append(
                _issue(
                    "invalid_profile_value",
                    f"Profile field '{field}' has an invalid value.",
                    f"画像字段“{label_zh}”的值无效。",
                    field=field,
                )
            )
        conclusion_type = candidate.get("conclusion_type")
        if rows and conclusion_type not in CONCLUSION_TYPES:
            field_errors.append(
                _issue(
                    "invalid_conclusion_type",
                    "A profile candidate must be a source_statement or inference.",
                    "画像候选必须标记为 source_statement 或 inference。",
                    field=field,
                )
            )
        if conclusion_type == "inference" and not str(candidate.get("rationale", "")).strip():
            field_errors.append(
                _issue(
                    "inference_rationale_missing",
                    "An inference needs an explicit rationale.",
                    "推断必须包含明确理由。",
                    field=field,
                )
            )

        refs = candidate.get("evidence_refs") if rows else []
        if not isinstance(refs, list) or not refs:
            field_errors.append(
                _issue(
                    "profile_source_missing",
                    "Every profile field needs at least one source reference.",
                    "每个画像字段至少需要一条来源引用。",
                    field=field,
                )
            )
            refs = []
        resolved_refs: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, dict):
                field_errors.append(
                    _issue(
                        "invalid_profile_reference",
                        "A profile reference must be an object.",
                        "画像引用必须是对象。",
                        field=field,
                    )
                )
                continue
            source_id = str(ref.get("source_id", ""))
            source = sources.get(source_id)
            quote = ref.get("quote")
            if source is None:
                field_errors.append(
                    _issue(
                        "unknown_profile_source",
                        "A profile reference points to an unknown source.",
                        "画像引用指向不存在的来源。",
                        field=field,
                        subject=source_id,
                    )
                )
                continue
            if source.get("traceability_valid") is not True:
                field_errors.append(
                    _issue(
                        "invalid_profile_source",
                        "A profile field cannot use a source that failed its own traceability contract.",
                        "画像字段不能使用自身可追溯合同未通过的来源。",
                        field=field,
                        subject=source_id,
                    )
                )
                continue
            if (
                not isinstance(quote, str)
                or not quote.strip()
                or quote not in source.get("text", "")
            ):
                field_errors.append(
                    _issue(
                        "profile_quote_mismatch",
                        "The cited quote must be an exact non-empty substring of the source excerpt.",
                        "引用原话必须是来源摘录中的非空精确子串。",
                        field=field,
                        subject=source_id,
                    )
                )
                continue
            if source.get("kind") == "company_statement":
                response = source.get("response") or {}
                if field not in response or not _json_equal(response.get(field), value):
                    field_errors.append(
                        _issue(
                            "profile_answer_value_mismatch",
                            "A candidate citing a QA answer must exactly equal response[field].",
                            "引用 QA 回答的画像候选值必须与 response[field] 完全一致。",
                            field=field,
                            subject=source_id,
                        )
                    )
                    continue
                matching_answer_assertion = any(
                    isinstance(assertion, dict)
                    and assertion.get("field") == field
                    and _json_equal(assertion.get("value"), value)
                    and assertion.get("quote") == quote
                    for assertion in source.get("response_assertions", [])
                )
                if not matching_answer_assertion:
                    field_errors.append(
                        _issue(
                            "profile_answer_assertion_mismatch",
                            "A QA-answer profile reference must match its field/value/quote response assertion.",
                            "引用 QA 回答的画像字段必须匹配对应的字段—值—原话断言。",
                            field=field,
                            subject=source_id,
                        )
                    )
                    continue
            else:
                matching_assertion = any(
                    assertion.get("field") == field
                    and _json_equal(assertion.get("value"), value)
                    and assertion.get("quote") == quote
                    for assertion in source.get("field_assertions", [])
                )
                if not matching_assertion:
                    field_errors.append(
                        _issue(
                            "profile_source_assertion_mismatch",
                            "A document source must contain a matching field/value/quote assertion.",
                            "文档来源必须包含字段、值和引文均匹配的结构化断言。",
                            field=field,
                            subject=source_id,
                        )
                    )
                    continue
            resolved_refs.append(
                {
                    "source_id": source_id,
                    "source_kind": source.get("kind"),
                    "title": source.get("title"),
                    "locator": source.get("locator"),
                    "url_or_source_id": source.get("url_or_source_id"),
                    "quote": quote,
                }
            )

        field_errors = [
            item for index, item in enumerate(field_errors) if item not in field_errors[:index]
        ]
        if field_errors:
            gaps.append(
                {
                    "id": f"gap-profile-{field}",
                    "field": field,
                    "status": "gap",
                    "reasons": field_errors,
                    "recommended_question_topic": field,
                }
            )
        fields.append(
            {
                "id": field,
                "label": label,
                "label_zh": label_zh,
                "status": "gap" if field_errors else "supported",
                "value": value if not field_errors else None,
                "candidate_value": value if field_errors and rows else None,
                "conclusion_type": conclusion_type if rows else None,
                "rationale": candidate.get("rationale") if rows else None,
                "evidence_refs": resolved_refs,
                "errors": field_errors,
            }
        )
        errors.extend(field_errors)

    return {
        "schema_version": QA_SCHEMA_VERSION,
        "rule_version": QA_RULE_VERSION,
        "rule_digest": QA_RULE_DIGEST,
        "case_id": case.get("case", {}).get("id"),
        "company": deepcopy(case.get("company", {})),
        "passed": not errors,
        "fields": fields,
        "gap_queue": gaps,
        "errors": errors,
        "guardrails": {
            "traceability_is_structural_not_truth_verification": True,
            "company_statement_is_not_verified_fact": True,
            "no_investment_or_credit_rating": True,
            "no_aggregate_score": True,
        },
    }


def _field(profile: dict[str, Any], field_id: str) -> dict[str, Any] | None:
    return next((item for item in profile.get("fields", []) if item.get("id") == field_id), None)


def _reason(
    code: str,
    text: str,
    text_zh: str,
    profile_field: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "text": text,
        "text_zh": text_zh,
        "profile_field": profile_field.get("id"),
        "evidence_refs": deepcopy(profile_field.get("evidence_refs", [])),
    }


def triage_profile(
    profile: dict[str, Any],
    *,
    eligible: bool | None = None,
    upstream_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic routing stubs; no downstream agent is executed."""
    if eligible is None:
        eligible = profile.get("passed") is True
    if upstream_validation is None:
        upstream_validation = {
            "passed": eligible,
            "profile_passed": profile.get("passed") is True,
        }
    routes: dict[str, list[dict[str, Any]]] = {"expert": [], "map": [], "radar": []}
    product = _field(profile, "product_technology")
    subindustry = _field(profile, "subindustry")
    markets = _field(profile, "target_markets")
    stage = _field(profile, "export_stage")
    gaps = _field(profile, "core_gaps")
    resources = _field(profile, "resource_needs")

    if product and product.get("status") == "supported":
        routes["expert"].append(
            _reason(
                "product_scope_review",
                "Clarify product, technology, and specialist evidence needs.",
                "梳理产品、技术及需要专业判断的证据。",
                product,
            )
        )
    if subindustry and subindustry.get("status") == "supported":
        routes["expert"].append(
            _reason(
                "subindustry_scope_review",
                "Confirm the normalized subindustry and applicable technical or certification context.",
                "确认归一化子行业及适用的技术或认证语境。",
                subindustry,
            )
        )
    if markets and markets.get("status") == "supported":
        routes["map"].append(
            _reason(
                "target_market_path",
                "Map the evidence-backed target-market entry path.",
                "梳理有证据支持的目标市场进入路径。",
                markets,
            )
        )
    if stage and stage.get("status") == "supported":
        routes["map"].append(
            _reason(
                "export_stage_path",
                "Match market-entry work to completed export-stage actions.",
                "按已完成的出海阶段动作匹配市场进入工作。",
                stage,
            )
        )
    if gaps and gaps.get("status") == "supported":
        routes["radar"].append(
            _reason(
                "gap_monitoring",
                "Track the external facts and unresolved evidence behind declared gaps.",
                "持续跟踪已声明缺口背后的外部事实和未决证据。",
                gaps,
            )
        )
    if resources and resources.get("status") == "supported":
        routes["map"].append(
            _reason(
                "resource_matching",
                "Map requested resources to a concrete market-entry milestone.",
                "把资源需求映射到具体市场进入里程碑。",
                resources,
            )
        )
    if profile.get("gap_queue"):
        synthetic = {
            "id": "profile_gap_queue",
            "evidence_refs": [],
        }
        routes["radar"].append(
            _reason(
                "profile_evidence_gaps",
                "Monitor and close profile fields that lack traceable support.",
                "跟踪并补齐缺少可追溯依据的画像字段。",
                synthetic,
            )
        )

    return {
        "rule_version": QA_RULE_VERSION,
        "rule_digest": QA_RULE_DIGEST,
        "eligible": eligible,
        "upstream_validation": deepcopy(upstream_validation),
        "routes": [
            {
                "line": line,
                "status": "stub_only",
                "selected": bool(eligible and reasons),
                "reasons": reasons,
            }
            for line, reasons in routes.items()
        ],
        "guardrail": "Routing only. Expert, Map, and Radar are not implemented or executed.",
    }


def validate_qa_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate the complete QA -> traceable profile -> triage contract."""
    schema_errors = _schema_issues(case)
    errors: list[dict[str, str]] = list(schema_errors)
    if case.get("schema_version") != QA_SCHEMA_VERSION:
        errors.append(
            _issue(
                "schema_version",
                f"schema_version must be {QA_SCHEMA_VERSION}.",
                f"schema_version 必须为 {QA_SCHEMA_VERSION}。",
            )
        )
    case_record = case.get("case")
    human_selected = (
        isinstance(case_record, dict) and case_record.get("selection_origin") == "human_supplied"
    )
    if not human_selected:
        errors.append(
            _issue(
                "company_not_human_selected",
                "The QA company must be selected by a human.",
                "QA 企业必须由人工指定。",
            )
        )
    company = case.get("company")
    company_identity_present = isinstance(company, dict) and bool(
        str(company.get("legal_name", "")).strip()
    )
    if not company_identity_present:
        errors.append(
            _issue(
                "company_identity_missing",
                "A human-selected legal entity is required.",
                "必须提供由人工指定的法律主体。",
            )
        )
    stable_identifier = company.get("stable_identifier") if isinstance(company, dict) else None
    stable_identifier_present = (
        isinstance(stable_identifier, dict)
        and bool(str(stable_identifier.get("scheme", "")).strip())
        and str(stable_identifier.get("scheme")) != "replace"
        and bool(str(stable_identifier.get("value", "")).strip())
        and str(stable_identifier.get("value")) != "replace"
    )
    if not stable_identifier_present:
        errors.append(
            _issue(
                "stable_identifier_missing",
                "A stable identifier for the human-selected company is required.",
                "人工指定企业必须包含稳定标识。",
            )
        )
    next_question, _, replay_errors = _replay_qa_session(case)
    profile = build_company_profile(case)
    errors.extend(profile["errors"])
    if next_question is not None:
        errors.append(
            _issue(
                "qa_incomplete",
                "The dynamic QA session still has a next question.",
                "动态 QA 仍有待回答问题。",
                subject=next_question["id"],
            )
        )
    financial = case.get("financial_evidence")
    if financial is not None and not isinstance(financial, dict):
        errors.append(
            _issue(
                "invalid_financial_evidence",
                "financial_evidence must be an object.",
                "financial_evidence 必须是对象。",
            )
        )
    qa_complete = next_question is None and not replay_errors
    passed = not errors
    upstream_validation = {
        "passed": passed,
        "schema_passed": not schema_errors,
        "human_selected_company": human_selected,
        "company_identity_present": company_identity_present and stable_identifier_present,
        "qa_complete": qa_complete,
        "profile_passed": profile["passed"],
        "error_codes": sorted({item["code"] for item in errors}),
    }
    triage = triage_profile(
        profile,
        eligible=passed,
        upstream_validation=upstream_validation,
    )
    return {
        "schema_version": QA_SCHEMA_VERSION,
        "rule_version": QA_RULE_VERSION,
        "rule_digest": QA_RULE_DIGEST,
        "passed": passed,
        "validation_scope": "structural_traceability_only",
        "delivery_eligible": False,
        "human_profile_review_required_for_delivery": True,
        "qa": {
            "complete": qa_complete,
            "answer_count": len(_answers(case)),
            "next_question": next_question,
        },
        "profile": profile,
        "triage": triage,
        "errors": errors,
        "guardrails": {
            "human_selected_company_required": True,
            "unsupported_profile_fields_fail_closed": True,
            "financial_core_unchanged": True,
            "expert_map_radar_stub_only": True,
            "private_data_must_not_be_committed": True,
        },
    }
