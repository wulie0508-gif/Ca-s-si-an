# Round 1 Engineering Review

## Scope and safety boundary

This review used only the visible Round 1 outputs under `fa-initial/` and
`fa-supplement-baseline/`, plus product source code and tests. It did not read
`company-submission/`, `company-supplement/`, hidden truth, or another evaluator's
private work product. Existing double-blind reports were not edited.

The supplement baseline remained fail-closed on transaction authority: no Deal and
no valuation were created. Its 53/100 result is a workflow/product test score, not a
company, investment, credit, or aggregate-risk rating.

## Engineering disposition

| Issue | Classification | Round 1 disposition |
|---|---|---|
| R01-01 | Rule-contract bug | Fixed: coarse roles/profile hints no longer earn concrete requirement coverage. |
| R01-02 | Deterministic routing bug | Fixed: control artifacts are excluded; isolated weak generic terms do not route; strong phrases remain routable. |
| R01-03 | Product-format contract | Recorded only. No broad Markdown fact extraction was added. |
| R01-04 | Workflow applicability/integration bug | Fixed: company intake is the fail-closed default; acquisition requires explicit selection. |
| R01-05 | Next-action priority bug | Fixed: extraction and acquisition evidence gaps precede reference generation. |
| R01-08 | Audit product contract/roadmap | Recorded only. No empty audit file or isolated case-upload event was added. |
| R01-09 | Dependency-health latency contract | Recorded only. The timeout was not shortened as a substitute for a health-contract redesign. |

## Implemented changes

### Explicit acquisition applicability (R01-04)

- Added a persisted `workflow_type` with two accepted values:
  `company_intake` and `acquisition`.
- Existing Case URLs and the multipart `POST /api/ui/cases` endpoint are unchanged.
  `workflow_type` is an optional multipart field, so existing clients remain valid.
- New and legacy `enterprise`, `qa`, `demo`, and `unclassified` cases default to
  `company_intake` unless acquisition is explicitly selected.
- The browser UI now exposes an explicit workflow selector whose default is
  “企业首包整理”.
- A company-intake Case returns an acquisition diagnostic with
  `applicability.status=not_applicable`, `completeness.percent=null`, empty stage,
  gap, supplement, and question arrays, and a plain-language reason. It does not
  show an artificial 0% or generate the eight buyer/transaction questions.
- An explicit acquisition Case continues to use the existing endpoint and the
  deterministic eight-stage acquisition workflow.

No independent company-intake diagnostic was invented in this patch. That path is
therefore explicitly `not_applicable`, rather than silently reusing acquisition
logic.

### Versioned requirement-candidate coverage (R01-01)

The acquisition rule version is now `acquisition-workflow-1.2.0`. Concrete coverage
requires an artifact-local recognition contract of this form:

```json
{
  "requirement_candidates": {
    "schema_version": "1.0.0",
    "rule_version": "acquisition-workflow-1.2.0",
    "requirement_ids": ["nda_record"]
  }
}
```

- Only known requirement IDs under the exact current schema/rule version can earn
  `candidate_covered` and weighted completeness.
- Coarse `candidate_roles` and profile hints remain visible as routing signals but
  produce `candidate_topic_match`, which earns zero coverage and remains a gap for
  critical-gap, supplement-draft, and interview-question generation.
- Stale/malformed contracts and unknown requirement IDs fail closed and are reported
  in `input_summary`.
- Coverage sources now come only from the explicit requirement contract. Separate
  `routing_signal_artifact_ids` retain topic-routing provenance without presenting it
  as document evidence.
- Packaged and operator acquisition configs were updated together to the new rule
  version.

The workspace recognizer does not automatically mint concrete requirement candidates
from filenames or free text in this patch. That requires a separately specified,
versioned document classifier and human-review contract. Consequently, an explicit
acquisition Case with only coarse roles correctly begins at 0% candidate requirement
coverage instead of producing false late-stage completion.

### Safer role routing (R01-02)

- Control-style filenames identified generically by `manifest`, `index`, `readme`,
  `清单`, or `目录` do not participate in business-role recognition and remain
  `generic_supporting`.
- English signal matching now uses token/phrase boundaries and normalizes common
  filename separators.
- `legal`, `policy`, `customer`, `market`, and `revenue` are weak signals. One weak
  term cannot create a role; two independent weak signals for the same role may
  still create a routing candidate.
- Existing strong phrases continue to route. Strong technical-validation phrases
  were added so a generic `technical-validation-pack` can route to `technology_arl`
  without a Round-specific filename exception.

Roles remain `routing_hint_only`; none of these changes upgrades an artifact to a
verified fact or concrete acquisition requirement.

### Honest next-action priority (R01-05)

Case summary actions now follow this order:

1. material extraction/OCR failure → `resolve_material_extraction`;
2. applicable acquisition with critical gaps → `review_critical_evidence_gaps`;
3. applicable acquisition with insufficient interview evidence →
   `prepare_supplement_draft`;
4. only then refresh or generate reference suggestions.

These actions describe review or draft preparation. They do not claim that a
supplement request has been sent or persisted.

## Exact regression coverage

The regression suite now proves that:

- all coarse roles, even repeated across many accepted artifacts, earn 0% concrete
  requirement coverage and cannot make IOI/LOI, diligence, signing/closing, or PMI
  100% complete;
- an explicit, current-version NDA candidate covers only `nda_record`, not SPA,
  Closing Checklist, or the 100-day integration plan;
- stale requirement-candidate contracts fail closed;
- explicit current-version requirement candidates can still produce deterministic
  partial and complete positive cases;
- the synthetic blind evaluator generates versioned positive candidates, treats
  `candidate_topic_match` as uncovered, and preserves determinism, duplicate,
  authority, monotonicity, and source-provenance oracles;
- default Cases return a stable, null-valued `not_applicable` acquisition projection;
- explicit acquisition Cases are accepted through the existing multipart API;
- extraction/evidence-gap actions outrank recorded reference activity;
- control filenames and isolated weak terms do not produce business roles, while
  `cash flow` and `technical validation` remain positive routing controls;
- the static browser contract contains the explicit workflow selector and safely
  renders a not-applicable acquisition state.

Verification commands:

```powershell
.\.venv-new\Scripts\python.exe -m pytest `
  tests/test_acquisition_workflow.py `
  tests/test_acquisition_blind_eval.py `
  tests/test_agent_bridge.py -q

.\.venv-new\Scripts\python.exe -m ruff check `
  src/cleantech_finance/acquisition_workflow.py `
  src/cleantech_finance/workspace_service.py `
  src/cleantech_finance/agent_bridge.py `
  tests/test_acquisition_workflow.py `
  tests/test_acquisition_blind_eval.py `
  tests/test_agent_bridge.py `
  scripts/run_acquisition_blind_eval.py
```

Result: targeted pytest passed (`39 passed`); Ruff passed with no findings.
An additional full-suite compatibility run (`pytest -q`) reached 100% with exit
code 0.

## Deliberately unimplemented boundaries

- No company-intake requirement model or company-intake interview question set.
- No automatic mapping from supplement filenames/content to concrete acquisition
  requirement IDs.
- No persistent supplement-center state machine or per-question
  `answered`/`partial`/`contradicted` lifecycle.
- No loose Markdown profile extraction. A declared schema/front-matter contract must
  be chosen before that format can safely populate routing hints (R01-03).
- No unified bridge mutation audit. The current CLI audit path remains consent-event
  scoped; a complete append-only case/deal/valuation/consent contract is a separate
  product change (R01-08).
- No liveness/readiness split or cached RAG health probe. The existing synchronous
  dependency timeout remains unchanged pending a health API contract decision
  (R01-09).
- No Deal creation, valuation execution, investment/credit conclusion, or aggregate
  score was added.
