"""Versioned, subindustry-scoped deterministic evidence-signal rules.

Rules in this module are maintainer-authored product policy.  The two
``validated`` dimensions are executable and covered by the ordered public-case
release gate.  ``authored`` entries document intended rule inputs without
claiming that a card or signal has been validated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from .fact_semantics import (
    cash_operations_scope,
    margin_operations_scope,
    select_net_income_fact,
)

RULE_LIBRARY_VERSION = "0.3.2"
APPLICABILITY_CONTRACT_VERSION = "1.0.0"
APPLICABILITY_POLICY_ID = "pre-commercial-no-recognized-operating-revenue"
APPLICABILITY_POLICY_VERSION = "1.0.0"
VALID_RULE_STATUSES = {"authored", "validated"}
VALID_SIGNALS = {"red", "amber", "green"}
FORBIDDEN_SCOPES = {"", "*", "all", "any", "global"}


@dataclass(frozen=True)
class RuleDefinition:
    """An immutable rule branch or non-executable authored blueprint."""

    id: str
    dimension_id: str
    version: str
    status: str
    subindustry_scopes: tuple[str, ...]
    required_inputs: tuple[str, ...]
    conditions: tuple[tuple[str, str], ...]
    signal: str | None
    rationale: str
    rationale_zh: str
    path: str
    path_zh: str
    basis: str
    basis_zh: str

    @property
    def executable(self) -> bool:
        return self.status == "validated"

    def matches(self, scope_id: str, inputs: dict[str, Any]) -> bool:
        return (
            self.executable
            and scope_id in self.subindustry_scopes
            and all(inputs.get(key) == expected for key, expected in self.conditions)
        )


_PROFITABILITY_SCOPES = (
    "ev-charging-network-hardware-saas",
    "grid-scale-energy-storage-system-integration",
    "hydrogen-fuel-cell-electrolyzer-integrated",
    "lithium-materials-diversified-chemicals",
    "onsite-solid-oxide-fuel-cell-systems",
    "power-electronics-equipment",
    "solar-module-manufacturing",
    "solar-ebos-electrical-infrastructure-manufacturing",
    "solar-tracker-and-power-systems-manufacturing",
    "storage-equipment",
    "wind-blade-contract-manufacturing",
)
ASSET_OWNER_SCOPE = "contracted-renewable-generation-and-storage-asset-owner"
PRE_COMMERCIAL_TECHNOLOGY_SCOPE = (
    "pre-commercial-solid-state-lithium-metal-battery-development"
)
_CASH_SCOPES = (
    *_PROFITABILITY_SCOPES,
    ASSET_OWNER_SCOPE,
    PRE_COMMERCIAL_TECHNOLOGY_SCOPE,
)

_PRE_COMMERCIAL_APPLICABILITY_POLICY = {
    "policy_id": APPLICABILITY_POLICY_ID,
    "policy_version": APPLICABILITY_POLICY_VERSION,
    "dimension_id": "profitability-unit-economics",
    "subindustry_scope": PRE_COMMERCIAL_TECHNOLOGY_SCOPE,
    "required_contract_version": APPLICABILITY_CONTRACT_VERSION,
    "required_commercialization_stage": "pre_commercial",
    "required_recognized_operating_revenue": "none_recognized",
    "required_evidence_role": "subject",
    "period_policy": "recognized-revenue assertion covers every financial period",
    "date_policy": "commercialization-stage as_of is not later than assessment as_of",
}


def _digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


APPLICABILITY_POLICY_DIGEST = _digest(_PRE_COMMERCIAL_APPLICABILITY_POLICY)


def validate_applicability_context(
    context: dict[str, Any] | None,
    *,
    assessment_as_of: str,
    financial_periods: list[str],
    subject_source_ids: set[str],
) -> dict[str, Any]:
    """Validate cited pre-commercial applicability inputs without deriving an outcome.

    The manifest is allowed to supply evidence inputs only.  Policy-owned outcome,
    signal, and reason fields are deliberately absent from this contract.
    """

    if context is None:
        return {
            "status": "not_provided",
            "contract_version": None,
            "inputs": None,
            "validation": {"passed": True, "errors": []},
        }
    errors: list[str] = []
    if not isinstance(context, dict):
        return {
            "status": "invalid",
            "contract_version": None,
            "inputs": None,
            "validation": {
                "passed": False,
                "errors": ["applicability_context must be an object"],
            },
        }

    forbidden = {"outcome", "signal", "reason", "reason_zh", "reason_code"}.intersection(
        context
    )
    if forbidden:
        errors.append(
            "applicability_context cannot provide policy-owned fields: "
            + ", ".join(sorted(forbidden))
        )
    unknown_context_fields = set(context) - {
        "contract_version",
        "commercialization_stage",
        "recognized_operating_revenue",
    }
    if unknown_context_fields:
        errors.append(
            "applicability_context contains unsupported fields: "
            + ", ".join(sorted(unknown_context_fields))
        )
    if context.get("contract_version") != APPLICABILITY_CONTRACT_VERSION:
        errors.append(
            "applicability_context.contract_version must be "
            f"'{APPLICABILITY_CONTRACT_VERSION}'"
        )

    stage = context.get("commercialization_stage")
    if not isinstance(stage, dict):
        stage = {}
        errors.append("applicability_context.commercialization_stage must be an object")
    else:
        unknown_stage_fields = set(stage) - {"state", "as_of", "basis"}
        if unknown_stage_fields:
            errors.append(
                "commercialization_stage contains unsupported fields: "
                + ", ".join(sorted(unknown_stage_fields))
            )
    revenue = context.get("recognized_operating_revenue")
    if not isinstance(revenue, dict):
        revenue = {}
        errors.append(
            "applicability_context.recognized_operating_revenue must be an object"
        )
    else:
        unknown_revenue_fields = set(revenue) - {"state", "periods", "basis"}
        if unknown_revenue_fields:
            errors.append(
                "recognized_operating_revenue contains unsupported fields: "
                + ", ".join(sorted(unknown_revenue_fields))
            )
    if stage.get("state") != "pre_commercial":
        errors.append("commercialization_stage.state must be 'pre_commercial'")
    if revenue.get("state") != "none_recognized":
        errors.append(
            "recognized_operating_revenue.state must be 'none_recognized'"
        )

    stage_as_of = stage.get("as_of")
    try:
        parsed_stage_as_of = date.fromisoformat(stage_as_of)
        parsed_assessment_as_of = date.fromisoformat(assessment_as_of)
    except (TypeError, ValueError):
        errors.append(
            "commercialization_stage.as_of and assessment.as_of must be valid ISO dates"
        )
    else:
        if parsed_stage_as_of > parsed_assessment_as_of:
            errors.append(
                "commercialization_stage.as_of cannot be later than assessment.as_of"
            )

    claimed_periods = revenue.get("periods")
    if not isinstance(claimed_periods, list) or not claimed_periods or any(
        not isinstance(item, str) or not item for item in claimed_periods
    ):
        errors.append(
            "recognized_operating_revenue.periods must be a non-empty list of period ids"
        )
        normalized_periods: list[str] = []
    else:
        normalized_periods = sorted(set(claimed_periods))
        missing_periods = sorted(set(financial_periods) - set(normalized_periods))
        if missing_periods:
            errors.append(
                "recognized_operating_revenue.periods must cover all financial periods; "
                "missing: " + ", ".join(missing_periods)
            )
    if not financial_periods:
        errors.append(
            "applicability_context requires financial periods for coverage validation"
        )

    def validate_basis(field: str, raw: Any) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        if not isinstance(raw, list) or not raw:
            errors.append(f"{field}.basis must contain at least one citation")
            return normalized
        for index, citation in enumerate(raw, start=1):
            if not isinstance(citation, dict):
                errors.append(f"{field}.basis[{index}] must be a citation object")
                continue
            source_id = citation.get("source_id")
            locator = citation.get("locator")
            if not isinstance(source_id, str) or not source_id:
                errors.append(f"{field}.basis[{index}] requires source_id")
                continue
            if source_id not in subject_source_ids:
                errors.append(
                    f"{field}.basis may cite same-subject role=subject sources only; "
                    f"'{source_id}' is not eligible"
                )
            if not isinstance(locator, str) or not locator:
                errors.append(f"{field}.basis[{index}] requires locator")
                continue
            normalized.append({"source_id": source_id, "locator": locator})
        return sorted(normalized, key=lambda item: (item["source_id"], item["locator"]))

    stage_basis = validate_basis("commercialization_stage", stage.get("basis"))
    revenue_basis = validate_basis(
        "recognized_operating_revenue", revenue.get("basis")
    )
    inputs = {
        "contract_version": context.get("contract_version"),
        "commercialization_stage": {
            "state": stage.get("state"),
            "as_of": stage_as_of,
            "basis": stage_basis,
        },
        "recognized_operating_revenue": {
            "state": revenue.get("state"),
            "periods": normalized_periods,
            "basis": revenue_basis,
        },
    }
    return {
        "status": "validated" if not errors else "invalid",
        "contract_version": context.get("contract_version"),
        "inputs": inputs,
        "validation": {"passed": not errors, "errors": errors},
    }


def dimension_applicability(
    dimension_id: str,
    scope_id: str,
    applicability_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if dimension_id == "profitability-unit-economics" and scope_id == ASSET_OWNER_SCOPE:
        return {
            "status": "not_applicable",
            "reason": (
                "Manufacturing gross-margin unit economics are not applicable to a "
                "contracted generation asset owner whose cost-of-revenue concept excludes "
                "material depreciation and asset-level economics."
            ),
            "reason_zh": (
                "制造业毛利率单位经济性不适用于合约型发电资产所有者；其营业成本概念"
                "未覆盖重要折旧及资产层面经济性。"
            ),
        }
    if (
        dimension_id == "profitability-unit-economics"
        and scope_id == PRE_COMMERCIAL_TECHNOLOGY_SCOPE
        and (applicability_context or {}).get("status") == "validated"
    ):
        inputs = (applicability_context or {})["inputs"]
        period_text = ", ".join(inputs["recognized_operating_revenue"]["periods"])
        digest_inputs = {
            "dimension_id": dimension_id,
            "scope_id": scope_id,
            **inputs,
        }
        return {
            "status": "not_yet_applicable",
            "signal": None,
            "reason_code": "pre_commercial_no_recognized_operating_revenue",
            "reason": (
                "Profitability and unit economics are not yet applicable as of "
                f"{inputs['commercialization_stage']['as_of']}: cited same-subject evidence "
                "classifies the technology as pre-commercial and states that no operating "
                f"revenue was recognized for {period_text}. Missing revenue was not converted "
                "to zero."
            ),
            "reason_zh": (
                f"截至 {inputs['commercialization_stage']['as_of']}，盈利与单位经济性暂不适用："
                "同一主体来源的引用证据表明该技术仍处于预商业化阶段，且在 "
                f"{period_text} 未确认经营收入。缺失收入未被补记为零。"
            ),
            "basis": [
                *inputs["commercialization_stage"]["basis"],
                *inputs["recognized_operating_revenue"]["basis"],
            ],
            "policy_id": APPLICABILITY_POLICY_ID,
            "policy_version": APPLICABILITY_POLICY_VERSION,
            "policy_digest": APPLICABILITY_POLICY_DIGEST,
            "inputs_digest": _digest(digest_inputs),
            "inputs": inputs,
        }
    return {"status": "applicable", "reason": None, "reason_zh": None}


RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        id="profitability-own-margin-improving",
        dimension_id="profitability-unit-economics",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_PROFITABILITY_SCOPES,
        required_inputs=(
            "gross_margin_trend",
            "gross_margin_state",
            "net_income_state",
        ),
        conditions=(
            ("gross_margin_trend", "improving"),
            ("gross_margin_state", "nonnegative"),
            ("net_income_state", "profitable"),
        ),
        signal="green",
        rationale="The same-company gross-margin definition improved over the observed periods.",
        rationale_zh="同一公司、同一口径的毛利率在观察期内改善。",
        path="Classify the business first, then compare its own consistent gross-margin history before using adjacent-company context.",
        path_zh="先识别业务类型，再优先比较公司自身同口径毛利率历史，最后才使用相邻公司背景。",
        basis="Own-history direction; no cross-business-model absolute margin threshold.",
        basis_zh="依据公司自身历史方向判断；不采用跨商业模式的绝对毛利率阈值。",
    ),
    RuleDefinition(
        id="profitability-positive-margin-loss-making-improving",
        dimension_id="profitability-unit-economics",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_PROFITABILITY_SCOPES,
        required_inputs=(
            "gross_margin_trend",
            "gross_margin_state",
            "net_income_state",
        ),
        conditions=(
            ("gross_margin_trend", "improving"),
            ("gross_margin_state", "nonnegative"),
            ("net_income_state", "loss_making"),
        ),
        signal="amber",
        rationale="Gross margin improved and was positive, but the company remained loss-making at net-income level.",
        rationale_zh="毛利率改善且为正，但公司在净利润层面仍处于亏损。",
        path="Separate positive gross margin from achieved company-level profitability, then inspect mix, operating expense, and cash burn.",
        path_zh="区分正毛利率与已实现公司整体盈利，并检查收入组合、运营费用和现金消耗。",
        basis="Own-history gross-margin direction plus the accounting net-income boundary; no cross-business-model performance threshold.",
        basis_zh="依据公司自身毛利率方向及净利润盈亏边界；不采用跨商业模式的业绩阈值。",
    ),
    RuleDefinition(
        id="profitability-negative-margin-improving",
        dimension_id="profitability-unit-economics",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_PROFITABILITY_SCOPES,
        required_inputs=("gross_margin_trend", "gross_margin_state"),
        conditions=(
            ("gross_margin_trend", "improving"),
            ("gross_margin_state", "negative"),
        ),
        signal="amber",
        rationale="The same-company gross-margin definition improved but remained negative.",
        rationale_zh="同一公司、同一口径的毛利率虽有改善，但仍为负值。",
        path="Separate loss-stage improvement from achieved positive unit economics, then retain durability and funding gaps.",
        path_zh="区分亏损阶段改善与已实现正向单位经济性，并保留持续性和资金缺口。",
        basis="Own-history direction plus the accounting profit/loss boundary; no cross-business-model performance threshold.",
        basis_zh="依据公司自身历史方向及会计盈亏边界；不采用跨商业模式的业绩阈值。",
    ),
    RuleDefinition(
        id="profitability-own-margin-flat",
        dimension_id="profitability-unit-economics",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_PROFITABILITY_SCOPES,
        required_inputs=("gross_margin_trend",),
        conditions=(("gross_margin_trend", "flat"),),
        signal="amber",
        rationale="The same-company gross-margin definition was unchanged over the observed periods.",
        rationale_zh="同一公司、同一口径的毛利率在观察期内没有变化。",
        path="Classify the business first, then compare its own consistent gross-margin history before using adjacent-company context.",
        path_zh="先识别业务类型，再优先比较公司自身同口径毛利率历史，最后才使用相邻公司背景。",
        basis="Own-history direction; no cross-business-model absolute margin threshold.",
        basis_zh="依据公司自身历史方向判断；不采用跨商业模式的绝对毛利率阈值。",
    ),
    RuleDefinition(
        id="profitability-own-margin-declining",
        dimension_id="profitability-unit-economics",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_PROFITABILITY_SCOPES,
        required_inputs=("gross_margin_trend",),
        conditions=(("gross_margin_trend", "declining"),),
        signal="amber",
        rationale="The same-company gross-margin definition declined over the observed periods and needs durability review.",
        rationale_zh="同一公司、同一口径的毛利率在观察期内下降，需要进一步判断持续性。",
        path="Classify the business first, then compare its own consistent gross-margin history before using adjacent-company context.",
        path_zh="先识别业务类型，再优先比较公司自身同口径毛利率历史，最后才使用相邻公司背景。",
        basis="Own-history direction; no cross-business-model absolute margin threshold.",
        basis_zh="依据公司自身历史方向判断；不采用跨商业模式的绝对毛利率阈值。",
    ),
    RuleDefinition(
        id="cash-profitable-covered-improving",
        dimension_id="cash-runway",
        version="1.1.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "profitable_covered_improving"),),
        signal="green",
        rationale="A profitable company generated positive operating cash flow relative to capex and its own coverage improved.",
        rationale_zh="盈利公司经营现金流为正、能够覆盖资本开支，且自身覆盖趋势改善。",
        path="Select the profit-state branch, then compare operating cash flow with capex and the company's own prior-period coverage.",
        path_zh="先按盈利状态选择分支，再比较经营现金流、资本开支及公司自身上期覆盖情况。",
        basis="Profit-state branch and same-company cash-coverage direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支及公司自身现金覆盖方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-profitable-covered-flat",
        dimension_id="cash-runway",
        version="1.1.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "profitable_covered_flat"),),
        signal="green",
        rationale="A profitable company generated positive operating cash flow relative to capex and its own coverage was stable.",
        rationale_zh="盈利公司经营现金流为正、能够覆盖资本开支，且自身覆盖情况稳定。",
        path="Select the profit-state branch, then compare operating cash flow with capex and the company's own prior-period coverage.",
        path_zh="先按盈利状态选择分支，再比较经营现金流、资本开支及公司自身上期覆盖情况。",
        basis="Profit-state branch and same-company cash-coverage direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支及公司自身现金覆盖方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-profitable-covered-declining",
        dimension_id="cash-runway",
        version="1.1.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "profitable_covered_declining"),),
        signal="amber",
        rationale="A profitable company generated positive operating cash flow relative to capex, but its own coverage declined.",
        rationale_zh="盈利公司经营现金流为正并能够覆盖资本开支，但自身覆盖情况下降。",
        path="Select the profit-state branch, then compare operating cash flow with capex and the company's own prior-period coverage.",
        path_zh="先按盈利状态选择分支，再比较经营现金流、资本开支及公司自身上期覆盖情况。",
        basis="Profit-state branch and same-company cash-coverage direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支及公司自身现金覆盖方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-profitable-not-covered",
        dimension_id="cash-runway",
        version="1.1.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "profitable_not_covered"),),
        signal="red",
        rationale="The latest period was profitable, but operating cash flow did not positively cover capex.",
        rationale_zh="最近一期虽盈利，但经营现金流未能正向覆盖资本开支。",
        path="Select the profit-state branch, then compare operating cash flow with capex and the company's own prior-period coverage.",
        path_zh="先按盈利状态选择分支，再比较经营现金流、资本开支及公司自身上期覆盖情况。",
        basis="Profit-state branch and the arithmetic OCF/capex coverage boundary of 1.0x; no universal runway threshold.",
        basis_zh="依据盈利状态分支及经营现金流/资本开支达到 1.0 倍的算术覆盖边界；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-loss-making-positive-ocf",
        dimension_id="cash-runway",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "loss_making_positive_ocf"),),
        signal="amber",
        rationale="The company remained loss-making while operating cash flow was positive; forward funding still needs review.",
        rationale_zh="公司仍处于亏损状态，但经营现金流为正；前瞻资金需求仍需审查。",
        path="For a loss-making company, inspect the direction of operating cash use and expose the missing forward funding schedule.",
        path_zh="对于亏损公司，检查经营现金消耗方向，并明确缺失的前瞻资金计划。",
        basis="Profit-state branch and same-company operating-cash direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支和公司自身经营现金方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-loss-making-burn-improving",
        dimension_id="cash-runway",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "loss_making_burn_improving"),),
        signal="amber",
        rationale="The company remained loss-making and consumed operating cash, but the same-company burn direction improved.",
        rationale_zh="公司仍亏损且消耗经营现金，但公司自身现金消耗方向有所改善。",
        path="For a loss-making company, inspect the direction of operating cash use and expose the missing forward funding schedule.",
        path_zh="对于亏损公司，检查经营现金消耗方向，并明确缺失的前瞻资金计划。",
        basis="Profit-state branch and same-company operating-cash direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支和公司自身经营现金方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-loss-making-burn-not-improving",
        dimension_id="cash-runway",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "loss_making_burn_not_improving"),),
        signal="red",
        rationale="The company remained loss-making and consumed operating cash without an improving same-company burn direction.",
        rationale_zh="公司持续亏损并消耗经营现金，且公司自身现金消耗方向没有改善。",
        path="For a loss-making company, inspect the direction of operating cash use and expose the missing forward funding schedule.",
        path_zh="对于亏损公司，检查经营现金消耗方向，并明确缺失的前瞻资金计划。",
        basis="Profit-state branch and same-company operating-cash direction; no universal runway threshold.",
        basis_zh="依据盈利状态分支和公司自身经营现金方向；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="cash-profit-transition",
        dimension_id="cash-runway",
        version="1.0.0",
        status="validated",
        subindustry_scopes=_CASH_SCOPES,
        required_inputs=("cash_pattern",),
        conditions=(("cash_pattern", "profit_transition"),),
        signal="amber",
        rationale="Profit status changed between the observed periods, so the evidence remains transitional.",
        rationale_zh="观察期内盈利状态发生变化，因此证据仍处于过渡状态。",
        path="Treat a profit-state transition as unresolved and retain explicit funding and durability gaps for human review.",
        path_zh="将盈利状态变化视为尚未解决，并保留资金与持续性缺口供人工审查。",
        basis="Same-company profit-state transition; no universal runway threshold.",
        basis_zh="依据公司自身盈利状态变化；不采用统一现金跑道阈值。",
    ),
    RuleDefinition(
        id="revenue-quality-blueprint",
        dimension_id="revenue-traction-quality",
        version="0.1.0",
        status="authored",
        subindustry_scopes=("power-electronics-equipment",),
        required_inputs=("binding_demand_state", "concentration_direction"),
        conditions=(),
        signal=None,
        rationale="Authored input contract only; no executable signal branch is validated.",
        rationale_zh="仅完成输入合约编写；尚无经过验证的可执行信号分支。",
        path="Separate binding demand from cancellable or conditional demand, then inspect concentration.",
        path_zh="区分约束性需求与可取消或附条件需求，再检查集中度。",
        basis="Subindustry-specific revenue-quality evidence.",
        basis_zh="子行业特定的收入质量证据。",
    ),
    RuleDefinition(
        id="capex-scale-up-blueprint",
        dimension_id="capex-scale-up",
        version="0.1.0",
        status="authored",
        subindustry_scopes=("power-electronics-equipment",),
        required_inputs=("remaining_capital_state", "qualified_output_direction"),
        conditions=(),
        signal=None,
        rationale="Authored input contract only; no executable signal branch is validated.",
        rationale_zh="仅完成输入合约编写；尚无经过验证的可执行信号分支。",
        path="Relate remaining capital commitments to qualified saleable output rather than nameplate capacity alone.",
        path_zh="将剩余资本承诺与合格可售产出关联，而非只看名义产能。",
        basis="Subindustry-specific scale-up evidence.",
        basis_zh="子行业特定的扩产证据。",
    ),
    RuleDefinition(
        id="balance-sheet-funding-blueprint",
        dimension_id="balance-sheet-funding",
        version="0.1.0",
        status="authored",
        subindustry_scopes=("power-electronics-equipment",),
        required_inputs=("committed_funding_state", "restrictive_condition_state"),
        conditions=(),
        signal=None,
        rationale="Authored input contract only; no executable signal branch is validated.",
        rationale_zh="仅完成输入合约编写；尚无经过验证的可执行信号分支。",
        path="Separate committed capital from optional or expected funding and expose restrictive conditions.",
        path_zh="区分已承诺资本与可选或预期资金，并揭示限制性条件。",
        basis="Subindustry-specific balance-sheet and funding evidence.",
        basis_zh="子行业特定的资产负债表与融资证据。",
    ),
    RuleDefinition(
        id="project-bankability-blueprint",
        dimension_id="project-bankability",
        version="0.1.0",
        status="authored",
        subindustry_scopes=("power-electronics-equipment",),
        required_inputs=("independent_acceptance_state", "remedy_tenor_alignment"),
        conditions=(),
        signal=None,
        rationale="Authored input contract only; no executable signal branch is validated.",
        rationale_zh="仅完成输入合约编写；尚无经过验证的可执行信号分支。",
        path="Look for independent lender or insurer acceptance and tenor-aligned warranties and remedies.",
        path_zh="检查独立贷款人或保险人是否接受，并核对质保与补救是否匹配项目期限。",
        basis="Subindustry-specific project-finance acceptance evidence.",
        basis_zh="子行业特定的项目融资接受证据。",
    ),
)


def _validate_library() -> None:
    identities: set[tuple[str, str]] = set()
    for rule in RULES:
        identity = (rule.id, rule.version)
        if identity in identities:
            raise RuntimeError(f"Duplicate rule identity: {rule.id}@{rule.version}")
        identities.add(identity)
        if rule.status not in VALID_RULE_STATUSES:
            raise RuntimeError(f"Unsupported rule status: {rule.status}")
        if not rule.subindustry_scopes or any(
            scope.strip().lower() in FORBIDDEN_SCOPES for scope in rule.subindustry_scopes
        ):
            raise RuntimeError(f"Rule {rule.id} requires explicit subindustry scope")
        if not rule.required_inputs:
            raise RuntimeError(f"Rule {rule.id} requires named inputs")
        if rule.executable and (rule.signal not in VALID_SIGNALS or not rule.conditions):
            raise RuntimeError(f"Validated rule {rule.id} requires conditions and a signal")
        if not rule.executable and rule.signal is not None:
            raise RuntimeError(f"Authored-only rule {rule.id} cannot emit a signal")


_validate_library()


def rules_for_dimension(dimension_id: str) -> tuple[RuleDefinition, ...]:
    return tuple(rule for rule in RULES if rule.dimension_id == dimension_id)


def rule_status_for_dimension(dimension_id: str) -> str:
    rules = rules_for_dimension(dimension_id)
    if any(rule.status == "validated" for rule in rules):
        return "validated"
    if rules:
        return "authored"
    return "not_authored"


def _periods(financials: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    periods = sorted(financials["periods"], key=lambda item: item["end_date"])
    if len(periods) < 2:
        raise ValueError("Deterministic rules require two financial periods")
    return periods[-1], periods[-2]


def _value(period: dict[str, Any], fact_id: str) -> float:
    return float(period["facts"][fact_id]["value"])


def _direction(latest: float, prior: float) -> str:
    if latest > prior:
        return "improving"
    if latest < prior:
        return "declining"
    return "flat"


def _gross_margin(period: dict[str, Any]) -> float:
    revenue = _value(period, "revenue")
    gross_profit = period.get("facts", {}).get("gross_profit")
    if gross_profit is not None:
        return float(gross_profit["value"]) / revenue
    return (revenue - _value(period, "operating_cost")) / revenue


def derive_rule_inputs(dimension_id: str, financials: dict[str, Any]) -> dict[str, Any]:
    """Derive qualitative inputs only from the subject's two observed periods."""

    latest, prior = _periods(financials)
    if dimension_id == "profitability-unit-economics":
        latest_margin = _gross_margin(latest)
        prior_margin = _gross_margin(prior)
        latest_scope = margin_operations_scope(latest)
        prior_scope = margin_operations_scope(prior)
        if latest_scope != prior_scope:
            raise ValueError("Profitability trend mixes different operations scopes")
        latest_income_id, latest_income, latest_income_scope = select_net_income_fact(
            latest, latest_scope
        )
        prior_income_id, _, prior_income_scope = select_net_income_fact(prior, prior_scope)
        if latest_income_scope["attribution"] != prior_income_scope["attribution"]:
            raise ValueError("Profitability trend mixes different net-income attributions")
        return {
            "gross_margin_trend": _direction(latest_margin, prior_margin),
            "gross_margin_state": "nonnegative" if latest_margin >= 0 else "negative",
            "net_income_state": (
                "profitable" if float(latest_income["value"]) >= 0 else "loss_making"
            ),
            "operations_scope": latest_scope,
            "net_income_attribution": latest_income_scope["attribution"],
            "latest_net_income_fact_id": latest_income_id,
            "prior_net_income_fact_id": prior_income_id,
            "latest_gross_margin": round(latest_margin, 6),
            "prior_gross_margin": round(prior_margin, 6),
            "gross_margin_change": round(latest_margin - prior_margin, 6),
            "latest_period": latest["period"],
            "prior_period": prior["period"],
        }

    if dimension_id != "cash-runway":
        raise ValueError(f"Dimension '{dimension_id}' has no validated deterministic engine")

    latest_scope = cash_operations_scope(latest)
    prior_scope = cash_operations_scope(prior)
    if latest_scope != prior_scope:
        raise ValueError("Cash trend mixes different operations scopes")
    latest_income_id, latest_income_fact, latest_income_scope = select_net_income_fact(
        latest, latest_scope
    )
    prior_income_id, prior_income_fact, prior_income_scope = select_net_income_fact(
        prior, prior_scope
    )
    if latest_income_scope["attribution"] != prior_income_scope["attribution"]:
        raise ValueError("Cash trend mixes different net-income attributions")
    latest_income = float(latest_income_fact["value"])
    prior_income = float(prior_income_fact["value"])
    latest_ocf = _value(latest, "operating_cash_flow")
    prior_ocf = _value(prior, "operating_cash_flow")
    latest_capex = abs(_value(latest, "capex"))
    prior_capex = abs(_value(prior, "capex"))
    latest_coverage = latest_ocf / latest_capex if latest_capex else None
    prior_coverage = prior_ocf / prior_capex if prior_capex else None

    profitable_latest = latest_income >= 0
    profitable_prior = prior_income >= 0
    if profitable_latest != profitable_prior:
        cash_pattern = "profit_transition"
    elif profitable_latest:
        if latest_ocf <= 0 or latest_coverage is None or latest_coverage < 1:
            cash_pattern = "profitable_not_covered"
        else:
            trend = (
                _direction(latest_coverage, prior_coverage)
                if prior_coverage is not None
                else "declining"
            )
            cash_pattern = f"profitable_covered_{trend}"
    elif latest_ocf >= 0:
        cash_pattern = "loss_making_positive_ocf"
    elif latest_ocf > prior_ocf:
        cash_pattern = "loss_making_burn_improving"
    else:
        cash_pattern = "loss_making_burn_not_improving"

    return {
        "cash_pattern": cash_pattern,
        "operations_scope": latest_scope,
        "net_income_attribution": latest_income_scope["attribution"],
        "latest_net_income_fact_id": latest_income_id,
        "prior_net_income_fact_id": prior_income_id,
        "latest_net_income": latest_income,
        "prior_net_income": prior_income,
        "latest_operating_cash_flow": latest_ocf,
        "prior_operating_cash_flow": prior_ocf,
        "latest_ocf_to_capex": round(latest_coverage, 6) if latest_coverage is not None else None,
        "prior_ocf_to_capex": round(prior_coverage, 6) if prior_coverage is not None else None,
        "latest_period": latest["period"],
        "prior_period": prior["period"],
    }


def evaluate_rule(
    dimension_id: str,
    scope_id: str,
    financials: dict[str, Any],
    applicability_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one validated rule branch and fail closed if scope/inputs do not match."""

    if not scope_id or scope_id.strip().lower() in FORBIDDEN_SCOPES:
        raise ValueError("Deterministic rule evaluation requires an explicit subindustry scope")
    applicability = dimension_applicability(
        dimension_id, scope_id, applicability_context
    )
    if applicability["status"] != "applicable":
        raise ValueError(
            f"Dimension '{dimension_id}' is not applicable in scope '{scope_id}': "
            f"{applicability['reason']}"
        )
    inputs = derive_rule_inputs(dimension_id, financials)
    candidates = [
        rule for rule in rules_for_dimension(dimension_id) if rule.matches(scope_id, inputs)
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one validated rule for '{dimension_id}' in scope "
            f"'{scope_id}', found {len(candidates)}"
        )
    rule = candidates[0]
    rule_payload = {
        "id": rule.id,
        "dimension_id": rule.dimension_id,
        "version": rule.version,
        "status": rule.status,
        "subindustry_scopes": rule.subindustry_scopes,
        "required_inputs": rule.required_inputs,
        "conditions": rule.conditions,
        "signal": rule.signal,
        "rationale": rule.rationale,
        "rationale_zh": rule.rationale_zh,
        "path": rule.path,
        "path_zh": rule.path_zh,
        "basis": rule.basis,
        "basis_zh": rule.basis_zh,
    }
    rule_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(rule_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
    )
    inputs_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "dimension_id": dimension_id,
                    "scope_id": scope_id,
                    "rule_version": rule.version,
                    "inputs": inputs,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    if dimension_id == "profitability-unit-economics":
        summary = (
            f"Own-history gross margin moved from {inputs['prior_gross_margin'] * 100:.1f}% "
            f"to {inputs['latest_gross_margin'] * 100:.1f}% "
            f"({inputs['gross_margin_change'] * 100:+.1f} pp); the scoped rule maps the "
            f"{inputs['gross_margin_trend']} direction with a "
            f"{inputs['gross_margin_state']} latest margin and "
            f"{inputs['net_income_state']} net-income state to {rule.signal}."
        )
        summary_zh = (
            f"公司自身毛利率从 {inputs['prior_gross_margin'] * 100:.1f}% 变为 "
            f"{inputs['latest_gross_margin'] * 100:.1f}%"
            f"（{inputs['gross_margin_change'] * 100:+.1f} 个百分点）；该子行业规则将"
            f"{inputs['gross_margin_trend']}方向、{inputs['gross_margin_state']}的"
            f"最新毛利率及{inputs['net_income_state']}净利润状态映射为 {rule.signal}。"
        )
        basis_fact_ids = (
            inputs["latest_net_income_fact_id"],
            "gross-margin",
            "gross-margin-change",
        )
    else:
        latest_coverage = inputs["latest_ocf_to_capex"]
        prior_coverage = inputs["prior_ocf_to_capex"]
        coverage_text = (
            f"latest OCF/capex {latest_coverage:.2f}x"
            if latest_coverage is not None
            else "latest OCF/capex unavailable"
        )
        if prior_coverage is not None:
            coverage_text += f" versus prior {prior_coverage:.2f}x"
        summary = (
            f"The subject's two-period cash pattern is '{inputs['cash_pattern']}' "
            f"({coverage_text}); the scoped rule maps it to {rule.signal}."
        )
        summary_zh = (
            f"该主体两期现金模式为“{inputs['cash_pattern']}”（{coverage_text}）；"
            f"该子行业规则将其映射为 {rule.signal}。"
        )
        basis_fact_ids = (
            inputs["latest_net_income_fact_id"],
            "operating_cash_flow",
            "capex",
            "sustained-loss",
            "operating-cash-flow-to-capex",
        )
    return {
        "rule_id": rule.id,
        "rule_version": rule.version,
        "rule_status": rule.status,
        "rule_library_version": RULE_LIBRARY_VERSION,
        "rule_digest": rule_digest,
        "inputs_digest": inputs_digest,
        "subindustry_scope": scope_id,
        "deterministic": True,
        "inputs": inputs,
        "condition": dict(rule.conditions),
        "signal": rule.signal,
        "rationale": rule.rationale,
        "rationale_zh": rule.rationale_zh,
        "path": rule.path,
        "path_zh": rule.path_zh,
        "summary": summary,
        "summary_zh": summary_zh,
        "basis": rule.basis,
        "basis_zh": rule.basis_zh,
        "basis_fact_ids": list(basis_fact_ids),
    }
