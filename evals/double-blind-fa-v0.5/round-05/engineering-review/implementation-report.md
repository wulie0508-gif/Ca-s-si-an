# Round 05 engineering implementation report

Date: 2026-08-04

Scope: targeted repair of R05-F01, R05-F02, and R05-F03 only

Result: focused engineering gates passed; ready for coordinator/full-suite and independent FA postfix replay

## Outcome

The trusted valuation workflow no longer accepts an unproved non-year-end DCF timing assumption as a calculated screen-grade result. It now supports a source-bearing, human-confirmed per-period timing contract, rejects incomplete or conflicting timing at both request and calculation boundaries, and exposes the applied dates and exponents in calculation output, the FA UI, and the formula-bearing XLSX export.

The company supplement remains candidate evidence. Nothing in this repair imports it automatically, confirms it, advances a Deal, approves a valuation, or publishes an output.

## R05-F01 - DCF timing control

### Root cause

The original DCF core derived discount exponents solely from forecast position (`1/2/3` for period-end discounting). The workflow had no structured `period_end` or source-bearing `discount_exponent` input, so a 2026-06-30 valuation whose first cash flow was FY2027E could still report Calculation Integrity `passed` and Decision Readiness `screen_grade` without proving cash-flow timing.

### Implemented design

- Added optional structured `period_end` and source-bearing `discount_exponent` fields to each FCFF period. Explicit exponents use unit `years` and are included in the calculation input lineage.
- Added a request-time and immutable-version calculation-time timing gate. Explicit timing must cover every forecast period in all three scenarios, contain 3 to 5 periods, be positive, be no more than 100 years, be strictly increasing, and have identical ordered dates/exponents across Base, Downside, and Upside.
- Candidate timing can be stored as candidate input, but cannot calculate or confirm itself. Confirmed timing requires the existing human-confirmation status plus source ID, locator, and as-of date.
- Free-text period labels are never parsed to infer dates or exponents.
- Retained a narrow legacy compatibility path only for a December 31 valuation date with confirmed, structured, consecutive December 31 period ends. That path produces positional `1..N`; all other confirmed missing-timing cases fail closed.
- The explicit exponent controls each FCFF discount factor and the terminal-value discount factor. WACC/growth and WACC/exit sensitivities reuse the same scenario timing through the shared DCF calculation path.
- Calculation output now discloses the timing basis, valuation date, scenario consistency, period ends, exponents, and source input IDs. Failed calculations are stored as `inputs_incomplete`, never `calculated_screen_grade`, and cannot enter review.
- The FA bridge UI now supports 3, 4, or 5 periods, applies show/hide and required-state behavior, collects structured dates and exponents, reloads stored values, and explains that company candidate supplements are not auto-imported or auto-confirmed.
- The XLSX DCF sheet formula-links visible explicit exponents, uses the last period's discount factor for terminal value, and discloses period end, timing basis, timing input ID, source ID, locator, and as-of date. The H2 regression verifies `0.5/1.5/2.5/3.5`, formula `1/(1+$B$5)^C8`, and terminal use of the final-row factor.

## R05-F02 - package identity

Source metadata was already consistently `0.5.0`; the defect was stale editable-install metadata reporting `0.4.0`. The active `.venv-new` editable installation was refreshed from the current source, and a regression now compares `cleantech_finance.__version__` with installed distribution metadata when that metadata is present.

Verified after refresh:

- source version: `0.5.0`
- installed distribution version: `0.5.0`

## R05-F03 - confidentiality vocabulary

`internal_only` is now accepted as an input alias and persisted/audited using the existing canonical confidentiality level `internal`. No new authorization level or permission was introduced.

## Files changed in this repair

- `src/cleantech_finance/valuation.py`
- `src/cleantech_finance/valuation_workflow.py`
- `src/cleantech_finance/valuation_export.py`
- `src/cleantech_finance/deal_service.py`
- `src/cleantech_finance/web/agent_bridge.html`
- `src/cleantech_finance/web/agent_bridge.js`
- `tests/test_valuation.py`
- `tests/test_valuation_workflow.py`
- `tests/test_valuation_export.py`
- `tests/test_deal_service.py`
- `tests/test_agent_bridge_valuation.py`
- `tests/test_package_metadata.py`

## Verification

Focused Python gate:

```text
.venv-new\Scripts\python.exe -m pytest tests/test_valuation.py tests/test_valuation_workflow.py tests/test_valuation_export.py tests/test_deal_service.py tests/test_agent_bridge_valuation.py tests/test_package_metadata.py -q
```

Result: `101 passed`.

Additional checks:

- `tests/test_valuation_export.py -q`: `11 passed` after the final timing-source linkage assertion.
- Ruff over all changed Python source and tests: passed.
- `node --check src/cleantech_finance/web/agent_bridge.js`: passed.
- Existing Node valuation test: `6 passed`, `0 failed`.
- `git diff --check`: passed.
- `fix-plan.json`: parsed successfully.
- Source/installed package version parity: passed at `0.5.0`.

The full repository suite was intentionally left to the coordinator's final gate; it was not run in this focused engineering subtask. No commit or other Git mutation was performed.

## Boundaries and residual risk

- The H2 2026E stub and `0.5/1.5/2.5/3.5` timing in the company supplement remain pending candidate evidence. An FA must independently accept, enter, and human-confirm a source-bearing timing contract before relying on that path.
- This repair does not validate the commercial merits of the supplement, produce a formal valuation opinion, weight valuation methods, issue an investment/credit/risk rating, approve a valuation, or authorize external distribution.
- The narrow December 31 compatibility rule remains deliberately available for validated annual period-end cases; all non-year-end or unstructured-label cases require explicit exponents.
- Existing unrelated working-tree deletions under `outputs/release-gate-v0.2.1/` and the untracked `delivery/` directory were observed but not touched.

The Investment Banking `model-audit-tieout` and `dcf-model-builder` guidance and the frontend UI engineering guidance were available and applied; no skill fallback was required.
