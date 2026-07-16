"""Build the offline bilingual index for the ten registered company loops."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "evals" / "company-loops-v0.3.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "company-loops" / "index.html"


def _signals(audit: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "profitability-unit-economics": None,
        "cash-runway": None,
    }
    for card in audit.get("judgment_layer", {}).get("cards", []):
        result[card["dimension_id"]] = card["signal"]
    return result


def _signal_badge(signal: str | None) -> str:
    if signal is None:
        return '<span class="signal na">N/A / 不适用</span>'
    label = {
        "red": "Red / 红色",
        "amber": "Amber / 黄色",
        "green": "Green / 绿色",
    }[signal]
    return f'<span class="signal {signal}">{label}</span>'


def _load_cases() -> list[dict[str, Any]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if len(registry) != 10:
        raise ValueError(f"Index requires exactly 10 registered cases, found {len(registry)}")
    if [item["iteration"] for item in registry] != list(range(1, 11)):
        raise ValueError("Registry iterations must be ordered exactly 1 through 10")
    entity_ids = [item["entity_id"] for item in registry]
    if len(set(entity_ids)) != 10:
        raise ValueError("Registry requires 10 unique stable entity ids")

    cases: list[dict[str, Any]] = []
    for row in registry:
        output_dir = (ROOT / row["output_dir"]).resolve()
        audit_path = output_dir / "audit.json"
        report_path = output_dir / "report.html"
        if not audit_path.is_file() or not report_path.is_file():
            raise ValueError(f"Case '{row['id']}' is missing final audit/report artifacts")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if not audit.get("validation", {}).get("passed"):
            raise ValueError(f"Case '{row['id']}' did not pass audit validation")
        if audit.get("execution", {}).get("model_calls") != 0:
            raise ValueError(f"Case '{row['id']}' did not remain zero-model-call")
        cik = str(audit.get("subject", {}).get("cik") or "").zfill(10)
        if row["entity_id"] != f"sec-cik-{cik}":
            raise ValueError(f"Case '{row['id']}' stable identity does not match its CIK")
        signals = _signals(audit)
        if signals != row["expected_signals"]:
            raise ValueError(
                f"Case '{row['id']}' signal mismatch: {signals} != {row['expected_signals']}"
            )
        auxiliary = audit.get("auxiliary_validation", {})
        available = set(auxiliary.get("available_source_ids", []))
        selected = set(auxiliary.get("selected_source_ids", []))
        ignored = set(auxiliary.get("ignored_source_ids", []))
        if selected & ignored or available != selected | ignored:
            raise ValueError(f"Case '{row['id']}' has inconsistent auxiliary source sets")
        checks = auxiliary.get("checks", [])
        counts = {
            status: sum(check.get("status") == status for check in checks)
            for status in ("matched", "mismatch", "not_comparable", "context")
        }
        display_name = (
            audit.get("identity_resolution", {}).get("display_name")
            or audit["subject"]["organization"]
        )
        cases.append(
            {
                **row,
                "display_name": display_name,
                "signals": signals,
                "audit_passed": True,
                "citation_count": audit["validation"]["citation_count"],
                "auxiliary_status": auxiliary.get("status", "disabled"),
                "available_source_ids": sorted(available),
                "selected_source_ids": sorted(selected),
                "ignored_source_ids": sorted(ignored),
                "auxiliary_counts": counts,
                "report_href": f"{Path(row['output_dir']).name}/report.html",
            }
        )
    return cases


def _source_controls(case: dict[str, Any]) -> str:
    available = case["available_source_ids"]
    if not available:
        return "<p class='muted'>No auxiliary source available / 无可用辅助来源</p>"
    selected = set(case["selected_source_ids"])
    return "".join(
        "<label class='source-option'><input type='checkbox' data-source-id='"
        + html.escape(source_id)
        + "' "
        + ("checked " if source_id in selected else "")
        + "><code>"
        + html.escape(source_id)
        + "</code></label>"
        for source_id in available
    )


def _card(case: dict[str, Any]) -> str:
    profit = case["signals"]["profitability-unit-economics"]
    cash = case["signals"]["cash-runway"]
    signal_tokens = " ".join(
        "na" if value is None else value for value in (profit, cash)
    )
    counts = case["auxiliary_counts"]
    return f"""
<article class="case-card" data-case="{html.escape(case['id'])}" data-company="{html.escape(case['display_name'].lower())}"
  data-aux="{html.escape(case['auxiliary_status'])}" data-signals="{signal_tokens}">
  <div class="case-top"><span class="loop">Loop {case['iteration']:02d} / 第 {case['iteration']} 轮</span><span class="valid">✓ Passed / 已通过</span></div>
  <h2>{html.escape(case['display_name'])}</h2>
  <p class="entity"><code>{html.escape(case['entity_id'])}</code></p>
  <p>{html.escape(case['optimization'])}<span lang="zh-CN">{html.escape(case['optimization_zh'])}</span></p>
  <div class="dimension-row"><div><small>Profitability / 盈利</small>{_signal_badge(profit)}</div><div><small>Cash / 现金</small>{_signal_badge(cash)}</div></div>
  <div class="audit-meta"><span>Aux / 辅助: <strong>{html.escape(case['auxiliary_status'])}</strong></span><span>{case['citation_count']} citations / 引用</span></div>
  <p class="check-counts">Matched / 一致 {counts['matched']} · Mismatch / 不一致 {counts['mismatch']} · Not comparable / 不可比 {counts['not_comparable']} · Context / 上下文 {counts['context']}</p>
  <details class="selector"><summary>Auxiliary source choice / 辅助来源选择</summary>
    <p class="truth">Current applied selection / 当前已应用选择。Changing a checkbox only creates a local rerun draft; it never changes core signals. / 勾选变化只生成本地重跑草稿，绝不改变核心信号。</p>
    <div class="source-list">{_source_controls(case)}</div>
    <div class="draft" hidden><strong>Draft, not applied / 草稿，尚未应用</strong><pre><code class="command"></code></pre><button type="button" class="copy">Copy command / 复制命令</button><span class="copy-status" aria-live="polite"></span></div>
  </details>
  <a class="report-link" href="{html.escape(case['report_href'])}">Open bilingual report / 打开双语报告 →</a>
</article>"""


STYLE = """
:root{--ink:#14211b;--muted:#5f6c64;--paper:#f3f0e7;--panel:#fffdf8;--line:#d5d0c3;--green:#176746;--red:#94362f;--amber:#84540e;--deep:#17382c}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;overflow-x:hidden;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1240px;min-width:0;margin:auto;padding:48px 24px 80px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;color:var(--green);font-weight:800;font-size:12px}.eyebrow,.lede,.notice,h1{overflow-wrap:anywhere}h1{font:700 clamp(38px,6vw,70px)/1.02 Georgia,"Microsoft YaHei",serif;margin:.15em 0}h1 span[lang]{display:block}.lede{font-size:18px;color:var(--muted);max-width:850px}.notice{border-left:4px solid var(--amber);background:#fff8e7;padding:14px 18px;margin:24px 0}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:26px 0}.stat{min-width:0;overflow-wrap:anywhere;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}.stat strong{display:block;font:700 30px Georgia,serif}
.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;padding:16px;background:var(--deep);border-radius:16px;margin:30px 0;color:white}.controls label{font-weight:700}.controls input,.controls select{display:block;width:100%;margin-top:6px;padding:10px 11px;border:2px solid transparent;border-radius:8px;background:white;color:var(--ink);font:inherit}.controls input:focus,.controls select:focus,button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #66c391;outline-offset:3px}.result-count{grid-column:1/-1;margin:0;color:#c9e1d4}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.case-card{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:22px;box-shadow:0 12px 34px rgba(28,38,31,.06);min-width:0}.case-card[hidden]{display:none}.case-top,.audit-meta,.dimension-row{display:flex;justify-content:space-between;gap:12px}.loop{font-weight:800;color:var(--green);letter-spacing:.06em}.valid{color:var(--green);font-weight:800}.case-card h2{font:700 28px/1.15 Georgia,"Microsoft YaHei",serif;margin:12px 0 4px}.entity{margin:0;color:var(--muted)}.case-card p span[lang]{display:block;margin-top:5px}.dimension-row{margin:18px 0}.dimension-row>div{flex:1;border:1px solid var(--line);padding:12px;border-radius:11px}.dimension-row small{display:block;color:var(--muted);font-weight:700;margin-bottom:6px}.signal{display:inline-block;border-radius:999px;padding:4px 10px;font-weight:800;font-size:13px}.signal.green{background:#dceee4;color:var(--green)}.signal.amber{background:#f5e8c9;color:var(--amber)}.signal.red{background:#f1d9d5;color:var(--red)}.signal.na{background:#e7e3d8;color:#515a54}.audit-meta{font-size:13px;color:var(--muted)}.check-counts{font-size:12px;color:var(--muted)}
.selector{border-top:1px solid var(--line);padding-top:13px;margin-top:15px}.selector summary{cursor:pointer;color:var(--green);font-weight:800}.truth{font-size:13px;color:var(--muted)}.source-list{display:grid;gap:6px}.source-option{display:flex;align-items:flex-start;gap:8px;padding:7px;background:#f1eee5;border-radius:7px;overflow-wrap:anywhere}.source-option input{margin-top:4px}.draft{margin-top:12px;padding:12px;background:#fff3d7;border-left:4px solid var(--amber)}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0;background:#262d29;color:#e9f3ec;padding:10px;border-radius:7px}button{border:0;border-radius:7px;padding:8px 11px;background:var(--deep);color:white;font-weight:800;cursor:pointer}.copy-status{margin-left:8px;color:var(--green)}.report-link{display:inline-block;margin-top:17px;color:var(--green);font-weight:800}.muted{color:var(--muted)}.footer{margin-top:38px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted)}code{overflow-wrap:anywhere}
@media(max-width:800px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.controls{grid-template-columns:minmax(0,1fr)}.grid{grid-template-columns:minmax(0,1fr)}.result-count{grid-column:1}.case-top,.audit-meta{align-items:flex-start;flex-direction:column}}
@media(max-width:430px){main{padding:30px 14px 60px}.stats{grid-template-columns:1fr}.dimension-row{flex-direction:column}.case-card{padding:17px}}
"""


SCRIPT = r"""
const cards=[...document.querySelectorAll('.case-card')];
const search=document.querySelector('#search');
const signal=document.querySelector('#signal');
const aux=document.querySelector('#aux');
const count=document.querySelector('#result-count');
function filter(){const q=search.value.trim().toLowerCase();let shown=0;cards.forEach(card=>{const okQ=!q||card.dataset.company.includes(q)||card.dataset.case.includes(q);const okS=signal.value==='all'||card.dataset.signals.split(' ').includes(signal.value);const okA=aux.value==='all'||card.dataset.aux===aux.value;card.hidden=!(okQ&&okS&&okA);if(!card.hidden)shown++;});count.textContent=`${shown} result(s) / ${shown} 个结果`;}
[search,signal,aux].forEach(el=>el.addEventListener('input',filter));filter();
cards.forEach(card=>{const boxes=[...card.querySelectorAll('input[data-source-id]')];const draft=card.querySelector('.draft');if(!draft)return;const command=draft.querySelector('.command');const original=boxes.map(x=>x.checked);function update(){const changed=boxes.some((x,i)=>x.checked!==original[i]);draft.hidden=!changed;if(!changed)return;const selected=boxes.filter(x=>x.checked).map(x=>x.dataset.sourceId);let text=`.\\.venv-new\\Scripts\\python.exe scripts\\run_company_loop_case.py --case ${card.dataset.case}`;if(selected.length){selected.forEach(id=>text+=` --aux-source ${id}`);}else{text+=' --disable-auxiliary';}command.textContent=text;}boxes.forEach(x=>x.addEventListener('change',update));draft.querySelector('.copy').addEventListener('click',async()=>{const status=draft.querySelector('.copy-status');try{await navigator.clipboard.writeText(command.textContent);status.textContent='Copied / 已复制';}catch(_){const range=document.createRange();range.selectNodeContents(command);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);status.textContent='Selected; press Ctrl+C / 已选中，请按 Ctrl+C';}});});
"""


def build_index(output: str | Path = DEFAULT_OUTPUT) -> Path:
    cases = _load_cases()
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    payload_path = output_path.with_suffix(".json")
    cards = "".join(_card(case) for case in cases)
    statuses = sorted({case["auxiliary_status"] for case in cases})
    aux_options = "".join(
        f'<option value="{html.escape(status)}">{html.escape(status)}</option>'
        for status in statuses
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CleanTech Finance — 10-loop local validation</title><style>{STYLE}</style></head><body><main>
<div class="eyebrow">CleanTech Finance · offline deterministic core</div><h1>10-loop local validation<span lang="zh-CN">十轮本地验证总览</span></h1>
<p class="lede">Ten genuinely different companies, ten failure-driven generalization steps, bilingual evidence cards, and user-selectable non-authoritative sources.<span lang="zh-CN">十家不同公司、十次由失败驱动的泛化优化、双语证据卡，以及可由用户选择且不具信号权威的辅助来源。</span></p>
<div class="notice"><strong>Truth boundary / 真实性边界：</strong> Auxiliary values can validate or contextualize facts, but never change deterministic signals. These are independent evidence signals, not investment ratings, rankings, or a composite score.<span lang="zh-CN">辅助值可校验或补充事实，但绝不改变确定性信号；各维度相互独立，不是投资评级、排名或综合分数。</span></div>
<section class="stats"><div class="stat"><strong>10/10</strong>loops complete / 循环完成</div><div class="stat"><strong>10</strong>unique entities / 唯一实体</div><div class="stat"><strong>0</strong>model calls / 模型调用</div><div class="stat"><strong>2</strong>validated dimensions / 已验证维度</div></section>
<section class="controls" aria-label="Filters / 筛选"><label>Search / 搜索<input id="search" type="search" placeholder="Company or case id / 公司或案例编号"></label><label>Signal / 信号<select id="signal"><option value="all">All / 全部</option><option value="red">Red / 红色</option><option value="amber">Amber / 黄色</option><option value="green">Green / 绿色</option><option value="na">N/A / 不适用</option></select></label><label>Aux status / 辅助状态<select id="aux"><option value="all">All / 全部</option>{aux_options}</select></label><p id="result-count" class="result-count" aria-live="polite"></p></section>
<section class="grid">{cards}</section>
<footer class="footer">Generated from the strict registry and final audit artifacts. No directory scanning, remote assets, or hidden network dependency.<span lang="zh-CN">本页仅由严格注册表及最终审计产物生成；不扫描目录、不使用远程资源，也没有隐藏网络依赖。</span></footer>
</main><script>{SCRIPT}</script></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    payload_path.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    try:
        path = build_index(args.out)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"passed": True, "index": str(path.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
