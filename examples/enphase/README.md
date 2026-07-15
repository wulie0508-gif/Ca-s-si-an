# Enphase reproduction case

This case checks whether the two-lens Sungrow smoke test generalizes to a U.S.
GAAP Form 10-K with a different statement layout. The manifest contains no
financial values.

```bash
python scripts/download_demo_sources.py enphase
python scripts/download_demo_sources.py sungrow
cleantech-finance audit examples/enphase/manifest.auto.json \
  --only profitability-unit-economics cash-runway \
  --out outputs/enphase
python scripts/evaluate_audit.py \
  outputs/enphase/audit.json evals/enphase-2025.json \
  --out outputs/enphase/evaluation.json
python scripts/evaluate_cards.py \
  outputs/enphase/audit.json evals/enphase-cards-v0.2.json \
  --out outputs/enphase/card_evaluation.json
```

The audited statement pages were manually checked before creating the ground
truth: operations on PDF page 69, cash flows on page 72, and the cash
reconciliation on page 73. The test specifically covers three-year columns,
USD figures reported in thousands, currency symbols, and accounting
parentheses for capex outflows.

The 2025 result should recover USD 1.473bn revenue, USD 0.786bn cost of
revenues, USD 0.172bn net income, USD 0.137bn operating cash flow, USD 0.041bn
capex, and USD 0.474bn cash and equivalents. Deterministic calculations then produce 10.7% revenue
growth, 46.6% gross margin, USD 95.901m free cash flow, and 2.8% capex to
revenue. Positive historical free cash flow suppresses the simplistic runway
calculation and leaves a forward-funding review item.

The two five-cell cards both produce amber evidence signals: gross margin declined
slightly year over year, while operating-cash-flow coverage of capex fell materially
despite remaining positive. Sungrow is assigned `role: benchmark` and is treated as
adjacent equipment context, not a fully comparable peer. The card contract passes
27/27 checks; this is a reproducibility result, not an investment judgment.

SEC downloads require a truthful identifying user agent. Set `SEC_USER_AGENT`
to a value such as `Your Name your-email@example.com` before running the
download command; do not commit personal contact details.
