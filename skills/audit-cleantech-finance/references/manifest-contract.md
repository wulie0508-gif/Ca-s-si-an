# Manifest contract

Use the repository schema at `schemas/manifest.schema.json` as the machine-readable contract.

## Required scope

```json
{
  "subject": {
    "organization": "Legal entity",
    "technology": "Exact product and use case",
    "ticker": "Exchange:ticker or null"
  },
  "assessment": {
    "as_of": "YYYY-MM-DD",
    "horizon_years": 5,
    "geography": "Target market",
    "value_chain_scope": "Included activities"
  },
  "sources": []
}
```

Each source needs `id`, `path`, `title`, `url`, `publisher`, `published`, and `kind`. Set `role` to `subject` for documents about the company being audited and `benchmark` for comparator documents. Benchmark sources remain available to cited judgment context but are excluded from subject retrieval and fact extraction. Prefer these `kind` values when applicable: `audited_financial`, `regulatory_filing`, `government`, `regulator`, `standard`, `independent_research`, `company_report`, `investor_presentation`, `product_documentation`, `press_release`, or `media`.

## Automatic mode

Use only for supported English consolidated statements:

```json
"financial_extraction": {
  "enabled": true,
  "source_id": "annual-report",
  "currency": "USD",
  "years": [2025, 2024]
}
```

The extractor fails closed when an anchor, label, year, or numeric pair is missing.

## Structured cited mode

Use for unsupported formats. Store capex as a positive cash outflow magnitude.

```json
"financials": {
  "currency": "USD",
  "periods": [
    {
      "period": "FY2025",
      "end_date": "2025-12-31",
      "facts": {
        "revenue": {
          "value": 1000000,
          "source_id": "annual-report",
          "locator": "PDF page 81"
        }
      }
    }
  ]
}
```

Supported calculation fact names include `revenue`, `gross_profit`, `operating_cost`, `operating_income`, `net_income`, `operating_cash_flow`, `capex`, `cash_and_equivalents`, `total_debt`, and `backlog`.

Read [judgment-context.md](judgment-context.md) before adding the optional agent-prepared context used to render the two implemented five-cell cards.
