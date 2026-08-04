# Round 2 Engineering Review

## Scope and authority boundary

This fix used only the visible Round 2 `company-submission/`,
`company-supplement/`, `fa-initial/`, and `fa-supplement-baseline/` artifacts,
plus current product code, tests, and the CleanTech Finance audit skill. It did not
read hidden truth, Round 3, Round 4, or other private evaluation work.

All Round 2 business inputs are Synthetic and remain enterprise-prepared or
management-statement candidates. The implementation does not accept them as facts,
select a financial value, perform a financial calculation, create a Deal or
valuation, or produce an investment, credit, company, or aggregate-risk rating.

## Baseline audit

The initial six-file Case and combined nine-file Case were both successfully
ingested and hashed before this fix, but the product exposed no native financial-basis
preflight and no system questions. The inputs explicitly contained incompatible
structured metadata for:

- Standalone and management-group entity scopes, with multiple component entities;
- H1, YTD, R12M, point-in-time, and forecast periods;
- RMB values expressed in yuan, thousand, million, and percent units;
- excluding-VAT, including-VAT, dual-column, and unspecified tax bases;
- different cash as-of dates, restriction classes, and availability classes;
- two forecast versions with different scope/unit/VAT bases, both explicitly
  `Draft not approved`;
- an initial manifest explicitly stating that cross-file priority was not declared.

The supplement manifest later mapped R02-Q01 through R02-Q08 to submitted response
files and declared response states, but the baseline product did not retain that
mapping. The baseline correctly remained fail-closed: no calculation, Deal, or
valuation was performed.

## Bug fixes

### Deterministic structured financial-basis preflight

Added rule `company-intake-financial-basis-1.0.0`. The parser inspects only exact
structured fields in uploaded CSV and JSON:

- CSV basis fields: `entity_scope`, `source_scope`, `component_entity`,
  `period_label`, `period_start`, `period_end`, `as_of_date`, `currency`, `unit`,
  `value_unit`, `source_unit`, and `tax_basis`;
- cash fields: `restriction_class`, `availability_class`, and exact structured cash
  line-item labels;
- forecast fields: `forecast_version`, `approval_status`, scope, period, currency,
  unit, VAT basis, and as-of date;
- source-priority rows explicitly identified by `metric=Priority`;
- JSON manifest keys under `files`, `declared_versions`, `submission_policy`,
  `question_submission_mapping`, and `selected_normalization_basis`.

Markdown, TXT, filenames, arbitrary JSON prose, and unrecognized CSV columns never
populate the diagnostic. Dates are not ranked by recency, amounts are not ranked by
size, and similar entity names are not reconciled.

Every dimension returns all literal candidates with artifact and row provenance.
The contract keeps `selected_candidate`, `selected_version`, and
`selected_precedence` as `null`.

### Stable questions and calculation gate

The following stable question IDs are generated in deterministic order when their
structured trigger is present:

| ID | Dimension | Priority |
|---|---|---|
| R02-Q01 | Entity scope | Critical |
| R02-Q02 | Component/related entities | Critical |
| R02-Q03 | Reporting period | Critical |
| R02-Q04 | Currency and unit | Critical |
| R02-Q05 | VAT basis | Critical |
| R02-Q06 | Cash as-of, restrictions, and availability | Critical |
| R02-Q07 | Forecast version and approval | Critical |
| R02-Q08 | Source precedence and reconciliation | High |

`calculation_status.status` is `blocked` whenever a triggered critical dimension is
multiple, unknown, or contains an unapproved forecast. The output only gates future
work; it does not calculate or normalize financial values.

For the visible initial six files, all R02-Q01 through R02-Q08 are generated and
R02-Q01 through R02-Q07 block calculation. The source-precedence state is
`explicitly_not_declared`.

### Candidate supplement response receipts

When a JSON supplement manifest explicitly supplies `question_submission_mapping`,
the product records:

- the stable question ID and declared response state;
- referenced submitted files and whether those filenames are present in the Case;
- the declared remaining gap;
- `receipt_state=candidate_response_received`;
- `accepted_as_truth=false` and `question_closed=false`.

The combined nine-file Case therefore records eight candidate response receipts,
including the manifest's `full` declaration for R02-Q04, while all system questions
remain open and calculation remains blocked. A structured reconciliation priority
row changes source precedence only to `candidate_declared`; it does not authorize a
selected source hierarchy.

This is a receipt projection, not a persistent supplement-center or review/approval
state machine. Existing `open_requests=null` and
`request_tracking_state=not_implemented` remain truthful.

### Workspace, API, UI, and next action

- Company-intake Case create/get responses expose the complete
  `financial_basis_preflight` object.
- Dashboard summaries expose calculation status, stable blocking IDs, question
  count, and candidate-response receipt count.
- Extraction/OCR failure remains first priority. A blocked financial preflight then
  produces `review_financial_basis_questions`, ahead of reference generation or
  refresh.
- The browser renders preflight status, every candidate dimension, candidate response
  count, and R02 questions. Its copy explicitly states that no latest, largest, or
  name-similar candidate was selected and that response receipts were not accepted or
  closed.
- Cases without recognized structured financial metadata remain
  `not_applicable`; their Round 1 company-intake reference behavior is unchanged.

## Bugs versus product gaps

Fixed bugs:

- missing structured conflict detection despite explicit metadata;
- missing stable calculation-blocking questions;
- generic reference action outranking critical financial-basis review;
- loss of an explicit supplement-manifest question mapping;
- absence of an API/UI projection for the above states.

Product gaps, deliberately not represented as completed:

- human acceptance/rejection of a candidate basis;
- persistent question/request/submission/review history;
- verification against registry, bank, audit, invoice, tax, or approval evidence;
- a versioned automatic document-to-question closure classifier;
- scoped recomputation after an accepted answer;
- approved forecast selection and change-log governance.

## Deliberately not implemented

- No loose Markdown or free-prose metadata inference.
- No “latest date”, “largest value”, fuzzy entity-name, or filename-based selection.
- No automatic truth acceptance from `response_state=full` or a normalization bridge.
- No unit conversion, VAT conversion, aggregation, runway, funding-gap, forecast, or
  valuation calculation.
- No Deal, acquisition-stage transition, valuation, publication authorization, or
  aggregate rating.
- No claim that the supplement center is implemented.

## Focused regression verification

Added exact integration fixtures for the visible initial six files and combined nine
files, plus negative tests for Markdown, arbitrary CSV columns, and arbitrary JSON
prose. The tests assert deterministic R02 IDs, blocked status, literal candidate
preservation, null selections, candidate response receipt boundaries, next-action
priority over recorded references, UI copy, and preserved Round 1 behavior.

Commands:

```powershell
.\.venv-new\Scripts\python.exe -m pytest `
  tests/test_company_intake_preflight.py `
  tests/test_agent_bridge.py `
  tests/test_acquisition_workflow.py `
  tests/test_acquisition_blind_eval.py -q

.\.venv-new\Scripts\python.exe -m ruff check `
  src/cleantech_finance/company_intake_preflight.py `
  src/cleantech_finance/workspace_service.py `
  src/cleantech_finance/agent_bridge.py `
  tests/test_company_intake_preflight.py `
  tests/test_agent_bridge.py `
  tests/test_acquisition_workflow.py `
  tests/test_acquisition_blind_eval.py `
  scripts/run_acquisition_blind_eval.py
```

Result at implementation time: targeted pytest passed; Ruff passed with no findings.
The full suite was not run in this Round 2 step, per the requested bounded test gate.
