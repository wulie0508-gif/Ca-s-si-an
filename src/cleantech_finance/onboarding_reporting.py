"""Portable bilingual artifacts for local company onboarding cases."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

from .onboarding import (
    assessment_plan,
    benchmark_summary,
    build_agent_tasks,
    interview_guide,
    material_request_plan,
    validate_company_case,
)


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _gate_rows(validation: dict[str, Any]) -> str:
    rows = []
    for gate in validation["gates"]:
        blockers = "<br>".join(_esc(item["text_zh"]) for item in gate["blockers"]) or "—"
        status = "通过 / Passed" if gate["status"] == "passed" else "待处理 / Blocked"
        rows.append(
            f"<tr><td>{_esc(gate['name_zh'])}</td><td class='{gate['status']}'>{status}</td><td>{blockers}</td></tr>"
        )
    return "".join(rows)


def _claim_rows(case: dict[str, Any]) -> str:
    rows = []
    for claim in case.get("claims", []):
        if not isinstance(claim, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_esc(claim.get('id'))}</td>"
            f"<td>{_esc(claim.get('category'))}</td>"
            f"<td>{_esc(claim.get('text_zh'))}</td>"
            f"<td>{_esc(claim.get('status'))}</td>"
            f"<td>{_esc(claim.get('minimum_evidence_level', 'E1'))}</td>"
            f"<td>{_esc(claim.get('visibility'))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='6'>尚未记录主张 / No claims recorded.</td></tr>"


def _evidence_rows(case: dict[str, Any]) -> str:
    rows = []
    for evidence in case.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_esc(evidence.get('id'))}</td>"
            f"<td>{_esc(evidence.get('level'))}</td>"
            f"<td>{_esc(evidence.get('source_type'))}</td>"
            f"<td>{_esc(evidence.get('title'))}</td>"
            f"<td>{_esc(evidence.get('captured_at'))}</td>"
            f"<td>{_esc(evidence.get('review_status', 'candidate'))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='6'>尚未记录证据 / No evidence recorded.</td></tr>"


def onboarding_markdown(case: dict[str, Any], validation: dict[str, Any]) -> str:
    company = case["company"]
    plan = assessment_plan(case, validation)
    lines = [
        f"# {company.get('display_name_zh') or company.get('legal_name')} | Local company evidence case",
        "",
        "> 本报告是本地企业入驻与证据准备度工作底稿，不构成投资、信贷、法律、审计、ESG鉴证或DOE ARL评级。",
        "",
        "## 企业范围 / Company scope",
        "",
        f"- 法律主体 / Legal entity: {company.get('legal_name')}",
        f"- 稳定标识 / Identifier: {company.get('entity_identifier', {}).get('scheme')}:{company.get('entity_identifier', {}).get('value')}",
        f"- 行业 / Industry: {company.get('industry')}",
        f"- 商业模式 / Business model: {company.get('business_model')}",
        f"- 阶段 / Stage: {company.get('stage')}",
        f"- 产品或技术 / Solution: {company.get('technology_or_solution_zh') or company.get('technology_or_solution')}",
        "",
        "## 闸门 / Gates",
        "",
        "| 闸门 | 状态 | 阻塞项 |",
        "|---|---|---|",
    ]
    for gate in validation["gates"]:
        blockers = "；".join(item["text_zh"] for item in gate["blockers"]) or "—"
        lines.append(f"| {gate['name_zh']} | {gate['status']} | {blockers} |")
    lines.extend(["", "## 分析路线 / Assessment route", "", f"- 路线 / Route: {plan['route_zh']}", "", "| 模块 | 产品状态 | 输出 |", "|---|---|---|"])
    for module in plan["modules"]:
        lines.append(f"| {module['id']} | {module['state_zh']} | {module['output']} |")
    lines.extend(["", "## 访谈安排 / 30-minute interview", ""])
    for item in interview_guide(case):
        lines.append(f"- {item['time']}｜{item['topic_zh']}｜{item['question_zh']}")
    lines.extend(["", "## 阶段化补件 / Required materials", "", "| 材料 | 状态 | 目的 |", "|---|---|---|"])
    for item in material_request_plan(case):
        lines.append(f"| {item['label_zh']} | {item['status']} | {item['request_zh']} |")
    lines.extend(["", "## 主张台账 / Claim ledger", "", "| ID | 类别 | 主张 | 状态 | 最低证据 | 可见范围 |", "|---|---|---|---|---|---|"])
    for claim in case.get("claims", []):
        if isinstance(claim, dict):
            lines.append(
                f"| {claim.get('id')} | {claim.get('category')} | {claim.get('text_zh')} | {claim.get('status')} | {claim.get('minimum_evidence_level', 'E1')} | {claim.get('visibility')} |"
            )
    lines.extend(["", "## 证据台账 / Evidence ledger", "", "| ID | 等级 | 来源类型 | 标题 | 获取时间 |", "|---|---|---|---|---|"])
    for evidence in case.get("evidence", []):
        if isinstance(evidence, dict):
            lines.append(
                f"| {evidence.get('id')} | {evidence.get('level')} | {evidence.get('source_type')} | {evidence.get('title')} | {evidence.get('captured_at')} |"
            )
    lines.extend(["", "## 能力边界 / Capability boundary", ""])
    lines.extend(
        [
            "- 当前已验证的财务确定性内核仅覆盖盈利/单位经济性和现金流/资金缺口。",
            "- ESG、完整DOE ARL、出海准备度和综合评分在本工作台中为流程与证据框架，不自动产生认证分数。",
            "- 本地 Agent 返回的是候选证据；必须经人工审核，不能直接升级为已验证事实。",
            "- 红黄绿财务证据信号不会被本工作台汇总成总分、投资评级或信贷评级。",
        ]
    )
    return "\n".join(lines) + "\n"


def _workbench_script(case: dict[str, Any], validation: dict[str, Any]) -> str:
    payload = json.dumps(case, ensure_ascii=False).replace("</", "<\\/")
    validation_payload = json.dumps(validation, ensure_ascii=False).replace("</", "<\\/")
    plan = assessment_plan(case, validation)
    plan_rows = "".join(
        f"<tr><td>{_esc(module['id'])}</td><td>{_esc(module['state_zh'])}</td><td>{_esc(module['output'])}</td></tr>"
        for module in plan["modules"]
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CleanTech Local Workbench</title><style>
:root{{--ink:#162235;--muted:#60708a;--line:#dce4ee;--paper:#f5f8fb;--blue:#1664d9;--green:#137a5d;--amber:#b7791f;--red:#b42318}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}header{{padding:28px max(22px,calc((100vw - 1180px)/2));background:#10243e;color:#fff}}header p{{margin:.35rem 0 0;color:#cfe0f7}}main{{max-width:1180px;margin:22px auto;padding:0 22px 42px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}section{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 10px #10243e0a}}h2{{font-size:18px;margin:0 0 12px}}h3{{font-size:16px;margin:18px 0 8px}}label{{display:block;font-size:13px;font-weight:650;margin:10px 0 4px}}input,select,textarea,button{{font:inherit}}input,select,textarea{{width:100%;padding:8px;border:1px solid #b8c7d9;border-radius:7px}}textarea{{min-height:160px;font-family:ui-monospace,Consolas,monospace}}button{{border:0;border-radius:7px;background:var(--blue);color:#fff;padding:9px 12px;cursor:pointer;margin:8px 8px 0 0}}button.secondary{{background:#eaf1fa;color:#163968}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid var(--line)}}th{{background:#f4f7fb}}.passed{{color:var(--green);font-weight:700}}.blocked{{color:var(--red);font-weight:700}}.note{{color:var(--muted)}}.badge{{display:inline-block;border-radius:999px;padding:2px 8px;background:#eaf1fa;color:#163968;font-size:12px;font-weight:700}}.hidden{{display:none}}@media(max-width:700px){{main{{padding:0 12px}}section{{padding:14px}}table{{display:block;overflow:auto;white-space:nowrap}}}}
</style></head><body><header><h1>企业证据工作台 <span class="badge">Local-only</span></h1><p>访谈、主张、证据、授权与闸门。编辑后下载 JSON，再通过 CLI 生成正式工作底稿。</p></header><main>
<section><h2>案例概览 / Case overview</h2><div class="grid"><div><label>法律主体</label><input data-path="company.legal_name"></div><div><label>中文名称</label><input data-path="company.display_name_zh"></div><div><label>行业</label><input data-path="company.industry"></div><div><label>商业模式</label><input data-path="company.business_model"></div><div><label>阶段</label><select data-path="company.stage"><option value="research_development">研发期</option><option value="pilot">试点验证期</option><option value="early_commercial">早期商业化</option><option value="scaling">规模化</option><option value="mature">成熟经营</option></select></div><div><label>主体标识</label><input data-path="company.entity_identifier.value"></div></div><label>产品、技术或项目</label><input data-path="company.technology_or_solution_zh"></section>
<section><h2>授权 / Permissions</h2><div id="permissions" class="grid"></div><p class="note">公开内容、身份品牌、翻译字幕和 AI 合成媒体必须分别授权。未明确授权的内容保持内部。</p></section>
<section><h2>闸门快照 / Gate snapshot</h2><div id="gates"></div><p class="note">此页面提供本地编辑和预览；下载后请运行 <code>cleantech-finance case report case.json --out output</code> 取得权威验证结果。</p></section>
<section><h2>分析路线 / Assessment route</h2><p>{_esc(plan['route_zh'])}</p><table><thead><tr><th>模块</th><th>状态</th><th>当前输出边界</th></tr></thead><tbody>{plan_rows}</tbody></table></section>
<section><h2>主张台账 / Claims</h2><div id="claims"></div><h3>添加主张 / Add claim</h3><div class="grid"><div><label>ID</label><input id="claim-id" placeholder="claim-paid-customers"></div><div><label>类别</label><select id="claim-category"><option>commercial</option><option>financial</option><option>impact</option><option>ip</option><option>compliance</option><option>governance</option><option>content</option></select></div><div><label>状态</label><select id="claim-status"><option>unverified</option><option>partially_verified</option><option>verified</option><option>conflicted</option><option>refuted</option><option>not_applicable</option></select></div><div><label>最低证据</label><select id="claim-level"><option>E1</option><option>E2</option><option>E3</option><option>E4</option></select></div><div><label>可见范围</label><select id="claim-visibility"><option>internal</option><option>public_candidate</option><option>restricted</option><option>public_approved</option></select></div></div><label>中文主张</label><input id="claim-text" placeholder="企业主张……"><label><input id="claim-critical" type="checkbox"> 关键主张（至少 E3）</label><button id="add-claim">添加主张</button></section>
<section><h2>证据台账 / Evidence</h2><div id="evidence"></div><h3>添加证据 / Add evidence</h3><div class="grid"><div><label>ID</label><input id="evidence-id" placeholder="evidence-001"></div><div><label>来源类型</label><select id="evidence-source"><option>management_statement</option><option>internal_document</option><option>transaction_document</option><option>official_record</option><option>independent_verification</option><option>agent_candidate</option></select></div><div><label>获取日期</label><input id="evidence-date" placeholder="YYYY-MM-DD"></div><div><label>可见范围</label><select id="evidence-visibility"><option>internal</option><option>restricted</option><option>public_candidate</option></select></div></div><label>标题</label><input id="evidence-title" placeholder="合同、发票、官方登记或测试报告"><label>关联主张 ID（可用逗号分隔）</label><input id="evidence-claims" placeholder="claim-001,claim-002"><button id="add-evidence">添加证据</button></section>
<section><h2>高级 JSON 编辑 / Advanced JSON</h2><textarea id="json"></textarea><br><button id="apply">应用 JSON</button><button id="download" class="secondary">下载 case.json</button><button id="reset" class="secondary">恢复生成时内容</button><p id="message" class="note"></p></section>
</main><script>
const original={payload};let state=JSON.parse(JSON.stringify(original));const initialValidation={validation_payload};
const permissionLabels={{recording_and_transcription:'录音与转写',internal_analysis:'内部分析',public_content:'对外内容',identity_and_brand:'姓名、肖像与品牌',translation_and_subtitles:'翻译与字幕',ai_synthetic_media:'AI合成媒体'}};
function get(path){{return path.split('.').reduce((v,k)=>v&&v[k],state)}}function set(path,value){{const ks=path.split('.');let o=state;ks.slice(0,-1).forEach(k=>o=o[k]);o[ks.at(-1)]=value}}
function esc(v){{return String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function render(){{document.querySelectorAll('[data-path]').forEach(el=>{{const value=get(el.dataset.path)||'';el.value=value;el.oninput=()=>{{set(el.dataset.path,el.value);sync()}}}});const p=document.querySelector('#permissions');p.innerHTML='';Object.entries(permissionLabels).forEach(([key,label])=>{{const wrap=document.createElement('label');wrap.innerHTML=`<input type="checkbox" ${{state.permissions[key]?'checked':''}}> ${{label}}`;wrap.querySelector('input').onchange=e=>{{state.permissions[key]=e.target.checked;sync()}};p.appendChild(wrap)}});renderTables();document.querySelector('#json').value=JSON.stringify(state,null,2)}}
function renderTables(){{const claims=state.claims||[];document.querySelector('#claims').innerHTML=`<table><thead><tr><th>ID</th><th>主张</th><th>状态</th><th>最低证据</th><th>可见范围</th></tr></thead><tbody>${{claims.map(x=>`<tr><td>${{esc(x.id)}}</td><td>${{esc(x.text_zh)}}</td><td>${{esc(x.status)}}</td><td>${{esc(x.minimum_evidence_level||'E1')}}</td><td>${{esc(x.visibility)}}</td></tr>`).join('')||'<tr><td colspan="5">尚未添加主张。</td></tr>'}}</tbody></table>`;const evidence=state.evidence||[];document.querySelector('#evidence').innerHTML=`<table><thead><tr><th>ID</th><th>等级</th><th>来源类型</th><th>标题</th><th>状态</th></tr></thead><tbody>${{evidence.map(x=>`<tr><td>${{esc(x.id)}}</td><td>${{esc(x.level)}}</td><td>${{esc(x.source_type)}}</td><td>${{esc(x.title)}}</td><td>${{esc(x.review_status||'candidate')}}</td></tr>`).join('')||'<tr><td colspan="5">尚未添加证据。</td></tr>'}}</tbody></table>`;renderGates()}}
function renderGates(){{const fields=['legal_name','country','industry','business_model','stage','technology_or_solution'];const missing=fields.filter(x=>!String(state.company[x]||'').trim()||String(state.company[x]).startsWith('define-'));const rows=[['授权闸门',state.permissions.internal_analysis?'通过':'待处理',state.permissions.internal_analysis?'—':'需要内部分析授权'],['主体与范围闸门',missing.length?'待处理':'通过',missing.join('、')||'—'],['最低证据闸门','待处理','请在 CLI 中以材料、主张和证据完整校验'],['发布闸门',state.permissions.public_content&&state.permissions.identity_and_brand?'可用':'内部默认','仅已验证且明确授权的内容可发布']];document.querySelector('#gates').innerHTML=`<table><thead><tr><th>闸门</th><th>状态</th><th>说明</th></tr></thead><tbody>${{rows.map(r=>`<tr><td>${{r[0]}}</td><td class="${{r[1].includes('通过')?'passed':'blocked'}}">${{r[1]}}</td><td>${{r[2]}}</td></tr>`).join('')}}</tbody></table>`}}
function sync(){{renderTables();document.querySelector('#json').value=JSON.stringify(state,null,2)}}
function field(id){{return document.querySelector('#'+id).value.trim()}}function show(msg){{document.querySelector('#message').textContent=msg}}
document.querySelector('#add-claim').onclick=()=>{{const id=field('claim-id'),text=field('claim-text');if(!id||!text){{show('添加主张需要 ID 和中文主张。');return}}if((state.claims||[]).some(x=>x.id===id)){{show('主张 ID 已存在。');return}}state.claims.push({{id,category:field('claim-category'),text_zh:text,text_en:'',statement_id:null,critical:document.querySelector('#claim-critical').checked,minimum_evidence_level:field('claim-level'),evidence_ids:[],status:field('claim-status'),visibility:field('claim-visibility'),subject_scope:state.company.legal_name,period:''}});['claim-id','claim-text'].forEach(id=>document.querySelector('#'+id).value='');sync();show('已添加主张；请补充或关联证据后重新生成正式校验。')}};
document.querySelector('#add-evidence').onclick=()=>{{const id=field('evidence-id'),title=field('evidence-title'),source=field('evidence-source');if(!id||!title){{show('添加证据需要 ID 和标题。');return}}if((state.evidence||[]).some(x=>x.id===id)){{show('证据 ID 已存在。');return}}const claimIds=field('evidence-claims').split(',').map(x=>x.trim()).filter(Boolean),levels={{management_statement:'E1',internal_document:'E2',transaction_document:'E3',official_record:'E3',independent_verification:'E4',agent_candidate:'E1'}};state.evidence.push({{id,level:levels[source],source_type:source,title,captured_at:field('evidence-date')||'YYYY-MM-DD',visibility:field('evidence-visibility'),review_status:'candidate',raw_artifact:'',url_or_source_id:'',sha256:'',agent_run_id:source==='agent_candidate'?'local-agent-run-required':null,claim_ids:claimIds}});claimIds.forEach(claimId=>{{const claim=(state.claims||[]).find(x=>x.id===claimId);if(claim){{claim.evidence_ids=[...(claim.evidence_ids||[]),id]}}}});['evidence-id','evidence-title','evidence-claims'].forEach(id=>document.querySelector('#'+id).value='');sync();show('已添加候选证据；请补充原始文件、时间与审核状态后重新生成正式校验。')}};
document.querySelector('#apply').onclick=()=>{{try{{state=JSON.parse(document.querySelector('#json').value);render();document.querySelector('#message').textContent='已应用 JSON；请下载并用 CLI 生成正式校验。'}}catch(e){{document.querySelector('#message').textContent='JSON 格式错误：'+e.message}}}};document.querySelector('#download').onclick=()=>{{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(state,null,2)+'\\n'],{{type:'application/json'}}));a.download='case.json';a.click();URL.revokeObjectURL(a.href)}};document.querySelector('#reset').onclick=()=>{{state=JSON.parse(JSON.stringify(original));render()}};render();
</script></body></html>"""


def onboarding_html(case: dict[str, Any], validation: dict[str, Any]) -> str:
    company = case["company"]
    plan = assessment_plan(case, validation)
    material_rows = "".join(
        f"<tr><td>{_esc(item['label_zh'])}</td><td>{_esc(item['status'])}</td><td>{_esc(item['request_zh'])}</td></tr>"
        for item in material_request_plan(case)
    )
    interview_rows = "".join(
        f"<tr><td>{_esc(item['time'])}</td><td>{_esc(item['topic_zh'])}</td><td>{_esc(item['visibility'])}</td><td>{_esc(item['question_zh'])}</td></tr>"
        for item in interview_guide(case)
    )
    plan_rows = "".join(
        f"<tr><td>{_esc(item['id'])}</td><td>{_esc(item['state_zh'])}</td><td>{_esc(item['output'])}</td></tr>"
        for item in plan["modules"]
    )
    error_rows = "".join(f"<li>{_esc(item['text_zh'])}</li>" for item in validation["errors"]) or "<li>无阻塞错误 / No blocking validation errors.</li>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(company.get('display_name_zh') or company.get('legal_name'))} | Evidence intake</title><style>
body{{margin:0;background:#f5f8fb;color:#162235;font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}header{{background:#10243e;color:#fff;padding:30px max(24px,calc((100vw - 1100px)/2))}}header p{{color:#cfe0f7}}main{{max-width:1100px;margin:22px auto;padding:0 22px 42px}}section{{background:#fff;border:1px solid #dce4ee;border-radius:12px;padding:20px;margin:16px 0}}h2{{font-size:18px;margin-top:0}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:9px;text-align:left;vertical-align:top;border-bottom:1px solid #dce4ee}}th{{background:#f4f7fb}}.passed{{color:#137a5d;font-weight:700}}.blocked{{color:#b42318;font-weight:700}}.note{{color:#60708a}}.metric{{display:inline-block;padding:8px 12px;background:#eaf1fa;border-radius:8px;margin:0 8px 8px 0}}@media(max-width:700px){{main{{padding:0 12px}}table{{display:block;overflow:auto;white-space:nowrap}}}}</style></head><body><header><h1>{_esc(company.get('display_name_zh') or company.get('legal_name'))}</h1><p>本地企业入驻、访谈与证据工作底稿 / Local evidence-first onboarding record</p></header><main>
<section><div class="metric">阶段 / Stage: <strong>{_esc(company.get('stage'))}</strong></div><div class="metric">行业 / Industry: <strong>{_esc(company.get('industry'))}</strong></div><div class="metric">标识 / Identifier: <strong>{_esc(company.get('entity_identifier', {}).get('scheme'))}:{_esc(company.get('entity_identifier', {}).get('value'))}</strong></div><p class="note">本产物不构成投资、信用、ESG鉴证、法律意见或DOE ARL评级。当前已验证的财务内核仍仅覆盖盈利/单位经济性和现金流/资金缺口。</p></section>
<section><h2>五道闸门 / Five gates</h2><table><thead><tr><th>闸门</th><th>状态</th><th>阻塞项</th></tr></thead><tbody>{_gate_rows(validation)}</tbody></table></section>
<section><h2>分析路线 / Assessment route</h2><p>{_esc(plan['route_zh'])}</p><table><thead><tr><th>模块</th><th>状态</th><th>当前输出边界</th></tr></thead><tbody>{plan_rows}</tbody></table></section>
<section><h2>验证问题 / Validation issues</h2><ul>{error_rows}</ul></section>
<section><h2>30分钟人工访谈 / 30-minute founder interview</h2><table><thead><tr><th>时间</th><th>模块</th><th>默认可见范围</th><th>问题</th></tr></thead><tbody>{interview_rows}</tbody></table></section>
<section><h2>阶段化补件 / Stage-specific materials</h2><table><thead><tr><th>材料</th><th>状态</th><th>请求内容</th></tr></thead><tbody>{material_rows}</tbody></table></section>
<section><h2>主张台账 / Claim ledger</h2><table><thead><tr><th>ID</th><th>类别</th><th>主张</th><th>状态</th><th>最低证据</th><th>可见范围</th></tr></thead><tbody>{_claim_rows(case)}</tbody></table></section>
<section><h2>证据台账 / Evidence ledger</h2><table><thead><tr><th>ID</th><th>等级</th><th>来源类型</th><th>标题</th><th>获取时间</th><th>审核状态</th></tr></thead><tbody>{_evidence_rows(case)}</tbody></table></section>
<section><h2>本地工作方式 / Local operating boundary</h2><ul><li>企业材料与访谈默认在本地案例目录内处理。</li><li>本地 Agent 只能返回候选证据及原始快照；人工审核后才可能支持已验证事实。</li><li>对外内容只能使用已验证且明确标记为 <code>public_approved</code> 的主张。</li><li>同行比较必须保持子行业、阶段、商业模式、地区和期间可比；样本不足时不显示伪精确排名。</li></ul></section>
</main></body></html>"""


def write_onboarding_artifacts(case: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write a complete offline case packet without changing the input case."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    validation = validate_company_case(case)
    materials = material_request_plan(case)
    guide = interview_guide(case)
    tasks = build_agent_tasks(case)
    benchmark = benchmark_summary(case)
    plan = assessment_plan(case, validation)
    paths = {
        "case_json": output / "case.json",
        "validation_json": output / "case_validation.json",
        "report_markdown": output / "intake_report.md",
        "report_html": output / "intake_report.html",
        "workbench_html": output / "workbench.html",
        "interview_guide_markdown": output / "interview_guide.md",
        "material_request_markdown": output / "material_request.md",
        "claim_ledger_csv": output / "claim_ledger.csv",
        "evidence_ledger_csv": output / "evidence_ledger.csv",
        "content_release_register_csv": output / "content_release_register.csv",
        "agent_tasks_json": output / "agent_tasks.json",
        "benchmark_json": output / "benchmark.json",
        "assessment_plan_json": output / "assessment_plan.json",
    }
    paths["case_json"].write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["validation_json"].write_text(json.dumps(validation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["report_markdown"].write_text(onboarding_markdown(case, validation), encoding="utf-8")
    paths["report_html"].write_text(onboarding_html(case, validation), encoding="utf-8")
    paths["workbench_html"].write_text(_workbench_script(case, validation), encoding="utf-8")
    paths["interview_guide_markdown"].write_text(
        "# 30分钟人工访谈提纲\n\n" + "\n".join(f"- {item['time']}｜{item['topic_zh']}｜{item['question_zh']}" for item in guide) + "\n",
        encoding="utf-8",
    )
    paths["material_request_markdown"].write_text(
        "# 阶段化补件清单\n\n" + "\n".join(f"- [{item['status']}] {item['label_zh']}：{item['request_zh']}" for item in materials) + "\n",
        encoding="utf-8",
    )
    _write_csv(paths["claim_ledger_csv"], [item for item in case.get("claims", []) if isinstance(item, dict)], ["id", "category", "text_zh", "text_en", "statement_id", "critical", "minimum_evidence_level", "evidence_ids", "status", "visibility", "subject_scope", "period"])
    _write_csv(paths["evidence_ledger_csv"], [item for item in case.get("evidence", []) if isinstance(item, dict)], ["id", "level", "source_type", "title", "captured_at", "visibility", "review_status", "raw_artifact", "url_or_source_id", "sha256", "agent_run_id", "claim_ids"])
    content_rows = [
        {"claim_id": item.get("id"), "text_zh": item.get("text_zh"), "status": item.get("status"), "visibility": item.get("visibility"), "public_eligible": item.get("status") == "verified" and item.get("visibility") == "public_approved"}
        for item in case.get("claims", [])
        if isinstance(item, dict)
    ]
    _write_csv(paths["content_release_register_csv"], content_rows, ["claim_id", "text_zh", "status", "visibility", "public_eligible"])
    paths["agent_tasks_json"].write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["benchmark_json"].write_text(json.dumps(benchmark, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["assessment_plan_json"].write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {key: str(path.resolve()) for key, path in paths.items()}
