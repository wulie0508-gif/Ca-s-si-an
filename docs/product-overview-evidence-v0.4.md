# Product overview evidence and report notes — v0.4 working snapshot

Generated for the local product overview on 2026-07-17.

## Reporting job

- Audience: product stakeholders, including company leadership, internal diligence/product teams, prospective enterprise users, and implementation partners.
- Decision supported: understand what the product is, how information moves through it, which capabilities are real today, and what should be designed next.
- Delivery mode: one self-contained HTML report generated from the canonical Data Analytics report artifact.
- Scope: the current local working tree and the user's confirmed next design priority.

## Evidence inventory

- `README.md`: product positioning, two validated financial dimensions, ten-company loop, release-gate results, local workbench inventory, trust boundaries, and responsible-use limits.
- `docs/local-company-workbench.md`: local-first workflow, E1–E4 evidence boundary, five gates, stage-specific material request, publication control, and optional local-Agent boundary.
- `src/cleantech_finance/onboarding.py`: implemented case schema, stages, material catalogue, consent validation, claim/evidence checks, gates, interview guide, Agent task contracts, benchmark safety, and assessment routing.
- `src/cleantech_finance/onboarding_reporting.py`: implemented bilingual artifacts and offline workbench output.
- `src/cleantech_finance/cli.py`: implemented `case init`, `case validate`, `case report`, and `case agent-tasks` commands.
- `tests/test_onboarding.py`: local-only UI, Agent authority, publication permission, small-cohort benchmark, module-boundary, and artifact tests.
- `docs/product-maturity-inventory.sql`: reproducible four-row transformation of the reviewed README capability counts used by the maturity chart.
- Full local verification on 2026-07-17: 75 tests passed; Ruff passed.

## Capability-state mapping

| Capability | Report state | Evidence basis |
|---|---|---|
| Local company intake and workbench | Available in local v0.4 working tree | onboarding, reporting, CLI, and tests |
| Consent, identity, claims, evidence, and five gates | Available in local v0.4 working tree | onboarding and tests |
| Profitability/unit economics | Validated end to end | README, audit pipeline, release gate |
| Cash flow/funding gap | Validated end to end | README, audit pipeline, release gate |
| Four additional financial dimensions | Authored input-contract blueprints only | README |
| 17 DOE ARL dimensions | Retrieval scaffolds only | README |
| Full ESG, export readiness, aggregate score | Not validated or shipped as automated conclusions | README and assessment plan |
| Counterparty missing-information submission center | Product design confirmed in this task; engineering intentionally deferred | user direction on 2026-07-17 |

## New design decision: counterparty supplementation loop

The next product design must convert every material information gap into a structured submission request that the company can complete. The designed lifecycle is:

`gap_detected → request_drafted → request_sent → partially_submitted → submitted → needs_revision → accepted / rejected / waived`

Each request should preserve: related claim or assessment item, reason the information is needed, required fields, acceptable evidence types and levels, template/example, responsible party, due date, submission version, file hashes, reviewer, validation rules, rejection reason, and a controlled `not_applicable` justification. Blank values must never be treated as zero, false, or not applicable.

This is a product-design commitment, not a statement that the UI/API and persistence layer already exist.

## Report structure mapping

- Title: product name and purpose.
- Executive Summary: positioning, current truth, information flow, and the next design priority.
- Key findings/evidence: product boundary, end-to-end flow, information-state lifecycle, system architecture, authority model, gates, capability status, use cases, deliverables, and verification.
- Recommended next steps: design specification for the supplementation center before engineering.
- Further questions: choices intentionally left for the next design review.
- Caveats and assumptions: non-rating boundary, framework-versus-validated distinction, and local working-tree status.

## Chart map

- Segment: current capability boundary.
- Analytical question: how much of the declared professional-dimension inventory is validated end to end versus blueprint or retrieval-only?
- Takeaway: only two financial dimensions are validated end to end; four other financial dimensions are authored blueprints, while the 17 ARL dimensions remain retrieval scaffolds with zero validated automated ARL dimensions.
- Family and variant: comparison, horizontal single-series bar.
- Rows and fields: four semantic categories; `label`, `count`, `domain`, `status`, and `definition`.
- Scale: non-negative absolute counts beginning at zero; counts are inventory items, not company scores.
- Palette: single-root preferred, no redundant color or legend encoding; category labels carry identity.
- Delivery and QA surface: native chart in the canonical report artifact, rendered and verified in the self-contained HTML report.

No other quantitative chart was added because the remaining report describes system architecture and state transitions rather than measured trends or distributions. Ordered tables and process flows communicate those relationships without implying false quantitative precision.
