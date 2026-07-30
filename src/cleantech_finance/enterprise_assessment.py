"""Deterministic enterprise assessment and human-review orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .enterprise_evidence import evaluate_claim_burden
from .enterprise_matching import load_matching_config, match_catalog
from .enterprise_store import AssessmentStore

VALIDATED_FINANCIAL_DIMENSIONS = {
    "profitability-unit-economics",
    "cash-runway",
}
PROFITABILITY_METRICS = {
    "revenue-growth",
    "gross-margin",
    "net-margin",
    "contribution-margin",
    "unit-economics",
}
CASH_METRICS = {
    "free-cash-flow",
    "operating-cash-flow-to-capex",
    "capex-to-revenue",
    "cash-runway-months",
    "cash-burn",
}
DEFAULT_ASSESSMENT_CONFIG: dict[str, Any] = {
    "required_profile_fields": [
        "technology",
        "business_model",
        "stage",
        "geography",
        "needs",
    ],
    "minimum_verified_financial_evidence": 2,
    "hard_negative_severities": ["critical"],
}


def load_assessment_config(path: str | Path | None = None) -> dict[str, Any]:
    settings = dict(DEFAULT_ASSESSMENT_CONFIG)
    if path is None:
        return settings
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Assessment configuration root must be an object")
    section = payload.get("assessment", payload)
    if not isinstance(section, dict):
        raise ValueError("assessment configuration must be an object")
    settings.update(section)
    return settings


def _metric_dimension(metric_id: str) -> str | None:
    if metric_id in PROFITABILITY_METRICS:
        return "profitability-unit-economics"
    if metric_id in CASH_METRICS:
        return "cash-runway"
    return None


def import_financial_audit(
    store: AssessmentStore,
    case_id: str,
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Adapt validated v0.4 financial outputs into case metrics and evidence."""

    validation = audit.get("validation") or {}
    if not validation.get("passed"):
        raise ValueError("Financial audit must pass its deterministic validation before import")
    sources = {
        str(source.get("id")): source
        for source in audit.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    metrics: list[dict[str, Any]] = []
    for metric in (audit.get("financial_analysis") or {}).get("metrics", []):
        metric_id = str(metric.get("id") or "")
        dimension = _metric_dimension(metric_id)
        if not dimension:
            continue
        evidence_ids: list[str] = []
        for item in metric.get("inputs") or []:
            source_id = str(item.get("source_id") or "")
            source = sources.get(source_id, {})
            locator = str(item.get("locator") or "").strip()
            if not source_id or not locator:
                raise ValueError(f"Financial metric {metric_id} has an untraceable input")
            claim = (
                f"{item.get('name')} for {item.get('period')}: {item.get('value')} "
                f"{(audit.get('financial_analysis') or {}).get('currency') or ''}"
            ).strip()
            evidence_id = store.add_evidence(
                case_id,
                {
                    "evidence_key": (
                        f"financial:{metric_id}:{source_id}:{locator}:{item.get('name')}:"
                        f"{item.get('period')}"
                    ),
                    "claim": claim,
                    "source": source.get("title") or source_id,
                    "locator": locator,
                    "date": source.get("published"),
                    "entity_id": case_id,
                    "source_level": "L1",
                    "type": "fact",
                    "confidence": "high",
                    "review_status": "verified",
                    "source_url": source.get("url"),
                    "sha256": source.get("sha256"),
                    "metadata": {
                        "input_module": "financial",
                        "financial_dimension": dimension,
                        "metric_id": metric_id,
                        "fact_name": item.get("name"),
                        "period": item.get("period"),
                        "normalized_value": item.get("value"),
                        "statement_scope": item.get("statement_scope"),
                        "imported_from_validated_audit": True,
                    },
                },
            )
            evidence_ids.append(evidence_id)
        metrics.append(
            {
                "metric_id": metric_id,
                "dimension": dimension,
                "value": {
                    "name": metric.get("name"),
                    "period": metric.get("period"),
                    "value": metric.get("value"),
                    "unit": metric.get("unit"),
                    "formula": metric.get("formula"),
                },
                "status": metric.get("signal") or "observed",
                "evidence_ids": sorted(set(evidence_ids)),
                "method": "cleantech_finance_v0.4_deterministic_financial_core",
            }
        )
    return metrics


def _profile_value(profile: dict[str, Any], field: str) -> Any:
    value = profile.get(field)
    if isinstance(value, str):
        return value.strip()
    return value


def _profile_tags(profile: dict[str, Any]) -> dict[str, list[str] | str]:
    tags = profile.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}
    return {
        "industry": tags.get("industry") or profile.get("industry") or [],
        "stage": tags.get("stage") or profile.get("stage") or [],
        "need": tags.get("need") or profile.get("needs") or [],
        "technology": tags.get("technology") or profile.get("technology") or [],
        "geography": tags.get("geography") or profile.get("geography") or [],
        "market": tags.get("market") or profile.get("target_market") or [],
    }


def _conflicts(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        metadata = item.get("metadata") or {}
        topic = str(metadata.get("topic") or "").strip()
        if topic and metadata.get("normalized_value") is not None:
            groups.setdefault(topic, []).append(item)
    conflicts: list[dict[str, Any]] = []
    for topic, items in groups.items():
        values = {
            json.dumps(item["metadata"].get("normalized_value"), sort_keys=True, ensure_ascii=False)
            for item in items
        }
        has_owner = any(item["type"] == "owner_statement" for item in items)
        has_verified_fact = any(
            item["type"] == "fact" and item["review_status"] == "verified" for item in items
        )
        if len(values) > 1 and has_owner and has_verified_fact:
            conflicts.append(
                {
                    "topic": topic,
                    "evidence_ids": [item["id"] for item in items],
                    "values": sorted(values),
                }
            )
    explicit = [
        {
            "topic": str((item.get("metadata") or {}).get("topic") or "explicit_conflict"),
            "evidence_ids": [
                item["id"],
                str((item.get("metadata") or {}).get("contradicts_evidence_id")),
            ],
            "values": [],
        }
        for item in evidence
        if (item.get("metadata") or {}).get("contradicts_evidence_id")
    ]
    return conflicts + explicit


def _build_dimensions(
    *,
    profile: dict[str, Any],
    evidence: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    verified_financial = [
        item
        for item in evidence
        if item["review_status"] == "verified"
        and item["type"] == "fact"
        and (item.get("metadata") or {}).get("financial_dimension")
        in VALIDATED_FINANCIAL_DIMENSIONS
    ]
    covered_dimensions = {
        item["dimension"]
        for item in metrics
        if item["dimension"] in VALIDATED_FINANCIAL_DIMENSIONS
        and item["status"] not in {"gap", "not_available"}
    }
    minimum = int(config["minimum_verified_financial_evidence"])
    if covered_dimensions == VALIDATED_FINANCIAL_DIMENSIONS and len(verified_financial) >= minimum:
        financial_status = "sufficient"
    elif covered_dimensions or verified_financial:
        financial_status = "partial"
    else:
        financial_status = "insufficient"

    conflicts = _conflicts(evidence)
    comparable_topics = {
        str((item.get("metadata") or {}).get("topic"))
        for item in evidence
        if (item.get("metadata") or {}).get("topic")
    }
    comparable_evidence_ids = [
        item["id"]
        for item in evidence
        if (item.get("metadata") or {}).get("topic")
    ]
    claim_burden = {
        topic: evaluate_claim_burden(items)
        for topic, items in {
            topic: [
                item
                for item in evidence
                if str((item.get("metadata") or {}).get("topic") or "").strip() == topic
            ]
            for topic in comparable_topics
        }.items()
    }
    if conflicts:
        consistency_status = "review_needed"
    elif comparable_topics:
        consistency_status = "consistent_on_available_evidence"
    else:
        consistency_status = "unassessable"

    negative = [
        item for item in evidence if bool((item.get("metadata") or {}).get("negative"))
    ]
    verified_negative = [item for item in negative if item["review_status"] == "verified"]
    pending_negative = [item for item in negative if item["review_status"] == "pending"]
    negative_status = "confirmed_items_present" if verified_negative else "none_confirmed"

    required_fields = list(config["required_profile_fields"])
    present_fields = [field for field in required_fields if _profile_value(profile, field)]
    completeness_ratio = len(present_fields) / len(required_fields) if required_fields else 1.0
    source_modules = {
        str((item.get("metadata") or {}).get("input_module"))
        for item in evidence
        if (item.get("metadata") or {}).get("input_module")
    }
    if completeness_ratio == 1 and {"financial", "interview", "public"} <= source_modules:
        completeness_status = "complete"
    elif completeness_ratio >= 0.6 or source_modules:
        completeness_status = "partial"
    else:
        completeness_status = "sparse"

    dimensions = {
        "financial_evidence_sufficiency": {
            "status": financial_status,
            "validated_dimensions_only": sorted(VALIDATED_FINANCIAL_DIMENSIONS),
            "covered_dimensions": sorted(covered_dimensions),
            "verified_financial_evidence_count": len(verified_financial),
            "evidence_ids": [item["id"] for item in verified_financial],
            "note": (
                "Only profitability/unit economics and cash flow/funding gap are "
                "end-to-end validated. Other financial dimensions remain input blueprints."
            ),
        },
        "information_consistency": {
            "status": consistency_status,
            "comparable_topic_count": len(comparable_topics),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "evidence_ids": comparable_evidence_ids,
            "claim_support": claim_burden,
        },
        "reviewed_negative_items": {
            "status": negative_status,
            "verified_count": len(verified_negative),
            "pending_count": len(pending_negative),
            "verified_evidence_ids": [item["id"] for item in verified_negative],
            "pending_evidence_ids": [item["id"] for item in pending_negative],
            "note": "Pending negative leads are displayed but never counted in inference.",
        },
        "data_completeness": {
            "status": completeness_status,
            "required_profile_fields": required_fields,
            "present_profile_fields": present_fields,
            "missing_profile_fields": sorted(set(required_fields) - set(present_fields)),
            "profile_completeness_ratio": round(completeness_ratio, 4),
            "input_modules_present": sorted(source_modules),
            "evidence_ids": [
                item["id"]
                for item in evidence
                if (item.get("metadata") or {}).get("input_module")
            ],
        },
    }
    return dimensions, conflicts, pending_negative


def _gap(
    identifier: str,
    missing: str,
    reason: str,
    route: str,
    priority: str,
    recompute_scope: list[str],
    required_source_level: str | None = None,
) -> dict[str, Any]:
    return {
        "gap_id": identifier,
        "missing": missing,
        "reason": reason,
        "route": route,
        "priority": priority,
        "required_source_level": required_source_level,
        "status": "open",
        "recompute_scope": recompute_scope,
    }


def _build_gaps(
    dimensions: dict[str, Any],
    conflicts: list[dict[str, Any]],
    pending_negative: list[dict[str, Any]],
    *,
    sidecar_status: dict[str, Any] | None,
    course_supplied: bool,
    policy_supplied: bool,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    covered = set(dimensions["financial_evidence_sufficiency"]["covered_dimensions"])
    for dimension in sorted(VALIDATED_FINANCIAL_DIMENSIONS - covered):
        gaps.append(
            _gap(
                f"financial-{dimension}",
                f"{dimension}的可核验财务输入",
                "Validated financial dimension has no supported case metric.",
                "document_request",
                "high",
                ["financial_evidence_sufficiency", dimension, "triage_recommendation"],
                "L1",
            )
        )
    for field in dimensions["data_completeness"]["missing_profile_fields"]:
        gaps.append(
            _gap(
                f"profile-{field}",
                field,
                "Required company profile field is absent.",
                "interview",
                "medium",
                ["data_completeness", "course_matching", "policy_matching"],
            )
        )
    for index, conflict in enumerate(conflicts, start=1):
        gaps.append(
            _gap(
                f"conflict-{index}",
                f"口述与核验事实冲突：{conflict['topic']}",
                "Owner statements do not prove truth and conflict with verified evidence.",
                "expert_review",
                "high",
                ["information_consistency", "triage_recommendation"],
            )
        )
    for item in pending_negative:
        gaps.append(
            _gap(
                f"negative-review-{item['id']}",
                "待核验负面线索",
                item["claim"],
                "expert_review",
                "high",
                ["reviewed_negative_items", "triage_recommendation"],
                "L1",
            )
        )
    if sidecar_status and sidecar_status.get("status") == "sidecar_unavailable":
        gaps.append(
            _gap(
                "nex-sidecar-unavailable",
                "NEX 本地缓存检索",
                "本地缓存未使用；公开检索必须走实时官方来源并保留该降级标记。",
                "public_search",
                "medium",
                ["public_evidence", "information_consistency"],
                "L1",
            )
        )
    if not course_supplied:
        gaps.append(
            _gap(
                "course-catalog-not-supplied",
                "正式课程 Excel/CSV",
                "Course recommendation cannot run without the formal catalog.",
                "document_request",
                "low",
                ["course_matching"],
            )
        )
    if not policy_supplied:
        gaps.append(
            _gap(
                "policy-catalog-not-supplied",
                "正式政策 Excel/CSV",
                "Policy recommendation cannot run without the formal reviewed catalog.",
                "document_request",
                "low",
                ["policy_matching"],
            )
        )
    return gaps


def _triage_recommendation(
    dimensions: dict[str, Any],
    evidence: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[str, list[str]]:
    hard_severities = {str(value) for value in config["hard_negative_severities"]}
    hard_negatives = [
        item
        for item in evidence
        if item["review_status"] == "verified"
        and bool((item.get("metadata") or {}).get("negative"))
        and str((item.get("metadata") or {}).get("severity")) in hard_severities
    ]
    if hard_negatives:
        return (
            "不进",
            [
                f"存在 {len(hard_negatives)} 条经人工复核的关键负面证据；该项仍需 leader 最终确认。",
                "负面线索只有在 verified 后才进入本建议。",
            ],
        )
    reasons: list[str] = []
    if dimensions["financial_evidence_sufficiency"]["status"] != "sufficient":
        reasons.append("两项端到端财务维度的证据尚不充分。")
    if dimensions["information_consistency"]["status"] in {"review_needed", "unassessable"}:
        reasons.append("信息一致性仍需复核或当前不可评估。")
    if dimensions["data_completeness"]["status"] != "complete":
        reasons.append("企业画像或五路输入尚未完整。")
    if reasons:
        return "补充信息后再议", reasons[:3]
    return (
        "进",
        [
            "两项已验证财务维度具备可追溯输入。",
            "现有可比信息未发现待复核冲突。",
            "五路输入达到本配置的完整性要求。",
        ],
    )


class EnterpriseAssessmentEngine:
    """Coordinate deterministic modules while preserving human authority."""

    def __init__(
        self,
        store: AssessmentStore,
        *,
        assessment_config: dict[str, Any] | None = None,
        matching_config: dict[str, Any] | None = None,
    ):
        self.store = store
        self.assessment_config = assessment_config or load_assessment_config()
        self.matching_config = matching_config or load_matching_config()

    def run(
        self,
        case_id: str,
        *,
        financial_audit: dict[str, Any] | None = None,
        course_catalog: str | Path | None = None,
        policy_catalog: str | Path | None = None,
        sidecar_status: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        before = self.store.get_case_bundle(case_id)
        version = (
            self.store.next_case_version(case_id)
            if before["decisions"]
            else int(before["case"]["version"])
        )
        imported_metrics = (
            import_financial_audit(self.store, case_id, financial_audit)
            if financial_audit
            else []
        )
        refreshed = self.store.get_case_bundle(case_id)
        profile = refreshed["case"]["profile"]
        latest_by_metric: dict[str, dict[str, Any]] = {}
        for item in refreshed["metrics"]:
            current = latest_by_metric.get(item["metric_id"])
            if current is None or item["version"] > current["version"]:
                latest_by_metric[item["metric_id"]] = item
        existing_current_metrics = [
            {
                "metric_id": item["metric_id"],
                "dimension": item["dimension"],
                "value": item["value"],
                "status": item["status"],
                "evidence_ids": item["evidence_ids"],
                "method": item["method"],
            }
            for item in latest_by_metric.values()
        ]
        metrics = imported_metrics or existing_current_metrics
        dimensions, conflicts, pending_negative = _build_dimensions(
            profile=profile,
            evidence=refreshed["evidence"],
            metrics=metrics,
            config=self.assessment_config,
        )
        match_results: dict[str, Any] = {}
        recommendations: list[dict[str, Any]] = []
        tags = _profile_tags(profile)
        if course_catalog:
            result = match_catalog(
                course_catalog,
                category="course",
                profile_tags=tags,
                as_of=refreshed["case"]["as_of"],
                config=self.matching_config,
            )
            match_results["course"] = result
            recommendations.extend(result["matches"])
        else:
            match_results["course"] = {
                "status": "catalog_not_supplied",
                "matches": [],
                "message": "未提供正式课程目录。",
            }
        if policy_catalog:
            result = match_catalog(
                policy_catalog,
                category="policy",
                profile_tags=tags,
                as_of=refreshed["case"]["as_of"],
                config=self.matching_config,
            )
            match_results["policy"] = result
            recommendations.extend(result["matches"])
        else:
            match_results["policy"] = {
                "status": "catalog_not_supplied",
                "matches": [],
                "message": "未提供正式政策目录。",
            }
        gaps = _build_gaps(
            dimensions,
            conflicts,
            pending_negative,
            sidecar_status=sidecar_status,
            course_supplied=bool(course_catalog),
            policy_supplied=bool(policy_catalog),
        )
        recommendation, reasons = _triage_recommendation(
            dimensions,
            refreshed["evidence"],
            self.assessment_config,
        )
        human_confirmation = [
            gap["missing"] for gap in gaps if gap["priority"] in {"high", "medium"}
        ]
        if not human_confirmation:
            human_confirmation = ["Leader 对建议与证据链的最终确认"]
        self.store.replace_assessment_outputs(
            case_id,
            version=version,
            metrics=metrics,
            gaps=gaps,
            recommendations=recommendations,
        )
        decision_id = self.store.create_draft_decision(
            case_id,
            recommendation=recommendation,
            reasons=reasons,
            human_confirmation=human_confirmation,
            actor=actor,
            version=version,
        )
        return {
            "schema_version": "1.0.0",
            "case_id": case_id,
            "version": version,
            "guardrails": {
                "aggregate_score": False,
                "automated_decision": False,
                "investment_or_credit_rating": False,
                "agent_evidence_can_override_rules": False,
                "human_review_required": True,
            },
            "dimensions": dimensions,
            "gaps": gaps,
            "matching": match_results,
            "recommendation": recommendation,
            "core_reasons": reasons,
            "human_confirmation": human_confirmation,
            "if_entering": {
                "courses": match_results["course"]["matches"],
                "policies": match_results["policy"]["matches"],
                "expert_types": sorted(
                    {
                        "财务证据复核"
                        if gap["gap_id"].startswith("financial-")
                        else "法律与声誉线索复核"
                        if gap["gap_id"].startswith(("negative-", "conflict-"))
                        else "企业材料与业务访谈"
                        for gap in gaps
                        if gap["priority"] in {"high", "medium"}
                    }
                ),
            },
            "decision": {
                "id": decision_id,
                "status": "draft",
                "workflow": "draft -> pending_review -> approved / rejected(reason)",
            },
            "sidecar": sidecar_status
            or {
                "status": "not_requested",
                "warnings": ["本次未请求 NEX 本地缓存。"],
            },
        }
