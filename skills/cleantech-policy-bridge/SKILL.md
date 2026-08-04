---
name: cleantech-policy-bridge
description: Inspect a local CleanTech Finance policy workbook and run consent-gated, candidate-only policy matching through the loopback Agent Bridge. Use when Codex is asked to load, inspect, test, or match a .xlsx/.csv policy catalog without calling a model API or bypassing human review.
---

# CleanTech Policy Bridge

Use the repository's deterministic parser and loopback HTTP bridge. Treat every Agent result as a candidate; never approve, publish, or change policy review status.

## Workflow

1. Work from the CleanTech Finance repository root. Preserve the current Git worktree. Use the active project Python; if the package is not installed globally and `.venv-new\Scripts\python.exe` exists, use that executable.
2. When freshness is in scope, refresh only the curated official-source manifest
   into an isolated candidate feed:

   ```powershell
   python -m cleantech_finance.cli policy sync config\shanghai-policy-sources.json --out local-data\policy-updates\shanghai --as-of YYYY-MM-DD
   ```

   Treat every refreshed row as `candidate_pending_review`. Never merge it into
   the hash-attested catalog automatically.
3. Inspect the catalog before matching:

   ```powershell
   python -m cleantech_finance.cli policy inspect <catalog.xlsx> --as-of YYYY-MM-DD
   ```

4. Report the selected Sheet, header row, SHA-256, record count, eligible count, review-status counts, and exclusion reasons.
5. Stop recommendation work when `state` is `quarantined` or `eligible_count` is zero. Explain that the catalog loaded successfully but has no reviewed, eligible policy.
6. Start the local bridge only on loopback:

   ```powershell
   python -m cleantech_finance.cli bridge <catalog.xlsx> --host 127.0.0.1 --port 8765
   ```

7. Read `GET /api/agent/manifest`, then create an authorization request for
   `policy:read` and `policy:match`. Keep `request_secret` in process memory and
   never print or persist it.
8. Open `http://127.0.0.1:8765/`. Ask the user to review the real pending
   request and acknowledge the human-review boundary. Do not select consent
   controls or fabricate approval on the user's behalf.
9. Poll the request status with `X-Authorization-Request-Secret`; after approval,
   exchange it once for a short-lived Bearer token. See the complete handshake in
   `../cleantech-workflow-bridge/SKILL.md`.
10. Call only the tool contract exposed by the manifest. Keep the token in process
   memory; never write it to source files, logs, chat, or Git. Revoke through
   `POST /api/revoke` when the task ends.

## Match contract

Send `POST /api/agent/policy-match` with an active `policy:match` bearer token:

```json
{
  "as_of": "2026-07-31",
  "profile_tags": {
    "industry": ["储能"],
    "stage": ["早期商业化"],
    "need": ["现金流"],
    "technology": ["储热"],
    "geography": ["中国"],
    "market": ["工业脱碳"]
  }
}
```

Accept only `industry`, `stage`, `need`, `technology`, `geography`, and `market`. Preserve the returned Sheet and row locators.

## Non-negotiable boundaries

- Do not expose or call generic evidence ingestion, decision, approval, or publishing endpoints.
- Do not convert `待复核` into an eligible status for demonstration.
- Do not infer that a policy applies when every row is excluded.
- Do not treat match weights as an investment, credit, or aggregate risk score.
- Do not send the catalog or enterprise data to an external model API.
- Do not publish the raw workbook; it may contain private local paths.
