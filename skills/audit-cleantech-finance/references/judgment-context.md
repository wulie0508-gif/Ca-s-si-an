# Judgment-context contract

`judgment_context` is the bridge between cited agent research and the offline deterministic core. It is implemented only for `profitability-unit-economics` and `cash-runway`.

## Four structured stages

1. Identify the subindustry and value-chain position with at least one subject-source citation.
2. Retrieve the subject's own historical benchmark first. Add genuinely comparable peers when possible; describe an imperfect peer as adjacent context and record limitations.
3. Apply the locked framework. Emit only `red`, `amber`, or `green` as an evidence signal, plus a cited path and concise summary.
4. Expose at least one item of each kind: `evidence_gap`, `human_judgment`, and `verification`. Give every item an English `text` and an accurate Chinese `text_zh`.

These are concise stage results, not hidden chain-of-thought.

## Minimal shape

```json
{
  "judgment_context": {
    "prepared_by": "agent-assisted, maintainer-authorized",
    "prepared_at": "YYYY-MM-DD",
    "subindustry": {
      "name": "Power-electronics equipment provider",
      "value_chain_position": "Design and sale of inverters and storage systems",
      "summary": "Concise cited classification",
      "basis": [{"source_id": "annual-report", "locator": "PDF p.8"}]
    },
    "dimensions": {
      "profitability-unit-economics": {
        "benchmark": {
          "scope": "Own history first; adjacent equipment reference second",
          "observations": [
            {
              "entity": "Subject company",
              "business_model": "Power-electronics equipment",
              "metric": "Gross margin",
              "period": "FY2025",
              "value": 0.42,
              "unit": "ratio",
              "display_value": "42.0%",
              "citation": {"source_id": "annual-report", "locator": "PDF p.69"}
            }
          ],
          "limitations": ["Peer and subject are not fully like-for-like."]
        },
        "application": {
          "signal": "amber",
          "path": "Classify first, then compare own trend and bounded peer context.",
          "summary": "Concise inference that follows the fixed framework.",
          "basis": [{"source_id": "annual-report", "locator": "PDF p.69"}]
        },
        "gaps": [
          {"kind": "evidence_gap", "text": "Missing comparable segment disclosure.", "text_zh": "缺少可比分部披露。"},
          {"kind": "human_judgment", "text": "Assess durability of the trend.", "text_zh": "判断该趋势是否可持续。"},
          {"kind": "verification", "text": "Confirm accounting comparability.", "text_zh": "核验会计口径的可比性。"}
        ]
      }
    }
  }
}
```

## Hard boundaries

- Never add `framework`; the open-source-neutral methodology text and basis are compiled into the product and locked.
- Never use one absolute threshold across unlike clean-energy subindustries.
- Do not call a signal an investment, credit, or aggregate risk rating.
- Every benchmark observation and framework application needs a source id and page/line locator.
- Use `role: benchmark` for comparator documents so they cannot enter subject-company retrieval or fact extraction.
