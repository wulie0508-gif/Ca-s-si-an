# Judgment-context contract

Use `judgment_context` only to supply concise, cited research that the deterministic core cannot derive from financial statements. It is implemented for `profitability-unit-economics` and `cash-runway`.

## Authority split

1. The Agent identifies the subindustry and value-chain position with subject-source citations.
2. The Agent retrieves the subject's own history first and adds genuinely comparable peers only when useful. Label imperfect peers as adjacent context and state limitations.
3. The deterministic rule library selects the signal, application path, rationale, and summary.
4. The Agent exposes at least one `evidence_gap`, `human_judgment`, and `verification` item in English and Chinese.

Never put `application`, `signal`, `framework`, `rule`, `path`, `rationale`, or an Agent-authored positioning summary in this contract.

## Valid minimal shape

```json
{
  "judgment_context": {
    "contract_version": "0.3.0",
    "prepared_by": "agent-assisted, maintainer-authorized",
    "prepared_at": "YYYY-MM-DD",
    "subindustry": {
      "scope_id": "power-electronics-equipment",
      "name": "Power-electronics equipment provider",
      "name_zh": "电力电子设备供应商",
      "value_chain_position": "Design and sale of inverters and storage systems",
      "value_chain_position_zh": "逆变器与储能系统的设计和销售",
      "summary": "Concise cited classification.",
      "summary_zh": "简明且有引用支持的分类。",
      "basis": [
        {"source_id": "annual-report", "locator": "PDF p.8"}
      ]
    },
    "dimensions": {
      "profitability-unit-economics": {
        "benchmark": {
          "scope": "Own history first; adjacent equipment context second.",
          "scope_zh": "优先使用自身历史，其次使用相邻设备公司背景。",
          "observations": [
            {
              "comparison_type": "subject_history",
              "entity": "Subject company",
              "business_model": "Power-electronics equipment",
              "metric": "Gross margin",
              "period": "FY2025",
              "value": 42.0,
              "unit": "percent",
              "display_value": "42.0%",
              "citation": {"source_id": "annual-report", "locator": "PDF p.69"}
            }
          ],
          "limitations": ["No peer is treated as fully like-for-like."],
          "limitations_zh": ["不把任何同业公司视为完全同口径。"]
        },
        "gaps": [
          {
            "kind": "evidence_gap",
            "text": "Comparable segment disclosure is missing.",
            "text_zh": "缺少可比的分部披露。"
          },
          {
            "kind": "human_judgment",
            "text": "Assess whether the observed direction is durable.",
            "text_zh": "判断已观察到的方向是否可持续。"
          },
          {
            "kind": "verification",
            "text": "Confirm accounting comparability.",
            "text_zh": "核验会计口径的可比性。"
          }
        ]
      }
    }
  }
}
```

## Hard boundaries

- Use one explicit `scope_id`; never use `all`, `any`, `global`, or a company name.
- Cite every classification basis and benchmark observation with a known source id and page/line locator.
- Use `role: benchmark` for comparator documents so they cannot enter subject retrieval or extraction.
- Keep bilingual fields equally specific. Do not translate facts, numbers, page locators, or URLs.
- Treat these fields as structured stage results, not hidden chain-of-thought.
