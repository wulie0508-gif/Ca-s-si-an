"""Local-first company onboarding, evidence and readiness contracts.

This module deliberately does not assign an investment, credit, ESG, or ARL
rating.  It turns an intake interview and company materials into a traceable
case file, enforces evidence/consent gates, and prepares work for human review
or an optional local evidence-collection agent.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
from statistics import median
from typing import Any

CASE_SCHEMA_VERSION = "1.0.0"
MIN_BENCHMARK_SAMPLE = 5

STAGES = {
    "research_development": {
        "label": "Research & development",
        "label_zh": "研发期",
        "materials": ("entity_identity", "product_technology", "ip", "cash_summary"),
    },
    "pilot": {
        "label": "Pilot validation",
        "label_zh": "试点验证期",
        "materials": (
            "entity_identity",
            "product_technology",
            "ip",
            "pilot_evidence",
            "cash_summary",
        ),
    },
    "early_commercial": {
        "label": "Early commercial",
        "label_zh": "早期商业化",
        "materials": (
            "entity_identity",
            "product_technology",
            "customer_revenue",
            "financials",
            "unit_economics",
            "cash_summary",
            "compliance",
        ),
    },
    "scaling": {
        "label": "Scaling",
        "label_zh": "规模化",
        "materials": (
            "entity_identity",
            "product_technology",
            "customer_revenue",
            "financials",
            "unit_economics",
            "operations_supply_chain",
            "environment_impact",
            "people_safety",
            "compliance",
        ),
    },
    "mature": {
        "label": "Mature operations",
        "label_zh": "成熟经营",
        "materials": (
            "entity_identity",
            "product_technology",
            "customer_revenue",
            "financials",
            "operations_supply_chain",
            "environment_impact",
            "people_safety",
            "governance",
            "compliance",
        ),
    },
}

MATERIAL_CATALOG = {
    "entity_identity": {
        "label": "Entity and governance",
        "label_zh": "主体与治理",
        "request_zh": "营业执照、统一社会信用代码、股权结构、实际控制人、关联方与核心管理团队。",
    },
    "product_technology": {
        "label": "Product and technology",
        "label_zh": "产品与技术",
        "request_zh": "产品说明、技术路线、规格书、应用场景、研发或生产里程碑。",
    },
    "ip": {
        "label": "Intellectual property",
        "label_zh": "知识产权",
        "request_zh": "专利、商标、软著、发明人协议、转让或许可文件。",
    },
    "pilot_evidence": {
        "label": "Pilot evidence",
        "label_zh": "试点验证",
        "request_zh": "试点协议、成功标准、测试方法、原始数据、客户验收或反馈。",
    },
    "customer_revenue": {
        "label": "Customers and revenue",
        "label_zh": "客户与收入",
        "request_zh": "合同、订单、验收、发票、回款、续约/复购和客户集中度资料。",
    },
    "financials": {
        "label": "Financial statements",
        "label_zh": "财务与资金",
        "request_zh": "最近24–36个月财务报表、总账或税务资料、银行流水、应收应付、债务和预算。",
    },
    "unit_economics": {
        "label": "Unit economics",
        "label_zh": "单位经济性",
        "request_zh": "售价、材料、制造、安装、物流、渠道、售后、质保和回款周期。",
    },
    "cash_summary": {
        "label": "Cash and funding",
        "label_zh": "现金与融资",
        "request_zh": "现金余额、现金流预测、融资用途、已签融资、债务、担保和未来12个月关键里程碑。",
    },
    "operations_supply_chain": {
        "label": "Operations and supply chain",
        "label_zh": "运营与供应链",
        "request_zh": "产能、利用率、良率、库存、交付、关键供应商、替代供应商、质量和质保记录。",
    },
    "environment_impact": {
        "label": "Environmental and impact evidence",
        "label_zh": "环境与清洁技术影响",
        "request_zh": "能源、水、材料、排放、废弃物、基线、测量边界、原始数据、环评和许可。",
    },
    "people_safety": {
        "label": "People and safety",
        "label_zh": "人员与安全",
        "request_zh": "员工结构、安全制度、培训、工伤、事故、险情、申诉和职业健康记录。",
    },
    "governance": {
        "label": "Governance",
        "label_zh": "治理",
        "request_zh": "董事和管理制度、反商业贿赂、举报、关联交易、数据与隐私制度。",
    },
    "compliance": {
        "label": "Compliance and export",
        "label_zh": "合规与出海",
        "request_zh": "许可证、处罚、诉讼、保险、产品认证、出口管制、目标市场和客户要求。",
    },
}

EVIDENCE_LEVELS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}
CLAIM_STATUSES = {
    "verified",
    "partially_verified",
    "unverified",
    "conflicted",
    "refuted",
    "not_applicable",
}
VISIBILITIES = {"internal", "public_candidate", "public_approved", "restricted"}
SOURCE_LEVELS = {
    "management_statement": "E1",
    "internal_document": "E2",
    "transaction_document": "E3",
    "official_record": "E3",
    "independent_verification": "E4",
    "agent_candidate": "E1",
}


def new_company_case() -> dict[str, Any]:
    """Return an editable bilingual local-first enterprise case template."""
    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "case": {
            "id": "example-cleantech-company",
            "created_at": date.today().isoformat(),
            "language": "bilingual",
            "purpose": "enterprise_self_improvement",
        },
        "company": {
            "legal_name": "Example CleanTech Co., Ltd.",
            "display_name": "Example CleanTech",
            "display_name_zh": "示例清洁技术企业",
            "entity_identifier": {"scheme": "cn_uscc", "value": "replace-with-identifier"},
            "country": "CN",
            "industry": "define-subindustry",
            "business_model": "define-business-model",
            "stage": "pilot",
            "technology_or_solution": "Define one product, technology or project and its use case.",
            "technology_or_solution_zh": "明确一个产品、技术或项目及其使用场景。",
            "target_markets": ["CN"],
            "existing_reports": [],
        },
        "permissions": {
            "recording_and_transcription": False,
            "internal_analysis": True,
            "public_content": False,
            "identity_and_brand": False,
            "translation_and_subtitles": False,
            "ai_synthetic_media": False,
            "restricted_topics": [],
            "retention_until": None,
        },
        "interview": {
            "occurred_at": None,
            "interviewer": "",
            "participants": [],
            "summary_zh": "",
            "summary_en": "",
            "statements": [],
        },
        "claims": [],
        "evidence": [],
        "materials": [
            {"id": material_id, "status": "missing", "evidence_ids": []}
            for material_id in MATERIAL_CATALOG
        ],
        "benchmark_observations": [],
        "analysis_links": {"financial_audit_manifest": None},
        "agent_settings": {
            "enabled": False,
            "mode": "local_optional",
            "allowed_source_families": ["official_registry", "ip_office", "regulator"],
            "commercial_provider_authorized": False,
        },
    }


def _issue(level: str, code: str, text: str, text_zh: str, subject: str = "") -> dict[str, str]:
    return {"level": level, "code": code, "text": text, "text_zh": text_zh, "subject": subject}


def _as_mapping(value: Any, field_name: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(_issue("error", "invalid_type", f"{field_name} must be an object.", f"{field_name} 必须是对象。", field_name))
    return {}


def _as_list(value: Any, field_name: str, errors: list[dict[str, str]]) -> list[Any]:
    if isinstance(value, list):
        return value
    errors.append(_issue("error", "invalid_type", f"{field_name} must be an array.", f"{field_name} 必须是数组。", field_name))
    return []


def _max_evidence_level(claim: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> int:
    values = [
        EVIDENCE_LEVELS.get(str(evidence_by_id[evidence_id].get("level")), 0)
        for evidence_id in claim.get("evidence_ids", [])
        if evidence_id in evidence_by_id
    ]
    return max(values, default=0)


def _claim_minimum_level(claim: dict[str, Any]) -> int:
    requested = str(claim.get("minimum_evidence_level", "E1"))
    minimum = EVIDENCE_LEVELS.get(requested, 1)
    if claim.get("critical"):
        return max(minimum, EVIDENCE_LEVELS["E3"])
    return minimum


def _material_statuses(case: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id")): str(item.get("status"))
        for item in case.get("materials", [])
        if isinstance(item, dict)
    }


def _gate(name: str, name_zh: str, passed: bool, blockers: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "name_zh": name_zh,
        "status": "passed" if passed else "blocked",
        "blockers": blockers,
    }


def validate_company_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate a case without relying on an external service or model.

    The output is intentionally an intake/readiness result, not a risk rating.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if case.get("schema_version") != CASE_SCHEMA_VERSION:
        errors.append(_issue("error", "schema_version", f"schema_version must be {CASE_SCHEMA_VERSION}.", f"schema_version 必须为 {CASE_SCHEMA_VERSION}。", "schema_version"))

    company = _as_mapping(case.get("company"), "company", errors)
    permissions = _as_mapping(case.get("permissions"), "permissions", errors)
    interview = _as_mapping(case.get("interview"), "interview", errors)
    claims = _as_list(case.get("claims"), "claims", errors)
    evidence = _as_list(case.get("evidence"), "evidence", errors)
    materials = _as_list(case.get("materials"), "materials", errors)
    agent_settings = _as_mapping(case.get("agent_settings"), "agent_settings", errors)

    required_company = ("legal_name", "country", "industry", "business_model", "stage", "technology_or_solution")
    identity_blockers: list[dict[str, str]] = []
    for field in required_company:
        if not str(company.get(field, "")).strip() or str(company.get(field)).startswith("define-"):
            identity_blockers.append(_issue("error", "missing_company_field", f"Company field '{field}' is required.", f"企业字段 '{field}' 为必填项。", field))
    identifier = company.get("entity_identifier")
    if not isinstance(identifier, dict) or not str(identifier.get("value", "")).strip() or str(identifier.get("value")).startswith("replace-"):
        identity_blockers.append(_issue("error", "missing_entity_identifier", "A stable legal-entity identifier is required.", "需要稳定的法律主体标识。", "entity_identifier"))
    if company.get("stage") not in STAGES:
        identity_blockers.append(_issue("error", "unknown_stage", "Company stage must use a supported value.", "企业阶段必须使用支持的取值。", "stage"))
    errors.extend(identity_blockers)

    authorization_blockers: list[dict[str, str]] = []
    if permissions.get("internal_analysis") is not True:
        authorization_blockers.append(_issue("error", "internal_analysis_consent", "Internal analysis consent is required to process a company case.", "处理企业案例必须取得内部分析授权。", "permissions.internal_analysis"))
    statements = _as_list(interview.get("statements"), "interview.statements", errors)
    if statements and permissions.get("recording_and_transcription") is not True:
        authorization_blockers.append(_issue("error", "interview_consent", "Recorded statements require recording/transcription consent.", "保存访谈记录需要录音和转写授权。", "permissions.recording_and_transcription"))

    claim_ids: set[str] = set()
    statement_ids = {str(item.get("id")) for item in statements if isinstance(item, dict)}
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        if statement.get("visibility") not in VISIBILITIES:
            errors.append(_issue("error", "invalid_statement_visibility", "Statement visibility is invalid.", "访谈陈述的可见范围无效。", str(statement.get("id", ""))))
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append(_issue("error", "invalid_claim", "Each claim must be an object.", "每一条主张必须是对象。"))
            continue
        claim_id = str(claim.get("id", ""))
        if not claim_id or claim_id in claim_ids:
            errors.append(_issue("error", "duplicate_claim_id", "Every claim needs a unique id.", "每一条主张都需要唯一 ID。", claim_id))
        claim_ids.add(claim_id)
        if not str(claim.get("text_zh", "")).strip():
            errors.append(_issue("error", "claim_text_zh", "Every claim needs Chinese text.", "每一条主张都需要中文文本。", claim_id))
        if claim.get("visibility") not in VISIBILITIES:
            errors.append(_issue("error", "invalid_claim_visibility", "Claim visibility is invalid.", "主张的可见范围无效。", claim_id))
        if claim.get("status") not in CLAIM_STATUSES:
            errors.append(_issue("error", "invalid_claim_status", "Claim status is invalid.", "主张状态无效。", claim_id))
        statement_id = claim.get("statement_id")
        if statement_id and str(statement_id) not in statement_ids:
            errors.append(_issue("error", "unknown_statement", "Claim references an unknown interview statement.", "主张引用了不存在的访谈陈述。", claim_id))

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            errors.append(_issue("error", "invalid_evidence", "Each evidence item must be an object.", "每一条证据必须是对象。"))
            continue
        evidence_id = str(item.get("id", ""))
        if not evidence_id or evidence_id in evidence_by_id:
            errors.append(_issue("error", "duplicate_evidence_id", "Every evidence item needs a unique id.", "每一条证据都需要唯一 ID。", evidence_id))
        evidence_by_id[evidence_id] = item
        source_type = str(item.get("source_type", ""))
        expected_level = SOURCE_LEVELS.get(source_type)
        if not expected_level:
            errors.append(_issue("error", "invalid_evidence_source", "Evidence source type is invalid.", "证据来源类型无效。", evidence_id))
        elif item.get("level") != expected_level:
            errors.append(_issue("error", "evidence_level_mismatch", f"{source_type} must use {expected_level}.", f"{source_type} 必须使用 {expected_level} 证据等级。", evidence_id))
        if not str(item.get("title", "")).strip() or not str(item.get("captured_at", "")).strip():
            errors.append(_issue("error", "evidence_provenance", "Evidence title and captured_at are required.", "证据标题和获取时间为必填项。", evidence_id))
        if source_type == "agent_candidate":
            if not item.get("agent_run_id") or not item.get("raw_artifact"):
                errors.append(_issue("error", "agent_provenance", "Agent evidence needs agent_run_id and raw_artifact.", "Agent 证据必须包含 agent_run_id 和原始产物路径。", evidence_id))
            if item.get("review_status") == "accepted":
                errors.append(_issue("error", "agent_cannot_auto_accept", "Agent evidence must be reviewed by a human before acceptance.", "Agent 证据必须经人工审核后才能接受。", evidence_id))

    evidence_blockers: list[dict[str, str]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id", ""))
        evidence_ids = claim.get("evidence_ids", [])
        if not isinstance(evidence_ids, list):
            errors.append(_issue("error", "claim_evidence_ids", "claim.evidence_ids must be an array.", "claim.evidence_ids 必须是数组。", claim_id))
            continue
        unknown_ids = [str(item) for item in evidence_ids if str(item) not in evidence_by_id]
        if unknown_ids:
            errors.append(_issue("error", "unknown_claim_evidence", "Claim references unknown evidence.", "主张引用了不存在的证据。", claim_id))
        available_level = _max_evidence_level(claim, evidence_by_id)
        required_level = _claim_minimum_level(claim)
        if claim.get("status") == "verified" and available_level < required_level:
            errors.append(_issue("error", "unproven_verified_claim", "A verified claim lacks the required evidence level.", "已验证主张没有达到所需证据等级。", claim_id))
        if claim.get("critical") and claim.get("status") not in {"verified", "not_applicable"}:
            evidence_blockers.append(_issue("error", "critical_claim_open", "A critical claim remains unresolved.", "关键主张仍未完成验证。", claim_id))
        if claim.get("visibility") == "public_approved":
            if claim.get("status") != "verified":
                errors.append(_issue("error", "public_unverified_claim", "Public-approved claims must be verified.", "对外发布的主张必须已验证。", claim_id))
            if permissions.get("public_content") is not True or permissions.get("identity_and_brand") is not True:
                errors.append(_issue("error", "public_consent_missing", "Public content and identity/brand consent are required.", "对外内容与身份/品牌授权均为必需。", claim_id))

    if permissions.get("public_content") is True and permissions.get("translation_and_subtitles") is not True:
        warnings.append(_issue("warning", "translation_not_authorized", "Public content is enabled but bilingual publication is not authorized.", "已授权公开内容，但尚未授权双语翻译和字幕。", "permissions"))
    if agent_settings.get("enabled") and not agent_settings.get("allowed_source_families"):
        errors.append(_issue("error", "agent_allowlist", "Enabled local agents need an allowed-source allowlist.", "启用本地 Agent 时必须设置允许来源白名单。", "agent_settings"))

    material_statuses = _material_statuses(case)
    required_materials = STAGES.get(company.get("stage"), {}).get("materials", ())
    material_blockers = [
        _issue(
            "error",
            "required_material_missing",
            f"Required material is missing: {material_id}.",
            f"必需材料缺失：{MATERIAL_CATALOG[material_id]['label_zh']}。",
            material_id,
        )
        for material_id in required_materials
        if material_statuses.get(material_id) not in {"provided", "not_applicable"}
    ]
    if len(materials) < len(MATERIAL_CATALOG):
        warnings.append(_issue("warning", "incomplete_material_register", "The material register is incomplete.", "材料登记表尚不完整。", "materials"))

    public_blockers = [
        _issue("error", "public_content_consent", "Public content claims require explicit public-content consent.", "对外内容主张需要明确的公开内容授权。", "permissions")
    ] if any(isinstance(item, dict) and item.get("visibility") == "public_approved" for item in claims) and permissions.get("public_content") is not True else []

    gates = [
        _gate("authorization", "授权闸门", not authorization_blockers, authorization_blockers),
        _gate("identity_scope", "主体与范围闸门", not identity_blockers, identity_blockers),
        _gate("minimum_evidence", "最低证据闸门", not material_blockers and not evidence_blockers, material_blockers + evidence_blockers),
        _gate(
            "assessment_eligibility",
            "分析资格闸门",
            not identity_blockers and not material_blockers and not evidence_blockers,
            identity_blockers + material_blockers + evidence_blockers,
        ),
        _gate("publication", "发布闸门", not public_blockers, public_blockers),
    ]
    errors.extend(material_blockers)
    errors.extend(evidence_blockers)
    public_claims = [item for item in claims if isinstance(item, dict) and item.get("visibility") == "public_approved"]
    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "gates": gates,
        "summary": {
            "claim_count": len([item for item in claims if isinstance(item, dict)]),
            "evidence_count": len(evidence_by_id),
            "verified_claim_count": sum(isinstance(item, dict) and item.get("status") == "verified" for item in claims),
            "public_approved_claim_count": len(public_claims),
            "required_material_count": len(required_materials),
            "provided_required_material_count": sum(material_statuses.get(item) in {"provided", "not_applicable"} for item in required_materials),
            "evidence_levels": dict(sorted(Counter(str(item.get("level")) for item in evidence_by_id.values()).items())),
        },
        "guardrails": {
            "investment_rating": False,
            "credit_rating": False,
            "automated_arl_score": False,
            "agent_candidate_is_not_verified_fact": True,
            "human_review_required": True,
        },
    }


def material_request_plan(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a stage-specific request list, preserving not-applicable entries."""
    stage = case.get("company", {}).get("stage")
    statuses = _material_statuses(case)
    requested = STAGES.get(stage, {}).get("materials", ())
    return [
        {
            "id": material_id,
            "label": MATERIAL_CATALOG[material_id]["label"],
            "label_zh": MATERIAL_CATALOG[material_id]["label_zh"],
            "request_zh": MATERIAL_CATALOG[material_id]["request_zh"],
            "status": statuses.get(material_id, "missing"),
            "required": True,
        }
        for material_id in requested
    ]


def interview_guide(case: dict[str, Any]) -> list[dict[str, str]]:
    """Return a local bilingual 30-minute interview plan tailored by declared stage."""
    stage = case.get("company", {}).get("stage", "pilot")
    stage_label = STAGES.get(stage, STAGES["pilot"])["label_zh"]
    return [
        {"time": "00:00–02:00", "topic_zh": "授权与边界", "visibility": "internal", "question_zh": "请分别确认录音转写、内部分析、对外发布、身份品牌使用和双语翻译授权；哪些内容不能公开？"},
        {"time": "02:00–05:00", "topic_zh": "企业一句话与阶段", "visibility": "public_candidate", "question_zh": f"你为哪类客户解决什么昂贵问题？为什么客户会付费？我们当前暂定你处于{stage_label}，哪里需要纠正？"},
        {"time": "05:00–08:00", "topic_zh": "创始人起点与使命", "visibility": "public_candidate", "question_zh": "哪段真实经历让你决定做这家公司？如果问题不被解决，谁会承担什么代价？"},
        {"time": "08:00–12:00", "topic_zh": "市场观点与愿景", "visibility": "public_candidate", "question_zh": "未来三年行业最容易被看错的事情是什么？什么事实会证明你的判断错了？"},
        {"time": "12:00–17:00", "topic_zh": "产品、技术与环境价值", "visibility": "internal", "question_zh": "用一个案例说明产品把什么指标从多少变到多少；基线、边界、测量周期和替代方案是什么？"},
        {"time": "17:00–20:00", "topic_zh": "客户与商业证据", "visibility": "internal", "question_zh": "最硬的商业证据是什么：付费、回款、复购、扩单还是试点转化？请给出一个可以后续验证的案例。"},
        {"time": "20:00–23:00", "topic_zh": "规模化瓶颈", "visibility": "internal", "question_zh": "如果订单明天翻倍，供应链、产能、质量、许可、交付、人员和现金中谁会先卡住？"},
        {"time": "23:00–27:00", "topic_zh": "现金、融资与重大风险", "visibility": "restricted", "question_zh": "一单收入如何形成，主要直接成本和回款周期是什么？未来12个月的关键里程碑、资金缺口和最大风险是什么？"},
        {"time": "27:00–30:00", "topic_zh": "反证、补件与收尾", "visibility": "internal", "question_zh": "如果只能验证一个主张，你最希望验证哪个？三天内能提供哪些材料？哪些片段可以公开？"},
    ]


def build_agent_tasks(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Create optional local-agent tasks; task outputs remain candidate evidence."""
    company = case.get("company", {})
    identifier = company.get("entity_identifier", {})
    settings = case.get("agent_settings", {})
    allowlist = list(settings.get("allowed_source_families", []))
    if not settings.get("enabled"):
        return []
    base = {
        "case_id": case.get("case", {}).get("id"),
        "entity": {"legal_name": company.get("legal_name"), "identifier": identifier},
        "mode": "local_optional",
        "allowed_source_families": allowlist,
        "return_contract": {
            "source_type": "agent_candidate",
            "required_fields": ["raw_artifact", "url_or_source_id", "captured_at", "sha256", "entity_match", "fields", "errors"],
            "authority_boundary": "Candidate evidence only. A human must review before it can support a verified fact.",
        },
    }
    tasks = []
    for task_id, purpose, source_family in (
        ("entity-registry", "Confirm legal entity, status, name history and basic registration.", "official_registry"),
        ("intellectual-property", "Collect public patent/trademark candidates and ownership fields.", "ip_office"),
        ("regulatory-risk", "Collect public permits, penalties and disclosed regulatory notices.", "regulator"),
        ("public-risk", "Collect public court, enforcement or credit candidates where legally available.", "court"),
    ):
        if source_family in allowlist:
            task = deepcopy(base)
            task.update({"id": task_id, "purpose": purpose, "source_family": source_family})
            tasks.append(task)
    return tasks


def benchmark_summary(case: dict[str, Any]) -> dict[str, Any]:
    """Compute only descriptive local comparisons for a declared comparable cohort."""
    company = case.get("company", {})
    cohort = {
        "industry": company.get("industry"),
        "stage": company.get("stage"),
        "business_model": company.get("business_model"),
        "country": company.get("country"),
    }
    observations = [item for item in case.get("benchmark_observations", []) if isinstance(item, dict)]
    groups: dict[str, list[float]] = defaultdict(list)
    for item in observations:
        if item.get("cohort") != cohort:
            continue
        value = item.get("value")
        if isinstance(value, (int, float)):
            groups[str(item.get("metric", ""))].append(float(value))
    metrics = []
    for metric, values in sorted(groups.items()):
        values.sort()
        if len(values) < MIN_BENCHMARK_SAMPLE:
            metrics.append({"metric": metric, "sample_size": len(values), "status": "insufficient_sample", "range": [values[0], values[-1]], "median": median(values), "percentile": None})
            continue
        metrics.append({"metric": metric, "sample_size": len(values), "status": "descriptive_only", "range": [values[0], values[-1]], "median": median(values), "percentile": "available only after a subject metric with matching scope is supplied"})
    return {
        "cohort": cohort,
        "minimum_sample_size": MIN_BENCHMARK_SAMPLE,
        "metrics": metrics,
        "guardrail": "No cross-stage ranking, composite score or investment conclusion is produced.",
    }


def assessment_plan(case: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Describe the permitted assessment route without fabricating a score.

    This is a routing plan. It keeps the evidence framework useful for SMEs
    while making explicit which professional modules are not yet validated.
    """
    validation = validation or validate_company_case(case)
    company = case.get("company", {})
    reports = {str(item).lower() for item in company.get("existing_reports", [])}
    has_esg_report = any("esg" in item or "sustainability" in item for item in reports)
    financial_manifest = case.get("analysis_links", {}).get("financial_audit_manifest")
    gate = next(item for item in validation["gates"] if item["id"] == "assessment_eligibility")
    common_state = "eligible_for_human_review" if gate["status"] == "passed" else "blocked_by_intake_gates"
    return {
        "route": "report_led_esg_review" if has_esg_report else "sme_evidence_readiness",
        "route_zh": "ESG报告核验路线" if has_esg_report else "中小企业证据准备度路线",
        "assessment_gate": gate["status"],
        "modules": [
            {
                "id": "evidence_disclosure_quality",
                "state": common_state,
                "state_zh": "可进入人工审核" if common_state == "eligible_for_human_review" else "受入驻闸门阻塞",
                "output": "Evidence coverage, conflicts and missing-material register; no risk score.",
            },
            {
                "id": "esg",
                "state": "evidence_framework_only",
                "state_zh": "证据框架，尚无自动认证评分",
                "output": "Report applicability or SME ESG data pack and action list.",
            },
            {
                "id": "cleantech_impact",
                "state": "evidence_framework_only",
                "state_zh": "证据框架，尚无自动认证评分",
                "output": "Baseline, boundary, method and verification requirements for environmental claims.",
            },
            {
                "id": "doe_arl",
                "state": "retrieval_scaffold_only",
                "state_zh": "检索脚手架，不自动生成 ARL",
                "output": "Technology/product-specific evidence questions only; no DOE endorsement or 1–9 score.",
            },
            {
                "id": "financial_evidence_core",
                "state": "ready_to_run" if financial_manifest else "manifest_required",
                "state_zh": "可调用已验证财务内核" if financial_manifest else "需要财务审计 manifest",
                "output": "Validated deterministic cards only for profitability/unit economics and cash flow/funding gap.",
                "manifest": financial_manifest,
            },
            {
                "id": "export_customer_readiness",
                "state": "evidence_framework_only",
                "state_zh": "证据框架，尚无自动认证评分",
                "output": "Target-market, certification, supply-chain and customer-questionnaire material plan.",
            },
        ],
        "guardrails": {
            "no_aggregate_score": True,
            "no_investment_or_credit_rating": True,
            "no_automatic_esg_assurance": True,
            "no_automatic_arl_score": True,
        },
    }
