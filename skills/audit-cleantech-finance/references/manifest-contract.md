# Manifest contract

Treat `schemas/manifest.schema.json` as authoritative. Validate with Draft 2020-12 and a format checker.

## Subject and stable identity

Every manifest needs `subject`, `assessment`, and at least one local source.

```json
{
  "subject": {
    "organization": "Current legal entity",
    "technology": "Exact product and use case",
    "ticker": "TICKER",
    "cik": "0000000000",
    "identity": {
      "entity_id": "sec-cik-0000000000",
      "scheme": "sec_cik",
      "value": "0000000000",
      "legal_name": "Current legal entity",
      "display_name": "Current legal entity (formerly Old Legal Entity)",
      "display_name_zh": "Current legal entity（原 Old Legal Entity）",
      "legal_name_citation": {
        "source_id": "current-10k",
        "locator": "Cover page"
      },
      "aliases": []
    }
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

The identity object is optional for legacy manifests. When present, every `subject`, `identity`, and `auxiliary` source must carry the same `subject_entity_id`. Reject a conflicting CIK or source binding; never use fuzzy name similarity as proof.

## Source roles

Every source needs `id`, `path`, `title`, `url`, `publisher`, `published`, `kind`, and `role`.

- `subject`: authoritative filing used for subject retrieval and facts.
- `identity`: historical legal-name evidence; excluded from retrieval.
- `auxiliary`: optional user-selected cross-check or context; excluded from retrieval and signals.
- `benchmark`: cited comparator evidence; never allowed to contaminate subject facts.

## Automatic financial mode

Use only for supported English consolidated statements. Never provide `financials` at the same time.

```json
"financial_extraction": {
  "enabled": true,
  "source_id": "annual-report",
  "currency": "USD",
  "years": [2025, 2024],
  "fiscal_year_end": "12-31"
}
```

The extractor fails closed on missing statement anchors, labels, years, units, or numeric pairs.

## Structured cited financial mode

Use for unsupported formats. Preserve two comparable annual periods, explicit dates, inclusive duration, accounting scope, and source provenance. Store capex as a positive cash-outflow magnitude.

```json
"financials": {
  "currency": "USD",
  "periods": [
    {
      "period": "FY2025",
      "fiscal_year": 2025,
      "period_type": "annual",
      "start_date": "2025-01-01",
      "end_date": "2025-12-31",
      "duration_days": 365,
      "facts": {
        "revenue": {
          "value": 1000000,
          "source_id": "annual-report",
          "locator": "PDF p.81",
          "accounting_scope": "consolidated",
          "statement_scope": {
            "operations": "total_operations",
            "attribution": "not_applicable"
          }
        }
      }
    }
  ]
}
```

Keep selection provenance when multiple XBRL concepts are plausible. For revenue, cost, and gross profit, prefer a deterministic statement-identity reconciliation. Preserve excluded candidates and bilingual selection basis.

## Optional auxiliary validation

```json
"auxiliary_validation": {
  "enabled": true,
  "selected_source_ids": ["sec-companyfacts"],
  "relative_tolerance": 0,
  "absolute_tolerance": 0,
  "facts": []
}
```

The user controls `selected_source_ids`. Report all available, selected, and ignored sources. Compare currency, unit, period end, and accounting scope before values; classify a semantic mismatch as `not_comparable`, not a numerical mismatch. Context facts are descriptive only. `affects_signal` must remain false.

## Optional cash-conversion context

Use `cash_conversion_context` only for selected auxiliary XBRL drivers. Let versioned code derive polarity; never accept a user-provided multiplier or normalized value. Validate period start/end, currency, unit, consolidated scope, concept semantics, and selected source. Preserve both raw XBRL value and normalized cash effect. Label totals as selected major drivers, not a complete OCF reconciliation.

Read [judgment-context.md](judgment-context.md) before adding the cited bilingual research contract.
