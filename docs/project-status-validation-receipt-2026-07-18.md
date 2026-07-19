# CleanTech Finance v0.4 status validation receipt

Status date: 2026-07-18 (Asia/Shanghai)

This is a supporting evidence receipt for the portable project status report. It is not a second report surface and does not upgrade fixtures, historical cases, or code tests into real-company evidence.

## Repository state

- Workspace: the original Git working tree supplied by the user.
- Branch: `main`.
- HEAD: `350d497113122b8e3a5e0ef30d317a280865e6b8`.
- The worktree contains pre-existing modified and untracked v0.4 files. They were preserved; no reset, checkout, or discard operation was used.

Read-only commands:

```text
git status --short
git branch --show-current
git rev-parse HEAD
```

## Current-machine validation snapshot

- Full pytest collection: `145 passed`.
- Ruff: `All checks passed`.
- JSON Schema Draft 2020-12 meta-validation: `7/7 valid`.
- Ordered Sungrow release gate: extraction `29/29`, cards `27/27`, citations `112`, model calls `0`.
- Ordered Enphase release gate: extraction `28/28`, cards `27/27`, citations `113`, model calls `0`.
- Ten-company financial registry: `10/10 pass`; all model calls `0`.
- Local index: regenerated.
- Browser QA: desktop and 375px narrow layout showed no page-level horizontal overflow; regression-evidence and attestation-assurance fields were visible; console errors/warnings were zero.
- Formal real-company delivery inventory after validation: `qa_delivery` JSON count `0`; candidate five-company QA registry count `0`.

The final pytest and Ruff runs made after creating the status-report artifacts are recorded in the report handoff. Generated report files do not alter the product runtime, rule, Schema, or evaluator contracts.

## Material evidence anchors

- Product maturity: `docs/CLAUDE_HANDOFF_v0.4.md`, `docs/product-overview-brief.md`, `README.md`, `README.zh-CN.md`.
- Local workbench and onboarding: `docs/local-company-workbench.md`, `src/cleantech_finance/onboarding.py`, `src/cleantech_finance/onboarding_reporting.py`, `schemas/company-case.schema.json`.
- QA contract: `docs/qa-diagnostic-loop.md`, `schemas/qa-case.schema.json`, `schemas/qa-loop.schema.json`, `schemas/qa-profile-ground-truth.schema.json`.
- QA implementation: `src/cleantech_finance/qa_diagnostics.py`, `src/cleantech_finance/qa_loop.py`, `src/cleantech_finance/qa_reporting.py`, `scripts/run_qa_loop.py`, `src/cleantech_finance/cli.py`.
- QA tests: `tests/test_qa_diagnostics.py`.
- Existing financial core and regressions: `src/cleantech_finance/audit.py`, `tests/test_pipeline.py`, `evals/sungrow-2025.json`, `evals/enphase-2025.json`, `evals/sungrow-cards-v0.2.json`, `evals/enphase-cards-v0.2.json`.

## Interpretation limits

- Green engineering gates mean that the current code contracts and existing reference cases showed no observed regression.
- They do not prove the facts of a new company and do not count toward the human-selected five-company `qa_delivery` batch.
- Only profitability/unit economics and cash runway/funding gap are end-to-end validated financial dimensions.
- The other four finance dimensions are input blueprints. ESG, clean-tech impact, and export readiness are evidence frameworks. DOE ARL 17 dimensions are retrieval scaffolds and do not yield ARL 1–9 scores.
- Red/amber/green finance evidence signals are independent and are not weighted or aggregated into investment, credit, or overall risk ratings.
- Agent output remains candidate evidence. Interview statements prove only what was said. Public release requires separate authorization and human review.
