# Review protocol

## Interpret workflow status correctly

- `review_ready`: candidate evidence is strong enough to inspect efficiently. It is not a low-risk label.
- `partial`: evidence exists but needs corroboration, closer reading, or a stronger source.
- `gap`: the retrieval threshold found nothing. Treat this as a disclosure gap, not proof that the underlying capability is absent.

## Review in this order

1. Confirm entity, period, currency, consolidated scope, and source publication date.
2. Compare every automatically extracted financial value with the cited page and table header.
3. Recompute revenue growth, gross margin, free cash flow, and cash runway from the cited inputs.
4. Confirm the subindustry classification before accepting any cross-company comparison.
5. Read the subject's own trend before adjacent-company observations; verify product mix, geography, incentives, warranty, channel, and accounting boundaries.
6. Separate historical observations from management forecasts.
7. Check whether orders are binding, cancellable, conditional, funded, or merely described as pipeline.
8. Check whether product and project evidence comes from the company, an independent evaluator, a lender, an insurer, or a regulator.
9. Record conflicts and missing evidence without resolving them by intuition.

For five-cell cards, verify that cell 3 presents a neutral methodology statement and remains locked, cell 4 follows that framework, and cell 5 contains bilingual evidence, judgment, and verification gaps. Confirm the signal meaning and disclaimer are equally strict in English and Chinese. A red/amber/green label is only an evidence signal.

## Required conclusion labels

- `Fact`: directly stated in a cited source.
- `Calculation`: formula plus cited inputs.
- `Inference`: interpretation and its assumptions.
- `Needs human verification`: missing, conflicting, stale, forecast, or judgment-heavy evidence.

Leave `human_rating` null in software output. A person may record a decision outside the generated audit after completing review.
