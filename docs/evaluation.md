# Evaluation protocol

The product is not considered release-ready until this sequence passes in order:

1. **Feasibility smoke test** - run only `profitability-unit-economics` and `cash-runway` on Sungrow's audited annual report. Confirm that the public filing exposes the six required facts, page locators, formulas, and explicit review gaps.
2. **Sungrow correction loop** - compare the extraction with manually verified ground truth, repair every failed rule, and rerun until all required checks pass. Do not defer a known failure until after the wider product is built.
3. **Five-cell card regression** - require one fixed card per validated dimension, with a cited subindustry position, labeled facts/calculations, the locked methodology framework, cited relative application, and all three gap types.
4. **Product regression** - run the complete artifact pipeline and citation validation after the narrow smoke test passes.
5. **Comparable-company reproduction** - run Enphase, a similar clean-energy equipment company with a materially different U.S. GAAP filing format. Do not add company-name branches. A failure requires a general extractor or methodology fix, followed by rerunning both companies.

This is a stop-the-line gate: a release is blocked by any failed check. The checked public filing, checksum, ground truth, and reproduction commands must remain in the repository; the filing itself remains git-ignored.

## Required checks

- Exact-value accuracy for the audited ground-truth facts: 100% on the test set
- Page-locator accuracy: 100% on the test set
- Formula accuracy within floating-point tolerance: 100%
- Citation integrity validation: pass
- Automated investment ratings: zero
- Unsupported cash-runway claims: zero
- Parent-company statements incorrectly treated as consolidated evidence: zero
- Offline model calls and estimated model cost: zero
- Exactly five card cells for each implemented dimension
- Locked methodology framework coverage: 100% of implemented dimensions
- Personal signatures inside card methodology cells: zero
- Required bilingual card boundaries and gap text: present
- Absolute cross-subindustry thresholds in locked frameworks: zero
- Cited subindustry, application, and comparator observations: present
- `evidence_gap`, `human_judgment`, and `verification`: all present
- Four concise structured stage outputs per card; hidden chain-of-thought: not stored

## Current status

| Case | Filing | Extraction | Card contract | Expected evidence signals | Status |
|---|---|---:|---:|---|---|
| Sungrow | 2025 annual report, CNINFO | 29/29 | 27/27 | Profitability green; cash green | Pass |
| Enphase Energy | 2025 annual report/Form 10-K, SEC | 28/28 | 27/27 | Profitability amber; cash amber | Pass |

The comparable-company run exposed and fixed four extraction generalization defects: table-of-contents anchor collisions, management-summary precedence over audited statements, statement units expressed in thousands, and accounting parentheses for cash outflows. v0.2 additionally verifies benchmark-source isolation, framework immutability, fact/inference labels, and the non-rating boundary. Both companies are rerun after every gate change.

The expected card signals are maintainer-reviewed regression expectations for these two filings. They test that the same evidence and framework reproduce the intended card; they do not establish that a security is attractive, safe, or creditworthy.

Run the ordered full-product gate with:

```bash
python scripts/run_release_gate.py
```

Use `--skip-download` only when both local filings have already passed their recorded SHA-256 checks.

The table is updated only from checked `evaluation.json` and `card_evaluation.json` artifacts, not from a narrative claim.
