"""Local case workspace, safe material storage, and deterministic recognition.

This module deliberately stops before factual extraction.  It stores user-selected
materials, records immutable hashes, and proposes document roles from file-local
signals.  Proposed roles are routing hints only; they are never accepted evidence.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import unicodedata
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .acquisition_workflow import (
    acquisition_workflow_not_applicable,
    diagnose_acquisition_readiness,
)
from .company_intake_preflight import (
    diagnose_company_intake_financial_basis,
    parse_structured_financial_metadata,
)

MAX_CASE_FILES = 20
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_FILE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4_000
MAX_ARCHIVE_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_TEXT_SCAN_CHARS = 250_000
ALLOWED_MATERIAL_SUFFIXES = frozenset(
    {
        ".csv",
        ".docx",
        ".htm",
        ".html",
        ".json",
        ".md",
        ".pdf",
        ".pptx",
        ".txt",
        ".xlsx",
    }
)
CASE_ID_PATTERN = re.compile(r"^case-\d{8}-[a-f0-9]{10}$")
ARTIFACT_ID_PATTERN = re.compile(r"^artifact-\d{4}$")

ROLE_SIGNALS: dict[str, tuple[str, ...]] = {
    "company_identity": (
        "公司介绍",
        "企业介绍",
        "商业计划",
        "路演",
        "pitch deck",
        "company profile",
        "business plan",
    ),
    "financial_core": (
        "财务",
        "审计",
        "利润",
        "毛利",
        "单位经济",
        "现金流",
        "资金缺口",
        "回款",
        "revenue",
        "gross margin",
        "unit economics",
        "cash flow",
        "runway",
    ),
    "esg_impact": (
        "esg",
        "可持续",
        "环境",
        "碳排",
        "减排",
        "生命周期",
        "lca",
        "emission",
        "sustainability",
    ),
    "technology_arl": (
        "技术",
        "技术验证",
        "性能验证",
        "现场验证",
        "专利",
        "中试",
        "试点",
        "示范",
        "technical validation",
        "technology validation",
        "performance validation",
        "trl",
        "arl",
        "patent",
        "pilot",
    ),
    "market_export": (
        "市场",
        "客户",
        "订单",
        "海外",
        "出海",
        "persona",
        "消费者",
        "market",
        "customer",
        "export",
    ),
    "policy_resource": (
        "政策",
        "资助",
        "补贴",
        "申报",
        "policy",
        "subsidy",
        "grant",
    ),
    "governance_legal": (
        "股权",
        "法务",
        "合规",
        "许可证",
        "治理",
        "legal",
        "compliance",
        "governance",
    ),
}

WEAK_ROLE_SIGNALS = frozenset({"legal", "policy", "customer", "market", "revenue"})
CONTROL_ARTIFACT_TOKENS = frozenset({"manifest", "index", "readme"})
WORKFLOW_TYPES = frozenset({"company_intake", "acquisition"})

ROLE_TOPIC_LABELS = {
    "company_identity": "企业画像",
    "financial_core": "财务与现金流",
    "esg_impact": "ESG 与清洁技术影响",
    "technology_arl": "技术成熟度",
    "market_export": "市场与出海",
    "policy_resource": "政策资源",
    "governance_legal": "治理与合规",
    "generic_supporting": "综合材料",
}

STAGE_REFERENCE_LABELS = {
    "research_development": "研发",
    "pilot": "试点",
    "early_commercial": "早期商业化",
    "scaling": "规模化",
    "mature": "成熟",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MaterialValidationError(ValueError):
    """Raised when a browser-uploaded material violates the local contract."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.fragments: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not self._hidden_depth and cleaned:
            self.fragments.append(cleaned)


def _safe_file_name(raw_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw_name.replace("\\", "/"))
    name = normalized.rsplit("/", 1)[-1].strip().strip(".")
    if (
        not name
        or name in {".", ".."}
        or len(name) > 180
        or any(ord(character) < 32 for character in name)
    ):
        raise MaterialValidationError("Material file name is invalid")
    suffix = Path(name).suffix.casefold()
    if suffix not in ALLOWED_MATERIAL_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_MATERIAL_SUFFIXES))
        raise MaterialValidationError(
            f"Unsupported material format '{suffix or '(none)'}'; allowed: {allowed}"
        )
    return name


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _xml_visible_text(payload: bytes) -> str:
    if len(payload) > 12 * 1024 * 1024:
        raise MaterialValidationError("OpenXML component is too large to inspect safely")
    root = ElementTree.fromstring(payload)
    fragments = [
        element.text.strip()
        for element in root.iter()
        if element.text and element.text.strip()
    ]
    return " ".join(fragments)


def _openxml_text(payload: bytes, suffix: str) -> str:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise MaterialValidationError("OpenXML package has too many entries")
            expanded = sum(info.file_size for info in infos)
            if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
                raise MaterialValidationError("OpenXML package expands beyond the safety limit")
            if any(info.flag_bits & 0x1 for info in infos):
                raise MaterialValidationError("Encrypted OpenXML materials are not supported")

            if suffix == ".docx":
                selected = [
                    info
                    for info in infos
                    if info.filename == "word/document.xml"
                    or info.filename.startswith("word/header")
                    or info.filename.startswith("word/footer")
                ]
            elif suffix == ".pptx":
                selected = [
                    info
                    for info in infos
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", info.filename)
                ]
            else:
                selected = [
                    info
                    for info in infos
                    if info.filename == "xl/sharedStrings.xml"
                    or re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename)
                ]

            fragments: list[str] = []
            for info in selected:
                if sum(len(item) for item in fragments) >= MAX_TEXT_SCAN_CHARS:
                    break
                fragments.append(_xml_visible_text(archive.read(info)))
            return "\n".join(fragments)[:MAX_TEXT_SCAN_CHARS]
    except zipfile.BadZipFile as exc:
        raise MaterialValidationError("OpenXML material is not a valid ZIP package") from exc
    except ElementTree.ParseError as exc:
        raise MaterialValidationError("OpenXML material contains invalid XML") from exc


def _extract_text(file_name: str, payload: bytes) -> tuple[str, list[str]]:
    suffix = Path(file_name).suffix.casefold()
    warnings: list[str] = []
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return _decode_text(payload)[:MAX_TEXT_SCAN_CHARS], warnings
    if suffix in {".html", ".htm"}:
        parser = _VisibleTextParser()
        parser.feed(_decode_text(payload))
        return "\n".join(parser.fragments)[:MAX_TEXT_SCAN_CHARS], warnings
    if suffix in {".docx", ".pptx", ".xlsx"}:
        return _openxml_text(payload, suffix), warnings
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "", ["pdf_text_extractor_not_installed"]
        try:
            reader = PdfReader(BytesIO(payload))
            fragments: list[str] = []
            for page in reader.pages[:80]:
                fragments.append(page.extract_text() or "")
                if sum(len(item) for item in fragments) >= MAX_TEXT_SCAN_CHARS:
                    break
            text = "\n".join(fragments)[:MAX_TEXT_SCAN_CHARS]
            if not text.strip():
                warnings.append("pdf_has_no_extractable_text_manual_or_ocr_review_required")
            return text, warnings
        except Exception as exc:  # pypdf exposes multiple parser exception classes
            return "", [f"pdf_text_extraction_failed:{type(exc).__name__}"]
    return "", ["unsupported_text_extraction"]


def _is_control_artifact(file_name: str) -> bool:
    stem = unicodedata.normalize("NFKC", Path(file_name).stem).casefold()
    tokens = {
        token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", stem) if token
    }
    return bool(tokens.intersection(CONTROL_ARTIFACT_TOKENS)) or any(
        marker in stem for marker in ("清单", "目录")
    )


def _signal_present(corpus: str, signal: str) -> bool:
    normalized_signal = signal.casefold()
    if normalized_signal.isascii():
        normalized_corpus = re.sub(r"[_/\\-]+", " ", corpus)
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_signal)}(?![a-z0-9])",
                normalized_corpus,
            )
        )
    return normalized_signal in corpus


def _candidate_roles(file_name: str, text: str) -> tuple[list[str], list[str]]:
    if _is_control_artifact(file_name):
        return ["generic_supporting"], ["control_artifact_name"]
    corpus = f"{file_name}\n{text[:MAX_TEXT_SCAN_CHARS]}".casefold()
    matches: list[tuple[str, list[str]]] = []
    for role, signals in ROLE_SIGNALS.items():
        found = sorted({signal for signal in signals if _signal_present(corpus, signal)})
        strong = [signal for signal in found if signal.casefold() not in WEAK_ROLE_SIGNALS]
        weak = [signal for signal in found if signal.casefold() in WEAK_ROLE_SIGNALS]
        if strong or len(weak) >= 2:
            matches.append((role, found))
    matches.sort(key=lambda item: (-len(item[1]), item[0]))
    roles = [role for role, _ in matches[:4]]
    signals = [signal for _, found in matches[:4] for signal in found[:3]]
    return roles or ["generic_supporting"], signals[:10]


def _short_text(value: Any, *, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _profile_hints(file_name: str, text: str) -> dict[str, list[str]]:
    """Extract bounded declared profile fields from a recognized case JSON."""

    if Path(file_name).suffix.casefold() != ".json" or not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    company = payload.get("company")
    if not isinstance(company, dict):
        return {}

    hints: dict[str, list[str]] = {}

    def add(dimension: str, *values: Any) -> None:
        normalized: list[str] = list(hints.get(dimension, []))
        for value in values:
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                item = _short_text(candidate)
                if item and item not in normalized:
                    normalized.append(item)
        if normalized:
            hints[dimension] = normalized[:8]

    industry = company.get("industry")
    stage = _short_text(company.get("stage"))
    add("industry", industry)
    add("stage", stage, STAGE_REFERENCE_LABELS.get(stage))
    add(
        "technology",
        company.get("technology_or_solution_zh"),
        company.get("technology_or_solution"),
    )
    add("geography", company.get("country"))
    add("market", company.get("target_markets"))
    thematic_corpus = " ".join(
        _short_text(company.get(field)).casefold()
        for field in (
            "industry",
            "technology_or_solution",
            "technology_or_solution_zh",
        )
    )
    if any(signal in thematic_corpus for signal in ("光伏", "solar", "新能源")):
        add("industry", "新能源", "光伏")
        add("technology", "新能源", "光伏")
    if any(signal in thematic_corpus for signal in ("储能", "battery", "storage")):
        add("industry", "新能源", "储能")
        add("technology", "储能")
    if any(signal in thematic_corpus for signal in ("碳", "carbon", "decarbon")):
        add("need", "低碳转型")
    return hints


def _merge_profile_hints(artifacts: list[dict[str, Any]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for artifact in artifacts:
        recognition = artifact.get("recognition")
        if not isinstance(recognition, dict):
            continue
        hints = recognition.get("profile_hints")
        if not isinstance(hints, dict):
            continue
        for dimension, raw_values in hints.items():
            if not isinstance(raw_values, list):
                continue
            target = merged.setdefault(str(dimension), [])
            for value in raw_values:
                item = _short_text(value)
                if item and item not in target:
                    target.append(item)
    return {key: values[:20] for key, values in sorted(merged.items())}


def _suggest_case_name(
    prepared: list[tuple[str, bytes, str]],
) -> str:
    for name, payload, _ in prepared:
        if Path(name).suffix.casefold() != ".json":
            continue
        try:
            document = json.loads(_decode_text(payload))
        except json.JSONDecodeError:
            continue
        company = document.get("company") if isinstance(document, dict) else None
        if not isinstance(company, dict):
            continue
        for field in ("display_name_zh", "display_name", "legal_name"):
            value = _short_text(company.get(field))
            if value:
                return value
    return _short_text(Path(prepared[0][0]).stem) or "新企业案例"


def _module_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": "financial_core",
            "label": "财务核心",
            "maturity": "validated_end_to_end",
            "summary": "2/6 项端到端已验证：盈利/单位经济性、现金流/资金缺口。",
        },
        {
            "id": "financial_remaining",
            "label": "其余财务",
            "maturity": "input_blueprint_only",
            "summary": "输入蓝图，当前不执行判断。",
        },
        {
            "id": "esg",
            "label": "ESG",
            "maturity": "evidence_framework_only",
            "summary": "证据框架，不是自动认证。",
        },
        {
            "id": "cleantech_impact",
            "label": "清洁技术影响",
            "maturity": "evidence_framework_only",
            "summary": "证据框架，需要基线、边界与方法。",
        },
        {
            "id": "doe_arl",
            "label": "DOE ARL",
            "maturity": "retrieval_scaffold_only",
            "summary": "17 维检索脚手架，不输出 ARL 1–9 分数。",
        },
        {
            "id": "export_readiness",
            "label": "出海准备",
            "maturity": "evidence_framework_only",
            "summary": "证据与材料准备框架。",
        },
        {
            "id": "policy",
            "label": "政策资源",
            "maturity": "candidate_matching_only",
            "summary": "参考建议保留来源与有效期，不判断企业申报资格。",
        },
    ]


def _workflow_projection(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    needs_manual = any(
        item["recognition"]["status"] == "awaiting_human" for item in artifacts
    )
    return {
        "workflow": [
            {"id": "materials", "label": "材料", "state": "complete"},
            {
                "id": "evidence",
                "label": "证据",
                "state": "awaiting_human",
            },
            {"id": "analysis", "label": "分析", "state": "blocked"},
            {"id": "supplements", "label": "补件", "state": "not_available"},
            {"id": "review", "label": "复核", "state": "not_available"},
            {"id": "outputs", "label": "输出", "state": "not_available"},
        ],
        "next_action": {
            "id": "confirm_material_scope",
            "actor": "human",
            "label_zh": "确认材料识别范围",
            "reason": (
                "至少一个文件无法提取文本，需要人工确认或 OCR。"
                if needs_manual
                else "系统已识别材料主题，可以进入参考建议与分析准备。"
            ),
        },
    }


def _normalized_workflow_type(value: Any) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    return normalized if normalized in WORKFLOW_TYPES else "company_intake"


def _workflow_diagnostic(
    workflow_type: str,
    artifacts: list[dict[str, Any]],
    profile_hints: Any,
) -> dict[str, Any]:
    if workflow_type != "acquisition":
        return acquisition_workflow_not_applicable(workflow_type)
    return diagnose_acquisition_readiness(
        artifacts,
        profile_hints=profile_hints,
    )


def _enrich_manifest(case_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    artifacts: list[dict[str, Any]] = []
    for raw_artifact in payload.get("artifacts") or []:
        if not isinstance(raw_artifact, dict):
            continue
        artifact = dict(raw_artifact)
        raw_recognition = artifact.get("recognition")
        recognition = (
            dict(raw_recognition) if isinstance(raw_recognition, dict) else {}
        )
        if (
            "profile_hints" not in recognition
            or "structured_financial_metadata" not in recognition
        ):
            artifact_id = str(artifact.get("id") or "")
            extract_path = case_path / "extracts" / f"{artifact_id}.txt"
            try:
                extract = extract_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                extract = ""
            file_name = str(artifact.get("file_name") or "")
            if "profile_hints" not in recognition:
                recognition["profile_hints"] = _profile_hints(file_name, extract)
            if "structured_financial_metadata" not in recognition:
                recognition["structured_financial_metadata"] = (
                    parse_structured_financial_metadata(file_name, extract)
                )
        artifact["recognition"] = recognition
        artifacts.append(artifact)
    enriched["artifacts"] = artifacts
    if not isinstance(enriched.get("profile_hints"), dict):
        enriched["profile_hints"] = {
            "tags": _merge_profile_hints(artifacts),
            "authority": "routing_hint_only",
            "source": "declared_fields_in_uploaded_materials",
        }
    workflow_type = _normalized_workflow_type(payload.get("workflow_type"))
    enriched["workflow_type"] = workflow_type
    enriched["acquisition_diagnostic"] = _workflow_diagnostic(
        workflow_type,
        artifacts,
        enriched["profile_hints"],
    )
    if workflow_type == "company_intake":
        enriched["financial_basis_preflight"] = (
            diagnose_company_intake_financial_basis(artifacts)
        )
    else:
        enriched.pop("financial_basis_preflight", None)
    normalized_workflow: list[dict[str, Any]] = []
    for raw_step in payload.get("workflow") or []:
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        if step.get("id") in {"supplements", "review", "outputs"}:
            step["state"] = "not_available"
        normalized_workflow.append(step)
    if normalized_workflow:
        enriched["workflow"] = normalized_workflow
    return enriched


def _process_status(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = [
        item
        for item in payload.get("workflow") or []
        if isinstance(item, dict)
    ]
    active = next(
        (
            item
            for item in workflow
            if item.get("state") in {"ready", "running", "awaiting_human"}
        ),
        None,
    )
    if active is None:
        active = next(
            (item for item in workflow if item.get("state") == "blocked"),
            None,
        )
    if active is None:
        return {
            "stage_id": "unknown",
            "stage_label_zh": "状态未知",
            "state": "unknown",
            "state_label_zh": "状态未知",
            "source": "workflow",
        }
    state = str(active.get("state") or "unknown")
    state_labels = {
        "ready": "可开始",
        "running": "处理中",
        "awaiting_human": "待确认",
        "blocked": "等待前序",
        "complete": "已完成",
        "not_available": "尚未启用",
    }
    return {
        "stage_id": str(active.get("id") or "unknown"),
        "stage_label_zh": str(active.get("label") or "状态未知"),
        "state": state,
        "state_label_zh": state_labels.get(state, state),
        "source": "workflow",
    }


def _focus_topics(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for artifact in artifacts:
        recognition = artifact.get("recognition")
        if not isinstance(recognition, dict):
            continue
        for role in recognition.get("candidate_roles") or []:
            role_id = str(role)
            counts[role_id] = counts.get(role_id, 0) + 1
    return [
        {
            "id": role,
            "label_zh": ROLE_TOPIC_LABELS.get(role, role),
            "artifact_count": count,
            "authority": "routing_hint_only",
        }
        for role, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _case_summary(payload: dict[str, Any]) -> dict[str, Any]:
    artifacts = [
        item
        for item in payload.get("artifacts") or []
        if isinstance(item, dict) and item.get("kind") == "uploaded_material"
    ]
    candidate_ready = sum(
        item.get("recognition", {}).get("status") == "candidate_ready"
        for item in artifacts
        if isinstance(item.get("recognition"), dict)
    )
    needs_processing = sum(
        item.get("recognition", {}).get("status") == "awaiting_human"
        for item in artifacts
        if isinstance(item.get("recognition"), dict)
    )
    topics = _focus_topics(artifacts)
    declared_need = _short_text(payload.get("declared_need"), limit=240)
    if declared_need:
        need = {
            "text": declared_need,
            "source": "declared_by_user",
            "authority": "user_supplied",
        }
    elif topics:
        topic_names = "、".join(item["label_zh"] for item in topics[:2])
        need = {
            "text": f"{topic_names}的分析准备",
            "source": "derived_from_material_roles",
            "authority": "routing_hint_only",
        }
    else:
        need = {
            "text": "等待材料识别",
            "source": "system_state",
            "authority": "routing_hint_only",
        }
    reference_activity = payload.get("reference_activity")
    if not isinstance(reference_activity, dict):
        reference_activity = None
    workflow_type = _normalized_workflow_type(payload.get("workflow_type"))
    acquisition = payload.get("acquisition_diagnostic")
    if not isinstance(acquisition, dict):
        acquisition = _workflow_diagnostic(
            workflow_type,
            artifacts,
            payload.get("profile_hints"),
        )
    applicability = acquisition.get("applicability")
    if not isinstance(applicability, dict):
        applicability = {"status": "applicable"}
    acquisition_is_applicable = applicability.get("status") == "applicable"
    critical_gaps = [
        item
        for item in acquisition.get("critical_gaps") or []
        if isinstance(item, dict)
    ]
    interview_readiness = acquisition.get("business_model_interview_readiness")
    if not isinstance(interview_readiness, dict):
        interview_readiness = {}
    financial_preflight = payload.get("financial_basis_preflight")
    if workflow_type == "company_intake" and not isinstance(
        financial_preflight, dict
    ):
        financial_preflight = diagnose_company_intake_financial_basis(artifacts)
    if not isinstance(financial_preflight, dict):
        financial_preflight = {}
    financial_questions = [
        item
        for item in financial_preflight.get("questions") or []
        if isinstance(item, dict)
    ]
    financial_calculation = financial_preflight.get("calculation_status")
    if not isinstance(financial_calculation, dict):
        financial_calculation = {}
    financial_basis_blocked = (
        workflow_type == "company_intake"
        and financial_calculation.get("status") == "blocked"
        and bool(financial_questions)
    )
    if needs_processing:
        operational_status = {
            "id": "materials_need_processing",
            "label_zh": "材料需处理",
        }
        next_action = {
            "id": "resolve_material_extraction",
            "label_zh": "处理无法抽取的材料",
        }
    elif financial_basis_blocked:
        operational_status = {
            "id": "financial_basis_blocked",
            "label_zh": "财务口径待确认",
        }
        next_action = {
            "id": "review_financial_basis_questions",
            "label_zh": "复核财务口径问题",
        }
    elif acquisition_is_applicable and critical_gaps:
        operational_status = {
            "id": "critical_evidence_review_required",
            "label_zh": "关键证据待复核",
        }
        next_action = {
            "id": "review_critical_evidence_gaps",
            "label_zh": "复核关键证据缺口",
        }
    elif (
        acquisition_is_applicable
        and interview_readiness.get("status") == "insufficient"
    ):
        operational_status = {
            "id": "interview_evidence_insufficient",
            "label_zh": "访谈证据尚不足",
        }
        next_action = {
            "id": "prepare_supplement_draft",
            "label_zh": "准备补件草稿",
        }
    elif reference_activity and int(reference_activity.get("last_result_count") or 0) > 0:
        operational_status = {
            "id": "reference_search_run",
            "label_zh": "参考检索已运行",
        }
        next_action = {
            "id": "refresh_reference_suggestions",
            "label_zh": "更新参考建议",
        }
    else:
        operational_status = {
            "id": "materials_organized",
            "label_zh": "材料已整理",
        }
        next_action = {
            "id": "generate_reference_suggestions",
            "label_zh": "生成参考建议",
        }
    completeness = acquisition.get("completeness")
    if not isinstance(completeness, dict):
        completeness = {}
    stage_diagnostics = [
        item
        for item in acquisition.get("stage_diagnostics") or []
        if isinstance(item, dict)
    ]
    current_focus = next(
        (
            item
            for item in stage_diagnostics
            if float(item.get("completeness_ratio") or 0) < 1
        ),
        stage_diagnostics[-1] if stage_diagnostics else None,
    )
    return {
        "summary_version": "1.0",
        "case_id": payload.get("case_id"),
        "case_name": payload.get("case_name"),
        "case_type": payload.get("case_type"),
        "workflow_type": workflow_type,
        "revision": payload.get("revision"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "operational_status": operational_status,
        "process_status": _process_status(payload),
        "materials": {
            "total": len(artifacts),
            "candidate_ready": candidate_ready,
            "awaiting_manual_or_ocr": needs_processing,
            "hash_recorded": sum(bool(item.get("sha256")) for item in artifacts),
        },
        "material_count": len(artifacts),
        "focus_topics": topics,
        "current_need": need,
        "owner": payload.get("owner") or None,
        "responsible_actor_type": (
            payload.get("next_action", {}).get("actor")
            if isinstance(payload.get("next_action"), dict)
            else None
        ),
        "open_requests": None,
        "request_tracking_state": "not_implemented",
        "next_action": next_action,
        "reference_activity": reference_activity,
        "financial_basis": {
            "applicability": financial_preflight.get("applicability"),
            "calculation_status": financial_calculation.get("status"),
            "blocking_question_ids": list(
                financial_calculation.get("blocking_question_ids") or []
            ),
            "open_question_count": len(financial_questions),
            "question_ids": [item.get("id") for item in financial_questions],
            "candidate_response_receipt_count": len(
                financial_preflight.get("candidate_response_receipts") or []
            ),
            "authority": "preflight_projection_only",
        },
        "acquisition": {
            "applicability": dict(applicability),
            "material_readiness_percent": (
                float(completeness["percent"])
                if acquisition_is_applicable
                and isinstance(completeness.get("percent"), (int, float))
                else None
            ),
            "critical_gap_count": (
                len(critical_gaps) if acquisition_is_applicable else None
            ),
            "suggested_supplement_count": (
                len(acquisition.get("suggested_supplements") or [])
                if acquisition_is_applicable
                else None
            ),
            "current_focus_stage": (
                {
                    "id": current_focus.get("id"),
                    "order": current_focus.get("order"),
                    "name_zh": current_focus.get("name_zh"),
                    "coverage_status": current_focus.get("coverage_status"),
                }
                if current_focus
                else None
            ),
            "interview_readiness": {
                "status": interview_readiness.get(
                    "status",
                    "insufficient" if acquisition_is_applicable else "not_applicable",
                ),
                "label_zh": interview_readiness.get(
                    "label_zh",
                    "尚不足" if acquisition_is_applicable else "不适用",
                ),
            },
            "authority": (
                "candidate_material_coverage_only"
                if acquisition_is_applicable
                else "not_applicable"
            ),
            "deal_stage_is_human_confirmed": False,
        },
    }


class CaseWorkspaceStore:
    """Persist local case materials without exposing absolute paths to clients."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._write_lock = threading.Lock()

    def _case_path(self, case_id: str) -> Path:
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise MaterialValidationError("Invalid case identifier")
        candidate = (self.root / case_id).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise MaterialValidationError("Case path escapes workspace root") from exc
        return candidate

    @staticmethod
    def _public_projection(manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in manifest.items()
            if key not in {"storage_version"}
        }

    def create_case(
        self,
        *,
        case_name: str = "",
        files: list[tuple[str, bytes, str]],
        declared_need: str = "",
        owner: str = "",
        case_type: str = "unclassified",
        workflow_type: str = "company_intake",
    ) -> dict[str, Any]:
        normalized_need = re.sub(r"\s+", " ", declared_need).strip()
        normalized_owner = re.sub(r"\s+", " ", owner).strip()
        if len(normalized_need) > 240:
            raise MaterialValidationError(
                "Declared need must be at most 240 characters"
            )
        if len(normalized_owner) > 80:
            raise MaterialValidationError("Owner must be at most 80 characters")
        if case_type not in {"enterprise", "demo", "qa", "unclassified"}:
            raise MaterialValidationError(
                "Case type must be enterprise, demo, qa or unclassified"
            )
        normalized_workflow_type = str(workflow_type or "").strip()
        if normalized_workflow_type not in WORKFLOW_TYPES:
            raise MaterialValidationError(
                "Workflow type must be company_intake or acquisition"
            )
        if not files or len(files) > MAX_CASE_FILES:
            raise MaterialValidationError(
                f"Select between 1 and {MAX_CASE_FILES} material files"
            )
        total_bytes = sum(len(payload) for _, payload, _ in files)
        if total_bytes > MAX_TOTAL_FILE_BYTES:
            raise MaterialValidationError(
                f"Combined material size must not exceed {MAX_TOTAL_FILE_BYTES} bytes"
            )

        prepared: list[tuple[str, bytes, str]] = []
        seen_names: set[str] = set()
        for raw_name, payload, media_type in files:
            name = _safe_file_name(raw_name)
            if not payload:
                raise MaterialValidationError(f"Material is empty: {name}")
            if len(payload) > MAX_FILE_BYTES:
                raise MaterialValidationError(
                    f"Material exceeds {MAX_FILE_BYTES} bytes: {name}"
                )
            key = name.casefold()
            if key in seen_names:
                raise MaterialValidationError(f"Duplicate material file name: {name}")
            seen_names.add(key)
            prepared.append((name, payload, media_type))

        normalized_name = re.sub(r"\s+", " ", case_name).strip()
        if not normalized_name:
            normalized_name = _suggest_case_name(prepared)
        if len(normalized_name) > 120:
            raise MaterialValidationError("Case name must be at most 120 characters")

        case_id = f"case-{datetime.now():%Y%m%d}-{secrets.token_hex(5)}"
        case_path = self._case_path(case_id)
        temporary_path = self.root / f".{case_id}.tmp-{secrets.token_hex(4)}"
        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path.mkdir(parents=False, exist_ok=False)
        materials_path = temporary_path / "materials"
        extracts_path = temporary_path / "extracts"
        materials_path.mkdir()
        extracts_path.mkdir()

        artifacts: list[dict[str, Any]] = []
        try:
            for index, (name, payload, supplied_media_type) in enumerate(prepared, start=1):
                artifact_id = f"artifact-{index:04d}"
                stored_name = f"{index:03d}-{name}"
                destination = materials_path / stored_name
                destination.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                extracted_text, warnings = _extract_text(name, payload)
                roles, signals = _candidate_roles(name, extracted_text)
                profile_hints = _profile_hints(name, extracted_text)
                structured_financial_metadata = parse_structured_financial_metadata(
                    name, extracted_text
                )
                if extracted_text.strip():
                    (extracts_path / f"{artifact_id}.txt").write_text(
                        extracted_text,
                        encoding="utf-8",
                    )
                status = (
                    "awaiting_human"
                    if not extracted_text.strip()
                    else "candidate_ready"
                )
                media_type = (
                    supplied_media_type.strip()
                    or mimetypes.guess_type(name)[0]
                    or "application/octet-stream"
                )
                artifacts.append(
                    {
                        "id": artifact_id,
                        "kind": "uploaded_material",
                        "file_name": name,
                        "media_type": media_type,
                        "sha256": digest,
                        "byte_size": len(payload),
                        "version": 1,
                        "status": "ready",
                        "created_by_type": "human",
                        "created_at": _utc_now(),
                        "recognition": {
                            "status": status,
                            "candidate_roles": roles,
                            "matched_signals": signals,
                            "profile_hints": profile_hints,
                            "structured_financial_metadata": (
                                structured_financial_metadata
                            ),
                            "text_extracted": bool(extracted_text.strip()),
                            "extracted_character_count": len(extracted_text),
                            "warnings": warnings,
                            "authority": "routing_hint_only",
                            "human_review_required": True,
                        },
                    }
                )

            projection = _workflow_projection(artifacts)
            manifest: dict[str, Any] = {
                "storage_version": "1.0",
                "case_id": case_id,
                "revision": 1,
                "case_name": normalized_name,
                "case_type": case_type,
                "workflow_type": normalized_workflow_type,
                "declared_need": normalized_need or None,
                "owner": normalized_owner or None,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "artifacts": artifacts,
                "profile_hints": {
                    "tags": _merge_profile_hints(artifacts),
                    "authority": "routing_hint_only",
                    "source": "declared_fields_in_uploaded_materials",
                },
                "acquisition_diagnostic": _workflow_diagnostic(
                    normalized_workflow_type,
                    artifacts,
                    {
                        "tags": _merge_profile_hints(artifacts),
                        "authority": "routing_hint_only",
                        "source": "declared_fields_in_uploaded_materials",
                    },
                ),
                "financial_basis_preflight": (
                    diagnose_company_intake_financial_basis(artifacts)
                    if normalized_workflow_type == "company_intake"
                    else None
                ),
                "modules": _module_registry(),
                **projection,
                "boundaries": {
                    "material_roles_are_candidates": True,
                    "agent_outputs_are_candidates": True,
                    "human_review_required": True,
                    "public_release_authorized": False,
                    "aggregate_rating_available": False,
                },
            }
            (temporary_path / "workspace.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, case_path)
        except Exception:
            if temporary_path.exists():
                shutil.rmtree(temporary_path)
            raise
        return self._public_projection(manifest)

    def get_case(self, case_id: str) -> dict[str, Any]:
        path = self._case_path(case_id) / "workspace.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MaterialValidationError("Case workspace was not found") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaterialValidationError("Case workspace is unreadable") from exc
        if not isinstance(payload, dict):
            raise MaterialValidationError("Case workspace has an invalid root")
        enriched = _enrich_manifest(path.parent, payload)
        enriched["dashboard"] = _case_summary(enriched)
        return self._public_projection(enriched)

    def list_cases(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        summaries: list[dict[str, Any]] = []
        for path in self.root.glob("case-*/workspace.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            summaries.append(_case_summary(_enrich_manifest(path.parent, payload)))
        return sorted(
            summaries,
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )

    def dashboard(self) -> dict[str, Any]:
        cases = self.list_cases()
        enterprise_cases = [
            item for item in cases if item.get("case_type") == "enterprise"
        ]
        demo_cases = [
            item for item in cases if item.get("case_type") in {"demo", "qa"}
        ]
        unclassified_cases = [
            item for item in cases if item.get("case_type") == "unclassified"
        ]
        return {
            "generated_at": _utc_now(),
            "metrics": {
                "case_count": len(cases),
                "enterprise_count": len(enterprise_cases),
                "demo_count": len(demo_cases),
                "unclassified_count": len(unclassified_cases),
                "material_count": sum(
                    int(item.get("material_count") or 0) for item in cases
                ),
                "needs_processing_count": sum(
                    item.get("operational_status", {}).get("id")
                    == "materials_need_processing"
                    for item in cases
                    if isinstance(item.get("operational_status"), dict)
                ),
                "unassigned_enterprise_count": sum(
                    not item.get("owner") for item in enterprise_cases
                ),
                "critical_gap_company_count": sum(
                    int(item.get("acquisition", {}).get("critical_gap_count") or 0) > 0
                    for item in enterprise_cases
                    if isinstance(item.get("acquisition"), dict)
                ),
                "interview_schedulable_count": sum(
                    item.get("acquisition", {})
                    .get("interview_readiness", {})
                    .get("status")
                    == "interview_schedulable"
                    for item in enterprise_cases
                    if isinstance(item.get("acquisition"), dict)
                ),
            },
            "cases": cases,
            "source": {
                "type": "local_case_manifests",
                "case_count": len(cases),
                "authority": "workflow_projection",
            },
            "definitions": {
                "enterprise_count": (
                    "Explicit case_type=enterprise only; demo, QA and "
                    "unclassified cases are excluded."
                ),
                "current_need": (
                    "User-declared need when present; otherwise a routing hint derived "
                    "from material roles."
                ),
                "open_requests": (
                    "Not implemented; null must not be interpreted as zero requests."
                ),
                "material_readiness_percent": (
                    "Weighted coverage of candidate materials and routing hints; it is "
                    "not transaction progress and does not verify document contents."
                ),
            },
        }

    def record_reference_activity(
        self,
        case_id: str,
        *,
        result_count: int,
        query_status: str,
    ) -> dict[str, Any]:
        case_path = self._case_path(case_id)
        manifest_path = case_path / "workspace.json"
        with self._write_lock:
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise MaterialValidationError("Case workspace was not found") from exc
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MaterialValidationError("Case workspace is unreadable") from exc
            if not isinstance(payload, dict):
                raise MaterialValidationError("Case workspace has an invalid root")
            previous = payload.get("reference_activity")
            query_count = (
                int(previous.get("query_count") or 0) + 1
                if isinstance(previous, dict)
                else 1
            )
            now = _utc_now()
            payload["reference_activity"] = {
                "query_count": query_count,
                "last_queried_at": now,
                "last_result_count": max(0, int(result_count)),
                "last_status": _short_text(query_status, limit=80) or "unknown",
                "authority": "reference_suggestion_only",
            }
            payload["revision"] = int(payload.get("revision") or 0) + 1
            payload["updated_at"] = now
            temporary_path = manifest_path.with_name(
                f".workspace-{secrets.token_hex(4)}.tmp"
            )
            try:
                temporary_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary_path, manifest_path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        return self.get_case(case_id)

    def get_artifact_text(
        self,
        case_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        if not ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            raise MaterialValidationError("Invalid artifact identifier")
        case_payload = self.get_case(case_id)
        artifact = next(
            (
                item
                for item in case_payload.get("artifacts", [])
                if isinstance(item, dict) and item.get("id") == artifact_id
            ),
            None,
        )
        if artifact is None:
            raise MaterialValidationError("Material artifact was not found")
        extract_path = self._case_path(case_id) / "extracts" / f"{artifact_id}.txt"
        try:
            content = extract_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise MaterialValidationError(
                "Material has no extractable text; manual or OCR review is required"
            ) from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise MaterialValidationError("Material extract is unreadable") from exc
        return {
            "case_id": case_id,
            "artifact_id": artifact_id,
            "file_name": artifact.get("file_name"),
            "sha256": artifact.get("sha256"),
            "media_type": artifact.get("media_type"),
            "content": content,
            "character_count": len(content),
            "authority": "source_material_not_verified_fact",
            "human_review_required": True,
        }
