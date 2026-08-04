# FA resource workflow and policy freshness review

Date: 2026-08-02
Version: CleanTech Finance 0.4.0
Status: implemented locally; real-company and real-operator catalog validation remains required

## Outcome

The workbench now uses one consistent resource pipeline for policies, courses,
and mentors:

```text
company materials
  -> deterministic profile hints
  -> hard catalog gates
  -> candidate relevance/matching
  -> human confirmation
  -> external action outside the Agent
```

The system prepares the work and exposes provenance. An FA professional still
owns transaction strategy, outreach, negotiation, approvals, legal or tax
judgment, and the decision to use a resource. The Agent cannot enroll a company,
assign or contact a mentor, determine policy eligibility, or publish a result.

## Current resource layers

| Layer | Current local data | Authority | Can enter matching automatically? |
|---|---:|---|---|
| Hash-attested policy reference catalog | 73 records | Project-owner-confirmed reference catalog only | Only through the separate reference query; still requires official verification |
| Shanghai official update feed | 20 records | Official-page refresh candidates | No. Every row is `candidate_pending_review` |
| Course catalog | 10 synthetic fixtures | Simulation contract only | Yes, as visibly synthetic candidates |
| Mentor catalog | 12 synthetic fixtures | Simulation contract only | Yes, as visibly synthetic, non-contactable candidates |

The 20-page Shanghai sync completed with 20 successful fetches. A second run
returned 19 HTTP 304 responses and one newly supported page. At the stated
`2026-08-02` evaluation date the manifest contains five open application
windows, three ongoing processes, four explicitly historical closed calls, and
eight framework records. Those labels describe the curated source record; they
do not prove that a particular company qualifies.

## Policy refresh contract

The curated source manifest is
`config/shanghai-policy-sources.json` and its formal contract is
`schemas/policy-source-manifest.schema.json`. Sources are restricted to an
explicit Shanghai government host allowlist and HTTPS. Redirects are checked
again, page size is bounded, requests are rate-limited per host, and ETag or
Last-Modified validators are reused.

Run:

```powershell
& .\.venv-new\Scripts\python.exe -m cleantech_finance.cli policy sync `
  config\shanghai-policy-sources.json `
  --out local-data\policy-updates\shanghai `
  --as-of 2026-08-02 `
  --timeout 25 `
  --min-interval 2
```

The command writes four isolated artifacts:

- `raw/`: exact HTML snapshots for traceability;
- `state.json`: ETag, Last-Modified, hashes, and incremental-fetch state;
- `records.json`: normalized candidate records;
- `candidate-feed.csv` and `sync-receipt.json`: UI feed and run receipt.

It never edits the 73-record hash-attested workbook. New or changed pages remain
`candidate_pending_review`. A failed refresh retains an older snapshot, labels
the error, and never silently upgrades it.

Representative official sources include the Shanghai green-fuel R&D call,
renewable-energy funding notice, industrial energy-efficiency funding notice,
and the 2026 technology-SME evaluation notice:

- https://stcsm.sh.gov.cn/zwgk/kyjhxm/xmsb/20260713/1638fa0a03e445fc943942c0b847a5a9.html
- https://fgw.sh.gov.cn/fgw_ny/20251225/254cbaecdcf84aa192176a61f5cb86f8.html
- https://sheitc.sh.gov.cn/cyfz/20260414/1e15425f982a4811ae74ab2d27222e70.html
- https://kjgl.stcsm.sh.gov.cn/wdcms/xmsb/1696.jhtml

## Course and mentor contracts

The empty import templates are:

- `templates/course-catalog-template.csv`
- `templates/mentor-catalog-template.csv`

The runnable fixtures are:

- `examples/resource-catalog/synthetic-courses.csv`
- `examples/resource-catalog/synthetic-mentors.csv`

A synthetic course must declare `data_class=synthetic_fixture`,
`simulation_only=true`, and a non-empty disclosure. A synthetic mentor must do
the same, use a display name beginning with `模拟导师`, and is always emitted as
`contactable=false`. A real mentor additionally must pass availability, consent,
conflict, and validity gates.

Course matching applies publication status, active status, expiry, and
simulation-disclosure gates before tag relevance. Mentor matching requires a
core expertise or industry overlap when those profile dimensions are present;
geography alone cannot admit a candidate. Neither route produces an investment,
credit, company-quality, or aggregate-risk rating.

To replace fixtures, keep the same columns, replace every row with operator-owned
data, remove the synthetic flags, preserve source and update timestamps, and
rerun the full test suite. Real mentor records require documented consent and
conflict status before they can be browsed.

## Agent-native operation

No model API key is required. Codex or another local Agent supplies model
reasoning; the Bridge supplies deterministic data, permissions, and audit
boundaries.

New scopes and endpoints:

| Scope | Endpoint | Result |
|---|---|---|
| `resource:read` | `GET /api/agent/resources` | Read-only policy/course/mentor directory |
| `resource:match` | `POST /api/agent/resource-match` | Course or mentor candidates only |

`resource:match` requires separate consent and cannot accept `policy` as a
category. Policy uses its existing stricter reference and match routes.

## Product benchmark and open-source provenance

OffDeal is a New York/U.S. AI-native M&A adviser for U.S. small businesses, not
a Brazilian company. The useful benchmark is the operating pattern: a simple
seller input surface, AI-assisted analyst work, a transparent process, and human
bankers retaining relationship, judgment, and negotiation ownership. OffDeal is
proprietary; this project does not copy its software, data, interface, or copy.

Official references:

- https://offdeal.io/about-us
- https://offdeal.io/terms-of-service
- https://www.ycombinator.com/companies/offdeal

The implementation also reviewed public architecture patterns from Docling
(MIT), Unstructured (Apache-2.0), Haystack (Apache-2.0), the MCP Python SDK
(MIT), pytransitions (MIT), DataHub (Apache-2.0), and Microsoft GraphRAG (MIT).
No code from those repositories was copied in this change. OpenBB is AGPL-3.0;
it was considered only as an architectural reference and must not be merged into
this MIT repository without a separate license decision.

## What is still not finished

- The course and mentor records are test fixtures, not production data.
- The official policy update feed has no human promotion UI yet; it is a
  quarantined freshness layer.
- Resource choices and reviewer decisions are returned at runtime but are not
  yet a persistent acceptance/rejection history.
- The enterprise supplement center state machine remains roadmap work.
- Ordinary unstructured uploads still need stronger company-profile extraction;
  structured company JSON currently gives the most reliable tags.
- Real enterprise validation is still required before claiming operational
  generalization. Synthetic blind tests prove contract behavior, not real-world
  correctness.
- Public cloud deployment needs authentication, tenant isolation, encrypted
  storage, data-retention controls, and a private RAG architecture first.

These limitations do not prevent local demonstration or controlled pilot use,
but they do prevent describing the product as autonomous FA execution.
