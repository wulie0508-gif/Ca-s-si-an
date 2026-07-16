# CleanTech Finance v0.3.0 — ten-company validation report

Date: 2026-07-16  
Mode: local deterministic core; model calls 0; no upload

## Outcome

Ten distinct public-company loops completed. Each loop began with the then-current product, exposed a new generalization defect, implemented a general contract or rule change, added a focused regression, and reran the cumulative gates. Foundation work before First Solar is not counted.

| Loop | Company | Stable entity | Primary optimization | Profitability | Cash |
|---:|---|---|---|---|---|
| 1 | First Solar | `sec-cik-0001274494` | Optional non-authoritative cross-check | amber | green |
| 2 | Plug Power | `sec-cik-0001093691` | Reported gross profit and loss-stage state | amber | amber |
| 3 | ChargePoint | `sec-cik-0001777393` | Bilingual semantics, context facts, net-income gate | amber | amber |
| 4 | Bloom Energy | `sec-cik-0001664703` | XBRL statement-identity reconciliation | amber | amber |
| 5 | Fluence | `sec-cik-0001868941` | Explicit non-calendar annual period identity | amber | amber |
| 6 | Albemarle | `sec-cik-0000915913` | User-selected sources and semantic comparability | amber | amber |
| 7 | TPI Composites | `sec-cik-0001455684` | Total/continuing operations and attribution scope | amber | red |
| 8 | Clearway Energy | `sec-cik-0001567683` | Dimension-by-business applicability | not applicable | amber |
| 9 | Nextpower / Nextracker | `sec-cik-0001852131` | Stable identity across a legal-name change | amber | amber |
| 10 | Shoals Technologies | `sec-cik-0001831651` | True cash coverage and XBRL cash-effect polarity | amber | red |

Signals are independent evidence signals, not ratings, rankings, or a composite score.

## Final contracts

- The deterministic rule library is the only signal authority. Agent research cannot supply or override a signal, rule, path, rationale, or locked framework.
- Every executable rule has an exact subindustry scope and version. `authored` remains distinct from `validated`.
- Financial periods preserve fiscal year, start/end, annual identity, and duration.
- Statement facts preserve total/continuing operations and attribution; a dimension selects exactly one compatible net-income fact.
- Legal-name history can bind to one stable SEC CIK; conflicting sources fail closed.
- A dimension may be explicitly bilingual `not_applicable` without blocking another dimension.
- Auxiliary sources are available/selected/ignored by user choice, compared semantically before numerically, and cannot affect signals or digests.
- Cash-conversion context preserves raw XBRL signs and applies a versioned polarity policy only after period, currency, unit, scope, and source checks.

## Local product

- Ten-case registry: `evals/company-loops-v0.3.json`
- Detailed loop log: `docs/local-iteration-loop-v0.3.0.md`
- Strict registry runner: `scripts/run_company_loop_registry.py`
- Whitelist source selector: `scripts/run_company_loop_case.py`
- Bilingual index builder: `scripts/build_company_loop_index.py`
- Local index: `outputs/company-loops/index.html`
- Orchestrated Skill: `skills/audit-cleantech-finance/`

## Verification boundary

The release gate still preserves the original ordered public cases: Sungrow first, then Enphase. Their 29/29 and 28/28 checks validate extraction and provenance; 27/27 validates the card contract. These numbers, the ten new-company loops, and all red/amber/green labels do not validate an investment conclusion.
