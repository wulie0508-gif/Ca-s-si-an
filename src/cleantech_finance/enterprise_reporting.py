"""Durable JSON, Markdown and HTML enterprise assessment reports."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .enterprise_store import AssessmentStore

MODULE_PREFIX = {
    "financial": "A",
    "interview": "B",
    "public": "C",
    "course": "D",
    "policy": "E",
}
DIMENSION_LABELS = {
    "financial_evidence_sufficiency": "财务证据充分度",
    "information_consistency": "信息一致性",
    "reviewed_negative_items": "经复核负面项",
    "data_completeness": "数据完整度",
}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _evidence_labels(evidence: list[dict[str, Any]]) -> dict[str, str]:
    counters: dict[str, int] = {}
    labels: dict[str, str] = {}
    for item in evidence:
        module = str((item.get("metadata") or {}).get("input_module") or "public")
        prefix = MODULE_PREFIX.get(module, "C")
        counters[prefix] = counters.get(prefix, 0) + 1
        labels[item["id"]] = f"{prefix}-{counters[prefix]}"
    return labels


def _traceable_conclusions(
    assessment: dict[str, Any],
    labels: dict[str, str],
) -> list[dict[str, Any]]:
    dimensions = assessment["dimensions"]
    finance_refs = [
        labels.get(identifier, identifier)
        for identifier in dimensions["financial_evidence_sufficiency"].get("evidence_ids", [])
    ]
    conflict_refs = [
        labels.get(identifier, identifier)
        for identifier in dimensions["information_consistency"].get("evidence_ids", [])
        if identifier
    ]
    negative_refs = [
        labels.get(identifier, identifier)
        for identifier in (
            dimensions["reviewed_negative_items"].get("verified_evidence_ids", [])
            + dimensions["reviewed_negative_items"].get("pending_evidence_ids", [])
        )
    ]
    completeness_refs = [
        labels.get(identifier, identifier)
        for identifier in dimensions["data_completeness"].get("evidence_ids", [])
    ]
    conclusions: list[dict[str, Any]] = []
    for reason in assessment["core_reasons"]:
        if "财务" in reason:
            refs = finance_refs
        elif "一致性" in reason or "冲突" in reason:
            refs = conflict_refs
        elif "负面" in reason:
            refs = negative_refs
        else:
            refs = completeness_refs
        conclusions.append(
            {
                "conclusion": reason,
                "evidence_refs": sorted(set(refs)),
                "gap_refs": (
                    []
                    if refs
                    else [gap["gap_id"] for gap in assessment["gaps"][:3]]
                ),
            }
        )
    return conclusions


def build_enterprise_report(
    store: AssessmentStore,
    assessment: dict[str, Any],
) -> dict[str, Any]:
    bundle = store.get_case_bundle(assessment["case_id"])
    labels = _evidence_labels(bundle["evidence"])
    evidence = [
        {
            **item,
            "report_ref": labels[item["id"]],
        }
        for item in bundle["evidence"]
    ]
    return {
        "schema_version": "1.0.0",
        "report_type": "enterprise_assessment_and_triage",
        "case": bundle["case"],
        "guardrails": assessment["guardrails"],
        "dimensions": assessment["dimensions"],
        "evidence": evidence,
        "gaps": assessment["gaps"],
        "matching": assessment["matching"],
        "conclusions": _traceable_conclusions(assessment, labels),
        "fixed_ending": {
            "recommendation": assessment["recommendation"],
            "core_reasons": assessment["core_reasons"],
            "human_confirmation": assessment["human_confirmation"],
            "if_entering": assessment["if_entering"],
        },
        "decision": assessment["decision"],
        "sidecar": assessment["sidecar"],
        "system_of_record": {
            "database": str(store.path.resolve()),
            "authority": "Company, Case and Metrics in this SQLite database",
            "rag_role": "citation cache/sidecar only",
        },
    }


def enterprise_report_markdown(report: dict[str, Any]) -> str:
    case = report["case"]
    company = case["company"]
    lines = [
        f"# {company['legal_name']}｜企业评估与分诊报告",
        "",
        f"- Case：`{case['id']}` / v{case['version']}",
        f"- 截止日：{case['as_of']}",
        f"- 阶段：{case['stage']}",
        f"- 决策流状态：`{report['decision']['status']}`（必须人工审批）",
        "",
        "## 四项独立判断维度",
        "",
        "> 不生成聚合总分；各维度不互相加权，不构成投资、信用或综合风险评级。",
        "",
    ]
    for identifier, dimension in report["dimensions"].items():
        lines.append(f"- **{DIMENSION_LABELS[identifier]}**：`{dimension['status']}`")
    lines.extend(["", "## 可追溯结论", ""])
    for item in report["conclusions"]:
        refs = item["evidence_refs"] or item["gap_refs"]
        lines.append(f"- {item['conclusion']} [依据: {', '.join(refs) or '无'}]")
    lines.extend(["", "## 证据台账", ""])
    if report["evidence"]:
        lines.append("| 编号 | 主张 | 来源与定位 | 等级 | 类型 | 复核 |")
        lines.append("|---|---|---|---|---|---|")
        for item in report["evidence"]:
            lines.append(
                f"| {item['report_ref']} | {item['claim']} | "
                f"{item['source']} · {item['locator']} | {item['source_level']} | "
                f"{item['type']} | {item['review_status']} |"
            )
    else:
        lines.append("无可入账证据；不得推测补全。")
    lines.extend(["", "## 缺口与补充任务", ""])
    for gap in report["gaps"]:
        lines.append(
            f"- `{gap['gap_id']}` [{gap['priority']}] {gap['missing']}："
            f"{gap['reason']} → {gap['route']}"
        )
    lines.extend(["", "## 课程与政策匹配", ""])
    for category, title in (("course", "课程"), ("policy", "政策")):
        result = report["matching"][category]
        lines.append(f"### {title}")
        lines.append("")
        if result["matches"]:
            for item in result["matches"]:
                tags = [
                    tag
                    for reason in item["rationale"]
                    for tag in reason["matched_tags"]
                ]
                lines.append(
                    f"- {item['title']}（规则匹配值 {item['match_score']}；"
                    f"命中：{', '.join(tags)}）"
                )
        else:
            lines.append(f"- {result.get('message') or '无高匹配。'}")
        lines.append("")
    ending = report["fixed_ending"]
    lines.extend(
        [
            "## 固定结尾｜供 Leader 点头",
            "",
            f"**建议：{ending['recommendation']}**",
            "",
            "核心理由：",
            "",
        ]
    )
    lines.extend(f"- {reason}" for reason in ending["core_reasons"])
    lines.extend(["", "待人工确认项：", ""])
    lines.extend(f"- {item}" for item in ending["human_confirmation"])
    lines.extend(["", "若进：", ""])
    lines.append(
        "- 推荐课程："
        + (
            "、".join(item["title"] for item in ending["if_entering"]["courses"])
            or "无高匹配"
        )
    )
    lines.append(
        "- 相关政策："
        + (
            "、".join(item["title"] for item in ending["if_entering"]["policies"])
            or "无高匹配"
        )
    )
    lines.append(
        "- 建议专家类型："
        + ("、".join(ending["if_entering"]["expert_types"]) or "由 Leader 指定")
    )
    lines.extend(
        [
            "",
            "---",
            "",
            "本报告是证据与缺口驱动的研究支持，不是自动决策，不是投资、信用、法律、工程或安全意见。",
        ]
    )
    return "\n".join(lines) + "\n"


def enterprise_report_html(report: dict[str, Any]) -> str:
    case = report["case"]
    company = case["company"]
    dimensions = "".join(
        f"""<article class="metric"><span>{_esc(DIMENSION_LABELS[key])}</span>
        <strong>{_esc(value['status'])}</strong><small>{_esc(key)}</small></article>"""
        for key, value in report["dimensions"].items()
    )
    evidence_rows = "".join(
        f"""<tr><td><b>{_esc(item['report_ref'])}</b></td><td>{_esc(item['claim'])}</td>
        <td>{_esc(item['source'])}<br><small>{_esc(item['locator'])}</small></td>
        <td>{_esc(item['source_level'])}</td><td>{_esc(item['type'])}</td>
        <td><span class="pill {_esc(item['review_status'])}">{_esc(item['review_status'])}</span></td></tr>"""
        for item in report["evidence"]
    ) or '<tr><td colspan="6">无可入账证据；系统未推测补全。</td></tr>'
    gap_cards = "".join(
        f"""<article class="gap"><header><b>{_esc(gap['gap_id'])}</b>
        <span>{_esc(gap['priority'])}</span></header><h3>{_esc(gap['missing'])}</h3>
        <p>{_esc(gap['reason'])}</p><small>路径 { _esc(gap['route']) } ·
        局部重算 { _esc(', '.join(gap['recompute_scope'])) }</small></article>"""
        for gap in report["gaps"]
    ) or "<p>当前没有结构化补充任务。</p>"
    conclusions = "".join(
        f"""<li>{_esc(item['conclusion'])}
        <code>依据: {_esc(', '.join(item['evidence_refs'] or item['gap_refs']) or '无')}</code></li>"""
        for item in report["conclusions"]
    )

    def match_cards(category: str) -> str:
        result = report["matching"][category]
        if not result["matches"]:
            return f"<p class='empty'>{_esc(result.get('message') or '无高匹配。')}</p>"
        return "".join(
            f"""<article class="match"><b>{_esc(item['title'])}</b>
            <span>规则匹配值 {_esc(item['match_score'])}</span>
            <small>{_esc(' · '.join(
                reason['dimension'] + ': ' + ', '.join(reason['matched_tags'])
                for reason in item['rationale']
            ))}</small></article>"""
            for item in result["matches"]
        )

    ending = report["fixed_ending"]
    warnings = "".join(f"<li>{_esc(item)}</li>" for item in report["sidecar"].get("warnings", []))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(company['legal_name'])}｜企业评估与分诊</title>
<style>
:root{{--ink:#111;--paper:#f5f3ee;--orange:#ff5a1f;--line:#d8d4ca;--muted:#6d6a63;--green:#147d51}}
*{{box-sizing:border-box}}body{{margin:0;overflow-x:hidden;background:var(--paper);color:var(--ink);font:15px/1.6 Inter,"Noto Sans SC",system-ui,sans-serif}}
main{{max-width:1240px;min-width:0;margin:auto;padding:24px}}.hero{{min-height:400px;background:#111;color:#fff;padding:52px;border-radius:28px;display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden}}
.hero:after{{content:"";position:absolute;width:430px;height:430px;border:100px solid var(--orange);border-radius:50%;right:-150px;top:-180px;opacity:.9}}
.kicker{{color:var(--orange);font-weight:800;letter-spacing:.13em;text-transform:uppercase}}h1{{font-size:clamp(42px,7vw,88px);line-height:.95;max-width:900px;margin:32px 0;letter-spacing:-.055em;overflow-wrap:anywhere}}
.meta{{display:flex;gap:28px;flex-wrap:wrap;color:#bbb}}section{{margin:70px 0}}h2{{font-size:34px;letter-spacing:-.035em;margin:0 0 24px}}h2 em{{color:var(--orange);font-style:normal}}
.notice{{border-left:6px solid var(--orange);padding:16px 22px;background:#fff;margin:24px 0}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.metric,.gap,.match{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px}}.metric span,.metric small{{display:block;color:var(--muted)}}.metric strong{{font-size:22px;display:block;margin:20px 0}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:16px;overflow:hidden}}th,td{{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid var(--line)}}th{{background:#111;color:#fff}}
.pill{{display:inline-block;padding:3px 8px;border-radius:99px;background:#eee}}.pill.verified{{color:var(--green);background:#e5f5ec}}.pill.pending{{color:#9b431f;background:#fff0e8}}
.gaps{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.gap header{{display:flex;justify-content:space-between;color:var(--orange)}}.gap h3{{margin:12px 0 6px}}.gap p{{color:#444}}
.matches{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.match{{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}}.match span{{color:var(--orange);font-weight:700}}
.ending{{background:var(--orange);padding:42px;border-radius:28px}}.ending .answer{{font-size:54px;font-weight:900;letter-spacing:-.05em}}code{{background:#ece9e1;padding:3px 7px;border-radius:5px}}
.workflow{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.workflow span{{border:1px solid;padding:7px 12px;border-radius:99px}}footer{{border-top:1px solid var(--line);padding:30px 0;color:var(--muted)}}
@media(max-width:800px){{.hero{{padding:30px;min-height:350px}}.grid,.gaps,.matches{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}}}
</style></head>
<body><main>
<header class="hero"><div><div class="kicker">CleanTech Finance · Evidence First</div>
<h1>{_esc(company['legal_name'])}</h1></div>
<div class="meta"><span>Case {_esc(case['id'])}</span><span>As of {_esc(case['as_of'])}</span>
<span>Version {_esc(case['version'])}</span><span>{_esc(case['stage'])}</span></div></header>
<section><h2>四项独立判断<em>，没有总分</em></h2>
<div class="notice">本报告不生成投资、信用或综合风险评级；红黄绿或维度状态不汇总。当前只有盈利/单位经济性与现金流/资金缺口两项财务维度完成端到端验证。</div>
<div class="grid">{dimensions}</div></section>
<section><h2>可追溯结论</h2><ol>{conclusions}</ol></section>
<section><h2>证据台账</h2><table><thead><tr><th>编号</th><th>主张</th><th>来源与定位</th><th>等级</th><th>类型</th><th>复核</th></tr></thead>
<tbody>{evidence_rows}</tbody></table></section>
<section><h2>缺口驱动的补充任务</h2><div class="gaps">{gap_cards}</div></section>
<section><h2>资源分诊</h2><div class="matches"><div><h3>课程</h3>{match_cards('course')}</div>
<div><h3>政策</h3>{match_cards('policy')}</div></div></section>
<section><h2>人工闭环</h2><div class="workflow"><span>draft</span>→<span>pending_review</span>→
<span>approved</span>/<span>rejected(reason)</span></div>
<div class="notice"><b>NEX sidecar：</b>{_esc(report['sidecar'].get('status'))}<ul>{warnings}</ul></div></section>
<section class="ending"><div class="kicker">For Leader Review</div><div class="answer">建议：{_esc(ending['recommendation'])}</div>
<h3>核心理由</h3><ul>{''.join(f'<li>{_esc(reason)}</li>' for reason in ending['core_reasons'])}</ul>
<h3>待人工确认项</h3><ul>{''.join(f'<li>{_esc(item)}</li>' for item in ending['human_confirmation'])}</ul></section>
<footer>研究支持而非自动决策。Company / Case / Metrics SQLite 主账本是权威；RAG 仅为证据检索侧车。</footer>
</main></body></html>"""


def write_enterprise_report(
    store: AssessmentStore,
    assessment: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = build_enterprise_report(store, assessment)
    paths = {
        "report_json": output / "enterprise-assessment.json",
        "report_markdown": output / "enterprise-assessment.md",
        "report_html": output / "enterprise-assessment.html",
        "case_snapshot": output / "case-snapshot.json",
    }
    paths["report_json"].write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["report_markdown"].write_text(
        enterprise_report_markdown(report),
        encoding="utf-8",
    )
    paths["report_html"].write_text(
        enterprise_report_html(report),
        encoding="utf-8",
    )
    paths["case_snapshot"].write_text(
        json.dumps(store.get_case_bundle(assessment["case_id"]), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return {key: str(path.resolve()) for key, path in paths.items()}
