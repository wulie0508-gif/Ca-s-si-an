# Landscape and project gap

Snapshot date: 2026-07-14. This is a scoped design review, not a claim that no adjacent project exists.

## What already exists

| Project or framework | Useful capability | Decision for v0.2 |
|---|---|---|
| [Docling](https://github.com/docling-project/docling) | Rich PDF and document conversion, including layout-aware parsing | Keep as a future OCR/layout adapter; the default install stays lightweight with `pypdf` |
| [EdgarTools](https://github.com/dgunning/edgartools) | Convenient SEC filing retrieval and XBRL access | Keep as an optional future U.S.-filing adapter; v0.2 accepts local public filings and avoids forcing a U.S.-only dependency |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | General web-research orchestration | Do not embed a general agent runtime; CleanTech Finance focuses on deterministic provenance and review boundaries |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | Broad financial data and analysis platform | Interoperate through exported facts later; do not copy or vendor code because the product scope and licensing model differ |
| [DOE Adoption Readiness Levels](https://www.energy.gov/technologycommercialization/adoption-readiness-levels-arl-framework) | Seventeen commercialization-risk dimensions | Reuse the public dimension structure as a subordinate evidence lens; do not reproduce the official questionnaire or calculate a DOE ARL score |

## The practical gap

The useful missing layer is not another general company summarizer or market-data terminal. It is a small, auditable bridge between clean-energy financial statements and the non-financial assumptions that determine whether forecast revenue, margin, capex, and financing can materialize.

CleanTech Finance therefore makes four boundaries first-class:

1. source facts retain a stable URL, checksum, and page or line locator;
2. formulas run locally and expose every cited input;
3. commercialization passages are candidates for review, not automated risk conclusions;
4. release claims must survive an ordered public-company correction and reproduction test.
5. open-source-neutral financial judgment frameworks remain locked while agent-produced applications stay cited and reviewable.

## Why the product is finance-led

The primary output is currently two validated financial evidence cards, with four additional financial lenses explicitly marked unvalidated. The DOE-derived layer only interrogates assumptions behind those financial lenses: customer acceptance, supply chain, manufacturing scale, regulation, project delivery, and other adoption constraints. It is not a technology-readiness product with financial fields attached.

## Integration policy

Adapters should be optional and format-level. A new parser or filing client is valuable when it improves traceability without changing the audit contract. Company-name branches, opaque automated ratings, and dependencies that force users to upload confidential documents are outside scope.
