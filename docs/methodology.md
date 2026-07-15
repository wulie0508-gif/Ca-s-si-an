# Methodology

## Research boundary

CleanTech Finance separates five card cells and their actors:

1. **Subindustry position** - a concise agent-prepared classification with citations.
2. **Source facts and deterministic calculations** - values at page/line locators and formulas whose inputs retain provenance.
3. **Judgment framework** - fixed product text with an open-source-neutral methodology statement and comparison basis, locked against manifest overrides.
4. **Framework application** - a cited inference and conservative evidence signal that follows cell 3.
5. **Gaps and required human judgment** - evidence gaps, strategic judgment, and verification tasks that software does not resolve.

The Agent Skill records only concise structured outputs for four research stages: subindustry identification, benchmark retrieval, relative positioning/trend, and gap exposure. Hidden chain-of-thought is neither requested nor stored.

## Relative-comparison policy

Clean-energy margins and cash needs vary materially by business model. The product therefore does not use one universal gross-margin or cash threshold across manufacturers, power-electronics vendors, installers, and asset owners/operators.

The comparison order is:

1. classify the value-chain position and business model;
2. compare the subject with its own prior period using consistent definitions;
3. add genuinely comparable peers when available;
4. label adjacent-company observations as directional when comparability is incomplete;
5. expose accounting, incentive, warranty, geography, product-mix, and capital-intensity limitations.

Red, amber, and green are evidence signals only. They are not numeric scores and are never aggregated into an investment, credit, or risk rating.

The formal five-cell card presents the framework, cell headings, signal meaning, review gaps, and disclaimer in English and Chinese. Extracted numbers, page locators, source titles, and links remain in their source form.

## Locked frameworks implemented in v0.2

**Profitability and unit economics:** do not compare gross margin across unlike business models. Classify first, then compare consistent definitions over time and with genuinely comparable peers. Treat product mix, warranty, freight, incentives, and accounting scope as explanations to verify, not proof of durability.

**Cash flow and funding gap:** use cash runway for loss-making companies; for profitable companies, examine whether operating cash flow covers capital expenditure. Historical positive cash flow alone does not prove future funding sufficiency.

## Source hierarchy

The retrieval layer labels, but does not hide, source quality:

1. Audited financial statements, regulatory filings, regulators, government publications, and standards
2. Independent research
3. Company reports, investor presentations, and product documents
4. Press releases and media context

Multiple company documents do not become independent corroboration merely because they have different filenames.

## Evidence statuses

- `review_ready`: enough high-quality candidate passages exist for focused human review.
- `partial`: at least one candidate exists, but sourcing, directness, recency, or corroboration is weak.
- `gap`: no passage cleared the documented lexical threshold.

These are workflow states, not low/medium/high risk ratings.

## Core financial formulas

- Revenue growth = `(latest revenue - prior revenue) / abs(prior revenue)`
- Gross margin = `gross profit / revenue`, or `(revenue - operating cost) / revenue`
- Free cash flow = `operating cash flow - abs(cash paid for long-term assets)`
- Net margin = `net income / revenue`
- Operating cash flow to capex = `operating cash flow / abs(capex)`
- Simple cash runway = `cash and equivalents / abs(annual free cash flow) * 12`
- Net cash = `cash and equivalents - total debt`
- Capex to revenue = `abs(capex) / abs(revenue)`
- Backlog to annual revenue = `backlog / abs(revenue)`

Simple runway is calculated only when observed annual free cash flow is negative. When it is non-negative, the tool emits a review note rather than claiming funding sufficiency.

## Automatic financial extraction

The v0.2 extractor remains deliberately narrow. It requires:

- a configured primary source and two reporting years;
- a consolidated income-statement anchor;
- a consolidated cash-flow-statement anchor;
- exact or near-exact English statement labels;
- two values next to each label.

It currently extracts six facts: revenue, operating cost, net income, operating cash flow, cash paid for fixed/intangible/other long-term assets, and period-end cash equivalents. Net income selects the cash-analysis branch. If a required fact cannot be linked to an anchored statement window, the run fails instead of guessing.

When a filing repeats a statement title in its table of contents or management discussion, the extractor prefers the formal statement window using title position, numeric density, statement-field cues, and the notes footer. It normalizes statement-level `in thousands` and `in millions` units to whole currency units. Accounting parentheses remain signed values, while the capex cash-outflow fact is stored as a positive magnitude. These are format rules, not company-name exceptions.

## Commercialization framework

The 17 adoption-risk dimension names follow the U.S. Department of Energy Adoption Readiness Levels framework across value proposition, market acceptance, resource maturity, and license to operate. CleanTech Finance adds original retrieval cues and review questions. It does not reproduce the official assessment, aggregate the dimensions into an ARL score, or claim DOE endorsement.

The commercial adoption layer exists to test whether assumptions behind revenue, margin, capital expenditure, and financing can plausibly be realized. It is subordinate to the financial research card, not a replacement for it.

## Known limitations

- Only profitability and cash-flow/funding-gap cards are implemented and publicly regression-tested. Four other finance lenses and all 17 adoption-risk dimensions are framework-ready retrieval only.
- Agent-prepared `judgment_context` can contain research error. The deterministic core validates structure, citations, framework lock, and calculations; it does not prove that a comparator is economically perfect.

- Table extraction quality depends on the PDF text layer. Scanned reports need OCR before ingestion.
- Automatic fact extraction currently targets common English annual-report labels; other formats use cited structured inputs.
- Unit normalization assumes the statement-level unit applies to the extracted rows; unusual mixed-unit tables must use cited structured inputs.
- Lexical retrieval can miss synonyms and can surface negated or boilerplate passages. Human page review is mandatory.
- A public-disclosure gap is not proof of an operating weakness.
- Cross-company comparison requires consistent accounting boundaries, currencies, periods, and segment definitions.
