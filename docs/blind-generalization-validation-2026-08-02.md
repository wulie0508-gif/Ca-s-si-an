# CleanTech Finance v0.4 — blind generalization and corrective validation report

Date: 2026-08-02
Audience: product owner, Codex, Claude, and future maintainers
Workspace: `D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance`
Mode: local-first; public-company evidence; synthetic adversarial data; zero model calls inside the deterministic audit core

## Executive conclusion

This cycle produced real product improvements rather than another demonstration run.

- The acquisition diagnostic workflow was exercised through 4,012 generated public-API calls. The first two rounds found material defects in artifact identity, status handling, profile-hint authority, and generic-document coverage. The third round passed 2,852 calls with byte-identical output across two Python hash seeds.
- The Agent/RAG bridge went through four independent hostile HTTP reviews. The final review passed fact-authority, rating-removal, agent scope, route isolation, list isolation, and recursive cross-company provenance checks.
- QuantumScape was selected without choosing an expected signal. Its official FY2025 and FY2024 filings exposed a new real boundary: the audited statements contain no revenue, cost-of-revenue, or gross-profit line, but the cash dimension still has usable historical inputs.
- The product now distinguishes permanent business-model `not_applicable` from stage-dependent `not_yet_applicable`. Missing revenue remains missing and is never converted to zero.
- A second synthetic black-box harness then ran 4,800 large-run audit calls over 360 new seeds, plus 108 focused-test calls. All oracles passed without importing rule definitions or authoring an expected red/amber/green result.
- The current full suite is 230/230 passing; Ruff lint passes; all 17 example manifests validate; the ordered Sungrow then Enphase release gate passes; the ten final registered company loops pass with zero model calls.

One formal gate remains deliberately open: the QuantumScape HTML could not be opened through the in-app browser because direct `file://` navigation was blocked by browser policy. Automated HTML structure checks passed, but a real visual inspection has not occurred. QuantumScape is therefore a passing candidate and is intentionally not counted or placed in the final registry yet.

## Capability boundary preserved

Nothing in this cycle changes the product's truth boundary:

- Only profitability/unit economics and cash flow/funding gap are end-to-end deterministic financial dimensions.
- The other four financial dimensions remain input blueprints.
- DOE ARL remains a 17-dimension evidence-retrieval scaffold; it does not output ARL 1–9.
- ESG, clean-technology impact, and internationalization remain evidence frameworks, not automatic certification.
- Red/amber/green are independent evidence signals. They are not weighted or aggregated.
- No investment, credit, or composite risk rating is produced.
- Agent/RAG output remains candidate evidence and cannot override deterministic rules or become a fact automatically.
- A statement from management proves what was said, not that the underlying assertion is true.
- Public release still requires separate authorization and human review.

## Test design

### Independent roles

The work was split so the same reasoning path did not both create and grade every case:

1. A case curator selected public-company candidates and official primary sources without supplying expected signals.
2. A synthetic acquisition runner generated randomized cases and used metamorphic invariants instead of expected business outcomes.
3. An HTTP blind judge treated the RAG sidecar and agent routes as a black box and did not read production implementation code.
4. A filing fact-pack reviewer independently extracted QuantumScape facts and preserved missing-versus-zero, cash scope, source hashes, and the FY2024 reclassification difference.
5. A separate pre-commercial architecture review identified where the existing pipeline incorrectly coupled profitability inputs to cash execution.
6. A second generated-data runner tested the resulting applicability contract through the public `run_audit` API without importing rule definitions.

### Oracle policy

The generated-data harnesses do not decide whether a company should be red, amber, or green. They check invariants that must hold regardless of the final rule branch:

- repeat determinism;
- rename and stable-identity invariance;
- period-order invariance;
- exact-scope matching;
- duplicate identity idempotency and conflicting duplicate rejection;
- evidence-role and case-scope isolation;
- missing-versus-zero preservation;
- one explicit outcome per requested dimension;
- correspondence between an evaluated outcome and exactly one card;
- no card or signal for a non-evaluated outcome;
- zero model calls and zero audit-time network calls.

## Acquisition diagnostic rounds

### Round 1 — 310 calls, defect discovery

64 generated cases were repeated across two `PYTHONHASHSEED` values. The run exposed three material behaviors:

1. Two records with the same artifact identity but split roles could increase readiness from 0.400 to 0.775.
2. Recognition accepted every status other than `awaiting_human`, allowing unapproved states to influence the result.
3. The public contract did not clearly normalize or reject not-applicable aliases.

An independent review found two additional authority problems:

4. A generic supporting text file could satisfy six concrete document requirements and move completeness from 0% to 20%.
5. External `profile_hints` could increase material coverage from 21.25% to 40%, even though they were not artifact-derived evidence.

### Corrective implementation

- Artifact identity is now based on explicit id/hash/file-name tokens.
- Exact duplicates are idempotent; conflicting duplicates fail closed with a deterministic error.
- Only artifact status `ready` and recognition status `candidate_ready` are accepted.
- External profile hints may route workflow prompts but cannot satisfy material requirements.
- `generic_supporting` remains a recognized role but cannot satisfy any concrete requirement by itself.
- The output records duplicate, missing-identity, and ignored-status counts.

### Round 2 — 850 calls, corrective verification

106 new seeds were repeated four times across two hash seeds. All 106 passed:

- external hints did not change coverage;
- generic files did not cover concrete requirements;
- exact duplicates remained idempotent;
- ten conflicting-identity variants failed closed;
- invalid statuses contributed nothing;
- repeated results were semantically deterministic.

### Round 3 — 2,852 calls, fresh-seed confirmation

120 further seeds were evaluated under two hash seeds, 1,426 calls each. Both result files were byte-identical:

`bc69cd44300e3f616d135859ae0b0a0c1cb4a59376f561ce2d878782c89b8723`

All 120 seeds passed with zero failed invariants.

Acquisition large-run total: **4,012 public diagnostic calls**.

## Agent/RAG hostile HTTP review

### Defects found

The bridge originally allowed untrusted sidecar fields such as `review_status`, `is_fact`, and rating-like values to pass through nested payloads. A later round found that evidence with no top-level entity id could be rebound to the requested company. A still deeper round found that a top-level correct entity id could conceal a conflicting entity id inside `source` or `provenance`, leaving the hostile claim text visible after field sanitization.

### Corrective implementation

- The bridge constructs a new whitelist response instead of spreading the sidecar payload.
- Returned evidence is forced to `review_status: pending`, `is_fact: false`, `authority: reference_suggestion_only`, and `human_review_required: true`.
- Rating and unknown authority fields are removed.
- Evidence requires an explicit top-level entity id exactly equal to the requested case.
- Any structured `case_id`, `entity_id`, or `subject_entity_id` at any nested dict/list level that conflicts with the requested case causes the entire evidence item to be discarded.

### Independent Round 4 result

All tested oracles passed:

- O16 fact-authority sanitization;
- O17 investment/credit/composite/risk-rating removal;
- O18 agent case-scope isolation;
- O19 scoped list isolation;
- O21 recursive cross-company evidence isolation.

Four nested attack shapes were tested. Each retained exactly one safe control and zero hostile evidence. Case A detail/material routes returned 200; case B detail/material/RAG returned 403; the rejected B RAG request did not call the stub; the scoped list contained only A.

Boundary: the current web surface is a trusted loopback operator interface, not an authenticated multi-user security boundary. Cloud or shared deployment still requires real authentication and authorization.

## Real-company candidate — QuantumScape

### Why this company was selected

QuantumScape was absent from the registry and exercises a real residual risk: a pre-commercial clean-technology developer can have audited loss and cash-flow facts while lacking a valid historical revenue/margin basis. The company was selected before any product signal was generated.

Other independent candidates retained for later loops are ReNew Energy Global, which would test IFRS/20-F and mixed asset-owner/manufacturing semantics, and Li-Cycle, which would test transition-period and restatement boundaries.

### Source evidence

- FY2025 official investor-relations PDF: `https://ir.quantumscape.com/static-files/215ea548-1576-4ea0-8b50-bb6234e50a19`
- FY2024 official investor-relations PDF: `https://ir.quantumscape.com/static-files/f0dee583-54fe-41b9-8764-a3bffc8f07e6`
- FY2025 SEC filing: `https://www.sec.gov/Archives/edgar/data/1811414/000119312526071556/qs-20251231.htm`

Verified PDF SHA-256:

- FY2025: `3868e25fe35806379c0878d25159ac9f8007226a7fb9ff7c4e7243de3c76c5fe`
- FY2024: `ed600623a89eefea897a43bac53842366309b4f11d984d1265e5d1a1292e0b3b`

### Verified facts

| Fact | FY2025 | FY2024 | Treatment |
|---|---:|---:|---|
| Revenue | missing | missing | No statement line; never converted to 0 |
| Cost of revenue | missing | missing | No statement line; never converted to 0 |
| Gross profit | missing | missing | No statement line; never converted to 0 |
| Net loss | USD 435.050m | USD 477.942m | Consolidated, negative reported value |
| Operating cash flow | USD -242.473m | USD -274.555m | Net cash used in operations |
| Capex cash-outflow magnitude | USD 36.277m | USD 62.247m | Latest comparative presentation |
| Cash and cash equivalents | USD 230.524m | USD 140.866m | Cash only |
| Current marketable securities | USD 740.283m | USD 769.901m | Kept separate from cash |

The 2024 filing originally showed FY2024 purchases of property and equipment of USD 62.131m. The 2025 comparative column shows USD 62.247m and a USD 0.116m investing-activities reclassification while preserving the investing subtotal. The candidate selects the later comparative presentation and records the difference rather than silently choosing one value.

### Initial product failure

The preserved `manifest.initial.json` failed with:

- `Missing judgment context for 'profitability-unit-economics'`
- `Expected exactly one validated rule for 'cash-runway' in scope 'pre-commercial-solid-state-lithium-metal-battery-development', found 0`

This was the correct fail-closed behavior, but the product had no truthful state between “permanently not applicable” and “missing inputs.”

### General optimization

The new `applicability_context` v1.0.0 accepts only cited inputs:

- commercialization stage;
- stage as-of date;
- recognized operating revenue state;
- covered financial periods;
- same-subject source locators.

It does not accept a status, signal, outcome, reason, or rating. For the exact pre-commercial scope, the deterministic policy can emit:

- `status: not_yet_applicable`;
- `signal: null`;
- a bilingual reason;
- `reason_code`;
- policy id/version/digest;
- input digest;
- cited basis.

`not_applicable` remains reserved for structural business-model incompatibility, such as the existing contracted asset-owner case. Ordinary missing revenue with no valid applicability evidence still fails closed.

### Candidate result

- Audit validation: passed.
- Citation count: 33.
- Profitability/unit economics: `not_yet_applicable`, no card, no signal.
- Cash flow/funding gap: `evaluated`, `amber`, rule `cash-loss-making-burn-improving`.
- Generated financial metrics: free cash flow, OCF/capex, and simple cash-only runway.
- Revenue growth, gross margin, operating margin, net margin, and capex/revenue are absent.
- Model calls: 0.
- Network calls inside the deterministic audit: 0.

The amber value is an independent historical cash evidence signal. It is not a statement that funding is sufficient, not an investment or credit opinion, and not derived from the size of cash or marketable securities.

## Pre-commercial generated-data rounds

The dedicated harness imports only `cleantech_finance.audit.run_audit`. It labels every input synthetic and does not inspect the internal rule registry.

| Round | Seeds | Audit API calls | Failures | Determinism evidence |
|---|---:|---:|---:|---|
| 1, hash seed 43 | 120 | 1,200 | 0 | Byte-identical to hash seed 977 |
| 1, hash seed 977 | 120 | 1,200 | 0 | SHA-256 `e5d536ee4e173485abbbf4f58e03d00f555307e78b98a412434787b9547105e6` |
| 2, hash seed 211 | 120 | 1,200 | 0 | Fresh seed range |
| 3, hash seed 557 | 120 | 1,200 | 0 | Fresh seed range |

Large-run total: **4,800 calls over 360 independent seeds**. Focused test reruns contributed another 108 calls.

Covered mutations include complete identity rename, period-order reversal, missing stage evidence, missing no-revenue evidence, wrong-role stage citation, wrong-role revenue citation, and a near-match scope. Every negative case failed closed; every positive case kept one explicit outcome per dimension; the cash card remained independent.

## Final automated gates

| Gate | Result |
|---|---|
| Full pytest | 230 passed |
| Ruff lint | Passed |
| `git diff --check` | Passed |
| Example Manifest Schema | 17/17 valid |
| Sungrow extraction/cards | 29/29; 27/27; 112 citations; 0 model calls |
| Enphase extraction/cards | 28/28; 27/27; 113 citations; 0 model calls |
| Ordered release gate | Passed in Sungrow → Enphase order |
| Final registered company loops | 10/10 passed under explicit outcome contract; 0 model calls |
| QuantumScape candidate | Automated audit passed; 33 citations; 0 model calls |
| QuantumScape HTML structure | Bilingual labels, source URL, responsive CSS, status distinction, and missing-versus-zero wording passed |
| QuantumScape visual inspection | Pending because direct local `file://` navigation was blocked |

`ruff format --check` is not currently a repository gate and reports 37 existing files that would be reformatted. No bulk formatting was applied, because it would create a large unrelated diff over the user's dirty worktree. Ruff lint itself passes.

## Files produced or changed by this validation cycle

Core contracts and safety:

- `src/cleantech_finance/rules.py`
- `src/cleantech_finance/audit.py`
- `src/cleantech_finance/financials.py`
- `src/cleantech_finance/judgment.py`
- `src/cleantech_finance/reporting.py`
- `src/cleantech_finance/agent_bridge.py`
- `schemas/manifest.schema.json`

Reproducible blind harnesses:

- `scripts/run_acquisition_blind_eval.py`
- `tests/test_acquisition_blind_eval.py`
- `scripts/run_precommercial_blind_eval.py`
- `tests/test_precommercial_blind_eval.py`
- `tests/test_precommercial_applicability.py`

Outcome contract:

- `evals/company-loops-v0.3.json`
- `scripts/run_company_loop_registry.py`
- `scripts/run_company_loop_case.py`
- `scripts/build_company_loop_index.py`
- `tests/test_company_loops.py`

Real-company candidate:

- `examples/company-loops/quantumscape/manifest.initial.json`
- `examples/company-loops/quantumscape/initial-failure.json`
- `examples/company-loops/quantumscape/manifest.json`
- `examples/company-loops/quantumscape/source.txt`
- `outputs/company-loops/11-quantumscape/` (generated and gitignored)

## Defect, debt, product choice, and roadmap classification

### Fixed defects

- Duplicate artifact identities could inflate readiness.
- Loose statuses could contribute to workflow coverage.
- Generic support and external profile hints could satisfy concrete evidence requirements.
- Sidecar fact/rating authority could leak through nested fields.
- Cross-company structured provenance could leave a hostile claim visible.
- The product could not represent a cited stage-dependent profitability boundary while continuing the cash dimension.
- Nullable expected signals could hide a missing card as N/A.
- The CLI starter fabricated a revenue value of zero; it now uses extraction configuration instead of a dummy financial fact.

### Engineering debt

- Repository-wide formatting is not normalized; 37 files differ from Ruff formatter output.
- Several older company-loop sources depend on local `.cache` filings. The QuantumScape final candidate avoids that dependency by retaining a normalized official-source extract, but the historical registry is not yet fully self-contained for a fresh clone.
- Visual report inspection is still manual and not captured as a first-class review receipt.

### Deliberate product choices

- Exact scopes fail closed; fuzzy or adjacent scope names do not inherit rules.
- Stage evidence may suppress only the historical profitability/unit-economics card, not all forward commercial questions.
- Marketable securities remain separate from cash in the simple runway metric.
- Auxiliary and Agent evidence cannot change a deterministic signal or digest.

### Still roadmap, not implemented

- Authenticated multi-user/cloud authorization.
- Persistent enterprise supplement-request state machine and company-facing submission UI.
- Automatic ESG certification, ARL scoring, or internationalization certification.
- End-to-end validation of the other four finance dimensions.
- First-revenue transition policy that expires stale pre-commercial applicability evidence.
- Formal visual-review receipt and final QuantumScape registry promotion.

## Recommended next cycle

1. Open `outputs/company-loops/11-quantumscape/report.html` locally and record the visual result. If it is legible and semantically correct, add QuantumScape as iteration 11 using explicit expected outcomes and rebuild the index.
2. Use a real first-revenue transition company to prove that `not_yet_applicable` expires when recognized operating revenue appears.
3. Test ReNew Energy Global for IFRS/20-F and mixed asset-owner/manufacturing scope.
4. Test Li-Cycle for transition-period, restatement, and accounting-comparability failure modes.
5. Before any Vercel or shared deployment, add real authentication, authorization, durable storage, secrets handling, and a publication approval workflow. Do not interpret the current loopback Agent token as a cloud security boundary.
