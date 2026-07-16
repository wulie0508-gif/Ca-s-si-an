"""Collect one reproducible SEC 10-K case and optionally enable XBRL cross-checks.

The collector performs network I/O before the offline audit. It downloads the
official filing and SEC company-facts payload into ``.cache`` and writes a
manifest whose primary facts cite the filing. The optional company-facts layer
is advisory only and cannot alter deterministic evidence signals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
CONCEPTS = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ),
    "operating_cost": (
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ),
    "gross_profit": ("GrossProfit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "net_income_continuing": (
        "NetIncomeLossFromContinuingOperationsAvailableToCommonShareholdersBasic",
        "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
    ),
    "cash_and_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
}
INSTANT_FACTS = {"cash_and_equivalents"}
FACT_LABELS_ZH = {
    "revenue": "营业收入",
    "operating_cost": "营业成本",
    "gross_profit": "毛利",
    "net_income": "净利润",
    "net_income_continuing": "持续经营净利润",
    "operating_cash_flow": "经营活动现金流",
    "capex": "资本开支",
    "cash_and_equivalents": "现金及现金等价物",
}
CASH_CONTEXT_CONCEPTS = {
    "accounts_receivable_change": {
        "concept": "IncreaseDecreaseInAccountsReceivable",
        "sign_semantics": "increase_decrease",
    },
    "inventory_change": {
        "concept": "IncreaseDecreaseInInventories",
        "sign_semantics": "increase_decrease",
    },
    "accounts_payable_change": {
        "concept": "IncreaseDecreaseInAccountsPayable",
        "sign_semantics": "increase_decrease",
    },
    "contract_liability_change": {
        "concept": "IncreaseDecreaseInContractWithCustomerLiability",
        "sign_semantics": "increase_decrease",
    },
    "warranty_claim_payments": {
        "concept": "ProductWarrantyAccrualPayments",
        "sign_semantics": "payment_magnitude",
    },
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("Company slug cannot be empty")
    return slug


def _download_json(url: str, destination: Path, user_agent: str) -> dict[str, Any]:
    _download(url, destination, user_agent)
    return json.loads(destination.read_text(encoding="utf-8"))


def _download(url: str, destination: Path, user_agent: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        return
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with (
            urllib.request.urlopen(request, timeout=90) as response,
            temporary.open("wb") as output,
        ):
            while block := response.read(1024 * 1024):
                output.write(block)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _latest_10k(submissions: dict[str, Any]) -> dict[str, str]:
    recent = submissions["filings"]["recent"]
    for index, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "accession": recent["accessionNumber"][index],
                "filed": recent["filingDate"][index],
                "report_date": recent["reportDate"][index],
                "primary_document": recent["primaryDocument"][index],
            }
    raise ValueError("No recent 10-K found in SEC submissions")


def _prior_10k(
    submissions: dict[str, Any], latest_accession: str
) -> dict[str, str]:
    recent = submissions["filings"]["recent"]
    found_latest = False
    for index, form in enumerate(recent["form"]):
        if form != "10-K":
            continue
        accession = recent["accessionNumber"][index]
        if accession == latest_accession:
            found_latest = True
            continue
        if found_latest:
            return {
                "accession": accession,
                "filed": recent["filingDate"][index],
                "report_date": recent["reportDate"][index],
                "primary_document": recent["primaryDocument"][index],
            }
    raise ValueError("No prior 10-K found for former-name identity evidence")


def _prior_end(end_date: str) -> str:
    parsed = date.fromisoformat(end_date)
    try:
        return parsed.replace(year=parsed.year - 1).isoformat()
    except ValueError:
        return parsed.replace(year=parsed.year - 1, day=28).isoformat()


def _duration_days(item: dict[str, Any]) -> int | None:
    if not item.get("start") or not item.get("end"):
        return None
    return (date.fromisoformat(item["end"]) - date.fromisoformat(item["start"])).days


def _fact_candidates(
    companyfacts: dict[str, Any],
    fact_id: str,
    end_date: str,
    accession: str,
    currency: str,
) -> list[dict[str, Any]]:
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    result: list[dict[str, Any]] = []
    for concept in CONCEPTS[fact_id]:
        units = gaap.get(concept, {}).get("units", {})
        candidates = list(units.get(currency, []))
        candidates = [
            item
            for item in candidates
            if item.get("form") == "10-K" and item.get("end") == end_date
        ]
        if fact_id not in INSTANT_FACTS:
            candidates = [
                item
                for item in candidates
                if (days := _duration_days(item)) is not None and 300 <= days <= 400
            ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda item: (
                item.get("accn") == accession,
                item.get("filed", ""),
                item.get("start", ""),
            ),
            reverse=True,
        )
        selected = candidates[0]
        result.append(
            {
                "fact_id": fact_id,
                "concept": concept,
                "value": float(selected["val"]),
                "start": selected.get("start"),
                "end": selected["end"],
                "filed": selected.get("filed"),
                "accession": selected.get("accn"),
                "form": selected.get("form"),
                "unit": currency,
            }
        )
    return result


def _cash_context_facts(
    companyfacts: dict[str, Any],
    end_date: str,
    accession: str,
    currency: str,
    source_id: str,
) -> list[dict[str, Any]]:
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    output: list[dict[str, Any]] = []
    for driver_id, policy in CASH_CONTEXT_CONCEPTS.items():
        concept = policy["concept"]
        candidates = list(gaap.get(concept, {}).get("units", {}).get(currency, []))
        candidates = [
            item
            for item in candidates
            if item.get("form") == "10-K"
            and item.get("end") == end_date
            and (days := _duration_days(item)) is not None
            and 300 <= days <= 400
        ]
        candidates.sort(
            key=lambda item: (
                item.get("accn") == accession,
                item.get("filed", ""),
            ),
            reverse=True,
        )
        if not candidates:
            continue
        selected = candidates[0]
        output.append(
            {
                "period": f"FY{end_date[:4]}",
                "period_start": selected.get("start"),
                "period_end": end_date,
                "driver_id": driver_id,
                "reported_value": float(selected["val"]),
                "sign_semantics": policy["sign_semantics"],
                "unit": currency,
                "currency": currency,
                "accounting_scope": "consolidated",
                "source_id": source_id,
                "locator": (
                    f"us-gaap:{concept} / {currency} / end {end_date} / "
                    f"filed {selected.get('filed')}"
                ),
            }
        )
    return output


def _selection_metadata(
    selected: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    method: str,
    basis: str,
    basis_zh: str,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    alternatives = [
        {
            "concept": item["concept"],
            "value": item["value"],
            "unit": item["unit"],
            "reason": "Not selected by the deterministic semantic policy.",
            "reason_zh": "未被确定性语义口径策略选中。",
        }
        for item in candidates
        if item["concept"] != selected["concept"] or item["value"] != selected["value"]
    ]
    metadata: dict[str, Any] = {
        "concept": selected["concept"],
        "method": method,
        "basis": basis,
        "basis_zh": basis_zh,
        "excluded_candidates": alternatives,
    }
    if reconciliation is not None:
        metadata["reconciliation"] = reconciliation
    return metadata


def _select_facts(
    companyfacts: dict[str, Any],
    end_date: str,
    accession: str,
    currency: str,
) -> dict[str, dict[str, Any]]:
    """Select annual facts and explain ambiguous statement-level concepts.

    Revenue and cost concepts are selected jointly when reported gross profit is
    available.  The pair that most closely satisfies the audited statement
    identity ``revenue - cost of revenue = gross profit`` wins.  This prevents a
    narrower contract-revenue or product-cost tag from silently replacing the
    consolidated statement total.
    """

    candidates = {
        fact_id: _fact_candidates(companyfacts, fact_id, end_date, accession, currency)
        for fact_id in CONCEPTS
    }
    required = {
        "revenue",
        "net_income",
        "operating_cash_flow",
        "capex",
        "cash_and_equivalents",
    }
    missing = [fact_id for fact_id in required if not candidates[fact_id]]
    if not candidates["gross_profit"] and not candidates["operating_cost"]:
        missing.append("gross_profit_or_operating_cost")
    if missing:
        raise ValueError(
            f"No annual SEC fact found for {', '.join(sorted(missing))} at {end_date}"
        )

    selected = {fact_id: items[0].copy() for fact_id, items in candidates.items() if items}
    reconciliation: dict[str, Any] | None = None
    triples = [
        (abs(revenue["value"] - cost["value"] - gross_profit["value"]), revenue, cost, gross_profit)
        for revenue in candidates["revenue"]
        for cost in candidates["operating_cost"]
        for gross_profit in candidates["gross_profit"]
    ]
    if triples:
        difference, revenue, cost, gross_profit = min(
            triples,
            key=lambda item: (
                item[0],
                CONCEPTS["revenue"].index(item[1]["concept"]),
                CONCEPTS["operating_cost"].index(item[2]["concept"]),
            ),
        )
        selected.update(
            {
                "revenue": revenue.copy(),
                "operating_cost": cost.copy(),
                "gross_profit": gross_profit.copy(),
            }
        )
        reconciliation = {
            "equation": "revenue - operating_cost = gross_profit",
            "difference": difference,
            "unit": currency,
            "passed": difference <= max(1.0, abs(gross_profit["value"]) * 1e-6),
        }

    semantic_ids = {"revenue", "operating_cost", "gross_profit"}
    for fact_id, fact in selected.items():
        if fact_id in semantic_ids and reconciliation is not None:
            fact["selection"] = _selection_metadata(
                fact,
                candidates[fact_id],
                method="statement_identity_reconciliation",
                basis=(
                    "Selected the consolidated concept combination that best reconciles "
                    "reported revenue, cost of revenue, and gross profit."
                ),
                basis_zh="选择最能勾稽已披露收入、营业成本与毛利的合并报表概念组合。",
                reconciliation=reconciliation,
            )
        else:
            fact["selection"] = _selection_metadata(
                fact,
                candidates[fact_id],
                method="ordered_concept_policy",
                basis="Selected the first available annual concept in the documented policy.",
                basis_zh="按已记录的概念优先级选择首个可用年度事实。",
            )
    return selected


def _relative_path(target: Path, manifest_path: Path) -> str:
    return Path(os.path.relpath(target.resolve(), manifest_path.parent.resolve())).as_posix()


def _accounting_scope(fact_id: str, concept: str) -> str:
    if fact_id in {"net_income", "net_income_continuing"} and concept in {
        "NetIncomeLoss",
        "NetIncomeLossFromContinuingOperationsAvailableToCommonShareholdersBasic",
    }:
        return "attributable_to_parent"
    return "consolidated"


def _statement_scope(
    fact_id: str, concept: str, performance_operations_scope: str
) -> dict[str, str]:
    if fact_id in {"net_income", "net_income_continuing"}:
        attribution = (
            "attributable_to_parent"
            if concept
            in {
                "NetIncomeLoss",
                "NetIncomeLossFromContinuingOperationsAvailableToCommonShareholdersBasic",
            }
            else "consolidated"
        )
    else:
        attribution = "not_applicable"
    if fact_id in {"revenue", "operating_cost", "gross_profit"}:
        operations = performance_operations_scope
    elif fact_id == "net_income_continuing":
        operations = "continuing_operations"
    else:
        operations = "total_operations"
    return {"operations": operations, "attribution": attribution}


def _observation(
    company: str,
    business_model: str,
    metric: str,
    period: str,
    value: float,
    unit: str,
    display_value: str,
    source_id: str,
    locator: str,
) -> dict[str, Any]:
    return {
        "comparison_type": "subject_history",
        "entity": company,
        "business_model": business_model,
        "metric": metric,
        "period": period,
        "value": value,
        "unit": unit,
        "display_value": display_value,
        "citation": {"source_id": source_id, "locator": locator},
    }


def _gaps(dimension_id: str) -> list[dict[str, str]]:
    if dimension_id == "profitability-unit-economics":
        return [
            {
                "kind": "evidence_gap",
                "text": "The automated case does not yet normalize segment mix, warranty accounting, or incentive effects.",
                "text_zh": "自动化案例尚未统一分部组合、质保会计或激励政策影响。",
            },
            {
                "kind": "human_judgment",
                "text": "Assess whether the observed margin direction is durable for this business model.",
                "text_zh": "需人工判断观察到的毛利率方向对该商业模式是否可持续。",
            },
            {
                "kind": "verification",
                "text": "Verify the selected XBRL revenue and cost concepts against the audited statements and notes.",
                "text_zh": "需将所选 XBRL 收入和成本概念与审计报表及附注核对。",
            },
        ]
    return [
        {
            "kind": "evidence_gap",
            "text": "The automated case does not build a forward schedule of commitments, maturities, or working-capital needs.",
            "text_zh": "自动化案例尚未建立承诺、到期债务或营运资金需求的前瞻计划。",
        },
        {
            "kind": "human_judgment",
            "text": "Stress-test whether historical cash conversion remains representative under the company's next operating cycle.",
            "text_zh": "需人工压力测试历史现金转化在公司下一经营周期是否仍具代表性。",
        },
        {
            "kind": "verification",
            "text": "Verify capex classification and restricted-cash scope against the cash-flow statement and notes.",
            "text_zh": "需对照现金流量表及附注核验资本开支分类和受限现金口径。",
        },
    ]


def collect(args: argparse.Namespace) -> Path:
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise RuntimeError(
            "Set SEC_USER_AGENT to a truthful contact string before collecting SEC sources"
        )
    cik = str(args.cik).zfill(10)
    slug = args.slug or _slug(args.company)
    output = Path(args.out or f"examples/company-loops/{slug}/manifest.json")
    cache = Path(args.cache_root) / slug
    submissions_path = cache / "submissions.json"
    facts_path = cache / "companyfacts.json"
    submissions = _download_json(
        f"{SEC_DATA}/submissions/CIK{cik}.json", submissions_path, user_agent
    )
    companyfacts = _download_json(
        f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json", facts_path, user_agent
    )
    filing = _latest_10k(submissions)
    accession_compact = filing["accession"].replace("-", "")
    filing_url = f"{SEC_ARCHIVES}/{int(cik)}/{accession_compact}/{filing['primary_document']}"
    filing_path = cache / filing["primary_document"]
    _download(filing_url, filing_path, user_agent)
    entity_id = f"sec-cik-{cik}"

    former_filing: dict[str, str] | None = None
    former_filing_url: str | None = None
    former_filing_path: Path | None = None
    former_source_id: str | None = None
    if args.former_name:
        if not args.rename_effective_period:
            raise ValueError(
                "--rename-effective-period is required with --former-name"
            )
        former_filing = _prior_10k(submissions, filing["accession"])
        former_accession = former_filing["accession"].replace("-", "")
        former_filing_url = (
            f"{SEC_ARCHIVES}/{int(cik)}/{former_accession}/"
            f"{former_filing['primary_document']}"
        )
        former_filing_path = cache / former_filing["primary_document"]
        _download(former_filing_url, former_filing_path, user_agent)
        former_source_id = f"{slug}-former-name-10k"

    end_dates = (filing["report_date"], _prior_end(filing["report_date"]))
    periods: list[dict[str, Any]] = []
    selected_by_period: dict[str, dict[str, dict[str, Any]]] = {}
    source_id = f"{slug}-10k"
    for end_date in reversed(end_dates):
        period = f"FY{end_date[:4]}"
        selected = _select_facts(
            companyfacts, end_date, filing["accession"], args.currency
        )
        selected_by_period[period] = selected
        facts = {
            fact_id: {
                "value": fact["value"],
                "source_id": source_id,
                "locator": (
                    f"Inline XBRL {fact['concept']}; period ended {fact['end']}; "
                    f"accession {fact['accession']}"
                ),
                "accounting_scope": _accounting_scope(fact_id, fact["concept"]),
                "statement_scope": _statement_scope(
                    fact_id, fact["concept"], args.performance_operations_scope
                ),
                "selection": fact["selection"],
            }
            for fact_id, fact in selected.items()
        }
        start_date = selected["revenue"].get("start")
        if not start_date:
            raise ValueError(f"Revenue fact for {period} has no annual start date")
        duration_days = (
            date.fromisoformat(end_date) - date.fromisoformat(start_date)
        ).days + 1
        periods.append(
            {
                "period": period,
                "fiscal_year": int(end_date[:4]),
                "period_type": "annual",
                "start_date": start_date,
                "end_date": end_date,
                "duration_days": duration_days,
                "facts": facts,
            }
        )

    latest_period, prior_period = periods[-1], periods[-2]
    latest_facts = latest_period["facts"]
    prior_facts = prior_period["facts"]
    def gross_margin(facts: dict[str, Any]) -> float:
        if "gross_profit" in facts:
            return facts["gross_profit"]["value"] / facts["revenue"]["value"]
        return (
            facts["revenue"]["value"] - facts["operating_cost"]["value"]
        ) / facts["revenue"]["value"]

    latest_margin = gross_margin(latest_facts)
    prior_margin = gross_margin(prior_facts)
    latest_coverage = latest_facts["operating_cash_flow"]["value"] / abs(
        latest_facts["capex"]["value"]
    )
    prior_coverage = prior_facts["operating_cash_flow"]["value"] / abs(
        prior_facts["capex"]["value"]
    )
    business_model = args.business_model or args.technology
    margin_locator_latest = latest_facts["revenue"]["locator"]
    margin_locator_prior = prior_facts["revenue"]["locator"]
    cash_locator_latest = latest_facts["operating_cash_flow"]["locator"]
    cash_locator_prior = prior_facts["operating_cash_flow"]["locator"]

    sources: list[dict[str, Any]] = [
        {
            "id": source_id,
            "path": _relative_path(filing_path, output),
            "url": filing_url,
            "title": f"{args.company} {latest_period['period']} Form 10-K",
            "publisher": args.company,
            "published": filing["filed"],
            "kind": "regulatory_filing",
            "role": "subject",
            "subject_entity_id": entity_id,
        }
    ]
    if former_filing and former_filing_url and former_filing_path and former_source_id:
        sources.append(
            {
                "id": former_source_id,
                "path": _relative_path(former_filing_path, output),
                "url": former_filing_url,
                "title": (
                    f"{args.former_name} FY{former_filing['report_date'][:4]} "
                    "Form 10-K"
                ),
                "publisher": args.former_name,
                "published": former_filing["filed"],
                "kind": "regulatory_filing",
                "role": "identity",
                "subject_entity_id": entity_id,
            }
        )
    auxiliary_facts: list[dict[str, Any]] = []
    auxiliary_id: str | None = None
    if args.enable_auxiliary:
        auxiliary_id = f"{slug}-sec-companyfacts"
        sources.append(
            {
                "id": auxiliary_id,
                "path": _relative_path(facts_path, output),
                "url": f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json",
                "title": f"SEC company facts for {args.company}",
                "publisher": "U.S. Securities and Exchange Commission",
                "published": filing["filed"],
                "kind": "regulator",
                "role": "auxiliary",
                "subject_entity_id": entity_id,
            }
        )
        for period, facts in selected_by_period.items():
            for fact_id, fact in facts.items():
                auxiliary_facts.append(
                    {
                        "period": period,
                        "fact_id": fact_id,
                        "mode": "crosscheck",
                        "label": fact_id.replace("_", " ").title(),
                        "label_zh": FACT_LABELS_ZH[fact_id],
                        "unit": args.currency,
                        "currency": args.currency,
                        "period_end": fact["end"],
                        "accounting_scope": _accounting_scope(
                            fact_id, fact["concept"]
                        ),
                        "value": fact["value"],
                        "source_id": auxiliary_id,
                        "locator": (
                            f"us-gaap:{fact['concept']} / {fact['unit']} / "
                            f"end {fact['end']} / filed {fact['filed']}"
                        ),
                    }
                )

    if args.enable_cash_conversion_context and not args.enable_auxiliary:
        raise ValueError(
            "--enable-cash-conversion-context requires --enable-auxiliary"
        )
    cash_context_facts = []
    if args.enable_cash_conversion_context and auxiliary_id:
        for end_date in end_dates:
            cash_context_facts.extend(
                _cash_context_facts(
                    companyfacts,
                    end_date,
                    filing["accession"],
                    args.currency,
                    auxiliary_id,
                )
            )

    company_zh = args.company_zh or args.company
    display_name = args.company
    display_name_zh = company_zh
    aliases: list[dict[str, Any]] = []
    if args.former_name and former_source_id:
        former_name_zh = args.former_name_zh or args.former_name
        display_name = f"{args.company} (formerly {args.former_name})"
        display_name_zh = f"{company_zh}（原 {former_name_zh}）"
        aliases.append(
            {
                "name": args.former_name,
                "name_zh": former_name_zh,
                "status": "former",
                "effective_until": args.rename_effective_period,
                "source_id": former_source_id,
                "locator": "Cover page and registrant legal name",
            }
        )

    payload = {
        "subject": {
            "organization": args.company,
            "technology": args.technology,
            "ticker": args.ticker,
            "cik": cik,
            "identity": {
                "entity_id": entity_id,
                "scheme": "sec_cik",
                "value": cik,
                "legal_name": args.company,
                "display_name": display_name,
                "display_name_zh": display_name_zh,
                "legal_name_citation": {
                    "source_id": source_id,
                    "locator": "Cover page and registrant legal name",
                },
                "aliases": aliases,
            },
        },
        "assessment": {
            "as_of": date.today().isoformat(),
            "horizon_years": 5,
            "geography": args.geography,
            "value_chain_scope": business_model,
        },
        "sources": sources,
        "financials": {"currency": args.currency, "periods": periods},
        "auxiliary_validation": {
            "enabled": bool(args.enable_auxiliary),
            "selected_source_ids": [
                f"{slug}-sec-companyfacts"
            ] if args.enable_auxiliary else [],
            "relative_tolerance": 0,
            "absolute_tolerance": 0,
            "facts": auxiliary_facts,
        },
        "cash_conversion_context": {
            "enabled": bool(args.enable_cash_conversion_context),
            "facts": cash_context_facts,
        },
        "judgment_context": {
            "contract_version": "0.3.0",
            "prepared_by": "collect_sec_case.py with user-supplied business classification",
            "prepared_at": date.today().isoformat(),
            "subindustry": {
                "scope_id": args.scope_id,
                "name": business_model,
                "name_zh": args.business_model_zh,
                "value_chain_position": business_model,
                "value_chain_position_zh": args.business_model_zh,
                "summary": (
                    f"{args.company} is tested in the '{args.scope_id}' scope. "
                    "The classification must be verified against Item 1 before publication."
                ),
                "summary_zh": (
                    f"{args.company} 按“{args.business_model_zh}”口径测试；"
                    "发布前必须对照 Form 10-K Item 1 核验分类。"
                ),
                "basis": [{"source_id": source_id, "locator": "Form 10-K Item 1"}],
            },
            "dimensions": {
                "profitability-unit-economics": {
                    "benchmark": {
                        "scope": "The company's own two-year gross-margin direction is primary; no peer threshold is used.",
                        "scope_zh": "优先比较公司自身连续两年的毛利率方向，不使用跨公司的绝对阈值。",
                        "observations": [
                            _observation(
                                args.company,
                                business_model,
                                "Gross margin",
                                latest_period["period"],
                                latest_margin * 100,
                                "percent",
                                f"{latest_margin * 100:.1f}%",
                                source_id,
                                margin_locator_latest,
                            ),
                            _observation(
                                args.company,
                                business_model,
                                "Gross margin",
                                prior_period["period"],
                                prior_margin * 100,
                                "percent",
                                f"{prior_margin * 100:.1f}%",
                                source_id,
                                margin_locator_prior,
                            ),
                        ],
                        "limitations": [
                            "This automated onboarding case uses own-history direction and does not establish peer comparability."
                        ],
                        "limitations_zh": [
                            "本自动接入案例只使用公司自身历史方向，不能据此证明同业可比性。"
                        ],
                    },
                    "gaps": _gaps("profitability-unit-economics"),
                },
                "cash-runway": {
                    "benchmark": {
                        "scope": "The profit-state branch and the company's own two-year OCF/capex direction are primary.",
                        "scope_zh": "优先使用盈亏状态分支及公司自身连续两年的经营现金流/资本开支方向。",
                        "observations": [
                            _observation(
                                args.company,
                                business_model,
                                "Operating cash flow / capex",
                                latest_period["period"],
                                latest_coverage,
                                "times",
                                f"{latest_coverage:.2f}x",
                                source_id,
                                cash_locator_latest,
                            ),
                            _observation(
                                args.company,
                                business_model,
                                "Operating cash flow / capex",
                                prior_period["period"],
                                prior_coverage,
                                "times",
                                f"{prior_coverage:.2f}x",
                                source_id,
                                cash_locator_prior,
                            ),
                        ],
                        "limitations": [
                            "Historical OCF/capex does not include every forward commitment or financing constraint."
                        ],
                        "limitations_zh": [
                            "历史经营现金流/资本开支并未覆盖所有前瞻承诺或融资约束。"
                        ],
                    },
                    "gaps": _gaps("cash-runway"),
                },
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(output.resolve()),
                "company": args.company,
                "filing": filing_url,
                "report_date": filing["report_date"],
                "auxiliary_enabled": bool(args.enable_auxiliary),
                "source_sha256": hashlib.sha256(filing_path.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cik", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--company-zh")
    parser.add_argument("--former-name")
    parser.add_argument("--former-name-zh")
    parser.add_argument(
        "--rename-effective-period",
        help="YYYY-MM period in which the former legal name ceased to be current",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--technology", required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--business-model")
    parser.add_argument("--business-model-zh", required=True)
    parser.add_argument(
        "--performance-operations-scope",
        choices=("total_operations", "continuing_operations"),
        default="total_operations",
    )
    parser.add_argument("--slug")
    parser.add_argument("--geography", default="Global")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--out")
    parser.add_argument("--cache-root", default=".cache/company-loops")
    parser.add_argument("--enable-auxiliary", action="store_true")
    parser.add_argument("--enable-cash-conversion-context", action="store_true")
    return parser


def main() -> int:
    try:
        collect(build_parser().parse_args())
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
