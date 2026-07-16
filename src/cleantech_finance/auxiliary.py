"""Optional, non-authoritative cross-checks against user-selected public sources."""

from __future__ import annotations

from typing import Any

from .models import Source


def _disabled(sources: list[Source]) -> dict[str, Any]:
    available = sorted(source.id for source in sources if source.role == "auxiliary")
    return {
        "enabled_by_user": False,
        "status": "disabled",
        "status_zh": "未启用",
        "affects_signal": False,
        "checks": [],
        "available_source_ids": available,
        "selected_source_ids": [],
        "ignored_source_ids": available,
        "summary": "Auxiliary source validation was not selected.",
        "summary_zh": "用户未选择辅助数据源校验。",
        "validation": {"passed": True, "errors": []},
    }


def validate_auxiliary_sources(
    manifest: dict[str, Any],
    sources: list[Source],
    financials: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare normalized facts without allowing auxiliary values to alter signals."""

    config = manifest.get("auxiliary_validation") or {}
    if not config.get("enabled"):
        return _disabled(sources)

    errors: list[str] = []
    if not financials:
        errors.append("Auxiliary validation requires primary financial facts")
    source_lookup = {source.id: source for source in sources}
    available_source_ids = sorted(
        source.id for source in sources if source.role == "auxiliary"
    )
    selected_source_ids = config.get("selected_source_ids")
    if not isinstance(selected_source_ids, list) or not all(
        isinstance(source_id, str) for source_id in selected_source_ids
    ):
        errors.append("auxiliary_validation.selected_source_ids must be a list of source ids")
        selected_source_ids = []
    selected_source_ids = sorted(set(selected_source_ids))
    invalid_selected = sorted(set(selected_source_ids) - set(available_source_ids))
    if invalid_selected:
        errors.append(
            "Selected auxiliary source ids are unavailable: " + ", ".join(invalid_selected)
        )
    ignored_source_ids = sorted(set(available_source_ids) - set(selected_source_ids))
    primary: dict[tuple[str, str], dict[str, Any]] = {}
    for period in (financials or {}).get("periods", []):
        for fact_id, fact in (period.get("facts") or {}).items():
            primary[(period.get("period"), fact_id)] = {
                "fact": fact,
                "period_end": period.get("end_date"),
                "currency": (financials or {}).get("currency"),
                "accounting_scope": fact.get("accounting_scope", "consolidated"),
            }

    relative_tolerance = config.get("relative_tolerance", 0.001)
    absolute_tolerance = config.get("absolute_tolerance", 0.0)
    if not isinstance(relative_tolerance, (int, float)) or relative_tolerance < 0:
        errors.append("auxiliary_validation.relative_tolerance must be non-negative")
        relative_tolerance = 0.001
    if not isinstance(absolute_tolerance, (int, float)) or absolute_tolerance < 0:
        errors.append("auxiliary_validation.absolute_tolerance must be non-negative")
        absolute_tolerance = 0.0

    checks: list[dict[str, Any]] = []
    for item in config.get("facts") or []:
        period = item.get("period")
        fact_id = item.get("fact_id")
        source_id = item.get("source_id")
        if source_id not in selected_source_ids:
            continue
        source = source_lookup.get(source_id)
        if not source:
            errors.append(f"Auxiliary fact cites unknown source '{source_id}'")
            continue
        if source.role != "auxiliary":
            errors.append(f"Auxiliary fact source '{source_id}' must have role 'auxiliary'")
            continue
        if not item.get("locator"):
            errors.append(f"Auxiliary fact '{fact_id}' is missing a locator")
        if not isinstance(item.get("value"), (int, float)):
            errors.append(f"Auxiliary fact '{fact_id}' requires a numeric value")
            continue
        common = {
            "period": period,
            "fact_id": fact_id,
            "label": item.get("label") or fact_id,
            "label_zh": item.get("label_zh") or item.get("label") or fact_id,
            "unit": item.get("unit"),
            "currency": item.get("currency"),
            "period_end": item.get("period_end"),
            "accounting_scope": item.get("accounting_scope"),
            "auxiliary_value": item["value"],
            "source": {
                "source_id": source.id,
                "title": source.title,
                "url": source.url,
                "locator": item.get("locator", ""),
                "role": source.role,
            },
        }
        if item.get("mode", "crosscheck") == "context":
            checks.append(
                {
                    **common,
                    "mode": "context",
                    "status": "context",
                    "status_zh": "辅助信息",
                    "primary_value": None,
                    "difference": None,
                }
            )
            continue
        primary_item = primary.get((period, fact_id))
        if not primary_item:
            checks.append(
                {
                    **common,
                    "mode": "crosscheck",
                    "status": "not_comparable",
                    "status_zh": "无法比较",
                    "primary_value": None,
                    "difference": None,
                }
            )
            continue
        semantic_mismatches = []
        for field in ("currency", "period_end", "accounting_scope"):
            if item.get(field) != primary_item.get(field):
                semantic_mismatches.append(
                    {
                        "field": field,
                        "primary": primary_item.get(field),
                        "auxiliary": item.get(field),
                    }
                )
        if item.get("unit") != primary_item.get("currency"):
            semantic_mismatches.append(
                {
                    "field": "unit",
                    "primary": primary_item.get("currency"),
                    "auxiliary": item.get("unit"),
                }
            )
        if semantic_mismatches:
            checks.append(
                {
                    **common,
                    "mode": "crosscheck",
                    "status": "not_comparable",
                    "status_zh": "口径不可比",
                    "primary_value": primary_item["fact"]["value"],
                    "difference": None,
                    "semantic_mismatches": semantic_mismatches,
                }
            )
            continue
        primary_value = float(primary_item["fact"]["value"])
        auxiliary_value = float(item["value"])
        difference = auxiliary_value - primary_value
        allowed = max(abs(primary_value) * float(relative_tolerance), float(absolute_tolerance))
        matched = abs(difference) <= allowed
        checks.append(
            {
                **common,
                "mode": "crosscheck",
                "status": "matched" if matched else "mismatch",
                "status_zh": "一致" if matched else "不一致",
                "primary_value": primary_value,
                "auxiliary_value": auxiliary_value,
                "difference": difference,
                "allowed_difference": allowed,
            }
        )

    if not config.get("facts"):
        errors.append("Enabled auxiliary validation requires at least one fact")
    elif not any(item.get("source_id") in selected_source_ids for item in config["facts"]):
        errors.append("Selected auxiliary sources require at least one configured fact")
    mismatches = sum(item["status"] == "mismatch" for item in checks)
    not_comparable = sum(item["status"] == "not_comparable" for item in checks)
    matched = sum(item["status"] == "matched" for item in checks)
    context_count = sum(item["status"] == "context" for item in checks)
    status = "invalid" if errors else "warning" if mismatches or not_comparable else "passed"
    status_zh = {"invalid": "配置无效", "warning": "存在差异", "passed": "通过"}[status]
    return {
        "enabled_by_user": True,
        "status": status,
        "status_zh": status_zh,
        "affects_signal": False,
        "checks": checks,
        "available_source_ids": available_source_ids,
        "selected_source_ids": selected_source_ids,
        "ignored_source_ids": ignored_source_ids,
        "summary": (
            f"{matched} matched, {mismatches} mismatched, {not_comparable} not comparable, "
            f"and {context_count} context facts. "
            "Auxiliary values never alter deterministic evidence signals."
        ),
        "summary_zh": (
            f"{matched} 项一致、{mismatches} 项不一致、{not_comparable} 项无法比较、"
            f"{context_count} 项辅助信息。"
            "辅助值永远不会改变确定性证据信号。"
        ),
        "validation": {"passed": not errors, "errors": errors},
    }
