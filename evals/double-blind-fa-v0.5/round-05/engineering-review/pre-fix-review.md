# Round 05 pre-fix engineering review

Frozen before product-code changes on 2026-08-04.

## Scope and evidence boundary

- Reviewed only the Round 05 protocol, company submission, FA initial artifacts, company supplement, and valuation/Deal/API/UI implementation and tests permitted by the engineering mandate.
- Did not read Round 01-04 conclusions, any future `fa-postfix` material, or any total/final report.
- The supplement remains company-side candidate evidence. It is not an FA confirmation, approval, or instruction to overwrite the original valuation inputs.

## Reproduced baseline

### R05-F01 — S1 / critical

- Valuation date: `2026-06-30`.
- First explicit forecast cash flow: `FY2027E`; the original workflow input contains no H2 2026/FY2026 stub, structured DCF period end, or per-period discount exponent.
- `calculate_dcf_scenario()` generated exponents from `enumerate(..., start=1)` and `_discount_denominator()`, producing `1/2/3` for period-end convention.
- After all 146 original inputs were independently human-confirmed, the service returned HTTP 201 and DCF EV of `568.55 / 1036.51 / 1534.36 CNYm`, while reporting Calculation Integrity=`passed` and Decision Readiness=`screen_grade` with no timing warning or blocker.
- This is a calculation-readiness control failure: an unproved cash-flow timing assumption can materially change explicit-period PV and terminal-value PV while the trusted output reports success.

The Round 05 company supplement proposes H2 2026E FCFF and exponents `0.5/1.5/2.5/3.5`, but explicitly marks them `v1.0-candidate`, `fa_human_acceptance_status=pending`, and `confirm_inputs=false`. They therefore cannot repair or confirm the model automatically.

### R05-F02 — S2 / major

- Source metadata is internally aligned at `0.5.0`: `pyproject.toml`, `cleantech_finance.__version__`, README, release notes, and workbook application metadata.
- The active `.venv-new` distribution metadata nevertheless resolved `cleantech-finance` to `0.4.0` from `cleantech_finance-0.4.0.dist-info`, while the imported module reported `0.5.0`.
- Root cause: stale installed/editable distribution metadata, not a source-version constant.

### R05-F03 — S3 / minor

- `DealStore.create_deal()` accepted `public`, `internal`, `confidential`, and `highly_confidential` only.
- The company authorization vocabulary `internal_only` was rejected even though its intended canonical product level is `internal`.
- The failure is recoverable but creates avoidable manual translation friction.

## Pre-fix test baseline

Focused baseline command:

```text
.venv-new/Scripts/python.exe -m pytest tests/test_valuation.py tests/test_valuation_workflow.py tests/test_deal_service.py tests/test_agent_bridge_valuation.py -q
```

Result: `76 passed` (pytest rendered 76 dots) before changes.

## Frozen readiness conclusion

- Audit evidence pack: complete enough for the directed repair.
- Audited DCF timing behavior: **not ready** for reliance because the missing timing input is an S1 hard-failure condition.
- No method weighting, investment/credit/risk rating, formal valuation opinion, approval, or publication capability is in scope.
