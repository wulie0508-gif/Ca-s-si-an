"""End-to-end evidence audit orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from . import __version__
from .auxiliary import validate_auxiliary_sources
from .capabilities import capability_matrix
from .cash_conversion import build_cash_conversion_context
from .fact_extraction import extract_financial_facts
from .finance_framework import FINANCE_DIMENSIONS
from .financials import derive_financial_metrics
from .framework import DIMENSIONS
from .identity import resolve_entity_identity
from .ingest import ingest_sources, load_manifest
from .judgment import build_judgment_layer
from .models import Dimension, DimensionResult
from .retrieval import EvidenceRetriever
from .rules import dimension_applicability


def _result_for(retriever: EvidenceRetriever, dimension: Dimension, top_k: int) -> DimensionResult:
    candidates = retriever.candidates_for(dimension, top_k=top_k)
    source_count = len({candidate.source_id for candidate in candidates})
    high_quality = any(candidate.source_quality == "high" for candidate in candidates)
    high_directness = any(candidate.directness == "high" for candidate in candidates)
    if (source_count >= 2 and high_quality) or (
        len(candidates) >= 2 and high_quality and high_directness
    ):
        status = "review_ready"
        reason = "Enough high-quality candidate evidence was found for focused human review; no risk conclusion is automated."
    elif candidates:
        status = "partial"
        reason = "Candidate evidence exists but needs corroboration, stronger sourcing, or closer reading."
    else:
        status = "gap"
        reason = "No candidate passage cleared the transparent lexical retrieval threshold."
    return DimensionResult(
        id=dimension.id,
        category=dimension.category,
        name=dimension.name,
        objective=dimension.objective,
        status=status,
        candidates=candidates,
        review_questions=dimension.review_questions,
        review_reason=reason,
    )


def _coverage(results: Iterable[DimensionResult]) -> dict[str, Any]:
    results = list(results)
    total = len(results)
    counts = {
        status: sum(result.status == status for result in results)
        for status in ("review_ready", "partial", "gap")
    }
    covered = total - counts["gap"]
    return {
        "total_dimensions": total,
        "covered_dimensions": covered,
        "coverage_ratio": round(covered / total, 4) if total else 0,
        **counts,
    }


def run_audit(
    manifest_path: str,
    top_k: int = 3,
    only_dimensions: set[str] | None = None,
    *,
    allowed_input_root: str | None = None,
    manifest_bytes: bytes | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    manifest, sources, resolved_manifest, source_payloads = load_manifest(
        manifest_path,
        allowed_root=allowed_input_root,
        manifest_bytes=manifest_bytes,
        include_payloads=True,
    )
    chunks = ingest_sources(sources, source_payloads)
    as_of = manifest["assessment"].get("as_of")
    if not as_of:
        raise ValueError("Manifest assessment requires an 'as_of' date")
    retriever = EvidenceRetriever(chunks, sources, as_of)
    known_dimensions = {dimension.id for dimension in (*FINANCE_DIMENSIONS, *DIMENSIONS)}
    if only_dimensions:
        unknown = only_dimensions - known_dimensions
        if unknown:
            raise ValueError(f"Unknown dimension id(s): {', '.join(sorted(unknown))}")
    selected_finance = (
        tuple(d for d in FINANCE_DIMENSIONS if d.id in only_dimensions)
        if only_dimensions
        else FINANCE_DIMENSIONS
    )
    selected_adoption = (
        tuple(d for d in DIMENSIONS if d.id in only_dimensions) if only_dimensions else DIMENSIONS
    )
    selected_ids = (
        set(only_dimensions)
        if only_dimensions
        else {dimension.id for dimension in (*FINANCE_DIMENSIONS, *DIMENSIONS)}
    )
    finance_results = tuple(
        _result_for(retriever, dimension, top_k) for dimension in selected_finance
    )
    adoption_results = tuple(
        _result_for(retriever, dimension, top_k) for dimension in selected_adoption
    )
    auto_extraction: dict[str, Any] | None = None
    financials = manifest.get("financials")
    if not financials and manifest.get("financial_extraction", {}).get("enabled"):
        auto_extraction = extract_financial_facts(
            chunks,
            sources,
            manifest["financial_extraction"],
        )
        financials = auto_extraction["financials"]
    scope_id = str(
        (manifest.get("judgment_context") or {}).get("subindustry", {}).get("scope_id") or ""
    )
    inapplicable_dimensions = {
        dimension_id
        for dimension_id in ("profitability-unit-economics", "cash-runway")
        if dimension_applicability(dimension_id, scope_id)["status"] == "not_applicable"
    }
    financial_analysis = derive_financial_metrics(
        financials,
        {source.id for source in sources if source.role == "subject"},
        inapplicable_dimensions,
    )
    judgment_layer = build_judgment_layer(manifest, financials, sources, selected_ids)
    auxiliary_validation = validate_auxiliary_sources(manifest, sources, financials)
    cash_conversion_context = build_cash_conversion_context(
        manifest,
        sources,
        auxiliary_validation.get("selected_source_ids", []),
        financials,
    )
    audit = {
        "schema_version": "0.3.0",
        "tool": {"name": "cleantech-finance", "version": __version__},
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "manifest": str(resolved_manifest),
        "subject": manifest["subject"],
        "assessment": manifest["assessment"],
        "identity_resolution": resolve_entity_identity(manifest),
        "selected_dimensions": sorted(only_dimensions) if only_dimensions else "all",
        "guardrails": {
            "automated_investment_rating": False,
            "automated_arl_score": False,
            "human_review_required": True,
            "evidence_signals_are_not_ratings": True,
            "scope": "Research support only; not investment, legal, engineering, or safety advice.",
        },
        "execution": {
            "mode": "offline_deterministic_core",
            "model_calls": 0,
            "estimated_model_cost": 0,
            "network_calls": 0,
            "imported_agent_stage_outputs": judgment_layer["status"] != "not_provided",
        },
        "sources": [
            {
                "id": source.id,
                "title": source.title,
                "url": source.url,
                "publisher": source.publisher,
                "published": source.published,
                "kind": source.kind,
                "role": source.role,
                "sha256": source.sha256,
            }
            for source in sources
        ],
        "financial_analysis": financial_analysis,
        "financial_fact_extraction": auto_extraction,
        "judgment_layer": judgment_layer,
        "auxiliary_validation": auxiliary_validation,
        "cash_conversion_context": cash_conversion_context,
        "capability_matrix": capability_matrix(),
        "finance_evidence": [result.to_dict() for result in finance_results],
        "adoption_risk_evidence": [result.to_dict() for result in adoption_results],
        "metrics": {
            "source_count": len(sources),
            "chunk_count": len(chunks),
            "finance": _coverage(finance_results),
            "adoption": _coverage(adoption_results),
        },
    }
    audit["validation"] = validate_audit(audit)
    audit["execution"]["elapsed_seconds"] = round(perf_counter() - started, 4)
    return audit


def validate_audit(audit: dict[str, Any]) -> dict[str, Any]:
    source_ids = {source["id"] for source in audit.get("sources", [])}
    errors: list[str] = []
    citation_count = 0
    for section in ("finance_evidence", "adoption_risk_evidence"):
        for result in audit.get(section, []):
            if result.get("human_rating") is not None:
                errors.append(
                    f"{section}:{result.get('id')} unexpectedly contains an automated rating"
                )
            for candidate in result.get("candidates", []):
                citation_count += 1
                if candidate.get("source_id") not in source_ids:
                    errors.append(f"Unknown source citation: {candidate.get('source_id')}")
                if not candidate.get("locator"):
                    errors.append(f"Missing locator for {section}:{result.get('id')}")
                if not candidate.get("source_url"):
                    errors.append(f"Missing URL for {section}:{result.get('id')}")
    for metric in audit.get("financial_analysis", {}).get("metrics", []):
        for input_ in metric.get("inputs", []):
            citation_count += 1
            if input_.get("source_id") not in source_ids:
                errors.append(f"Unknown financial input source: {input_.get('source_id')}")
            if not input_.get("locator"):
                errors.append(f"Missing financial input locator: {metric.get('id')}")
    judgment = audit.get("judgment_layer", {})
    if not judgment.get("validation", {}).get("passed", True):
        errors.extend(judgment["validation"].get("errors", []))
    auxiliary = audit.get("auxiliary_validation", {})
    if not auxiliary.get("validation", {}).get("passed", True):
        errors.extend(auxiliary["validation"].get("errors", []))
    for check in auxiliary.get("checks", []):
        source = check.get("source") or {}
        citation_count += 1
        if source.get("source_id") not in source_ids:
            errors.append(f"Unknown auxiliary source citation: {source.get('source_id')}")
        if not source.get("locator") or not source.get("url"):
            errors.append("Auxiliary citation is missing a locator or URL")
    cash_context = audit.get("cash_conversion_context", {})
    if not cash_context.get("validation", {}).get("passed", True):
        errors.extend(cash_context["validation"].get("errors", []))
    for item in cash_context.get("items", []):
        source = item.get("source") or {}
        citation_count += 1
        if source.get("source_id") not in source_ids:
            errors.append(f"Unknown cash-context source citation: {source.get('source_id')}")
        if not source.get("locator") or not source.get("url"):
            errors.append("Cash-context citation is missing a locator or URL")

    def card_citations(value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            if {"source_id", "locator", "url"}.issubset(value):
                yield value
            for child in value.values():
                yield from card_citations(child)
        elif isinstance(value, list):
            for child in value:
                yield from card_citations(child)

    for citation in card_citations(judgment.get("cards", [])):
        citation_count += 1
        if citation.get("source_id") not in source_ids:
            errors.append(f"Unknown judgment-card source: {citation.get('source_id')}")
        if not citation.get("locator") or not citation.get("url"):
            errors.append("Judgment-card citation is missing a locator or URL")
    return {
        "passed": not errors,
        "citation_count": citation_count,
        "errors": errors,
    }
