---
name: cleantech-workflow-bridge
description: Operate the loopback CleanTech Finance case workspace with user-approved Agent scopes. Use when Codex must read uploaded company-material text with its own model, query the local NEX RAG gateway for candidate evidence, inspect case workflow state, or run candidate-only policy matching without a model API or automated approval.
---

# CleanTech Workflow Bridge

Use the local Bridge as a controlled tool surface. Keep the browser simple for the
human; let Codex perform interpretation with its own model only after scoped consent.

## Start and verify

1. Preserve the current Git worktree.
2. Start NEX on `127.0.0.1:8000`; start the Bridge on `127.0.0.1:8765`.
3. Read `GET /api/health` and `GET /api/agent/manifest`.
4. Treat RAG service health and case-level evidence hits as separate facts.
5. Ask the user to create or select a case and upload materials in the browser.
   Uploading is a human UI action; it does not automatically ingest files into RAG.

## Request authorization

Request only the scopes needed:

- `case:read`: case list, artifacts, hashes, workflow, next action.
- `material:read`: extracted material text; also request `case:read`.
- `rag:query`: candidate retrieval through NEX.
- `resource:read`: read the connected policy, course, and mentor directories.
- `resource:match`: generate course or mentor candidates; also request
  `resource:read`.
- `policy:read`: policy catalog state.
- `policy:match`: candidate policy matching; also request `policy:read`.

Send:

```json
POST /api/agent/authorization-requests
{
  "actor": "Codex",
  "purpose": "Read one case and collect candidate evidence",
  "case_id": "case-YYYYMMDD-xxxxxxxxxx",
  "requested_scopes": ["case:read", "material:read", "rag:query"]
}
```

Keep `request_secret` in process memory. Never print it, write it to source, include
it in chat, or commit it. Tell the user a scoped request is waiting in the workbench.
The page shows requested scopes unchecked; do not select them for the user.

Poll:

```text
GET /api/agent/authorization-requests/{request_id}
X-Authorization-Request-Secret: <request_secret>
```

After status becomes `approved`, exchange once:

```text
POST /api/agent/authorization-requests/{request_id}/exchange
X-Authorization-Request-Secret: <request_secret>
Content-Type: application/json

{}
```

Keep the returned Bearer token in memory and revoke it through `POST /api/revoke`
when finished. A denied, expired, or already exchanged request cannot be reused.

## Work the case

1. Read `GET /api/agent/cases`, then
   `GET /api/agent/cases/{case_id}`.
2. For each user-authorized text artifact, read
   `GET /api/agent/cases/{case_id}/artifacts/{artifact_id}/text`.
3. Interpret material text with the current Codex model. Emit atomic claims as
   candidates; a source document is not automatically a verified fact.
4. Query `POST /api/agent/rag-query` with `case_id`, a narrow question, `mode`,
   `purpose`, and `top_k`. Preserve source and locator. Display all warnings.
5. Run `POST /api/agent/policy-match` only when policy scopes were approved.
6. Read `GET /api/agent/resources` only with `resource:read`. Run
   `POST /api/agent/resource-match` only for `course` or `mentor` and only with
   `resource:match`. Never enroll, assign, or contact from the returned list.
7. Hand candidate evidence and unresolved gaps back to the human review workflow.

## Non-negotiable boundaries

- Agent outputs remain `candidate_only`; never submit or describe them as verified.
- Interview statements prove only that a statement was made.
- Do not expose raw files when extracted text is unavailable; request OCR or human review.
- Do not auto-ingest uploaded enterprise materials into NEX.
- Do not output ESG certification, ARL 1–9 scores, investment or credit ratings,
  aggregate risk scores, or a combined red/yellow/green score.
- Only profitability/unit economics and cash flow/funding gap are validated
  end-to-end financial dimensions. Respect all other module maturity labels.
- Never accept evidence, approve a decision, change policy review status, waive a
  supplement, or publish through Agent tools.
