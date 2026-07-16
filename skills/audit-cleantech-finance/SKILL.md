---
name: audit-cleantech-finance
description: Run deterministic, bilingual CleanTech Finance evidence audits and failure-driven new-company generalization loops for profitability/unit economics and cash runway. Use when Codex must onboard or audit a clean-energy company, build source-traceable English/Chinese five-cell cards and local HTML reports, choose optional non-authoritative validation sources, test a new company, or improve the versioned rule and evidence contracts without issuing an investment rating.
---

# Audit CleanTech Finance

Use the repository's offline deterministic core to build one five-cell card per implemented dimension. Keep source facts, deterministic calculations, locked methodology, rule output, and human-review gaps separate.

Only `profitability-unit-economics` and `cash-runway` are validated end to end. Treat the other four financial dimensions as `authored` only and all 17 adoption-risk dimensions as retrieval scaffolds.

## Preserve the authority boundary

- Let deterministic extraction code produce financial facts.
- Let cited structured research provide the subindustry classification, own-history/comparator observations, and gaps.
- Let the versioned rule library alone choose `red`, `amber`, or `green` and produce the application path and summary.
- Reject manifest or Agent attempts to supply a signal, framework, rule, path, or application summary.
- Store structured stage outputs only. Never request or save hidden chain-of-thought.

## Choose a mode

### Audit one company

1. Define the legal entity, stable identifier, technology, value-chain scope, geography, date, and horizon.
2. Gather public primary sources. Prefer audited filings and regulator data. Assign `subject`, `identity`, `auxiliary`, and `benchmark` roles deliberately.
3. Read [references/manifest-contract.md](references/manifest-contract.md) and create or repair the manifest. Never mix automatic and structured financial modes.
4. Read [references/judgment-context.md](references/judgment-context.md) and prepare cited bilingual classification, benchmark, and gap fields. Do not provide a signal.
5. Run only the two validated dimensions:

   ```powershell
   .\.venv-new\Scripts\python.exe -m cleantech_finance audit manifest.json `
     --only profitability-unit-economics cash-runway `
     --out outputs\company
   ```

6. Inspect `audit.json`, `dimension_cards.json`, `cards/*.html`, and `report.html`. Verify entity, periods, units, statement scopes, XBRL selection provenance, formulas, citations, rule id/version/digests, bilingual text, and applicability outcomes.
7. Read [references/review-protocol.md](references/review-protocol.md), then validate:

   ```powershell
   .\.venv-new\Scripts\python.exe -m cleantech_finance validate outputs\company\audit.json
   ```

8. If the user chooses auxiliary sources, use the whitelist-checked runner. Auxiliary values must never alter signals or rule/input digests:

   ```powershell
   .\.venv-new\Scripts\python.exe scripts\run_company_loop_case.py `
     --case albemarle `
     --aux-source albemarle-2025-results
   ```

### Generalize with a new company

Read [references/company-loop-protocol.md](references/company-loop-protocol.md) and execute its complete failure-driven loop. A foundation refactor is not a company loop. Do not count a loop until the new case, focused regression, full suite, ordered release gate, final artifacts, and residual insight all pass.

## Release gates

For any extractor, rule, framework-application, schema, or rendering change:

1. Run Ruff and the full test suite.
2. Validate every manifest against Draft 2020-12 schema.
3. Run `python scripts/run_release_gate.py`; preserve Sungrow first and Enphase second.
4. Run the registered company-loop suite and confirm zero model calls.
5. Regenerate the bilingual local index with `python scripts/build_company_loop_index.py`.
6. Open the index and representative reports locally. Check Chinese rendering, desktop/mobile layout, navigation, filters, source-selection draft commands, and the Clearway not-applicable state.

## Guardrails

- Do not issue buy, sell, credit, aggregate risk, or investment ratings.
- Do not combine dimension signals into a score, rank, or weighted result.
- Do not use one absolute performance threshold across unlike subindustries. A direct arithmetic identity such as OCF/capex coverage at `1.0x` is allowed only when its meaning is explicit and scoped.
- Require an exact `subindustry_scope`; forbid `all`, `any`, `global`, or company-name branches.
- Treat `authored` and `validated` as different product states.
- Keep benchmark and auxiliary documents out of subject fact extraction.
- Fail closed on missing period identity, mixed accounting scope, conflicting entity identity, unknown XBRL semantics, or an unvalidated rule scope.
- Keep auxiliary validation optional and user-selectable. Display available, selected, and ignored sources; report non-comparable facts before numerical mismatches.
- Keep cash-conversion context non-authoritative and label selected drivers as an incomplete OCF reconciliation.
- State that 29/29 and 28/28 validate extraction/provenance and 27/27 validates the card contract; none validates an investment conclusion.
