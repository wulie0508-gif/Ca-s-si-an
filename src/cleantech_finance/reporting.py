"""Write human-readable and machine-readable audit artifacts."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def _format_value(metric: dict[str, Any]) -> str:
    value = metric["value"]
    if metric["unit"] == "ratio":
        return f"{value * 100:.1f}%"
    if metric["unit"] == "months":
        return f"{value:.1f} months"
    return f"{value:,.2f} {metric['unit']}"


def _format_auxiliary_value(item: dict[str, Any]) -> str:
    value = item.get("auxiliary_value")
    unit = item.get("unit") or ""
    if not isinstance(value, (int, float)):
        return "n/a"
    if unit == "USD":
        return _money_like(value, unit)
    return f"{value:,.4g} {unit}".strip()


def _money_like(value: float, currency: str) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{currency} {value / 1_000_000_000:,.3f}bn"
    if magnitude >= 1_000_000:
        return f"{currency} {value / 1_000_000:,.3f}m"
    return f"{currency} {value:,.2f}"


def _citation_markdown(citation: dict[str, Any]) -> str:
    return f"[{citation['title']}]({citation['url']}), {citation['locator']}"


def _citation_html(citation: dict[str, Any]) -> str:
    return (
        f"<a href='{html.escape(citation['url'])}'>{html.escape(citation['title'])}</a>"
        f" <span class='meta'>{html.escape(citation['locator'])}</span>"
    )


SIGNAL_LABELS = {
    "red": "red / 红色",
    "amber": "amber / 黄色",
    "green": "green / 绿色",
}
GAP_LABELS = {
    "evidence_gap": "evidence gap / 证据缺口",
    "human_judgment": "human judgment / 人工判断",
    "verification": "verification / 存疑核验",
}
FACT_LABELS = {
    "fact": "fact / 事实",
    "calculation": "calculation / 计算",
}


def card_markdown(card: dict[str, Any]) -> str:
    cells = card["cells"]
    subindustry = cells["1_subindustry_position"]
    facts = cells["2_extracted_facts"]["items"]
    framework = cells["3_judgment_framework"]
    application = cells["4_framework_application"]
    gaps = cells["5_gaps_and_human_judgment"]["items"]
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"## Dimension / 维度: {card['dimension']} / {card['dimension_zh']} · Company / 公司: {card['company']}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "### 1. Subindustry position / 子行业定位 · Agent structured output / Agent 结构化输出",
        "",
        f"**Classification：** {subindustry['name']}  ",
        f"**分类：** {subindustry['name_zh']}  ",
        f"**Value-chain position：** {subindustry['value_chain_position']}  ",
        f"**价值链位置：** {subindustry['value_chain_position_zh']}  ",
        subindustry["summary"],
        subindustry["summary_zh"],
        "",
        "Basis / 依据：" + "; ".join(_citation_markdown(item) for item in subindustry["basis"]),
        "",
        "### 2. Extracted facts / 抽取的事实",
        "",
    ]
    for fact in facts:
        citations = "; ".join(_citation_markdown(item) for item in fact["citations"])
        lines.append(
            f"- **{fact['name']}:** {fact['display_value']} · `{FACT_LABELS[fact['label']]}` · {citations}"
        )
        scope = fact.get("statement_scope")
        if scope:
            lines.append(
                "  - Statement scope / 报表口径: "
                f"`{scope['operations']}` · `{scope['attribution']}`"
            )
        selection = fact.get("selection")
        if selection:
            lines.append(
                f"  - XBRL concept / XBRL 概念: `{selection['concept']}`; "
                f"{selection['basis']} {selection['basis_zh']}"
            )
            alternatives = selection.get("excluded_candidates") or []
            if alternatives:
                excluded = ", ".join(
                    f"{item['concept']}={item['value']:,.4g} {item['unit']}"
                    for item in alternatives
                )
                lines.append(f"  - Excluded candidates / 排除候选: {excluded}")
    lines.extend(
        [
            "",
            "### 3. Judgment framework / 判断框架 · Locked / 锁定",
            "",
            f"> {framework['text']}",
            f"> {framework['text_zh']}",
            "",
            f"**Methodology / 方法论声明：** {framework['methodology']} / {framework['methodology_zh']}  ",
            f"**Basis / 方法论依据：** {framework['basis']} / {framework['basis_zh']}",
            "",
            "### 4. Position after applying the framework / 应用框架后的定位",
            "",
            f"**Evidence signal / 证据信号：** `{SIGNAL_LABELS[application['signal']]}`  ",
            f"**Signal meaning / 信号说明：** {card['signal_meaning']} / {card['signal_meaning_zh']}  ",
            f"**Path / 路径：** {application['path']}  ",
            f"**路径（中文）：** {application['path_zh']}  ",
            application["summary"],
            application["summary_zh"],
            "",
            f"**Comparator scope / 对标范围：** {application['benchmark']['scope']}",
            application["benchmark"]["scope_zh"],
        ]
    )
    for observation in application["benchmark"]["observations"]:
        lines.append(
            f"- {observation['entity']} · {observation['metric']} · "
            f"{observation['period']} · {observation['display_value']} · "
            f"{_citation_markdown(observation['citation'])}"
        )
    lines.append(
        "- **Benchmark limitation / 对标限制：** "
        + " ".join(application["benchmark"]["limitations"])
    )
    lines.append("  " + " ".join(application["benchmark"]["limitations_zh"]))
    lines.extend(["", "### 5. Gaps and required human judgment / 缺口与必须人工判断项", ""])
    for gap in gaps:
        lines.append(f"- **{GAP_LABELS[gap['kind']]}：** {gap['text']}  ")
        lines.append(f"  {gap['text_zh']}")
    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            card["disclaimer"],
            card["disclaimer_zh"],
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_results(title: str, results: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "_Candidate retrieval only; this section is not validated judgment._",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"### {result['name']}",
                "",
                f"**Retrieval status:** `{result['status']}`  ",
                f"**Why:** {result['review_reason']}",
                "",
            ]
        )
        if result["candidates"]:
            for candidate in result["candidates"]:
                lines.extend(
                    [
                        f"- [{candidate['source_title']}]({candidate['source_url']}) — "
                        f"{candidate['locator']}; relevance {candidate['relevance']:.1f}; "
                        f"directness `{candidate['directness']}`; source `{candidate['source_quality']}`",
                        f"  - Candidate excerpt: “{candidate['excerpt']}”",
                    ]
                )
        else:
            lines.append("- No passage cleared the retrieval threshold.")
        lines.extend(["", "Human review:"])
        lines.extend(f"- {question}" for question in result["review_questions"])
        lines.append("")
    return lines


def markdown_report(audit: dict[str, Any]) -> str:
    subject = audit["subject"]
    identity = audit.get("identity_resolution", {})
    display_name = identity.get("display_name") or subject["organization"]
    capability = audit["capability_matrix"]
    summary = capability["summary"]
    finance_coverage = audit["metrics"]["finance"]
    adoption_coverage = audit["metrics"]["adoption"]
    lines = [
        f"# {display_name} — CleanTech Finance Evidence Audit",
        "",
        f"**Technology / scope:** {subject['technology']}  ",
        f"**Assessment date:** {audit['assessment']['as_of']}  ",
        "**Guardrail:** Extraction accuracy is not investment, credit, or risk-judgment accuracy.",
        "",
        "> " + capability["public_claim"],
        "",
        "## Entity identity / 实体身份",
        "",
        f"**Status / 状态：** `{identity.get('status', 'legacy')}` / {identity.get('status_zh', '未提供')}  ",
        identity.get("summary", ""),
        identity.get("summary_zh", ""),
        f"**Stable entity id / 稳定实体标识：** `{identity.get('entity_id') or 'not supplied'}`  ",
        f"**Matching method / 匹配方式：** `{identity.get('match_method') or 'legacy name fields only'}`",
        "",
        "## Capability status",
        "",
        "| Dimension | Status | Judgment card |",
        "|---|---|---|",
    ]
    for item in capability["finance"]:
        lines.append(f"| {item['name']} | `{item['status']}` | `{item['judgment_card']}` |")
    lines.extend(
        [
            "",
            f"Validated finance dimensions: **{summary['validated_finance_dimensions']}/{summary['total_finance_dimensions']}**. "
            f"Validated adoption-risk dimensions: **{summary['validated_adoption_dimensions']}/{summary['total_adoption_dimensions']}**.",
            "",
            "## Five-cell dimension evidence cards",
            "",
        ]
    )
    cards = audit.get("judgment_layer", {}).get("cards", [])
    not_applicable = [
        item
        for item in audit.get("judgment_layer", {}).get("dimension_outcomes", [])
        if item.get("status") in {"not_applicable", "not_yet_applicable"}
    ]
    for item in not_applicable:
        status_label = (
            "not yet applicable / 暂不适用"
            if item.get("status") == "not_yet_applicable"
            else "not applicable / 不适用"
        )
        lines.extend(
            [
                f"### {item['dimension_id']} — {status_label}",
                "",
                item["reason"],
                item["reason_zh"],
                "",
            ]
        )
        if item.get("reason_code"):
            lines.extend(
                [
                    f"**Reason code:** `{item['reason_code']}`  ",
                    f"**Policy:** `{item['policy_id']}` / `{item['policy_version']}`  ",
                    f"**Policy digest:** `{item['policy_digest']}`  ",
                    f"**Inputs digest:** `{item['inputs_digest']}`",
                    "",
                ]
            )
        if item.get("basis"):
            lines.extend(
                [
                    "**Evidence basis / 证据依据：**",
                    *[
                        f"- {_citation_markdown(citation)}"
                        for citation in item["basis"]
                    ],
                    "",
                ]
            )
    if cards:
        for card in cards:
            lines.append(card_markdown(card))
    else:
        lines.append("No judgment context was supplied; no five-cell cards were generated.")
    lines.extend(["", "## Deterministic calculations", ""])
    financial = audit["financial_analysis"]
    if financial["metrics"]:
        lines.extend(["| Metric | Period | Value | Formula |", "|---|---|---:|---|"])
        for metric in financial["metrics"]:
            lines.append(
                f"| {metric['name']} | {metric['period']} | {_format_value(metric)} | {metric['formula']} |"
            )
    else:
        lines.append(financial["note"])
    for note in financial.get("screening_notes", []):
        lines.append(f"- **{note['status']}:** {note['text']}")
    auxiliary = audit.get("auxiliary_validation", {})
    lines.extend(
        [
            "",
            "## Optional auxiliary source validation / 可选辅助数据源校验",
            "",
            f"**Status / 状态：** `{auxiliary.get('status', 'disabled')}` / {auxiliary.get('status_zh', '未启用')}  ",
            auxiliary.get("summary", ""),
            auxiliary.get("summary_zh", ""),
            f"**Available / 可用：** {', '.join(auxiliary.get('available_source_ids', [])) or 'none'}  ",
            f"**Selected / 已选：** {', '.join(auxiliary.get('selected_source_ids', [])) or 'none'}  ",
            f"**Ignored / 已忽略：** {', '.join(auxiliary.get('ignored_source_ids', [])) or 'none'}",
            "",
        ]
    )
    for item in auxiliary.get("checks", []):
        lines.append(
            f"- **{item.get('label', item.get('fact_id'))} / "
            f"{item.get('label_zh', item.get('fact_id'))}:** "
            f"{_format_auxiliary_value(item)} · `{item.get('status')}` · "
            f"{_citation_markdown(item['source'])}"
        )
        if item.get("semantic_mismatches"):
            fields = ", ".join(
                mismatch["field"] for mismatch in item["semantic_mismatches"]
            )
            lines.append(f"  - Semantic mismatch / 口径不一致: {fields}")
    cash_context = audit.get("cash_conversion_context", {})
    lines.extend(
        [
            "",
            "## Optional cash-conversion context / 可选现金转换辅助信息",
            "",
            f"**Status / 状态：** `{cash_context.get('status', 'disabled')}` / {cash_context.get('status_zh', '未启用')}  ",
            cash_context.get("summary", ""),
            cash_context.get("summary_zh", ""),
            f"**Polarity policy / 符号策略：** `{cash_context.get('polarity_policy_version', 'n/a')}` / `{cash_context.get('polarity_policy_digest', 'n/a')}`",
            "",
        ]
    )
    if cash_context.get("items"):
        lines.extend(
            [
                "| Driver / 驱动项 | Period / 期间 | Raw XBRL / XBRL 原值 | Cash effect / 现金影响 | Direction / 方向 |",
                "|---|---|---:|---:|---|",
            ]
        )
        for item in cash_context["items"]:
            lines.append(
                f"| {item['label']} / {item['label_zh']} | {item['period']} | "
                f"{_money_like(item['reported_value'], item['currency'])} | "
                f"{_money_like(item['normalized_cash_effect'], item['currency'])} | "
                f"{item['effect']} / {item['effect_zh']} |"
            )
        lines.append("")
        for total in cash_context.get("totals_by_period", []):
            lines.append(
                f"- **{total['period']} selected-driver net effect / 所选驱动项净影响：** "
                f"{_money_like(total['net_effect'], audit['financial_analysis']['currency'])}"
            )
    lines.extend(
        [
            "",
            "## Candidate-retrieval coverage",
            "",
            "| Layer | Passages found | Review-ready | Partial | Gaps |",
            "|---|---:|---:|---:|---:|",
            f"| Finance retrieval | {finance_coverage['covered_dimensions']}/{finance_coverage['total_dimensions']} | {finance_coverage['review_ready']} | {finance_coverage['partial']} | {finance_coverage['gap']} |",
            f"| Adoption retrieval | {adoption_coverage['covered_dimensions']}/{adoption_coverage['total_dimensions']} | {adoption_coverage['review_ready']} | {adoption_coverage['partial']} | {adoption_coverage['gap']} |",
            "",
            "Retrieval coverage means candidate passages were found. It does not mean the dimension is implemented, validated, or low risk.",
            "",
        ]
    )
    lines.extend(
        _markdown_results("Financial and bankability retrieval", audit["finance_evidence"])
    )
    lines.extend(
        _markdown_results("Commercial adoption retrieval", audit["adoption_risk_evidence"])
    )
    lines.extend(["## Sources", ""])
    for source in audit["sources"]:
        lines.append(
            f"- [{source['title']}]({source['url']}) — {source['publisher']}; "
            f"role `{source['role']}`; published {source['published'] or 'undated'}; "
            f"SHA-256 `{source['sha256']}`"
        )
    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- Citation integrity: `{'passed' if audit['validation']['passed'] else 'failed'}`",
            f"- Traceable citations checked: {audit['validation']['citation_count']}",
            f"- Locked-framework coverage: {audit['judgment_layer']['framework_coverage']['locked']}/{audit['judgment_layer']['framework_coverage']['implemented']}",
            "- Automated investment, credit, or aggregate risk ratings: 0",
            "- Structured stage outputs are stored; hidden chain-of-thought is not stored.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _status_badge(status: str, label: str | None = None) -> str:
    label = label or status.replace("_", " ")
    return f'<span class="badge {html.escape(status)}">{html.escape(label)}</span>'


def _facts_html(facts: list[dict[str, Any]]) -> str:
    rows = []
    for fact in facts:
        citations = " · ".join(_citation_html(item) for item in fact["citations"])
        selection = fact.get("selection")
        selection_html = ""
        scope = fact.get("statement_scope")
        scope_html = (
            "<p class='meta'>Statement scope / 报表口径: <code>"
            + html.escape(scope["operations"])
            + "</code> · <code>"
            + html.escape(scope["attribution"])
            + "</code></p>"
            if scope
            else ""
        )
        if selection:
            alternatives = selection.get("excluded_candidates") or []
            excluded = ", ".join(
                f"{item['concept']}={item['value']:,.4g} {item['unit']}"
                for item in alternatives
            )
            selection_html = (
                "<details class='fact-selection'><summary>XBRL selection / XBRL 口径</summary>"
                f"<p><code>{html.escape(selection['concept'])}</code> · "
                f"{html.escape(selection['basis'])}"
                f"<span class='zh'>{html.escape(selection['basis_zh'])}</span></p>"
                + (
                    f"<p class='meta'>Excluded / 排除: {html.escape(excluded)}</p>"
                    if excluded
                    else ""
                )
                + "</details>"
            )
        rows.append(
            "<li><div><strong>"
            + html.escape(fact["name"])
            + "</strong><span class='fact-value'>"
            + html.escape(fact["display_value"])
            + "</span></div><div>"
            + _status_badge(fact["label"], FACT_LABELS[fact["label"]])
            + f" <span class='meta'>{citations}</span></div>{scope_html}{selection_html}</li>"
        )
    return "".join(rows)


def card_html(card: dict[str, Any]) -> str:
    cells = card["cells"]
    subindustry = cells["1_subindustry_position"]
    framework = cells["3_judgment_framework"]
    application = cells["4_framework_application"]
    gaps = cells["5_gaps_and_human_judgment"]["items"]
    subindustry_basis = " · ".join(_citation_html(item) for item in subindustry["basis"])
    app_basis = " · ".join(_citation_html(item) for item in application["basis"])
    observations = "".join(
        "<li><strong>"
        + html.escape(item["entity"])
        + "</strong> · "
        + html.escape(item["metric"])
        + " · "
        + html.escape(item["period"])
        + " · "
        + html.escape(item["display_value"])
        + " · "
        + _citation_html(item["citation"])
        + "</li>"
        for item in application["benchmark"]["observations"]
    )
    gap_items = "".join(
        f"<li><span class='gap-kind'>{html.escape(GAP_LABELS[item['kind']])}</span>"
        f"<span class='gap-text'>{html.escape(item['text'])}"
        f"<span class='zh'>{html.escape(item['text_zh'])}</span></span></li>"
        for item in gaps
    )
    return f"""
<article class="dimension-card">
  <header class="dimension-head"><div><span class="kicker">Single-dimension evidence card / 单维度证据审计卡</span>
    <h2>{html.escape(card["dimension"])}<span class="title-zh">{html.escape(card["dimension_zh"])}</span></h2><p>{html.escape(card["company"])}</p></div>
    {_status_badge(card["signal"], SIGNAL_LABELS[card["signal"]])}</header>
  <section class="cell"><div class="cell-no">01</div><div><h3>Subindustry position / 子行业定位</h3>
    <p><strong>{html.escape(subindustry["name"])}</strong> · {html.escape(subindustry["value_chain_position"])}</p>
    <p class="zh"><strong>{html.escape(subindustry["name_zh"])}</strong> · {html.escape(subindustry["value_chain_position_zh"])}</p>
    <p>{html.escape(subindustry["summary"])}<span class="zh">{html.escape(subindustry["summary_zh"])}</span></p><p class="meta">Basis / 依据：{subindustry_basis}</p></div></section>
  <section class="cell"><div class="cell-no">02</div><div><h3>Extracted facts / 抽取的事实</h3>
    <ul class="fact-list">{_facts_html(cells["2_extracted_facts"]["items"])}</ul></div></section>
  <section class="cell framework"><div class="cell-no">03</div><div><h3>Judgment framework / 判断框架 · locked / 锁定</h3>
    <blockquote>{html.escape(framework["text"])}</blockquote>
    <blockquote class="zh">{html.escape(framework["text_zh"])}</blockquote>
    <p class="methodology"><strong>Methodology / 方法论声明：</strong>{html.escape(framework["methodology"])} / {html.escape(framework["methodology_zh"])}<br>
    <strong>Basis / 方法论依据：</strong>{html.escape(framework["basis"])} / {html.escape(framework["basis_zh"])}</p></div></section>
  <section class="cell"><div class="cell-no">04</div><div><h3>Position after applying the framework / 应用框架后的定位</h3>
    <p>{_status_badge(application["signal"], SIGNAL_LABELS[application["signal"]])} <strong>{html.escape(application["path"])}</strong><span class="zh">{html.escape(application["path_zh"])}</span></p>
    <p class="signal-note">{html.escape(card["signal_meaning"])}<span class="zh">{html.escape(card["signal_meaning_zh"])}</span></p>
    <p>{html.escape(application["summary"])}<span class="zh">{html.escape(application["summary_zh"])}</span></p><p class="meta">Basis / 依据：{app_basis}</p>
    <details><summary>Comparator evidence and boundary / 对标证据与边界</summary><p>{html.escape(application["benchmark"]["scope"])}<span class="zh">{html.escape(application["benchmark"]["scope_zh"])}</span></p>
      <ul>{observations}</ul><p class="meta">Limitation / 对标限制：{html.escape(" ".join(application["benchmark"]["limitations"]))}<span class="zh">{html.escape(" ".join(application["benchmark"]["limitations_zh"]))}</span></p></details>
  </div></section>
  <section class="cell gaps"><div class="cell-no">05</div><div><h3>Gaps and required human judgment / 缺口与必须人工判断项</h3>
    <ul>{gap_items}</ul></div></section>
  <footer>{html.escape(card["disclaimer"])}<span class="zh">{html.escape(card["disclaimer_zh"])}</span></footer>
</article>"""


def _html_results(title: str, results: list[dict[str, Any]]) -> str:
    cards = []
    for result in results:
        candidates = (
            "".join(
                f"<li><a href='{html.escape(item['source_url'])}'>{html.escape(item['source_title'])}</a> "
                f"<span class='meta'>{html.escape(item['locator'])} · relevance {item['relevance']:.1f}</span>"
                f"<blockquote>{html.escape(item['excerpt'])}</blockquote></li>"
                for item in result["candidates"]
            )
            or "<li>No passage cleared the retrieval threshold.</li>"
        )
        cards.append(
            f"<details class='retrieval'><summary>{html.escape(result['name'])} {_status_badge(result['status'])}</summary>"
            f"<p>{html.escape(result['review_reason'])}</p><ol>{candidates}</ol></details>"
        )
    return f"<section><h2>{html.escape(title)}</h2><p class='meta'>Candidate retrieval only; not validated judgment.</p>{''.join(cards)}</section>"


STYLE = """
:root{--ink:#14211b;--muted:#627067;--paper:#f4f1e8;--panel:#fffdf7;--green:#176746;--amber:#9a6714;--red:#a33d33;--line:#d6d1c3;--deep:#17382c}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.58 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1120px;min-width:0;margin:auto;padding:52px 24px 84px;overflow-x:clip}h1{font:700 clamp(36px,6vw,64px)/1.02 Georgia,serif;margin:.15em 0;max-width:900px}.back-link{display:inline-block;margin-bottom:18px;color:var(--green);font-weight:800}
h2{font:700 30px/1.15 Georgia,serif;margin:50px 0 18px}h3{margin:0 0 8px;font-size:17px}a{color:var(--green)}
.eyebrow,.kicker{letter-spacing:.14em;text-transform:uppercase;color:var(--green);font-weight:800;font-size:12px}.lede{font-size:18px;color:var(--muted);max-width:800px}
.notice{border-left:4px solid var(--amber);background:#fff8e7;padding:15px 18px;margin:26px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:17px}.stat strong{display:block;font:700 31px Georgia,serif}
.badge{display:inline-block;border-radius:999px;padding:3px 9px;background:#e7e3d8;color:var(--muted);font-size:12px;white-space:nowrap}
.badge.green,.badge.validated_end_to_end,.badge.fact,.badge.calculation,.badge.matched,.badge.passed,.badge.cash_source{background:#dceee4;color:var(--green)}.badge.amber,.badge.partial,.badge.warning,.badge.context{background:#f5e8c9;color:#8a580f}
.badge.red,.badge.gap,.badge.cash_use,.badge.invalid,.badge.mismatch{background:#f1d9d5;color:var(--red)}.meta{font-size:13px;color:var(--muted)}table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}
th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#ece8dd}.dimension-card{margin:28px 0 42px;border:1px solid var(--line);background:var(--panel);box-shadow:0 16px 45px rgba(28,38,31,.07)}
.dimension-head{display:flex;justify-content:space-between;gap:20px;padding:26px 28px;border-bottom:1px solid var(--line);align-items:flex-start}.dimension-head h2{margin:6px 0 2px}.dimension-head p{margin:0;color:var(--muted)}
.cell{display:grid;grid-template-columns:52px 1fr;gap:18px;padding:24px 28px;border-bottom:1px solid var(--line)}.cell>div{min-width:0}.cell-no{font:700 22px Georgia,serif;color:#a5aa9e}.framework{background:var(--deep);color:#fff}
.framework .cell-no,.framework .meta{color:#9fc1ae}.framework blockquote{font:italic 19px/1.55 Georgia,serif;margin:10px 0;color:#eef7f1}.framework blockquote.zh{font-style:normal}.methodology{font-weight:700;color:#b6ddc8}.fact-list{list-style:none;padding:0;margin:0}.fact-list li{padding:10px 0;border-bottom:1px solid #ece7db}
.fact-list li>div:first-child{display:flex;justify-content:space-between;gap:18px}.fact-value{font-variant-numeric:tabular-nums;font-weight:700}.gaps{background:#fffaf0}.gaps li{margin:8px 0}.gap-kind{display:inline-block;min-width:130px;color:var(--amber);font-weight:800;text-transform:uppercase;font-size:11px;letter-spacing:.08em}
.dimension-card footer{padding:15px 28px;background:#eee9dc;color:var(--muted);font-weight:700}.zh,.title-zh{display:block}.title-zh{font:600 .58em/1.35 system-ui,-apple-system,Segoe UI,sans-serif;margin-top:5px;color:var(--muted)}.framework .title-zh{color:#b6ddc8}.signal-note{padding:10px 12px;background:#f2efe6;border-left:3px solid var(--amber)}.gap-text{display:block}.retrieval{background:var(--panel);border:1px solid var(--line);padding:14px 17px;margin:10px 0}.retrieval summary{cursor:pointer;font-weight:700}
.not-applicable{margin:24px 0;padding:20px 22px;border:1px solid var(--line);border-left:5px solid var(--muted);background:var(--panel)}.not-applicable h3{margin:0 0 8px}
blockquote{border-left:3px solid var(--line);padding-left:12px;color:var(--muted)}details summary{cursor:pointer;color:var(--green);font-weight:700}
section,details,li,blockquote{min-width:0}a,code,blockquote,.retrieval li{overflow-wrap:anywhere;word-break:break-word}
a:focus-visible,summary:focus-visible{outline:3px solid #2a7b59;outline-offset:3px}
@media(max-width:760px){.stats{grid-template-columns:1fr 1fr}.cell{grid-template-columns:28px 1fr;gap:10px;padding:20px 14px}.cell-no{font-size:18px}.framework blockquote{font-size:16px;line-height:1.48}.dimension-head{padding:22px 16px}.fact-list li>div:first-child{display:block}table{display:block;max-width:100%;overflow-x:auto;font-size:12px}}
"""


def html_report(audit: dict[str, Any], only_card: dict[str, Any] | None = None) -> str:
    subject = audit["subject"]
    identity = audit.get("identity_resolution", {})
    display_name = identity.get("display_name") or subject["organization"]
    back_href = "../../index.html" if only_card else "../index.html"
    capability = audit["capability_matrix"]
    summary = capability["summary"]
    cards = [only_card] if only_card else audit.get("judgment_layer", {}).get("cards", [])
    not_applicable = (
        []
        if only_card
        else [
            item
            for item in audit.get("judgment_layer", {}).get("dimension_outcomes", [])
            if item.get("status") in {"not_applicable", "not_yet_applicable"}
        ]
    )
    not_applicable_markup = "".join(
        "<article class='not-applicable'><h3>"
        + html.escape(item["dimension_id"])
        + (
            " · Not yet applicable / 暂不适用</h3><p>"
            if item.get("status") == "not_yet_applicable"
            else " · Not applicable / 不适用</h3><p>"
        )
        + html.escape(item["reason"])
        + "<span class='zh'>"
        + html.escape(item["reason_zh"])
        + "</span></p>"
        + (
            "<p class='meta'><strong>Reason code:</strong> "
            + html.escape(str(item["reason_code"]))
            + " · <strong>Policy:</strong> "
            + html.escape(str(item["policy_id"]))
            + " / "
            + html.escape(str(item["policy_version"]))
            + "<br><strong>Policy digest:</strong> "
            + html.escape(str(item["policy_digest"]))
            + "<br><strong>Inputs digest:</strong> "
            + html.escape(str(item["inputs_digest"]))
            + "</p>"
            if item.get("reason_code")
            else ""
        )
        + (
            "<h4>Evidence basis / 证据依据</h4><ul>"
            + "".join(
                "<li>" + _citation_html(citation) + "</li>"
                for citation in item["basis"]
            )
            + "</ul>"
            if item.get("basis")
            else ""
        )
        + "</article>"
        for item in not_applicable
    )
    card_markup = (
        not_applicable_markup
        + ("".join(card_html(card) for card in cards) or "")
        or "<p>No judgment context supplied.</p>"
    )
    capability_rows = "".join(
        f"<tr><td>{html.escape(item['name'])}</td><td>{_status_badge(item['status'])}</td>"
        f"<td>{html.escape(item['judgment_card'].replace('_', ' '))}</td><td>{html.escape(item['claim_boundary'])}</td></tr>"
        for item in capability["finance"]
    )
    metric_rows = "".join(
        f"<tr><td>{html.escape(item['name'])}</td><td>{html.escape(item['period'])}</td>"
        f"<td>{html.escape(_format_value(item))}</td><td>{html.escape(item['formula'])}</td></tr>"
        for item in audit["financial_analysis"]["metrics"]
    )
    source_items = "".join(
        f"<li><a href='{html.escape(item['url'])}'>{html.escape(item['title'])}</a> · "
        f"{html.escape(item['publisher'])} · role {html.escape(item['role'])}</li>"
        for item in audit["sources"]
    )
    identity_aliases = "".join(
        "<li><strong>"
        + html.escape(str(item.get("name", "")))
        + "</strong><span class='zh'>"
        + html.escape(str(item.get("name_zh", "")))
        + "</span><span class='meta'>former name through / 原名称截至 "
        + html.escape(str(item.get("effective_until", "")))
        + "</span></li>"
        for item in identity.get("aliases", [])
    )
    identity_bindings = "".join(
        "<li><code>"
        + html.escape(str(item.get("source_id", "")))
        + "</code> · "
        + html.escape(str(item.get("publisher", "")))
        + " · <span class='meta'>matched by entity_id / 按实体标识匹配</span></li>"
        for item in identity.get("source_bindings", [])
    )
    identity_markup = (
        "<section class='identity' data-identity-status='"
        + html.escape(str(identity.get("status", "legacy")))
        + "'><h2>Entity identity / 实体身份</h2><p>"
        + _status_badge(
            str(identity.get("status", "legacy")),
            f"{identity.get('status', 'legacy')} / {identity.get('status_zh', '未提供')}",
        )
        + " <strong>"
        + html.escape(str(identity.get("entity_id") or "stable id not supplied"))
        + "</strong></p><p>"
        + html.escape(str(identity.get("summary", "")))
        + "<span class='zh'>"
        + html.escape(str(identity.get("summary_zh", "")))
        + "</span></p>"
        + ("<h3>Name history / 名称历史</h3><ul>" + identity_aliases + "</ul>" if identity_aliases else "")
        + ("<details><summary>Source bindings / 来源绑定</summary><ul>" + identity_bindings + "</ul></details>" if identity_bindings else "")
        + "</section>"
    )
    auxiliary = audit.get("auxiliary_validation", {})
    auxiliary_rows = "".join(
        "<tr data-auxiliary-status='"
        + html.escape(str(item.get("status", "")))
        + "'><td>"
        + html.escape(str(item.get("label", item.get("fact_id", ""))))
        + "<span class='zh'>"
        + html.escape(str(item.get("label_zh", item.get("fact_id", ""))))
        + "</span></td><td>"
        + html.escape(item.get("period", ""))
        + "</td><td>"
        + html.escape(_format_auxiliary_value(item))
        + "</td><td>"
        + _status_badge(str(item.get("status", "")), str(item.get("status_zh", "")))
        + "</td><td>"
        + _citation_html(item["source"])
        + "</td></tr>"
        for item in auxiliary.get("checks", [])
    )
    auxiliary_markup = (
        "<section class='auxiliary' data-auxiliary-enabled='"
        + str(bool(auxiliary.get("enabled_by_user"))).lower()
        + "'><h2>Optional auxiliary source validation / 可选辅助数据源校验</h2>"
        + "<p>"
        + _status_badge(
            str(auxiliary.get("status", "disabled")),
            f"{auxiliary.get('status', 'disabled')} / {auxiliary.get('status_zh', '未启用')}",
        )
        + " "
        + html.escape(auxiliary.get("summary", ""))
        + "<span class='zh'>"
        + html.escape(auxiliary.get("summary_zh", ""))
        + "</span></p><p class='meta'>Available / 可用: "
        + html.escape(", ".join(auxiliary.get("available_source_ids", [])) or "none")
        + "<br>Selected / 已选: "
        + html.escape(", ".join(auxiliary.get("selected_source_ids", [])) or "none")
        + "<br>Ignored / 已忽略: "
        + html.escape(", ".join(auxiliary.get("ignored_source_ids", [])) or "none")
        + "</p>"
        + (
            "<table><thead><tr><th>Fact / 事实</th><th>Period / 期间</th>"
            "<th>Value / 数值</th><th>Status / 状态</th><th>Source / 来源</th>"
            "</tr></thead><tbody>" + auxiliary_rows + "</tbody></table>"
            if auxiliary_rows
            else ""
        )
        + "</section>"
    )
    cash_context = audit.get("cash_conversion_context", {})
    cash_context_rows = "".join(
        "<tr><td>"
        + html.escape(item["label"])
        + "<span class='zh' lang='zh-CN'>"
        + html.escape(item["label_zh"])
        + "</span></td><td>"
        + html.escape(item["period"])
        + "</td><td>"
        + html.escape(_money_like(item["reported_value"], item["currency"]))
        + "</td><td><strong>"
        + html.escape(_money_like(item["normalized_cash_effect"], item["currency"]))
        + "</strong></td><td>"
        + _status_badge(item["effect"], f"{item['effect']} / {item['effect_zh']}")
        + "</td><td>"
        + _citation_html(item["source"])
        + "<span class='zh' lang='zh-CN'>"
        + html.escape(item["reason_zh"])
        + "</span></td></tr>"
        for item in cash_context.get("items", [])
    )
    cash_context_totals = "".join(
        "<li><strong>"
        + html.escape(item["period"])
        + "</strong> · selected-driver net effect / 所选驱动项净影响: "
        + html.escape(
            _money_like(item["net_effect"], audit["financial_analysis"]["currency"])
        )
        + "</li>"
        for item in cash_context.get("totals_by_period", [])
    )
    cash_context_markup = (
        "<section id='cash-conversion-context' class='cash-context' data-cash-context-enabled='"
        + str(bool(cash_context.get("enabled_by_user"))).lower()
        + "'><h2>Optional cash-conversion context / 可选现金转换辅助信息</h2><p>"
        + _status_badge(
            str(cash_context.get("status", "disabled")),
            f"{cash_context.get('status', 'disabled')} / {cash_context.get('status_zh', '未启用')}",
        )
        + " "
        + html.escape(str(cash_context.get("summary", "")))
        + "<span class='zh' lang='zh-CN'>"
        + html.escape(str(cash_context.get("summary_zh", "")))
        + "</span></p><p class='meta'>Polarity policy / 符号策略: <code>"
        + html.escape(str(cash_context.get("polarity_policy_version", "n/a")))
        + "</code> · <code>"
        + html.escape(str(cash_context.get("polarity_policy_digest", "n/a")))
        + "</code></p>"
        + (
            "<table><thead><tr><th>Driver / 驱动项</th><th>Period / 期间</th>"
            "<th>Raw XBRL / XBRL 原值</th><th>Cash effect / 现金影响</th>"
            "<th>Direction / 方向</th><th>Basis / 依据</th></tr></thead><tbody>"
            + cash_context_rows
            + "</tbody></table><ul>"
            + cash_context_totals
            + "</ul>"
            if cash_context_rows
            else ""
        )
        + "</section>"
    )
    detail = (
        ""
        if only_card
        else (
            _html_results("Financial retrieval detail", audit["finance_evidence"])
            + _html_results("Adoption-risk retrieval detail", audit["adoption_risk_evidence"])
        )
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(display_name)} — CleanTech Finance Evidence Audit</title><style>{STYLE}</style></head><body><main>
<a class="back-link" href="{back_href}">← Ten-loop index / 返回十轮总览</a><div class="eyebrow">Evidence-first clean energy finance</div><h1>{html.escape(display_name)}</h1>
<p class="lede"><strong>{html.escape(subject["technology"])}</strong><br>Two validated financial dimensions, locked judgment frameworks, and explicit human-review gaps.</p>
<div class="notice"><strong>Truth boundary.</strong> {html.escape(capability["public_claim"])}</div>
<div class="stats"><div class="stat"><strong>{summary["validated_finance_dimensions"]}/{summary["total_finance_dimensions"]}</strong>finance dimensions validated</div>
<div class="stat"><strong>{len(audit.get("judgment_layer", {}).get("cards", []))}</strong>five-cell cards generated</div>
<div class="stat"><strong>0/{summary["total_adoption_dimensions"]}</strong>adoption dimensions validated</div>
<div class="stat"><strong>{audit["validation"]["citation_count"]}</strong>citations checked</div></div>
{identity_markup}
{"" if only_card else "<section><h2>Capability status</h2><table><thead><tr><th>Dimension</th><th>Status</th><th>Card</th><th>Claim boundary</th></tr></thead><tbody>" + capability_rows + "</tbody></table></section>"}
<section><h2>Single-dimension evidence cards</h2>{card_markup}</section>
{"" if only_card else "<section><h2>Deterministic calculations</h2><table><thead><tr><th>Metric</th><th>Period</th><th>Value</th><th>Formula</th></tr></thead><tbody>" + metric_rows + "</tbody></table></section>"}
{"" if only_card else auxiliary_markup}
{"" if only_card else cash_context_markup}
{detail}<section><h2>Sources</h2><ul>{source_items}</ul></section>
<section><h2>Validation</h2><p>Citation integrity: <strong>{"passed" if audit["validation"]["passed"] else "failed"}</strong>. Automated investment, credit, or aggregate risk ratings: <strong>0</strong>.</p>
<p class="meta">Signals are evidence signals and always remain attached to their basis and gaps. Structured stage outputs are stored; hidden chain-of-thought is not.</p></section>
</main></body></html>"""


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts(audit: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cards_dir = output / "cards"
    cards_dir.mkdir(exist_ok=True)
    paths: dict[str, Path] = {
        "json": output / "audit.json",
        "markdown": output / "report.md",
        "html": output / "report.html",
        "dimension_cards_json": output / "dimension_cards.json",
        "evidence_csv": output / "evidence.csv",
        "review_queue_csv": output / "review_queue.csv",
        "financial_metrics_csv": output / "financial_metrics.csv",
    }
    paths["json"].write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(markdown_report(audit), encoding="utf-8")
    paths["html"].write_text(html_report(audit), encoding="utf-8")
    cards = audit.get("judgment_layer", {}).get("cards", [])
    paths["dimension_cards_json"].write_text(
        json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for card in cards:
        identifier = card["dimension_id"]
        markdown_path = cards_dir / f"{identifier}.md"
        html_path = cards_dir / f"{identifier}.html"
        markdown_path.write_text(card_markdown(card), encoding="utf-8")
        html_path.write_text(html_report(audit, only_card=card), encoding="utf-8")
        paths[f"card_{identifier}_markdown"] = markdown_path
        paths[f"card_{identifier}_html"] = html_path

    evidence_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for section, results in (
        ("finance", audit["finance_evidence"]),
        ("adoption", audit["adoption_risk_evidence"]),
    ):
        for result in results:
            review_rows.append(
                {
                    "section": section,
                    "dimension_id": result["id"],
                    "dimension": result["name"],
                    "status": result["status"],
                    "reason": result["review_reason"],
                    "questions": " | ".join(result["review_questions"]),
                }
            )
            for candidate in result["candidates"]:
                evidence_rows.append(
                    {
                        "section": section,
                        "dimension_id": result["id"],
                        "dimension": result["name"],
                        "source_id": candidate["source_id"],
                        "source_title": candidate["source_title"],
                        "source_url": candidate["source_url"],
                        "locator": candidate["locator"],
                        "relevance": candidate["relevance"],
                        "directness": candidate["directness"],
                        "source_quality": candidate["source_quality"],
                        "freshness": candidate["freshness"],
                        "matched_cues": " | ".join(candidate["matched_cues"]),
                        "excerpt": candidate["excerpt"],
                    }
                )
    for card in cards:
        for gap in card["cells"]["5_gaps_and_human_judgment"]["items"]:
            review_rows.append(
                {
                    "section": "judgment_card",
                    "dimension_id": card["dimension_id"],
                    "dimension": card["dimension"],
                    "status": gap["kind"],
                    "reason": gap["text"],
                    "questions": "",
                }
            )
    _write_csv(
        paths["evidence_csv"],
        evidence_rows,
        [
            "section",
            "dimension_id",
            "dimension",
            "source_id",
            "source_title",
            "source_url",
            "locator",
            "relevance",
            "directness",
            "source_quality",
            "freshness",
            "matched_cues",
            "excerpt",
        ],
    )
    _write_csv(
        paths["review_queue_csv"],
        review_rows,
        ["section", "dimension_id", "dimension", "status", "reason", "questions"],
    )
    metric_rows = [
        {
            "id": item["id"],
            "name": item["name"],
            "period": item["period"],
            "value": item["value"],
            "unit": item["unit"],
            "signal": item["signal"],
            "formula": item["formula"],
            "inputs": json.dumps(item["inputs"], ensure_ascii=False),
        }
        for item in audit["financial_analysis"]["metrics"]
    ]
    _write_csv(
        paths["financial_metrics_csv"],
        metric_rows,
        ["id", "name", "period", "value", "unit", "signal", "formula", "inputs"],
    )
    return {key: str(path.resolve()) for key, path in paths.items()}
