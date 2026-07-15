---
name: audit-cleantech-finance
description: Build bilingual, source-traceable five-cell evidence cards for a clean energy company's profitability and cash-flow/funding-gap dimensions from annual reports, filings, PDFs, and cited public comparators. Use when Codex needs to classify a cleantech business model, extract audited facts, apply the locked CleanTech Finance methodology framework, expose evidence gaps in English and Chinese, or prepare human-reviewed financial research without issuing an investment, credit, or risk rating.
---

# Audit CleanTech Finance

Build one fixed five-cell evidence card per implemented dimension with the repository's deterministic CLI. Keep agent-prepared structured outputs, source facts, formulas, the locked framework, inference, and required human judgment separate.

Only `profitability-unit-economics` and `cash-runway` are implemented and publicly validated end to end. Treat the other four financial lenses and all 17 adoption-risk dimensions as retrieval scaffolds, not completed judgment products.

## Workflow

1. Define the subject before extracting evidence:
   - Name the legal entity and ticker when applicable.
   - Name the exact technology or product scope.
   - Set the `as_of` date, geography, value-chain boundary, and decision horizon.
   - Prefer consolidated company results unless the user explicitly requests parent-company results.

2. Gather public primary sources:
   - Prefer audited annual reports, regulatory filings, regulator publications, standards, and government documents.
   - Record publisher, publication date, stable URL, and local path for every source.
   - Do not place private CRM, contact, agreement, or internal pipeline data in the repository or output.
   - Assign the subject filing `role: subject`. Assign comparator filings `role: benchmark`; benchmark documents must not contaminate subject-company fact extraction or retrieval.

3. Create a manifest. Read [references/manifest-contract.md](references/manifest-contract.md) when creating or repairing one.
   - Use `financial_extraction` for supported English consolidated statements.
   - Use `financials` for other formats, and cite every numeric fact with a source id and page or line locator.
   - Never provide both modes in one manifest.

4. Prepare `judgment_context`. Read [references/judgment-context.md](references/judgment-context.md) and record four concise, cited stage outputs for each implemented dimension:
   - `subindustry_identification`: classify manufacturing, power electronics/equipment, installation/service, or asset ownership/operation and state the value-chain position.
   - `benchmark_retrieval`: use the subject's own prior period first, then genuinely comparable peers; label adjacent-company context when comparability is incomplete.
   - `relative_positioning_and_trend`: apply the locked framework and select a conservative red/amber/green evidence signal with cited basis.
   - `gap_exposure`: include at least one `evidence_gap`, `human_judgment`, and `verification` item, with accurate English `text` and Chinese `text_zh`.

   Store only these structured outputs. Do not request, reveal, or save hidden chain-of-thought. Do not put a `framework` key in `judgment_context`; the CLI rejects attempts to replace the locked methodology text.

5. Run only the two implemented dimensions:

   ```bash
   cleantech-finance audit manifest.json \
     --only profitability-unit-economics cash-runway \
     --out outputs/company
   ```

   Do not present a wider all-dimension run as validated product output.

6. Inspect `audit.json`, `dimension_cards.json`, `cards/*.html`, and `report.html`:
   - Verify each automatically extracted financial fact against its cited page.
   - Recompute a sample of formulas from cited inputs.
   - Open the top candidate passages; do not treat relevance as truth probability.
   - Confirm parent-company statements were not mixed into consolidated evidence.
   - Confirm each card has exactly five cells, the neutral methodology framework is locked, and the signal remains attached to its cited basis and bilingual gaps.
   - Confirm the framework, cell headings, signal meaning, gap items, and disclaimer are accurate in both English and Chinese.

7. Read [references/review-protocol.md](references/review-protocol.md) before interpreting evidence statuses or drafting conclusions.

8. Write conclusions with explicit labels:
   - `Fact` for a statement directly supported by a cited source.
   - `Calculation` for a deterministic formula with cited inputs.
   - `Inference` for a reasoned interpretation.
   - `Needs human verification` for evidence gaps, conflicting boundaries, forecasts, or material judgment.

9. Run validation before delivery:

   ```bash
   cleantech-finance validate outputs/company/audit.json
   ```

   Stop and repair the run if citation integrity fails, a source locator is missing, or software populated a human rating.

10. For a release, extractor, framework-application, or card-rendering change, run `python scripts/run_release_gate.py`. It must pass Sungrow first, then Enphase, including both extraction and card-contract evaluations. Fix failures with format-level or contract-level rules, never company-name extraction branches, and rerun both cases before claiming generalization.

## Guardrails

- Do not issue buy, sell, credit, or risk ratings on the user's behalf.
- Do not use a universal gross-margin or cash threshold across unlike clean-energy business models.
- Do not calculate a numeric score or weighted aggregate from the evidence signals.
- Do not let manifest or agent output alter the locked CleanTech Finance methodology framework.
- Do not calculate an aggregate DOE ARL score.
- Do not equate evidence coverage with low risk.
- Do not infer funding sufficiency from positive historical cash flow alone.
- Do not hide extraction failure. Preserve the missing field in the review queue.
- Keep the deterministic core offline unless the user explicitly authorizes source retrieval.
- State honestly that 29/29 and 28/28 validate extraction and provenance, while 27/27 validates the card contract; none validates an investment conclusion.
