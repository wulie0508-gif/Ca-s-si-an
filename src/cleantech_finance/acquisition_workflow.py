"""Deterministic, candidate-only workflow diagnostics for cross-border acquisitions.

This module intentionally has no dependency on the HTTP bridge or workspace service.
It consumes their public artifact shape, but never treats recognition output as verified
facts and never decides a transaction gate.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "acquisition-workflow-1.2.0"
REQUIREMENT_CANDIDATE_SCHEMA_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent / "config" / "acquisition-workflow.default.json"
)

ROLE_LABELS = {
    "deal_sponsor": "交易发起人",
    "corporate_development": "企业发展/并购负责人",
    "industry_research": "行业研究",
    "finance_valuation": "财务与估值",
    "financing": "融资",
    "legal": "法律",
    "tax": "税务",
    "regulatory": "监管合规",
    "technology_ip": "技术与知识产权",
    "quality_ehs": "质量与EHS",
    "project_management": "项目管理",
    "integration_lead": "并购后整合负责人",
    "human_decision_body": "人工决策机构",
}

WORKSTREAMS: tuple[dict[str, str], ...] = (
    {
        "id": "commercial_industry_research",
        "name_zh": "商业与行业研究",
        "scope_zh": "产业链、市场、客户、竞争与商业协同候选分析。",
    },
    {
        "id": "finance_valuation_financing",
        "name_zh": "财务、估值与融资",
        "scope_zh": "财务核验、估值模型、资金来源与融资条件。",
    },
    {
        "id": "legal_tax_regulatory",
        "name_zh": "法律、税务与监管",
        "scope_zh": "交易文件、税务结构和条件化监管筛查。",
    },
    {
        "id": "technology_ip_quality_ehs",
        "name_zh": "技术、IP、质量与EHS",
        "scope_zh": "技术、知识产权、质量体系、环境健康安全核验。",
    },
    {
        "id": "project_management_communication_pmi",
        "name_zh": "项目管理、沟通与并购后整合",
        "scope_zh": "节奏、责任、沟通、交割准备与整合跟踪。",
    },
)


def _requirement(
    requirement_id: str,
    label_zh: str,
    *,
    accepted_materials: tuple[str, ...],
    fields: tuple[str, ...],
    criticality: str,
    owner_roles: tuple[str, ...],
    candidate_roles: tuple[str, ...] = (),
    profile_hint_fields: tuple[str, ...] = (),
    match_policy: str = "any",
    interview_question_zh: str,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "label_zh": label_zh,
        "accepted_materials": accepted_materials,
        "fields": fields,
        "criticality": criticality,
        "owner_roles": owner_roles,
        "candidate_roles": candidate_roles,
        "profile_hint_fields": profile_hint_fields,
        "match_policy": match_policy,
        "interview_question_zh": interview_question_zh,
    }


def _trigger(
    trigger_id: str,
    label_zh: str,
    *,
    condition_zh: str,
    screening_fields: tuple[str, ...],
    owner_roles: tuple[str, ...],
    candidate_role_signals: tuple[str, ...] = (),
    profile_keywords: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": trigger_id,
        "label_zh": label_zh,
        "condition_zh": condition_zh,
        "screening_fields": screening_fields,
        "owner_roles": owner_roles,
        "candidate_role_signals": candidate_role_signals,
        "profile_keywords": profile_keywords,
        "authority": "screening_question_only",
    }


STAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "strategy_and_mandate",
        "order": 1,
        "name_zh": "收购战略与委托确认",
        "name_en": "Acquisition strategy and mandate",
        "core_task_zh": "明确买什么、为什么买、预算、股权比例和红线",
        "deliverables": ("Acquisition Brief", "Target Criteria"),
        "decision_gate": "是否正式启动",
        "responsible_roles": (
            "deal_sponsor",
            "corporate_development",
            "finance_valuation",
            "legal",
        ),
        "workstream_ids": (
            "commercial_industry_research",
            "finance_valuation_financing",
            "legal_tax_regulatory",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "acquisition_thesis",
                "收购逻辑与目标边界",
                accepted_materials=("Acquisition Brief", "战略说明", "董事会立项材料"),
                fields=("strategic_rationale", "target_scope", "red_lines"),
                criticality="critical",
                owner_roles=("deal_sponsor", "corporate_development"),
                candidate_roles=("company_identity", "market_export", "technology_arl"),
                profile_hint_fields=("industry", "technology", "market", "need"),
                match_policy="role_and_profile",
                interview_question_zh="本次收购要解决的核心战略问题、目标边界和不可接受红线分别是什么？",
            ),
            _requirement(
                "transaction_parameters",
                "预算、股权比例与交易参数",
                accepted_materials=("Target Criteria", "预算授权", "交易参数表"),
                fields=("budget_range", "ownership_range", "funding_source", "timeline"),
                criticality="critical",
                owner_roles=("deal_sponsor", "finance_valuation", "corporate_development"),
                candidate_roles=("financial_core", "company_identity"),
                profile_hint_fields=("stage", "need"),
                match_policy="role_and_profile",
                interview_question_zh="预算区间、目标持股比例、资金来源与计划时间表目前分别是什么？",
            ),
            _requirement(
                "mandate_authorization",
                "委托与内部授权",
                accepted_materials=("委托书", "立项批准", "授权矩阵"),
                fields=("mandate_owner", "approval_body", "approval_limit"),
                criticality="important",
                owner_roles=("deal_sponsor", "legal", "project_management"),
                candidate_roles=("governance_legal",),
                match_policy="roles_only",
                interview_question_zh="谁拥有项目委托权、谁构成最终决策机构、授权额度到哪里？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "strategy_market_access_screen",
                "中国外商投资准入与行业限制初筛",
                condition_zh="仅当交易将形成外资持股或控制，且标的业务可能落入限制或特别管理领域时触发。",
                screening_fields=("target_industry", "ownership_plan", "control_rights"),
                owner_roles=("legal", "regulatory"),
                candidate_role_signals=("governance_legal", "policy_resource"),
                profile_keywords=("中国", "china", "氢能", "hydrogen"),
            ),
        ),
    },
    {
        "id": "industry_research_and_longlist",
        "order": 2,
        "name_zh": "产业研究与 Longlist",
        "name_en": "Industry research and longlist",
        "core_task_zh": "拆解氢能产业链，广泛搜寻中国标的",
        "deliverables": ("产业地图", "Longlist", "信息来源库"),
        "decision_gate": "哪些进入初筛",
        "responsible_roles": (
            "industry_research",
            "corporate_development",
            "technology_ip",
            "project_management",
        ),
        "workstream_ids": (
            "commercial_industry_research",
            "technology_ip_quality_ehs",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "industry_map",
                "产业链与技术路线地图",
                accepted_materials=("产业地图", "技术路线研究", "市场研究"),
                fields=("value_chain_segment", "technology_route", "market_size_basis"),
                criticality="critical",
                owner_roles=("industry_research", "technology_ip"),
                candidate_roles=("market_export", "technology_arl", "policy_resource"),
                profile_hint_fields=("industry", "technology", "market"),
                match_policy="role_and_profile",
                interview_question_zh="标的位于哪一段产业链、采用什么技术路线，其目标市场依据来自哪里？",
            ),
            _requirement(
                "longlist_universe",
                "候选标的 Longlist",
                accepted_materials=("Longlist", "企业名录", "筛选底表"),
                fields=("target_name", "location", "segment", "ownership", "source_id"),
                criticality="critical",
                owner_roles=("industry_research", "corporate_development"),
                candidate_roles=("company_identity", "market_export"),
                profile_hint_fields=("geography", "industry"),
                match_policy="role_and_profile",
                interview_question_zh="当前候选标的清单如何形成，覆盖了哪些地区、产业环节和所有制类型？",
            ),
            _requirement(
                "source_register",
                "信息来源与可追溯记录",
                accepted_materials=("信息来源库", "检索日志", "出处台账"),
                fields=("source_url", "retrieved_at", "source_owner", "source_scope"),
                criticality="important",
                owner_roles=("industry_research", "project_management"),
                candidate_roles=("policy_resource",),
                match_policy="roles_only",
                interview_question_zh="Longlist 中每个候选项的来源、检索日期和适用范围能否逐项追溯？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "longlist_sanctions_export_screen",
                "制裁、出口管制与受限主体初筛",
                condition_zh="仅当候选主体、股东、最终用户、技术或目的地可能受相关规则约束时触发。",
                screening_fields=("beneficial_owner", "end_user", "controlled_technology", "destination"),
                owner_roles=("legal", "regulatory", "technology_ip"),
                candidate_role_signals=("governance_legal", "technology_arl", "policy_resource"),
                profile_keywords=("美国", "usa", "us", "跨境", "export"),
            ),
        ),
    },
    {
        "id": "shortlist_and_preliminary_valuation",
        "order": 3,
        "name_zh": "Shortlist 与初步估值",
        "name_en": "Shortlist and preliminary valuation",
        "core_task_zh": "战略协同、技术、财务、可交易性和监管评分",
        "deliverables": ("Screening Matrix", "Target Profile", "估值区间"),
        "decision_gate": "是否接触",
        "responsible_roles": (
            "corporate_development",
            "industry_research",
            "finance_valuation",
            "technology_ip",
            "legal",
            "regulatory",
        ),
        "workstream_ids": (
            "commercial_industry_research",
            "finance_valuation_financing",
            "legal_tax_regulatory",
            "technology_ip_quality_ehs",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "target_business_profile",
                "标的身份、产品与业务范围",
                accepted_materials=("Target Profile", "公司简介", "产品与业务清单"),
                fields=("legal_name", "product", "technology", "location", "business_scope"),
                criticality="critical",
                owner_roles=("corporate_development", "industry_research"),
                candidate_roles=("company_identity", "technology_arl"),
                profile_hint_fields=("industry", "technology", "geography"),
                match_policy="role_and_profile",
                interview_question_zh="请确认标的法律主体、核心产品、技术路线、经营地域和实际业务边界。",
            ),
            _requirement(
                "commercial_model_baseline",
                "客户、收入来源与商业模式材料",
                accepted_materials=("客户结构", "订单或合同样本", "商业模式说明", "市场计划"),
                fields=("customer_segments", "revenue_streams", "pricing", "sales_cycle", "unit_economics_basis"),
                criticality="critical",
                owner_roles=("industry_research", "finance_valuation", "corporate_development"),
                candidate_roles=("market_export", "financial_core", "company_identity"),
                profile_hint_fields=("market", "need"),
                match_policy="role_and_profile",
                interview_question_zh="标的服务谁、如何收费、销售周期多长，收入与单位经济性依据分别是什么？",
            ),
            _requirement(
                "preliminary_valuation",
                "初步财务与估值区间",
                accepted_materials=("历史财务", "预算预测", "估值模型", "可比交易资料"),
                fields=("historical_financials", "forecast", "valuation_method", "valuation_range"),
                criticality="critical",
                owner_roles=("finance_valuation",),
                candidate_roles=("financial_core",),
                match_policy="roles_only",
                interview_question_zh="初步估值使用了哪些财务口径、预测假设和可比依据，区间如何形成？",
            ),
            _requirement(
                "screening_matrix",
                "多维初筛矩阵",
                accepted_materials=("Screening Matrix", "Shortlist 决策记录"),
                fields=("strategic_fit", "technology_fit", "financial_fit", "dealability", "regulatory_questions"),
                criticality="important",
                owner_roles=("corporate_development", "project_management"),
                candidate_roles=(
                    "company_identity",
                    "financial_core",
                    "technology_arl",
                    "market_export",
                    "governance_legal",
                ),
                match_policy="roles_only",
                interview_question_zh="Shortlist 的战略、技术、财务、可交易性和监管维度使用了哪些统一口径？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "preliminary_merger_control_screen",
                "中国经营者集中及其他合并申报门槛初筛",
                condition_zh="仅当交易结构和相关主体规模可能达到适用申报门槛时触发。",
                screening_fields=("transaction_structure", "group_turnover", "china_turnover", "control_change"),
                owner_roles=("legal", "regulatory", "finance_valuation"),
                candidate_role_signals=("financial_core", "governance_legal"),
            ),
            _trigger(
                "us_asset_cfius_screen",
                "美国业务或资产的 CFIUS 适用性初筛",
                condition_zh="仅当标的含美国业务、资产、敏感数据或交易结构可能形成美国受管辖交易时触发；不得因买方为美国主体而自动认定。",
                screening_fields=("us_business", "us_assets", "sensitive_data", "covered_transaction_basis"),
                owner_roles=("legal", "regulatory"),
                candidate_role_signals=("governance_legal",),
                profile_keywords=("美国", "usa", "us"),
            ),
        ),
    },
    {
        "id": "initial_contact_and_nda",
        "order": 4,
        "name_zh": "初步接触与 NDA",
        "name_en": "Initial contact and NDA",
        "core_task_zh": "匿名接触、确认交易意愿、签署保密协议",
        "deliverables": ("接触记录", "NDA", "管理层会议材料"),
        "decision_gate": "是否继续",
        "responsible_roles": (
            "corporate_development",
            "legal",
            "project_management",
            "deal_sponsor",
        ),
        "workstream_ids": (
            "commercial_industry_research",
            "legal_tax_regulatory",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "contact_and_interest_record",
                "接触、权限与交易意愿记录",
                accepted_materials=("接触记录", "沟通纪要", "授权联系人清单"),
                fields=("contact_owner", "contact_date", "counterparty_authority", "interest_status"),
                criticality="critical",
                owner_roles=("corporate_development", "project_management"),
                candidate_roles=("company_identity",),
                match_policy="roles_only",
                interview_question_zh="谁代表双方接触、对方是否获授权、交易意愿和保留条件分别是什么？",
            ),
            _requirement(
                "nda_record",
                "已签署 NDA 与保密边界",
                accepted_materials=("NDA", "保密信息范围", "签署页"),
                fields=("nda_parties", "effective_date", "confidential_scope", "permitted_recipients"),
                criticality="critical",
                owner_roles=("legal", "corporate_development"),
                candidate_roles=("governance_legal",),
                match_policy="roles_only",
                interview_question_zh="NDA 覆盖哪些主体、信息和获准接收人，何时生效并有哪些例外？",
            ),
            _requirement(
                "management_meeting_pack",
                "管理层会议材料",
                accepted_materials=("管理层会议材料", "管理层问答", "会议纪要"),
                fields=("meeting_scope", "attendees", "questions", "follow_ups"),
                criticality="important",
                owner_roles=("corporate_development", "project_management"),
                candidate_roles=("company_identity",),
                match_policy="roles_only",
                interview_question_zh="首次管理层会议需要验证哪些假设，由谁回答并如何记录后续材料承诺？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "cross_border_data_room_screen",
                "跨境数据室与个人信息初筛",
                condition_zh="仅当拟共享材料含个人信息、重要数据、受限技术数据或依法不得跨境的信息时触发。",
                screening_fields=("data_categories", "data_location", "recipient_location", "sharing_legal_basis"),
                owner_roles=("legal", "regulatory", "technology_ip"),
                candidate_role_signals=("governance_legal", "technology_arl"),
                profile_keywords=("跨境", "美国", "usa", "us"),
            ),
        ),
    },
    {
        "id": "ioi_loi_and_exclusivity",
        "order": 5,
        "name_zh": "IOI / LOI 与排他",
        "name_en": "IOI, LOI and exclusivity",
        "core_task_zh": "明确价格、比例、结构、留任及交易前提",
        "deliverables": ("IOI 或 LOI", "排他协议"),
        "decision_gate": "是否进入全面尽调",
        "responsible_roles": (
            "deal_sponsor",
            "corporate_development",
            "finance_valuation",
            "legal",
            "tax",
            "project_management",
        ),
        "workstream_ids": (
            "commercial_industry_research",
            "finance_valuation_financing",
            "legal_tax_regulatory",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "ioi_loi_terms",
                "IOI/LOI 核心条款",
                accepted_materials=("IOI", "LOI", "核心条款表"),
                fields=("price_range", "ownership", "structure", "conditions", "validity"),
                criticality="critical",
                owner_roles=("corporate_development", "finance_valuation", "legal"),
                candidate_roles=("financial_core", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="IOI/LOI 中价格、比例、结构、有效期和主要前提分别如何约定？",
            ),
            _requirement(
                "management_retention_terms",
                "管理层留任与激励假设",
                accepted_materials=("留任方案", "激励框架", "关键人员清单"),
                fields=("key_people", "retention_period", "incentive_terms", "succession_risk"),
                criticality="important",
                owner_roles=("deal_sponsor", "corporate_development", "legal"),
                candidate_roles=("company_identity", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="哪些管理层与技术骨干必须留任，期限、激励和替代安排是什么？",
            ),
            _requirement(
                "exclusivity_record",
                "排他范围与期限",
                accepted_materials=("排他协议", "排他条款", "违约与退出机制"),
                fields=("exclusivity_scope", "start_date", "end_date", "termination", "remedy"),
                criticality="important",
                owner_roles=("legal", "corporate_development"),
                candidate_roles=("governance_legal",),
                match_policy="roles_only",
                interview_question_zh="排他覆盖哪些行为、持续多久、如何终止以及违约后果是什么？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "loi_foreign_investment_security_screen",
                "中国外商投资安全审查候选触发筛查",
                condition_zh="仅当交易行业、实际控制、关键技术或其他法定因素可能满足适用条件时触发。",
                screening_fields=("industry", "control_rights", "key_technology", "national_security_nexus"),
                owner_roles=("legal", "regulatory"),
                candidate_role_signals=("governance_legal", "technology_arl", "policy_resource"),
                profile_keywords=("氢能", "hydrogen", "能源", "energy"),
            ),
        ),
    },
    {
        "id": "diligence_and_transaction_structure",
        "order": 6,
        "name_zh": "尽调与交易结构",
        "name_en": "Due diligence and transaction structure",
        "core_task_zh": "商业、财务、法律、税务、技术、IP、EHS、监管",
        "deliverables": ("DD 报告", "红旗清单", "交易模型", "结构方案"),
        "decision_gate": "投资委员会是否批准",
        "responsible_roles": (
            "corporate_development",
            "finance_valuation",
            "legal",
            "tax",
            "regulatory",
            "technology_ip",
            "quality_ehs",
            "human_decision_body",
        ),
        "workstream_ids": tuple(item["id"] for item in WORKSTREAMS),
        "requirements": (
            _requirement(
                "commercial_diligence",
                "商业尽调材料",
                accepted_materials=("商业尽调报告", "客户访谈", "订单与合同样本", "市场数据"),
                fields=("customer_concentration", "order_quality", "competition", "market_assumptions"),
                criticality="critical",
                owner_roles=("industry_research", "corporate_development"),
                candidate_roles=("market_export", "company_identity"),
                match_policy="roles_only",
                interview_question_zh="客户集中、订单质量、竞争位置和市场假设分别由哪些底层材料支持？",
            ),
            _requirement(
                "financial_tax_diligence",
                "财务与税务尽调材料",
                accepted_materials=("审计报告", "总账与明细", "税务申报", "财务尽调报告"),
                fields=("quality_of_earnings", "net_debt", "working_capital", "tax_exposure"),
                criticality="critical",
                owner_roles=("finance_valuation", "tax"),
                candidate_roles=("financial_core",),
                match_policy="roles_only",
                interview_question_zh="盈利质量、净债务、营运资金和税务事项分别需要哪些可核验底表？",
            ),
            _requirement(
                "legal_regulatory_diligence",
                "法律与监管尽调材料",
                accepted_materials=("公司档案", "重大合同", "许可清单", "诉讼清单", "合规报告"),
                fields=("ownership", "material_contracts", "permits", "litigation", "compliance"),
                criticality="critical",
                owner_roles=("legal", "regulatory"),
                candidate_roles=("governance_legal", "policy_resource"),
                match_policy="roles_only",
                interview_question_zh="股权、重大合同、许可、诉讼和合规事项中哪些尚未形成完整可核验清单？",
            ),
            _requirement(
                "technology_ip_quality_ehs_diligence",
                "技术、IP、质量与 EHS 尽调材料",
                accepted_materials=("技术尽调", "IP 清单", "质量体系", "EHS 许可与记录"),
                fields=("technology_status", "ip_ownership", "quality_system", "ehs_permits", "incidents"),
                criticality="critical",
                owner_roles=("technology_ip", "quality_ehs", "legal"),
                candidate_roles=("technology_arl", "esg_impact", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="技术状态、IP 权属、质量体系、EHS 许可和事故记录分别有哪些原始材料？",
            ),
            _requirement(
                "transaction_model_and_structure",
                "交易模型与结构方案",
                accepted_materials=("交易模型", "结构方案", "资金路径", "税务结构备忘录"),
                fields=("purchase_price_bridge", "funding", "legal_structure", "tax_structure", "sensitivity"),
                criticality="critical",
                owner_roles=("finance_valuation", "financing", "legal", "tax"),
                candidate_roles=("financial_core", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="交易模型如何衔接购买价、融资、法律结构、税务结构和敏感性假设？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "dd_data_cybersecurity_screen",
                "数据安全、网络安全与跨境传输深入筛查",
                condition_zh="仅当标的处理个人信息、重要数据、关键信息基础设施数据或拟跨境传输时触发。",
                screening_fields=("data_inventory", "processing_scale", "critical_infrastructure", "transfer_mechanism"),
                owner_roles=("legal", "regulatory", "technology_ip"),
                candidate_role_signals=("governance_legal", "technology_arl"),
                profile_keywords=("数据", "data", "跨境"),
            ),
            _trigger(
                "dd_technology_transfer_export_screen",
                "技术进出口与出口管制深入筛查",
                condition_zh="仅当交易涉及受限或受控技术、软件、设备、技术许可或跨境技术转移时触发。",
                screening_fields=("technology_classification", "export_control_code", "license", "transfer_route"),
                owner_roles=("technology_ip", "legal", "regulatory"),
                candidate_role_signals=("technology_arl", "governance_legal", "policy_resource"),
                profile_keywords=("技术", "technology", "出口", "export"),
            ),
            _trigger(
                "dd_ehs_permit_screen",
                "EHS 许可与历史责任筛查",
                condition_zh="仅当运营、资产或历史活动涉及环境、职业健康、安全许可或潜在责任时触发。",
                screening_fields=("site", "permit", "emission", "incident", "remediation"),
                owner_roles=("quality_ehs", "legal"),
                candidate_role_signals=("esg_impact", "governance_legal"),
                profile_keywords=("能源", "energy", "制造", "manufacturing"),
            ),
        ),
    },
    {
        "id": "signing_approval_and_closing",
        "order": 7,
        "name_zh": "签约、审批与交割",
        "name_en": "Signing, approvals and closing",
        "core_task_zh": "谈判 SPA、完成融资及监管审批、满足交割条件",
        "deliverables": ("SPA", "审批文件", "Closing Checklist"),
        "decision_gate": "是否完成交割",
        "responsible_roles": (
            "deal_sponsor",
            "corporate_development",
            "finance_valuation",
            "financing",
            "legal",
            "tax",
            "regulatory",
            "project_management",
            "human_decision_body",
        ),
        "workstream_ids": (
            "finance_valuation_financing",
            "legal_tax_regulatory",
            "project_management_communication_pmi",
        ),
        "requirements": (
            _requirement(
                "spa_and_disclosure",
                "SPA 与披露文件",
                accepted_materials=("SPA", "披露函", "披露附件", "签署授权"),
                fields=("price_mechanics", "representations", "indemnity", "conditions_precedent"),
                criticality="critical",
                owner_roles=("legal", "corporate_development"),
                candidate_roles=("governance_legal",),
                match_policy="roles_only",
                interview_question_zh="SPA 的价格机制、陈述保证、赔偿和交割前提如何落到可执行文件？",
            ),
            _requirement(
                "financing_commitments",
                "融资承诺与资金可用性",
                accepted_materials=("融资承诺", "资金证明", "提款条件", "资金流向表"),
                fields=("committed_amount", "conditions", "funds_flow", "expiry"),
                criticality="critical",
                owner_roles=("financing", "finance_valuation"),
                candidate_roles=("financial_core",),
                match_policy="roles_only",
                interview_question_zh="融资是否形成有约束力承诺，提款条件、到期日和资金流向是什么？",
            ),
            _requirement(
                "regulatory_approvals",
                "监管审批与备案文件",
                accepted_materials=("审批文件", "申报回执", "许可或备案", "法律意见"),
                fields=("authority", "filing", "approval_status", "conditions"),
                criticality="critical",
                owner_roles=("legal", "regulatory"),
                candidate_roles=("governance_legal", "policy_resource"),
                match_policy="roles_only",
                interview_question_zh="适用审批、申报和备案分别由谁负责，目前状态、条件与证据是什么？",
            ),
            _requirement(
                "closing_checklist",
                "交割条件与 Closing Checklist",
                accepted_materials=("Closing Checklist", "交割文件包", "资金流向确认"),
                fields=("condition", "owner", "evidence", "status", "waiver_authority"),
                criticality="critical",
                owner_roles=("project_management", "legal", "finance_valuation"),
                candidate_roles=("governance_legal", "financial_core"),
                match_policy="roles_only",
                interview_question_zh="每项交割条件的责任人、完成证据、状态和豁免权限是否已逐项确认？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "closing_conditions_regulatory_screen",
                "审批、外汇、税务与许可交割条件筛查",
                condition_zh="仅当适用审批、登记、税务、外汇、许可证或第三方同意尚未完成时触发。",
                screening_fields=("approval_matrix", "foreign_exchange", "tax_clearance", "permit_transfer", "consent"),
                owner_roles=("legal", "tax", "regulatory", "finance_valuation"),
                candidate_role_signals=("governance_legal", "policy_resource", "financial_core"),
                profile_keywords=("跨境", "中国", "china", "美国", "usa", "us"),
            ),
        ),
    },
    {
        "id": "post_merger_integration",
        "order": 8,
        "name_zh": "并购后整合",
        "name_en": "Post-merger integration",
        "core_task_zh": "管理团队、技术、供应链、客户和美国市场协同",
        "deliverables": ("100 天整合计划", "协同目标", "跟踪指标"),
        "decision_gate": "是否兑现交易价值",
        "responsible_roles": (
            "deal_sponsor",
            "integration_lead",
            "project_management",
            "finance_valuation",
            "technology_ip",
            "quality_ehs",
            "legal",
            "human_decision_body",
        ),
        "workstream_ids": tuple(item["id"] for item in WORKSTREAMS),
        "requirements": (
            _requirement(
                "hundred_day_plan",
                "100 天整合计划",
                accepted_materials=("100 天整合计划", "Day-1 清单", "整合治理架构"),
                fields=("workstream", "owner", "milestone", "dependency", "escalation"),
                criticality="critical",
                owner_roles=("integration_lead", "project_management"),
                candidate_roles=("company_identity", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="Day-1 和 100 天内各工作流的责任人、里程碑、依赖与升级机制是什么？",
            ),
            _requirement(
                "people_and_governance_integration",
                "团队留任与治理整合",
                accepted_materials=("组织方案", "留任协议", "治理矩阵", "沟通计划"),
                fields=("organization", "decision_rights", "retention", "communication"),
                criticality="important",
                owner_roles=("integration_lead", "deal_sponsor", "legal"),
                candidate_roles=("company_identity", "governance_legal"),
                match_policy="roles_only",
                interview_question_zh="交割后组织、决策权、关键人员留任和员工沟通将如何安排？",
            ),
            _requirement(
                "operating_integration",
                "技术、供应链与客户整合",
                accepted_materials=("技术整合路线图", "供应链计划", "客户迁移计划", "质量计划"),
                fields=("technology_integration", "supplier_plan", "customer_plan", "quality_controls"),
                criticality="critical",
                owner_roles=("integration_lead", "technology_ip", "quality_ehs", "industry_research"),
                candidate_roles=("technology_arl", "market_export", "esg_impact"),
                match_policy="roles_only",
                interview_question_zh="技术、供应链、客户和质量体系整合的顺序、依赖和不中断措施是什么？",
            ),
            _requirement(
                "synergy_tracking",
                "协同目标与跟踪指标",
                accepted_materials=("协同目标", "基线台账", "跟踪指标", "复盘机制"),
                fields=("baseline", "target", "owner", "measurement", "review_cycle"),
                criticality="critical",
                owner_roles=("integration_lead", "finance_valuation", "human_decision_body"),
                candidate_roles=("financial_core", "market_export"),
                match_policy="roles_only",
                interview_question_zh="协同目标的基线、目标值、责任人、计量口径和复盘周期分别是什么？",
            ),
        ),
        "regulatory_triggers": (
            _trigger(
                "pmi_labor_data_ip_ehs_screen",
                "交割后劳动、数据、IP 与 EHS 持续合规筛查",
                condition_zh="仅当人员转移、系统或数据跨境、IP 许可、技术转移、许可承继或现场责任实际发生时触发。",
                screening_fields=("employee_transfer", "data_migration", "ip_license", "permit_continuity", "ehs_owner"),
                owner_roles=("integration_lead", "legal", "technology_ip", "quality_ehs"),
                candidate_role_signals=("governance_legal", "technology_arl", "esg_impact"),
                profile_keywords=("跨境", "美国", "usa", "us", "技术", "technology"),
            ),
        ),
    },
)


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


WORKFLOW_DEFINITION_DIGEST = _canonical_digest(
    {"schema_version": SCHEMA_VERSION, "stages": STAGES, "workstreams": WORKSTREAMS}
)


def _all_requirement_ids() -> set[str]:
    return {
        requirement["id"]
        for stage in STAGES
        for requirement in stage["requirements"]
    }


def _validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(config))
    if candidate.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported acquisition workflow schema_version: {candidate.get('schema_version')}")
    if candidate.get("rule_version") != RULE_VERSION:
        raise ValueError(f"unsupported acquisition workflow rule_version: {candidate.get('rule_version')}")

    weights = candidate.get("criticality_weights")
    if not isinstance(weights, Mapping) or set(weights) != {"critical", "important", "supporting"}:
        raise ValueError("criticality_weights must define critical, important, and supporting")
    for name, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"criticality weight {name} must be a positive number")

    interview = candidate.get("interview")
    if not isinstance(interview, Mapping):
        raise ValueError("interview config must be an object")
    maximum = interview.get("maximum_questions")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 8:
        raise ValueError("interview.maximum_questions must be an integer from 1 to 8")
    threshold = interview.get("minimum_completeness_ratio")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("interview.minimum_completeness_ratio must be between 0 and 1")
    entry_ids = interview.get("required_entry_requirement_ids")
    if not isinstance(entry_ids, list) or not entry_ids or not all(isinstance(item, str) for item in entry_ids):
        raise ValueError("interview.required_entry_requirement_ids must be a non-empty string list")
    unknown_entry_ids = set(entry_ids) - _all_requirement_ids()
    if unknown_entry_ids:
        raise ValueError(f"unknown interview entry requirement ids: {sorted(unknown_entry_ids)}")

    known_roles = candidate.get("recognized_candidate_roles")
    known_fields = candidate.get("recognized_profile_fields")
    if not isinstance(known_roles, list) or not all(isinstance(item, str) for item in known_roles):
        raise ValueError("recognized_candidate_roles must be a string list")
    if not isinstance(known_fields, list) or not all(isinstance(item, str) for item in known_fields):
        raise ValueError("recognized_profile_fields must be a string list")
    return candidate


def load_acquisition_workflow_config(
    source: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Load and validate a complete acquisition workflow configuration."""

    if isinstance(source, Mapping):
        return _validate_config(source)
    path = Path(source) if source is not None else DEFAULT_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("acquisition workflow config root must be an object")
    return _validate_config(raw)


def _public_requirement(requirement: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": requirement["id"],
        "label_zh": requirement["label_zh"],
        "accepted_materials": list(requirement["accepted_materials"]),
        "fields": list(requirement["fields"]),
        "profile_hint_fields": list(requirement["profile_hint_fields"]),
        "criticality": requirement["criticality"],
        "responsible_roles": [
            {"id": role, "label_zh": ROLE_LABELS[role]} for role in requirement["owner_roles"]
        ],
        "candidate_role_signals": list(requirement["candidate_roles"]),
        "match_policy": requirement["match_policy"],
    }


def _public_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    requirements = [_public_requirement(item) for item in stage["requirements"]]
    materials = list(dict.fromkeys(item for req in requirements for item in req["accepted_materials"]))
    fields = list(dict.fromkeys(item for req in requirements for item in req["fields"]))
    triggers = []
    for item in stage["regulatory_triggers"]:
        trigger = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in item.items()
            if key not in {"candidate_role_signals", "profile_keywords"}
        }
        trigger["responsible_roles"] = [
            {"id": role, "label_zh": ROLE_LABELS[role]} for role in item["owner_roles"]
        ]
        trigger.pop("owner_roles", None)
        triggers.append(trigger)
    return {
        "id": stage["id"],
        "order": stage["order"],
        "name_zh": stage["name_zh"],
        "name_en": stage["name_en"],
        "core_task_zh": stage["core_task_zh"],
        "deliverables": list(stage["deliverables"]),
        "materials": materials,
        "fields": fields,
        "criticality": "stage_gate_critical",
        "responsible_roles": [
            {"id": role, "label_zh": ROLE_LABELS[role]} for role in stage["responsible_roles"]
        ],
        "workstream_ids": list(stage["workstream_ids"]),
        "requirements": requirements,
        "decision_gate": {
            "question_zh": stage["decision_gate"],
            "authority": "human_only",
            "agent_may_prepare_candidates": True,
            "agent_may_decide": False,
        },
        "conditional_regulatory_triggers": triggers,
    }


def acquisition_workflow_definition() -> dict[str, Any]:
    """Return a defensive copy of the fixed eight-stage workflow definition."""

    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "definition_digest": WORKFLOW_DEFINITION_DIGEST,
        "stages": [_public_stage(stage) for stage in STAGES],
        "workstreams": copy.deepcopy(list(WORKSTREAMS)),
        "authority": {
            "agent_outputs": "candidate_only",
            "decision_gates": "human_only",
            "fact_upgrade": "human_evidence_review_only",
        },
    }


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})
    return []


def _profile_tags(value: Any, allowed_fields: set[str]) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    raw = value.get("tags", value)
    if not isinstance(raw, Mapping):
        return {}
    return {
        field: values
        for field in sorted(allowed_fields)
        if (values := _string_values(raw.get(field)))
    }


def _normalize_inputs(
    materials: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    profile_hints: Mapping[str, Any] | None,
    *,
    allowed_roles: set[str],
    allowed_fields: set[str],
) -> dict[str, Any]:
    if materials is None:
        raw_artifacts: Any = []
    elif isinstance(materials, Mapping):
        raw_artifacts = materials.get("artifacts", [])
        if profile_hints is None and isinstance(materials.get("profile_hints"), Mapping):
            profile_hints = materials["profile_hints"]
    else:
        raw_artifacts = materials
    if not isinstance(raw_artifacts, Sequence) or isinstance(raw_artifacts, (str, bytes, bytearray)):
        raise ValueError("materials must be an artifact list or a manifest object")

    roles: set[str] = set()
    ignored_roles: set[str] = set()
    role_sources: dict[str, set[str]] = {}
    requirement_candidates: set[str] = set()
    requirement_candidate_sources: dict[str, set[str]] = {}
    ignored_requirement_candidate_ids: set[str] = set()
    ignored_requirement_candidate_contract_count = 0
    known_requirement_ids = {
        requirement["id"]
        for stage in STAGES
        for requirement in stage["requirements"]
    }
    profile_field_sources: dict[str, set[str]] = {}
    merged_hints: dict[str, set[str]] = {
        field: set(values) for field, values in _profile_tags(profile_hints, allowed_fields).items()
    }
    accepted_artifacts = 0
    ignored_artifacts = 0
    duplicate_artifacts = 0
    missing_identity_artifacts = 0
    ignored_recognition_statuses: set[str] = set()
    ignored_artifact_statuses: set[str] = set()
    seen_identities: dict[tuple[str, str], str] = {}
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            ignored_artifacts += 1
            continue

        identity_tokens: list[tuple[str, str]] = []
        artifact_id = artifact.get("id")
        if isinstance(artifact_id, str) and artifact_id.strip():
            identity_tokens.append(("id", artifact_id.strip()))
        artifact_sha256 = artifact.get("sha256")
        if isinstance(artifact_sha256, str) and artifact_sha256.strip():
            identity_tokens.append(("sha256", artifact_sha256.strip().casefold()))
        file_name = artifact.get("file_name")
        if isinstance(file_name, str) and file_name.strip():
            identity_tokens.append(("file_name", file_name.strip().casefold()))
        if not identity_tokens:
            missing_identity_artifacts += 1
            ignored_artifacts += 1
            continue

        artifact_digest = _canonical_digest(artifact)
        prior_digests = {
            seen_identities[token] for token in identity_tokens if token in seen_identities
        }
        if prior_digests:
            if prior_digests != {artifact_digest}:
                labels = ", ".join(f"{kind}={value}" for kind, value in identity_tokens)
                raise ValueError(f"conflicting duplicate artifact identity: {labels}")
            duplicate_artifacts += 1
            ignored_artifacts += 1
            continue
        for token in identity_tokens:
            seen_identities[token] = artifact_digest

        recognition = artifact.get("recognition")
        if not isinstance(recognition, Mapping):
            ignored_artifacts += 1
            continue
        recognition_status = recognition.get("status")
        if recognition_status != "candidate_ready":
            if recognition_status is None:
                ignored_recognition_statuses.add("<missing-or-null>")
            elif isinstance(recognition_status, str):
                ignored_recognition_statuses.add(recognition_status or "<empty>")
            else:
                ignored_recognition_statuses.add(f"<{type(recognition_status).__name__}>")
            ignored_artifacts += 1
            continue
        artifact_status = artifact.get("status")
        if artifact_status != "ready":
            if artifact_status is None:
                ignored_artifact_statuses.add("<missing-or-null>")
            elif isinstance(artifact_status, str):
                ignored_artifact_statuses.add(artifact_status or "<empty>")
            else:
                ignored_artifact_statuses.add(f"<{type(artifact_status).__name__}>")
            ignored_artifacts += 1
            continue
        accepted_artifacts += 1
        source_id = str(artifact.get("id") or artifact.get("sha256") or artifact.get("file_name"))
        for role in _string_values(recognition.get("candidate_roles")):
            if role not in allowed_roles:
                ignored_roles.add(role)
                continue
            roles.add(role)
            role_sources.setdefault(role, set()).add(source_id)
        requirement_contract = recognition.get("requirement_candidates")
        if requirement_contract is not None:
            if (
                not isinstance(requirement_contract, Mapping)
                or requirement_contract.get("schema_version")
                != REQUIREMENT_CANDIDATE_SCHEMA_VERSION
                or requirement_contract.get("rule_version") != RULE_VERSION
            ):
                ignored_requirement_candidate_contract_count += 1
            else:
                for requirement_id in _string_values(
                    requirement_contract.get("requirement_ids")
                ):
                    if requirement_id not in known_requirement_ids:
                        ignored_requirement_candidate_ids.add(requirement_id)
                        continue
                    requirement_candidates.add(requirement_id)
                    requirement_candidate_sources.setdefault(
                        requirement_id, set()
                    ).add(source_id)
        for field, values in _profile_tags(
            recognition.get("profile_hints"), allowed_fields
        ).items():
            merged_hints.setdefault(field, set()).update(values)
            profile_field_sources.setdefault(field, set()).add(source_id)

    normalized_hints = {field: sorted(values) for field, values in sorted(merged_hints.items()) if values}
    return {
        "candidate_roles": sorted(roles),
        "profile_hints": normalized_hints,
        "role_sources": {role: sorted(values) for role, values in sorted(role_sources.items())},
        "requirement_candidates": sorted(requirement_candidates),
        "requirement_candidate_sources": {
            requirement_id: sorted(values)
            for requirement_id, values in sorted(
                requirement_candidate_sources.items()
            )
        },
        "profile_field_sources": {
            field: sorted(values)
            for field, values in sorted(profile_field_sources.items())
        },
        "artifact_count": len(raw_artifacts),
        "accepted_artifact_count": accepted_artifacts,
        "ignored_artifact_count": ignored_artifacts,
        "duplicate_artifact_count": duplicate_artifacts,
        "missing_identity_artifact_count": missing_identity_artifacts,
        "ignored_recognition_statuses": sorted(ignored_recognition_statuses),
        "ignored_artifact_statuses": sorted(ignored_artifact_statuses),
        "ignored_candidate_roles": sorted(ignored_roles),
        "ignored_requirement_candidate_ids": sorted(
            ignored_requirement_candidate_ids
        ),
        "ignored_requirement_candidate_contract_count": (
            ignored_requirement_candidate_contract_count
        ),
    }


def _requirement_match(
    requirement: Mapping[str, Any],
    requirement_candidates: set[str],
    candidate_roles: set[str],
    artifact_profile_fields: set[str],
    requirement_candidate_sources: Mapping[str, Sequence[str]],
    role_sources: Mapping[str, Sequence[str]],
    profile_field_sources: Mapping[str, Sequence[str]],
) -> tuple[bool, list[str], list[str], list[str], list[str]]:
    matched_roles = sorted(candidate_roles.intersection(requirement["candidate_roles"]))
    matched_fields = sorted(
        artifact_profile_fields.intersection(requirement["profile_hint_fields"])
    )
    satisfied = requirement["id"] in requirement_candidates
    source_ids = list(requirement_candidate_sources.get(requirement["id"], []))
    routing_source_ids = sorted(
        {
            source_id
            for role in matched_roles
            for source_id in role_sources.get(role, [])
        }
        | {
            source_id
            for field in matched_fields
            for source_id in profile_field_sources.get(field, [])
        }
    )
    return satisfied, matched_roles, matched_fields, source_ids, routing_source_ids


def _trigger_diagnostic(
    trigger: Mapping[str, Any],
    candidate_roles: set[str],
    all_hint_values: set[str],
) -> dict[str, Any]:
    role_signals = sorted(candidate_roles.intersection(trigger["candidate_role_signals"]))
    keyword_signals = sorted(
        keyword
        for keyword in trigger["profile_keywords"]
        if any(keyword.casefold() in value.casefold() for value in all_hint_values)
    )
    return {
        "id": trigger["id"],
        "label_zh": trigger["label_zh"],
        "status": "candidate_trigger" if role_signals or keyword_signals else "not_evaluated",
        "condition_zh": trigger["condition_zh"],
        "screening_fields": list(trigger["screening_fields"]),
        "matched_candidate_role_signals": role_signals,
        "matched_profile_keyword_signals": keyword_signals,
        "authority": "screening_question_only",
        "requires_human_legal_review": True,
    }


def _diagnose_stages(
    normalized: Mapping[str, Any],
    weights: Mapping[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float]:
    candidate_roles = set(normalized["candidate_roles"])
    requirement_candidates = set(normalized["requirement_candidates"])
    artifact_profile_fields = set(normalized["profile_field_sources"])
    all_hint_values = {
        value for values in normalized["profile_hints"].values() for value in values
    }
    stage_diagnostics: list[dict[str, Any]] = []
    all_requirements: list[dict[str, Any]] = []
    earned_weight = 0.0
    total_weight = 0.0
    for stage in STAGES:
        requirement_diagnostics = []
        stage_earned = 0.0
        stage_total = 0.0
        for index, requirement in enumerate(stage["requirements"]):
            weight = float(weights[requirement["criticality"]])
            (
                satisfied,
                matched_roles,
                matched_fields,
                source_ids,
                routing_source_ids,
            ) = _requirement_match(
                requirement,
                requirement_candidates,
                candidate_roles,
                artifact_profile_fields,
                normalized["requirement_candidate_sources"],
                normalized["role_sources"],
                normalized["profile_field_sources"],
            )
            if satisfied:
                status = "candidate_covered"
            elif matched_roles or matched_fields:
                status = "candidate_topic_match"
            else:
                status = "missing"
            diagnostic = {
                "id": requirement["id"],
                "label_zh": requirement["label_zh"],
                "stage_id": stage["id"],
                "stage_order": stage["order"],
                "requirement_order": index + 1,
                "status": status,
                "criticality": requirement["criticality"],
                "weight": weight,
                "accepted_materials": list(requirement["accepted_materials"]),
                "fields": list(requirement["fields"]),
                "responsible_roles": list(requirement["owner_roles"]),
                "matched_candidate_roles": matched_roles,
                "matched_profile_fields": matched_fields,
                "source_artifact_ids": source_ids,
                "routing_signal_artifact_ids": routing_source_ids,
                "interview_question_zh": requirement["interview_question_zh"],
                "authority": "candidate_coverage_only",
            }
            requirement_diagnostics.append(diagnostic)
            all_requirements.append(diagnostic)
            stage_total += weight
            total_weight += weight
            if satisfied:
                stage_earned += weight
                earned_weight += weight
        covered_count = sum(item["status"] == "candidate_covered" for item in requirement_diagnostics)
        if covered_count == len(requirement_diagnostics):
            coverage_status = "candidate_coverage_complete"
        elif covered_count:
            coverage_status = "candidate_coverage_partial"
        else:
            coverage_status = "candidate_coverage_missing"
        stage_diagnostics.append(
            {
                "id": stage["id"],
                "order": stage["order"],
                "name_zh": stage["name_zh"],
                "coverage_status": coverage_status,
                "completeness_ratio": round(min(1.0, stage_earned / stage_total), 4),
                "requirements": requirement_diagnostics,
                "decision_gate": {
                    "question_zh": stage["decision_gate"],
                    "status": "human_pending",
                    "authority": "human_only",
                    "agent_may_decide": False,
                },
                "conditional_regulatory_triggers": [
                    _trigger_diagnostic(item, candidate_roles, all_hint_values)
                    for item in stage["regulatory_triggers"]
                ],
            }
        )
    return stage_diagnostics, all_requirements, earned_weight, total_weight


def _gap_item(requirement: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": requirement["id"],
        "stage_id": requirement["stage_id"],
        "stage_order": requirement["stage_order"],
        "label_zh": requirement["label_zh"],
        "criticality": requirement["criticality"],
        "accepted_materials": list(requirement["accepted_materials"]),
        "required_fields": list(requirement["fields"]),
        "responsible_roles": list(requirement["responsible_roles"]),
        "reason": (
            "未提供匹配当前规则版本的显式 requirement candidate；"
            "候选角色与 profile hints 仅作路由提示。"
        ),
        "authority": "candidate_gap_only",
    }


def _suggested_supplement(requirement: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "request_id": f"request-{requirement['id']}",
        "stage_id": requirement["stage_id"],
        "requirement_id": requirement["id"],
        "title_zh": f"补充：{requirement['label_zh']}",
        "accepted_materials": list(requirement["accepted_materials"]),
        "requested_fields": list(requirement["fields"]),
        "criticality": requirement["criticality"],
        "responsible_roles": list(requirement["responsible_roles"]),
        "basis": "由缺少显式 requirement candidate 生成；提交后仍需人工核验。",
        "authority": "draft_request_only",
    }


def _interview_questions(
    missing: list[dict[str, Any]],
    *,
    maximum: int,
    normalized: Mapping[str, Any],
    weights: Mapping[str, float],
) -> list[dict[str, Any]]:
    ordered = sorted(
        missing,
        key=lambda item: (
            -float(weights[item["criticality"]]),
            item["stage_order"],
            item["requirement_order"],
            item["id"],
        ),
    )
    questions = []
    for index, requirement in enumerate(ordered[:maximum], start=1):
        questions.append(
            {
                "id": f"interview-q{index:02d}",
                "question_zh": requirement["interview_question_zh"],
                "stage_id": requirement["stage_id"],
                "gap_requirement_id": requirement["id"],
                "criticality": requirement["criticality"],
                "basis": {
                    "missing_requirement": requirement["label_zh"],
                    "accepted_materials": list(requirement["accepted_materials"]),
                    "required_fields": list(requirement["fields"]),
                    "current_candidate_roles": list(normalized["candidate_roles"]),
                    "current_requirement_candidates": list(
                        normalized["requirement_candidates"]
                    ),
                    "current_profile_fields": sorted(normalized["profile_hints"]),
                    "authority": "candidate_gap_only",
                },
            }
        )
    return questions


def acquisition_workflow_not_applicable(
    workflow_type: str = "company_intake",
) -> dict[str, Any]:
    """Return a stable fail-closed projection when acquisition was not selected."""

    loaded_config = load_acquisition_workflow_config()
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "definition_digest": WORKFLOW_DEFINITION_DIGEST,
        "config_digest": _canonical_digest(loaded_config),
        "applicability": {
            "status": "not_applicable",
            "workflow_type": workflow_type,
            "reason_code": "explicit_acquisition_workflow_not_selected",
            "reason_zh": "未显式选择跨境收购工作流；不计算八阶段覆盖率或生成买方问题。",
            "authority": "workflow_applicability_only",
        },
        "input_summary": {
            "artifact_count": None,
            "accepted_artifact_count": None,
            "ignored_artifact_count": None,
            "candidate_roles": [],
            "profile_hints": {},
            "requirement_candidates": [],
            "authority": "not_evaluated",
        },
        "completeness": {
            "status": "not_applicable",
            "earned_weight": None,
            "total_weight": None,
            "ratio": None,
            "percent": None,
            "critical_required_count": None,
            "critical_candidate_covered_count": None,
            "authority": "not_applicable",
        },
        "business_model_interview_readiness": {
            "status": "not_applicable",
            "label_zh": "不适用",
            "minimum_completeness_ratio": None,
            "required_entry_requirement_ids": [],
            "missing_entry_requirement_ids": [],
            "basis_zh": "跨境收购工作流未启用，因此不生成买方或交易访谈问题。",
            "authority": "not_applicable",
        },
        "stage_diagnostics": [],
        "critical_gaps": [],
        "suggested_supplements": [],
        "interview_questions": [],
        "boundaries": {
            "agent_outputs_are_candidates": True,
            "agent_can_complete_decision_gate": False,
            "agent_can_upgrade_fact": False,
            "commercial_model_status_is_fact_determination": False,
            "investment_rating_produced": False,
            "credit_rating_produced": False,
            "aggregate_risk_score_produced": False,
            "regulatory_trigger_is_legal_conclusion": False,
        },
    }


def diagnose_acquisition_readiness(
    materials: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    *,
    profile_hints: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Diagnose candidate material coverage without making a transaction decision."""

    loaded_config = load_acquisition_workflow_config(config)
    allowed_roles = set(loaded_config["recognized_candidate_roles"])
    allowed_fields = set(loaded_config["recognized_profile_fields"])
    normalized = _normalize_inputs(
        materials,
        profile_hints,
        allowed_roles=allowed_roles,
        allowed_fields=allowed_fields,
    )
    weights = loaded_config["criticality_weights"]
    stage_diagnostics, all_requirements, earned_weight, total_weight = _diagnose_stages(
        normalized, weights
    )
    ratio = min(1.0, earned_weight / total_weight) if total_weight else 0.0
    missing = [
        item for item in all_requirements if item["status"] != "candidate_covered"
    ]
    critical_gaps = [_gap_item(item) for item in missing if item["criticality"] == "critical"]
    supplements = [_suggested_supplement(item) for item in missing]

    entry_ids = loaded_config["interview"]["required_entry_requirement_ids"]
    requirement_status = {item["id"]: item["status"] for item in all_requirements}
    missing_entry_ids = [
        requirement_id
        for requirement_id in entry_ids
        if requirement_status.get(requirement_id) != "candidate_covered"
    ]
    threshold = float(loaded_config["interview"]["minimum_completeness_ratio"])
    schedulable = not missing_entry_ids and ratio >= threshold
    maximum_questions = int(loaded_config["interview"]["maximum_questions"])

    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "definition_digest": WORKFLOW_DEFINITION_DIGEST,
        "config_digest": _canonical_digest(loaded_config),
        "applicability": {
            "status": "applicable",
            "workflow_type": "acquisition",
            "reason_code": "explicit_acquisition_workflow_selected",
            "authority": "workflow_applicability_only",
        },
        "input_summary": {
            "artifact_count": normalized["artifact_count"],
            "accepted_artifact_count": normalized["accepted_artifact_count"],
            "ignored_artifact_count": normalized["ignored_artifact_count"],
            "duplicate_artifact_count": normalized["duplicate_artifact_count"],
            "missing_identity_artifact_count": normalized["missing_identity_artifact_count"],
            "candidate_roles": list(normalized["candidate_roles"]),
            "requirement_candidates": list(normalized["requirement_candidates"]),
            "profile_hints": copy.deepcopy(normalized["profile_hints"]),
            "ignored_recognition_statuses": list(normalized["ignored_recognition_statuses"]),
            "ignored_artifact_statuses": list(normalized["ignored_artifact_statuses"]),
            "ignored_candidate_roles": list(normalized["ignored_candidate_roles"]),
            "ignored_requirement_candidate_ids": list(
                normalized["ignored_requirement_candidate_ids"]
            ),
            "ignored_requirement_candidate_contract_count": normalized[
                "ignored_requirement_candidate_contract_count"
            ],
            "authority": "routing_candidates_only",
        },
        "completeness": {
            "earned_weight": round(earned_weight, 4),
            "total_weight": round(total_weight, 4),
            "ratio": round(ratio, 4),
            "percent": round(ratio * 100, 2),
            "critical_required_count": sum(
                item["criticality"] == "critical" for item in all_requirements
            ),
            "critical_candidate_covered_count": sum(
                item["criticality"] == "critical" and item["status"] == "candidate_covered"
                for item in all_requirements
            ),
            "authority": "candidate_material_coverage_only",
        },
        "business_model_interview_readiness": {
            "status": "interview_schedulable" if schedulable else "insufficient",
            "label_zh": "可安排访谈" if schedulable else "尚不足",
            "minimum_completeness_ratio": threshold,
            "required_entry_requirement_ids": list(entry_ids),
            "missing_entry_requirement_ids": missing_entry_ids,
            "basis_zh": "仅表示候选材料覆盖足以安排验证性访谈，不表示商业模式成立或材料内容为真。",
            "authority": "workflow_readiness_not_fact_verification",
        },
        "stage_diagnostics": stage_diagnostics,
        "critical_gaps": critical_gaps,
        "suggested_supplements": supplements,
        "interview_questions": _interview_questions(
            missing,
            maximum=maximum_questions,
            normalized=normalized,
            weights=weights,
        ),
        "boundaries": {
            "agent_outputs_are_candidates": True,
            "agent_can_complete_decision_gate": False,
            "agent_can_upgrade_fact": False,
            "commercial_model_status_is_fact_determination": False,
            "investment_rating_produced": False,
            "credit_rating_produced": False,
            "aggregate_risk_score_produced": False,
            "regulatory_trigger_is_legal_conclusion": False,
        },
    }
