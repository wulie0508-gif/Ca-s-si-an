# New-company generalization loop

Use this protocol when improving the product through new public-company cases. Each loop is a fresh product experiment, not a repeated regression run.

## Preconditions

- Establish a green baseline first: Ruff, full tests, manifest schema validation, and the ordered Sungrow → Enphase release gate.
- Read `evals/company-loops-v0.3.json` and the latest residual insight in `docs/local-iteration-loop-v0.3.0.md`.
- Select a public company whose stable entity id is absent from the registry and whose facts exercise the residual risk. Never select a company because its expected signal is convenient.
- Use audited filings as the primary source. Keep collection network I/O outside the offline deterministic audit.

## One countable loop

1. **Inspect** — Run the unmodified current product on the new company. Preserve `manifest.initial.json` and, when useful, an initial failing output directory.
2. **Diagnose** — Identify the smallest general contract, semantic, rule, or rendering defect. Record concrete evidence; do not create a company-name exception.
3. **Propose** — State one primary generalizable optimization and its truth boundary. A tightly coupled safety check may accompany it, but avoid unrelated refactors.
4. **Implement** — Change format-level or contract-level code. Keep facts deterministic, signals rule-owned, and auxiliary data non-authoritative.
5. **Focus-test** — Add a regression that fails before the change and passes after it. Include an adversarial or fail-closed case when identity, period, scope, selection, applicability, or polarity is involved.
6. **Retest the new company** — Verify expected independent signals or explicit not-applicable outcomes, citations, bilingual fields, auxiliary status, rule/input digests, and zero model calls.
7. **Run broad gates** — Run Ruff, all tests, all manifest schemas, Sungrow first, Enphase second, and every registered company case. Stop on the first failed ordered release gate.
8. **Render and inspect** — Generate the final output directory. Open the report locally and check Chinese text, layout, source links, dimension independence, and auxiliary selection display.
9. **Register** — Add the unique stable entity id, manifest, exact scope, expected signals, output directory, English/Chinese optimization summary, and default auxiliary status to the registry.
10. **Record** — Add initial failure, optimization, result, automated evidence, artifact path, and one residual insight to the loop log.

A loop counts only after all ten steps pass. Foundation work, dependency repair, and repeat runs of a previously registered company do not count.

## Required adversarial gates

- Entity: a conflicting CIK or historical-name source binding fails closed.
- Period: a transition period, duplicate annual identity, or non-comparable duration fails closed.
- Statement semantics: mixed total/continuing operations or attribution fails closed.
- XBRL selection: consolidated revenue/cost/gross-profit identity must reconcile; excluded candidates remain visible.
- Applicability: an economically invalid dimension becomes bilingual `not_applicable` without blocking independent dimensions.
- Auxiliary selection: toggling sources cannot change signals, rule digest, or input digest; semantic non-comparability precedes numerical comparison.
- Cash polarity: unknown concepts or incompatible period/currency/unit/scope fail closed; raw signs remain visible beside derived cash effects.
- Guardrails: no aggregate score, ranking, investment rating, universal cross-subindustry performance threshold, or company-name branch.

## Final ten-loop acceptance

- Registry contains at least ten iterations and ten unique stable entity ids.
- Every default case matches its expected signal or null applicability and passes citation validation with zero model calls.
- All manifests pass Draft 2020-12 validation.
- Full tests, Ruff, and ordered Sungrow → Enphase gate pass on the current machine.
- The generated local index contains exactly the registered final cases, not initial/before artifacts.
- Auxiliary controls show current applied selection and label checkbox changes as a draft until the whitelist runner succeeds.
- English and Chinese report content is non-empty and visually legible at desktop, tablet, and narrow mobile widths.
- A fresh Agent can follow this Skill on an unseen company without being given the expected signal or intended fix.
