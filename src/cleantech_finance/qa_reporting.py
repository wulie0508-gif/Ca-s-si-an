"""Portable bilingual reports for the QA diagnostic layer."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .qa_diagnostics import validate_qa_case


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _display(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value if value is not None else "")


def _markdown_ref(ref: dict[str, Any]) -> str:
    target = str(ref.get("url_or_source_id") or "").strip()
    location = f"{ref['source_id']} @ {ref['locator']}"
    if target.lower().startswith(("https://", "http://")):
        location = f"[{location}]({target})"
    elif target:
        location += f" [{target}]"
    return f"{location}: {ref['quote']}"


def _html_ref(ref: dict[str, Any]) -> str:
    target = str(ref.get("url_or_source_id") or "").strip()
    location = f"{_esc(ref['source_id'])} @ {_esc(ref['locator'])}"
    if target.lower().startswith(("https://", "http://")):
        location = (
            f'<a href="{html.escape(target, quote=True)}" rel="noopener noreferrer">{location}</a>'
        )
    elif target:
        location += f" [{_esc(target)}]"
    return f"{location}: {_esc(ref['quote'])}"


def qa_markdown(case: dict[str, Any], result: dict[str, Any]) -> str:
    company = case.get("company", {})
    profile = result["profile"]
    lines = [
        f"# {company.get('legal_name', '')}｜QA diagnostic profile",
        "",
        "> 本报告用于企业进入诊断与分诊，不构成投资、信用、风险、ESG 或 ARL 评级。企业原话只能证明其作出过该陈述。",
        "",
        f"- Case: {case.get('case', {}).get('id', '')}",
        f"- QA status: {'complete' if result['qa']['complete'] else 'incomplete'}",
        f"- Traceability gate: {'passed' if profile['passed'] else 'failed'}",
        f"- Validation scope: {result.get('validation_scope', 'structural_traceability_only')}",
        (
            "- Delivery: independent human profile review passed for this immutable packet."
            if result.get("delivery_gate", {}).get("passed")
            else "- Delivery: independent human profile review is required before this packet can be counted or routed downstream."
        ),
        f"- Rule version: {result['rule_version']}",
        "",
        "## 画像卡 / Profile card",
        "",
        "| 字段 | 状态 | 类型 | 候选值 | 出处 |",
        "|---|---|---|---|---|",
    ]
    for field in profile["fields"]:
        refs = "；".join(_markdown_ref(ref) for ref in field["evidence_refs"]) or "—"
        value = field["value"] if field["status"] == "supported" else field["candidate_value"]
        lines.append(
            f"| {field['label_zh']} / {field['label']} | {field['status']} | "
            f"{field.get('conclusion_type') or '—'} | {_display(value) or '—'} | {refs} |"
        )
    lines.extend(
        [
            "",
            "## 分诊 / Triage",
            "",
            f"- Eligibility: {'eligible' if result['triage']['eligible'] else 'blocked'}",
            "",
        ]
    )
    if not result["triage"]["eligible"]:
        lines.append(
            "- 上游验证失败，所有分诊均已关闭。 / Upstream validation failed; all routes are blocked."
        )
        lines.append("")
    for route in result["triage"]["routes"]:
        if not route["selected"]:
            continue
        lines.append(f"### {route['line'].title()}（仅留桩 / Stub only）")
        lines.append("")
        for reason in route["reasons"]:
            lines.append(f"- {reason['text_zh']} / {reason['text']} [{reason['profile_field']}]")
            refs = "；".join(_markdown_ref(ref) for ref in reason["evidence_refs"])
            lines.append(f"  - Evidence / 出处: {refs or '—'}")
        lines.append("")
    if not any(route["selected"] for route in result["triage"]["routes"]):
        lines.append(
            "- 暂无可追溯画像可用于分诊。 / No traceable profile field is available for triage."
        )
        lines.append("")
    lines.extend(["## 缺口队列 / Gap queue", ""])
    if profile["gap_queue"]:
        for gap in profile["gap_queue"]:
            reasons = "；".join(item["text_zh"] for item in gap["reasons"])
            lines.append(f"- {gap['field']}: {reasons}")
    else:
        lines.append("- 无画像出处缺口。 / No profile traceability gaps.")
    lines.extend(["", "## 下一题 / Next question", ""])
    next_question = result["qa"]["next_question"]
    if next_question:
        lines.extend(
            [
                f"- ID: {next_question['id']}",
                f"- {next_question['text_zh']}",
                f"- {next_question['text']}",
                f"- Trigger: {next_question['reason_code']}",
            ]
        )
    else:
        lines.append("- QA 问题图已走完。 / The QA question graph is complete.")
    lines.extend(
        [
            "",
            "## 能力边界 / Capability boundary",
            "",
            "- Expert、Map、Radar 仅输出分诊指向，当前没有执行任何下游 Agent。",
            "- 画像出处校验只证明存在精确引用，不证明企业陈述为真。",
            "- 未提供财务 Manifest 时不得生成财务证据卡；现有两项财务内核保持独立。",
        ]
    )
    return "\n".join(lines) + "\n"


def qa_html(case: dict[str, Any], result: dict[str, Any]) -> str:
    company = case.get("company", {})
    rows = []
    for field in result["profile"]["fields"]:
        refs = "<br>".join(_html_ref(ref) for ref in field["evidence_refs"]) or "—"
        value = field["value"] if field["status"] == "supported" else field["candidate_value"]
        rows.append(
            "<tr>"
            f"<td>{_esc(field['label_zh'])}<br><span>{_esc(field['label'])}</span></td>"
            f"<td class='{_esc(field['status'])}'>{_esc(field['status'])}</td>"
            f"<td>{_esc(field.get('conclusion_type') or '—')}</td>"
            f"<td>{_esc(_display(value) or '—')}</td>"
            f"<td>{refs}</td>"
            "</tr>"
        )
    routes = []
    for route in result["triage"]["routes"]:
        if not route["selected"]:
            continue
        items = "".join(
            "<li>"
            f"{_esc(reason['text_zh'])}<br><span>{_esc(reason['text'])}</span>"
            "<br><small>Evidence / 出处: "
            + ("；".join(_html_ref(ref) for ref in reason["evidence_refs"]) or "—")
            + "</small></li>"
            for reason in route["reasons"]
        )
        routes.append(
            f"<article><h3>{_esc(route['line'].title())}</h3><p>Stub only / 仅留桩</p><ul>{items}</ul></article>"
        )
    gaps = (
        "".join(
            f"<li><strong>{_esc(gap['field'])}</strong>: "
            + "；".join(_esc(reason["text_zh"]) for reason in gap["reasons"])
            + "</li>"
            for gap in result["profile"]["gap_queue"]
        )
        or "<li>无画像出处缺口 / No profile traceability gaps.</li>"
    )
    question = result["qa"]["next_question"]
    next_block = (
        f"<p><strong>{_esc(question['id'])}</strong></p><p>{_esc(question['text_zh'])}</p><p>{_esc(question['text'])}</p>"
        if question
        else "<p>QA 问题图已走完 / The QA question graph is complete.</p>"
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(company.get("legal_name"))}｜QA diagnostic</title><style>
:root{{--ink:#172235;--muted:#62718a;--line:#dbe3ee;--paper:#f4f7fb;--blue:#155eef;--green:#067647;--red:#b42318}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}header{{padding:30px max(22px,calc((100vw - 1180px)/2));background:#10243e;color:white}}header p{{color:#cfe0f7}}main{{max-width:1180px;margin:22px auto;padding:0 22px 44px}}section,article{{background:white;border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}}.routes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}.routes article{{margin:0}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}}th{{background:#f7f9fc}}span{{color:var(--muted)}}.supported{{color:var(--green);font-weight:700}}.gap{{color:var(--red);font-weight:700}}code{{word-break:break-all}}@media(max-width:720px){{main{{padding:0 10px}}table{{display:block;overflow:auto}}}}</style></head><body><header><h1>{_esc(company.get("legal_name"))}</h1><p>QA 企业进入诊断与分诊｜Company-entry diagnostic and routing</p></header><main>
<section><p><strong>Traceability gate:</strong> {"passed" if result["profile"]["passed"] else "failed"} · <strong>QA:</strong> {"complete" if result["qa"]["complete"] else "incomplete"}</p><p><strong>Validation scope:</strong> {_esc(result.get("validation_scope", "structural_traceability_only"))}. {"该不可变产物已通过独立人工画像复核。" if result.get("delivery_gate", dict()).get("passed") else "独立人工画像复核通过前，本产物不能计入五家公司交付或供下游消费。"}</p><p>本产物不构成投资、信用、综合风险、ESG 或 ARL 评级；企业原话不等于已验证事实。</p></section>
<section><h2>画像卡 / Profile card</h2><table><thead><tr><th>字段</th><th>状态</th><th>类型</th><th>值</th><th>出处</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>
<section><h2>分诊 / Triage</h2><p><strong>Eligibility:</strong> {"eligible" if result["triage"]["eligible"] else "blocked"}</p>{"<p>上游验证失败，所有分诊均已关闭。 / Upstream validation failed; all routes are blocked.</p>" if not result["triage"]["eligible"] else ""}<div class="routes">{"".join(routes) or "<p>暂无可追溯画像可用于分诊。</p>"}</div></section>
<section><h2>缺口队列 / Gap queue</h2><ul>{gaps}</ul></section>
<section><h2>下一题 / Next question</h2>{next_block}</section>
</main></body></html>"""


def write_qa_artifacts(
    case: dict[str, Any],
    output_dir: str | Path,
    *,
    validation_result: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write the QA diagnostic packet without changing the input case."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = validation_result if validation_result is not None else validate_qa_case(case)
    paths = {
        "case_json": output / "qa_case.json",
        "validation_json": output / "qa_validation.json",
        "profile_json": output / "company_profile.json",
        "triage_json": output / "triage.json",
        "gap_queue_json": output / "gap_queue.json",
        "next_question_json": output / "next_question.json",
        "report_markdown": output / "qa_report.md",
        "report_html": output / "qa_report.html",
    }
    payloads = {
        "case_json": case,
        "validation_json": result,
        "profile_json": result["profile"],
        "triage_json": result["triage"],
        "gap_queue_json": result["profile"]["gap_queue"],
        "next_question_json": {
            "complete": result["qa"]["complete"],
            "next_question": result["qa"]["next_question"],
        },
    }
    for key, payload in payloads.items():
        paths[key].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    paths["report_markdown"].write_text(qa_markdown(case, result), encoding="utf-8")
    paths["report_html"].write_text(qa_html(case, result), encoding="utf-8")
    return {key: str(path.resolve()) for key, path in paths.items()}
