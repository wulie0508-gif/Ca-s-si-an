"""Optional cash-conversion context with explicit XBRL sign normalization."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Source

POLARITY_POLICY_VERSION = "1.0.0"
DRIVER_POLARITY: dict[str, dict[str, Any]] = {
    "accounts_receivable_change": {
        "factor": -1,
        "sign_semantics": "increase_decrease",
        "label": "Accounts receivable change",
        "label_zh": "应收账款变动",
        "reason": "An increase in receivables uses cash; a decrease releases cash.",
        "reason_zh": "应收账款增加占用现金，减少则释放现金。",
    },
    "inventory_change": {
        "factor": -1,
        "sign_semantics": "increase_decrease",
        "label": "Inventory change",
        "label_zh": "存货变动",
        "reason": "An increase in inventory uses cash; a decrease releases cash.",
        "reason_zh": "存货增加占用现金，减少则释放现金。",
    },
    "accounts_payable_change": {
        "factor": 1,
        "sign_semantics": "increase_decrease",
        "label": "Accounts payable change",
        "label_zh": "应付账款变动",
        "reason": "An increase in payables provides cash; a decrease uses cash.",
        "reason_zh": "应付账款增加提供现金，减少则占用现金。",
    },
    "contract_liability_change": {
        "factor": 1,
        "sign_semantics": "increase_decrease",
        "label": "Contract liability change",
        "label_zh": "合同负债变动",
        "reason": "An increase in contract liabilities provides cash; a decrease uses cash.",
        "reason_zh": "合同负债增加提供现金，减少则占用现金。",
    },
    "warranty_claim_payments": {
        "factor": -1,
        "sign_semantics": "payment_magnitude",
        "label": "Warranty claim payments",
        "label_zh": "质保索赔付款",
        "reason": "A reported payment magnitude is a cash use.",
        "reason_zh": "披露的付款金额代表现金流出。",
    },
}
POLARITY_POLICY_DIGEST = "sha256:" + hashlib.sha256(
    json.dumps(DRIVER_POLARITY, ensure_ascii=False, sort_keys=True).encode("utf-8")
).hexdigest()


def _disabled(
    sources: list[Source], selected_source_ids: list[str] | None = None
) -> dict[str, Any]:
    available = sorted(source.id for source in sources if source.role == "auxiliary")
    selected = sorted(set(selected_source_ids or []) & set(available))
    return {
        "enabled_by_user": False,
        "status": "disabled",
        "status_zh": "未启用",
        "affects_signal": False,
        "polarity_policy_version": POLARITY_POLICY_VERSION,
        "polarity_policy_digest": POLARITY_POLICY_DIGEST,
        "available_source_ids": available,
        "selected_source_ids": selected,
        "ignored_source_ids": sorted(set(available) - set(selected)),
        "items": [],
        "totals_by_period": [],
        "summary": "Optional cash-conversion context was not selected.",
        "summary_zh": "用户未启用可选现金转换辅助信息。",
        "validation": {"passed": True, "errors": []},
    }


def build_cash_conversion_context(
    manifest: dict[str, Any],
    sources: list[Source],
    selected_source_ids: list[str],
    financials: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize selected auxiliary driver magnitudes without changing signals."""

    config = manifest.get("cash_conversion_context") or {}
    if not config.get("enabled"):
        return _disabled(sources, selected_source_ids)

    errors: list[str] = []
    source_lookup = {source.id: source for source in sources}
    available = sorted(source.id for source in sources if source.role == "auxiliary")
    selected = sorted(set(selected_source_ids))
    invalid_selected = sorted(set(selected) - set(available))
    if invalid_selected:
        errors.append(
            "Cash context selected unavailable auxiliary source(s): "
            + ", ".join(invalid_selected)
        )
    ignored = sorted(set(available) - set(selected))
    periods = {
        period.get("period"): period
        for period in (financials or {}).get("periods", [])
        if period.get("period")
    }
    financial_currency = (financials or {}).get("currency")
    items: list[dict[str, Any]] = []
    facts = config.get("facts") or []
    if not facts:
        errors.append("Enabled cash_conversion_context requires at least one fact")

    for fact in facts:
        source_id = fact.get("source_id")
        if source_id not in selected:
            continue
        source = source_lookup.get(source_id)
        if source is None or source.role != "auxiliary":
            errors.append(
                f"Cash-conversion fact cites non-auxiliary source '{source_id}'"
            )
            continue
        driver_id = str(fact.get("driver_id") or "")
        policy = DRIVER_POLARITY.get(driver_id)
        if policy is None:
            errors.append(f"Unknown cash-conversion driver '{driver_id}'")
            continue
        if fact.get("sign_semantics") != policy["sign_semantics"]:
            errors.append(
                f"Cash-conversion driver '{driver_id}' has incompatible sign semantics"
            )
            continue
        reported_value = fact.get("reported_value")
        if not isinstance(reported_value, (int, float)):
            errors.append(f"Cash-conversion driver '{driver_id}' requires a numeric value")
            continue
        if not fact.get("locator"):
            errors.append(f"Cash-conversion driver '{driver_id}' requires a locator")
        period = periods.get(fact.get("period"))
        if period is None:
            errors.append(
                f"Cash-conversion driver '{driver_id}' cites an unknown financial period"
            )
            continue
        semantic_mismatches: list[str] = []
        if fact.get("period_start") != period.get("start_date"):
            semantic_mismatches.append("period_start")
        if fact.get("period_end") != period.get("end_date"):
            semantic_mismatches.append("period_end")
        if fact.get("currency") != financial_currency:
            semantic_mismatches.append("currency")
        if fact.get("unit") != financial_currency:
            semantic_mismatches.append("unit")
        if fact.get("accounting_scope") != "consolidated":
            semantic_mismatches.append("accounting_scope")
        if semantic_mismatches:
            errors.append(
                f"Cash-conversion driver '{driver_id}' has incompatible semantic "
                "field(s): " + ", ".join(semantic_mismatches)
            )
            continue
        normalized = float(reported_value) * int(policy["factor"])
        effect = "cash_source" if normalized > 0 else "cash_use" if normalized < 0 else "neutral"
        items.append(
            {
                "period": fact.get("period"),
                "period_start": fact.get("period_start"),
                "period_end": fact.get("period_end"),
                "driver_id": driver_id,
                "label": policy["label"],
                "label_zh": policy["label_zh"],
                "reported_value": float(reported_value),
                "sign_semantics": policy["sign_semantics"],
                "normalization_factor": policy["factor"],
                "normalized_cash_effect": normalized,
                "effect": effect,
                "effect_zh": {
                    "cash_source": "现金来源",
                    "cash_use": "现金占用",
                    "neutral": "中性",
                }[effect],
                "reason": policy["reason"],
                "reason_zh": policy["reason_zh"],
                "unit": fact.get("unit"),
                "currency": fact.get("currency"),
                "accounting_scope": fact.get("accounting_scope"),
                "source": {
                    "source_id": source.id,
                    "title": source.title,
                    "url": source.url,
                    "locator": fact.get("locator", ""),
                    "role": source.role,
                },
            }
        )

    if facts and not items and not errors:
        errors.append("Selected auxiliary sources have no cash-conversion facts")
    totals_by_period = []
    for period_id in sorted({item["period"] for item in items}):
        period_items = [item for item in items if item["period"] == period_id]
        cash_sources = sum(
            max(0.0, item["normalized_cash_effect"]) for item in period_items
        )
        cash_uses = sum(
            min(0.0, item["normalized_cash_effect"]) for item in period_items
        )
        totals_by_period.append(
            {
                "period": period_id,
                "cash_sources": cash_sources,
                "cash_uses": cash_uses,
                "net_effect": cash_sources + cash_uses,
            }
        )
    status = "invalid" if errors else "passed"
    return {
        "enabled_by_user": True,
        "status": status,
        "status_zh": "配置无效" if errors else "通过",
        "affects_signal": False,
        "polarity_policy_version": POLARITY_POLICY_VERSION,
        "polarity_policy_digest": POLARITY_POLICY_DIGEST,
        "available_source_ids": available,
        "selected_source_ids": selected,
        "ignored_source_ids": ignored,
        "items": items,
        "totals_by_period": totals_by_period,
        "summary": (
            f"Normalized {len(items)} selected driver(s) into explicit cash sources "
            "and uses. These are selected major drivers, not a complete OCF "
            "reconciliation, and cannot alter deterministic evidence signals."
        ),
        "summary_zh": (
            f"已将 {len(items)} 个所选驱动项规范为明确的现金来源或现金占用；"
            "这些仅是所选主要驱动项，并非完整的经营现金流调节表，且不能改变确定性证据信号。"
        ),
        "validation": {"passed": not errors, "errors": errors},
    }
