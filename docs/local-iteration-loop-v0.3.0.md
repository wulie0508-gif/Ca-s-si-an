# CleanTech Finance v0.3.0 — local ten-iteration record

This is an evidence log, not hidden reasoning. Each iteration records the
observed product risk, the bounded change, automated checks, ordered public-case
regression, and the decision that follows. Remote publication is intentionally
outside this loop.

## Fixed loop

1. Inspect one concrete failure mode or contract gap.
2. Make the smallest local change that closes it.
3. Run focused tests, the full test suite, and static checks.
4. Run the ordered Sungrow then Enphase release gate.
5. Inspect the resulting machine-readable and human-readable artifacts.
6. Record the evidence and use the residual gap as the next iteration input.

## Iteration 1 — freeze the rule contract

- Observed gap: v0.2.1 had no immutable rule representation, so authored policy,
  validated behavior, scope, inputs, and output maturity were not separable.
- Change: added a frozen, versioned, explicitly subindustry-scoped rule library;
  added non-executable authored blueprints for the remaining four finance
  dimensions; added fail-closed and determinism tests.
- Focused checks: 11 rule tests passed; Ruff passed for changed files.
- Full suite: 25 tests passed.
- Ordered gate: Sungrow 29/29 extraction and 27/27 cards; Enphase 28/28
  extraction and 27/27 cards; zero model calls.
- Artifact path: `outputs/iteration-loop/01/`.
- Decision: the data contract is stable enough to replace the external signal
  assertion in the judgment layer during iteration 2.

## Iteration 2 — make the core the only signal authority

- Observed gap: v0.2.1 trusted `judgment_context.application.signal`, path, and
  summary supplied by an agent.
- Change: removed application assertions from both public manifests and the
  schema; required a canonical subindustry scope and comparison type; generated
  signal, bilingual path, bilingual summary, rule digest, and input digest in
  the deterministic core; rejected any external application override; recorded
  concrete sources for all four stages.
- Focused checks: 26 pipeline and rule tests passed; both public manifests are
  valid against the v0.3.0 schema; Ruff passed for changed Python files.
- Full suite: 26 tests passed.
- Ordered gate: Sungrow 29/29 extraction and 27/27 cards; Enphase 28/28
  extraction and 27/27 cards; expected signals remain green/green and
  amber/amber; zero model calls.
- Artifact path: `outputs/iteration-loop/02/`.
- Decision: deterministic authority and public-case compatibility are proven;
  iteration 3 will harden provenance, subject/benchmark isolation, and
  fail-closed behavior around the integrated path.

## Iteration 3 — close provenance and contamination paths

- Observed gap: extraction accepted any known source ID even if its manifest
  role was `benchmark`; identity labels and benchmark display values also
  needed an integrated invariance test.
- Change: required the extraction source and subindustry citation to have the
  `subject` role; required comparison-role alignment; made zero-capex cash-card
  evaluation fail with a clear message; added mapping-order, company-rename,
  benchmark-value mutation, and source-role adversarial tests.
- Focused checks: Ruff passed across `src`, `tests`, and `scripts`.
- Full suite: 30 tests passed.
- Ordered gate: Sungrow 29/29 extraction and 27/27 cards; Enphase 28/28
  extraction and 27/27 cards; zero model calls.
- Artifact path: `outputs/iteration-loop/03/`.
- Decision: subject facts are isolated from benchmark inputs and the rule result
  is invariant to identity/display mutations; iteration 4 will make product
  maturity claims derive from the explicit rule registry without overstating
  the four authored-only dimensions.

## Iteration 4 — separate rule maturity from product completion

- Observed gap: the capability matrix only knew whether a dimension had a
  validated card; it could not state that four additional rule input contracts
  were authored without implying they were implemented.
- Change: derived an independent `rule_status` from the rule registry; kept
  product completion at 2/6; exposed exactly two validated-rule dimensions and
  four authored-only dimensions; bumped package and audit schema versions to
  0.3.0; updated the English and Chinese truth-boundary text.
- Focused checks: capability assertions prove authored rules still have no
  judgment card; Ruff passed across the Python tree.
- Full suite: 30 tests passed.
- Ordered gate: Sungrow 29/29 extraction and 27/27 cards; Enphase 28/28
  extraction and 27/27 cards; zero model calls.
- Artifact path: `outputs/iteration-loop/04/`.
- Decision: maturity claims are now machine-derived and non-inflating;
  iteration 5 will re-author the Skill as a strict four-stage orchestrator whose
  semantic stages cannot control the deterministic signal.

## User-defined new-company loops

The four iterations above are foundation work and are not counted toward the
user-defined acceptance target below. Each numbered loop below starts from a
new company that has not appeared in an earlier test, records the concrete gap
it exposed, implements a bounded improvement, and validates that same company.

### New-company Loop 1/10 — First Solar

- New subject: First Solar, Inc. (`FSLR`), thin-film solar-module manufacturing.
- Primary evidence: FY2025 annual report hosted by First Solar Investor
  Relations; a normalized local fact pack preserves the official URL and page
  locators. An optional official FY2025 results source cross-checks net income.
- Initial failure: both cards failed closed because
  `solar-module-manufacturing` had no explicit rule scope.
- Optimization: added that exact scope; added the user-selected auxiliary source
  role and bilingual matched/mismatch reporting; auxiliary values are excluded
  from retrieval and cannot alter a signal; added a reusable new-company case
  registry and test.
- Result: validation passed; profitability `amber` because own-history GAAP
  margin declined; cash `green` because the profitable-company OCF/capex trend
  improved. Auxiliary check: 1 matched, 0 mismatched.
- Automated evidence: 32 tests passed; Ruff passed; model calls 0.
- Artifact path: `outputs/company-loops/01-first-solar/`.
- Residual insight: First Solar remained profitable. Loop 2 must test whether the
  same trend rule behaves safely when gross margin is still negative.

### New-company Loop 2/10 — Plug Power

- New subject: Plug Power Inc. (`PLUG`), integrated hydrogen, fuel-cell,
  electrolyzer, infrastructure, service, power, and fuel platform.
- Primary evidence: FY2025 Form 10-K Inline XBRL facts; optional SEC companyfacts
  values cross-check gross loss and net loss.
- Initial failure: the card builder crashed because it required
  `operating_cost`, even when the filing supplied the standard `GrossProfit`
  concept. The existing improving-margin rule would also have mapped a still
  negative but improving margin to green.
- Optimization: made gross profit/loss a first-class fact input; removed the
  irrelevant margin dependency from the cash card; added an explicit
  loss-stage margin state and a scoped rule that keeps negative-but-improving
  unit economics amber.
- Result: validation passed; profitability `amber` via
  `profitability-negative-margin-improving`; cash `amber` because operating cash
  burn improved while the company remained loss-making. Two auxiliary facts
  matched and remained non-authoritative.
- Automated evidence: 33 tests passed; Ruff passed; model calls 0.
- Artifact path: `outputs/company-loops/02-plug-power/`.
- Residual insight: the next company should test a mixed hardware/subscription
  model whose fiscal year is not labelled like a calendar-year manufacturer.

### New-company Loop 3/10 — ChargePoint

- New subject: ChargePoint Holdings, Inc. (`CHPT`), a networked EV-charging
  hardware, cloud-subscription, and services provider with a January fiscal
  year-end.
- Primary evidence: FY2026 Form 10-K Inline XBRL facts; optional SEC
  companyfacts provide hardware revenue, subscription revenue, and deferred
  revenue as contextual facts rather than purported like-for-like checks.
- Initial failure: the new scope failed closed. More importantly, the existing
  rule could map a strongly improving positive gross margin to green even while
  company-level net income remained negative, and the auxiliary-source contract
  had no honest way to distinguish contextual facts from cross-checks.
- Optimization: added the exact hardware/network/SaaS scope; added an explicit
  net-income state to the profitability rule; kept positive-margin but
  loss-making improvement amber; separated auxiliary facts into `crosscheck`
  and `context` modes; and required bilingual subindustry, benchmark-scope, and
  limitation fields in the semantic contract and rendered card.
- Result: validation passed; profitability `amber` via
  `profitability-positive-margin-loss-making-improving`; cash `amber` because
  operating cash burn improved but remained negative. Three optional context
  facts were displayed, stayed non-authoritative, and did not count as
  mismatches.
- Automated evidence: 34 tests passed; Ruff passed; five manifests passed the
  Draft 2020-12 schema validator; model calls 0.
- Artifact path: `outputs/company-loops/03-chargepoint/`.
- Residual insight: Loop 4 should test whether a filing with multiple plausible
  XBRL cost concepts can preserve and explain which fact was selected instead
  of silently accepting a semantically narrower alternative.

### New-company Loop 4/10 — Bloom Energy

- New subject: Bloom Energy Corporation (`BE`), an on-site solid-oxide
  fuel-cell systems and related-services company.
- Primary evidence: FY2025 Form 10-K and SEC companyfacts. The local source
  cache preserves the complete official filing and XBRL payload with the
  filing SHA-256 digest recorded by the collector.
- Initial failure: the collector selected
  `RevenueFromContractWithCustomerExcludingAssessedTax` (USD 2,001.614m) rather
  than consolidated `Revenues` (USD 2,023.994m). The same XBRL payload also
  exposed `CostOfGoodsAndServicesSold` (USD 18.000m) beside consolidated
  `CostOfRevenue` (USD 1,436.594m). Alias precedence alone could silently choose
  a narrower concept; the generated case also lagged the bilingual v0.3
  contract.
- Optimization: replaced first-hit aliases for statement-level revenue and
  cost with deterministic identity reconciliation against reported gross
  profit; preserved selected concept, bilingual basis, excluded candidates,
  and reconciliation result in every fact; fail closed when an asserted
  reconciliation does not pass; exposed the selection in Markdown and HTML;
  and upgraded the SEC collector to emit the full bilingual semantic contract.
- Result: both years reconcile exactly using `Revenues`, `CostOfRevenue`, and
  `GrossProfit`; validation passed; profitability `amber` because margin
  improved while net income remained negative; cash `amber` because positive
  OCF occurred in a loss-making branch. Fourteen optional SEC facts matched and
  remained non-authoritative.
- Automated evidence: 35 tests passed; Ruff passed; model calls 0.
- Artifact path: `outputs/company-loops/04-bloom-energy/`.
- Residual insight: Loop 5 should use a non-calendar-year company to prove that
  period identity comes from explicit start/end dates rather than SEC `frame`
  labels or calendar-year assumptions.

### New-company Loop 5/10 — Fluence Energy

- New subject: Fluence Energy, Inc. (`FLNC`), a grid-scale energy-storage
  system integrator with services and digital applications and a September 30
  fiscal year-end.
- Primary evidence: FY2025 Form 10-K and SEC companyfacts, cached locally with
  the collector's filing digest.
- Initial failure: the first generated manifest retained only `FY2025` and
  `2025-09-30`; it discarded the XBRL duration start. The core therefore could
  sort periods but could not prove that the two inputs were comparable annual
  periods, distinguish a transition period, or show that SEC `frame` had not
  been used as a fiscal-year label. The text extractor separately hard-coded
  December 31.
- Optimization: introduced an explicit period contract with fiscal year,
  annual period type, start date, end date, and inclusive duration; required
  unique annual labels and end dates; rejected transition periods and annual
  periods differing by more than seven days; updated both SEC collection and
  text extraction to preserve configured fiscal year-ends; and exposed the
  comparison evidence in the audit.
- Result: FY2024 is preserved as 2023-10-01 through 2024-09-30 (366 days) and
  FY2025 as 2024-10-01 through 2025-09-30 (365 days), explicitly independent of
  SEC `frame`. Validation passed; profitability `amber` and cash `amber` on a
  positive-to-negative profit/cash transition. Optional SEC facts passed and
  remained non-authoritative.
- Automated evidence: non-calendar extraction and transition-period rejection
  are regression-tested; Ruff and the full suite passed; model calls 0.
- Artifact path: `outputs/company-loops/05-fluence/`.
- Residual insight: Loop 6 should test a diversified company with several
  optional sources so the user can select which auxiliary sources participate
  and semantically non-comparable values cannot be reported as matches.

### New-company Loop 6/10 — Albemarle

- New subject: Albemarle Corporation (`ALB`), a lithium-materials and
  diversified-specialty-chemicals company.
- Primary evidence: FY2025 Form 10-K. Two optional official sources are
  available: SEC companyfacts and Albemarle's FY2025 results release.
- Initial failure: auxiliary validation had one global on/off switch. A user
  could not choose a source, and values were compared only by `(period label,
  fact id)`. A same-currency Energy Storage segment-revenue value could
  therefore be called a numerical mismatch with total-company revenue rather
  than correctly classified as not comparable.
- Optimization: added explicit `selected_source_ids`; audit output now records
  available, selected, and ignored sources; auxiliary facts carry currency,
  unit, period end, and accounting scope; any semantic mismatch is reported as
  `not_comparable` before numerical tolerance is considered; unselected source
  facts are ignored; and all auxiliary paths remain unable to alter signals or
  rule digests.
- Result: selecting SEC companyfacts produces 14 exact matches and `passed`.
  Selecting only the company results release produces one matched consolidated
  OCF fact and one correctly `not_comparable` Energy Storage segment-revenue
  fact, so auxiliary status becomes `warning` while both core signals and rule
  digests remain unchanged. The default case validates with profitability
  `amber` and cash `amber`.
- Automated evidence: source-choice invariance and semantic-scope rejection are
  regression-tested; Ruff and the full suite passed; model calls 0.
- Artifact path: `outputs/company-loops/06-albemarle/`.
- Residual insight: Loop 7 should make net-income attribution and continuing
  versus discontinued operations explicit before those facts are allowed to
  control the profitability and cash branches.

### New-company Loop 7/10 — TPI Composites

- New subject: TPI Composites, Inc. (`TPICQ` in the FY2025 filing), a wind-blade
  contract manufacturer and field-services provider.
- Primary evidence: FY2025 Form 10-K and SEC companyfacts. The filing restates
  the sold Türkiye and automotive businesses as discontinued operations and
  explicitly says its operating discussion reflects continuing operations,
  while consolidated cash flows include both continuing and discontinued
  operations.
- Initial failure: one unqualified `net_income` value controlled both cards.
  The generated performance facts were continuing-operations values, but the
  selected `NetIncomeLoss` was total operations. The core could therefore mix
  scopes silently; it also could not distinguish consolidated net income from
  income attributable to the parent.
- Optimization: introduced structured statement scope (`operations` and
  `attribution`); added a separately cited continuing-operations net-income
  fact; profitability now selects the one net-income fact matching the revenue
  and gross-profit scope, while cash selects the fact matching OCF scope;
  mixed operations scopes, changing attributions, missing matches, or duplicate
  matches fail closed; scope and chosen fact ids enter the input digest and the
  bilingual card provenance.
- Result: profitability uses parent-attributable continuing-operations losses
  (FY2025 USD -324.353m; FY2024 USD -222.755m) alongside continuing-operations
  revenue/margin and returns `amber`. Cash uses total-operations net losses
  (USD -340.802m; USD -240.707m) alongside total consolidated OCF and returns
  `red`. Optional SEC cross-checks pass and remain non-authoritative.
- Automated evidence: the test proves each dimension selects a different,
  scope-matched fact and fails when the continuing-operations fact is removed;
  Ruff and the full suite passed; model calls 0.
- Artifact path: `outputs/company-loops/07-tpi-composites/`.
- Residual insight: Loop 8 should test an asset owner for which a manufacturing
  gross-margin rule is not economically applicable, ensuring one dimension can
  be explicitly not applicable while the other still runs.

### New-company Loop 8/10 — Clearway Energy

- New subject: Clearway Energy, Inc. (`CWEN`), a contracted renewable-power
  generation and battery-storage asset owner.
- Primary evidence: FY2025 Form 10-K and SEC companyfacts.
- Initial failure: the generic collector found `CostOfRevenue` of USD 530m and
  revenue of USD 1,429m, which mechanically implies a 62.9% "gross margin."
  For this asset owner the cost concept excludes material depreciation and
  does not represent manufacturing unit economics. Merely adding the scope to
  the shared rules would have validated a category error; leaving it unknown
  also prevented the independent cash card from running.
- Optimization: split validated profitability scopes from cash scopes; added a
  deterministic dimension-by-scope applicability gate; represented
  profitability as an explicit bilingual `not_applicable` outcome rather than
  a signal; suppressed misleading gross- and net-margin calculations; kept the
  cash card, traces, citations, auxiliary checks, and report rendering fully
  independent; and taught the new-company registry to expect a null signal for
  an inapplicable dimension.
- Result: profitability has no signal and no manufactured margin metric. Cash
  evaluates parent-attributable profitability with consolidated OCF/capex and
  returns `amber` because coverage remained positive but declined. Validation
  and optional SEC checks pass.
- Automated evidence: tests prove no profitability card, no gross/net-margin
  metric, a present cash card, and an explicit applicability outcome; Ruff and
  the full suite passed; model calls 0.
- Artifact path: `outputs/company-loops/08-clearway-energy/`.
- Residual insight: Loop 9 should test stable entity identity across a legal
  company-name change so old and new disclosures are not split into two
  companies.

### New-company Loop 9/10 — Nextpower (formerly Nextracker)

- New subject: Nextpower Inc. (`NXT`), formerly Nextracker Inc., a solar
  tracking and power-conversion systems manufacturer. Its FY2026 Form 10-K says
  the corporate name changed in November 2025.
- Primary evidence: the Nextpower FY2026 Form 10-K, the Nextracker FY2025 Form
  10-K, and optional SEC companyfacts. Both filings have SEC CIK `0001852131`.
- Initial failure: the generated manifest stored the current organization name,
  ticker, and CIK, but sources had no stable subject binding or legal-name
  history. Joining the old and new filings therefore depended on a mutable name
  string; a conflicting source could be merged silently.
- Optimization: introduced a strict entity-identity contract keyed by
  `sec-cik-0001852131`; preserved current legal and bilingual display names,
  former-name alias, effective period, and citations; added a dedicated
  identity-source role; required every subject, identity, and auxiliary source
  to bind to the same entity id; and fail closed on a CIK or binding conflict.
  Reports now expose the matching method, name history, and source bindings.
- Result: current Nextpower, historical Nextracker, and SEC companyfacts resolve
  to one entity without fuzzy name matching. Profitability is `amber` because
  gross margin declined; cash is `amber` because profitable-company OCF/capex
  coverage remained positive but declined. Optional SEC checks pass and remain
  non-authoritative.
- Automated evidence: a regression test proves old and new publishers merge by
  stable CIK and that a conflicting historical source id is rejected; schema,
  Ruff, and the full suite pass; model calls 0.
- Artifact path: `outputs/company-loops/09-nextpower/`.
- Residual insight: Loop 10 should test whether positive XBRL magnitudes for
  receivable growth, inventory growth, and warranty payments are normalized to
  their negative cash effects before they are shown as cash-conversion context.

### New-company Loop 10/10 — Shoals Technologies

- New subject: Shoals Technologies Group, Inc. (`SHLS`), a manufacturer of
  solar electrical balance-of-systems infrastructure.
- Primary evidence: FY2025 Form 10-K and optional SEC companyfacts, including
  two annual periods of working-capital and warranty-payment facts.
- Initial failure: the new scope correctly failed closed. After adding the
  scope, a deeper rule defect appeared: a profitable company with any positive
  OCF was labelled "covered," even when OCF was lower than capex. Shoals had
  USD 17.067m of OCF and USD 33.043m of capex, only 0.516509x. Separately, SEC
  XBRL reported positive magnitudes for receivable growth, inventory growth,
  and warranty payments; displaying those raw signs as cash effects would
  reverse their meaning.
- Optimization: defined the direct 1.0x arithmetic OCF/capex coverage boundary
  and versioned the affected cash rules; added a policy-versioned, digest-bound
  polarity registry for operating assets, operating liabilities, and payment
  magnitudes; validated currency, unit, period start/end, accounting scope, and
  selected auxiliary source before normalization; preserved raw XBRL values
  beside derived cash effects; and kept the entire context unable to affect a
  signal or rule/input digest.
- Result: profitability is `amber` because gross margin declined from 35.57%
  to 35.03%. Cash is now correctly `red` via
  `cash-profitable-not-covered`. FY2025 selected drivers normalize to USD
  -65.070m: receivables -50.612m, inventory -35.107m, payables +43.320m,
  contract liabilities +18.294m, and warranty payments -40.965m. The report
  explicitly says these are selected major drivers, not a complete OCF
  reconciliation.
- Automated evidence: tests cover the 0.98x failure and exact 1.0x boundary,
  all five polarity classes, a negative FY2024 receivable change becoming a
  positive cash effect, fail-closed semantic mismatch, and source-toggle
  invariance of signals and both digests. Schema, Ruff, and the suite pass;
  model calls 0.
- Artifact path: `outputs/company-loops/10-shoals/`.
- Residual insight: the ten-company protocol is complete. The remaining work is
  productization: unify all artifacts under the latest engine, expose a true
  local auxiliary-source selection workflow, publish a bilingual ten-loop
  index, and rewrite the Skill so the deterministic core—not an Agent—is the
  only signal authority.
