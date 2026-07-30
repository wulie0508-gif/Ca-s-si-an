# 企业评估与分诊系统（v0.4 集成 MVP）

本模块把企业入口的五路信息组织进一套本地 SQLite 主账本，输出证据、缺口、四项独立判断维度、资源匹配和供 Leader 点头的建议。它不生成聚合总分，不做自动准入，也不输出投资、信用或综合风险评级。

## 已实现边界

- 权威数据链：`Company → Case → Evidence / Interview / Metrics / Gaps / Recommendations / Decision`。
- 统一证据：`claim / source / locator / date / entity_id / source_level / type / confidence / review_status`。
- 财务适配：只接纳已通过原系统确定性校验的财务审计；当前端到端成熟能力仍只有：
  - 盈利 / 单位经济性；
  - 现金流 / 资金缺口。
- 访谈：本机 `ffmpeg + faster-whisper`，默认 `base / CPU / int8`；转写归属于 Case，不写入 RAG。口述统一是 `owner_statement + pending`，不能承重事实。
- NEX：
  - `/v1/query` 只取 citation，不使用自然语言答案；
  - 缺 source 或 locator、明显代码/缓存噪声、把腾讯研究背景当企业事实的结果直接丢弃；
  - 命中项仍是 `pending` 候选证据；
  - 端口不可用时显式标注“本地缓存未使用”，不静默失败；
  - 时效敏感信息必须实时复核官方来源。
- 企业目录：只返回候选法律实体，禁止自动消歧、合并或写入 Company 主档。
- 能源资产库：只读生成候选证据，企业关联仍需人工确认。
- 课程 / 政策：读取正式 `.xlsx` 或 `.csv`，以标签交集和配置权重确定性匹配。政策“复核状态未通过”和“已过期”是不可关闭的硬过滤。
- 推断维度：财务证据充分度、信息一致性、经复核负面项、数据完整度；四项绝不汇总。
- 人工闭环：`draft → pending_review → approved / rejected(reason)`；退回案例自动快照到 `eval_cases/`。

## 1. 初始化主账本与企业案例

```powershell
$repo = 'D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance'
Set-Location $repo

.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise init-store `
  tmp\enterprise-demo.sqlite

.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise create `
  tmp\enterprise-demo.sqlite `
  examples\enterprise-assessment\complete-intake.json
```

第二条命令会打印 `company_id` 和 `case_id`。Company 的 canonical 名称或注册号命中已有记录时复用主档，但不会利用 NEX 目录自动合并实体。

## 2. 录入统一证据

示例文件中的 `entity_id` 使用占位符，CLI 入账时会安全替换为命令中的 Case ID。

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise ingest-evidence `
  tmp\enterprise-demo.sqlite `
  <CASE_ID> `
  examples\enterprise-assessment\complete-evidence.json
```

证据必须有非空 source 和 locator。`verified` 是人工/确定性校验状态，不由 Agent 或 RAG 自动赋予。

## 3. 访谈

已有转写可直接落盘，并可附带带时间戳的结构化口述点：

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise add-interview `
  tmp\enterprise-demo.sqlite <CASE_ID> artifacts\interview.txt `
  --consent-ref consent-2026-001 `
  --segments-json artifacts\segments.json `
  --points-json artifacts\owner-statements.json
```

本机转写：

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise transcribe `
  tmp\enterprise-demo.sqlite <CASE_ID> input\interview.m4a `
  --out artifacts\<CASE_ID>\interview `
  --consent-ref consent-2026-001 `
  --model base
```

转写需要本机可调用 `ffmpeg`，并在当前 Python 环境安装 `faster-whisper`。没有录音/转写授权时不要运行。

## 4. NEX 证据检索侧车

NEX 服务必须由用户在其独立项目中手工、本机启动，且只能绑定回环地址。示例：

```powershell
Set-Location 'D:\NEX_企业知识库'
.\.venv\Scripts\python.exe -m uvicorn nex_kb.api:app `
  --app-dir src --host 127.0.0.1 --port 8000
```

本系统不会自动启动或暴露该服务。若 NEX 配置了密钥，只从进程环境变量 `NEX_API_KEY` 读取，不写入配置或数据库。

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise sidecar-query `
  tmp\enterprise-demo.sqlite <CASE_ID> `
  '青岚储热科技的公开项目与官方登记证据' `
  --mode hybrid --top-k 5
```

退出码 `3` 表示侧车不可用且已进入显式降级路径；不是“没有风险”或“没有证据”。

只读企业候选与能源资产候选：

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise company-candidates `
  'D:\NEX_企业知识库\40_external_sources\derived\company_directory\company_directory.sqlite' `
  'company name'

.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise asset-candidates `
  'D:\NEX_企业知识库\40_external_sources\derived\energy_assets\energy_assets.sqlite' `
  <CASE_ID> 'operator or asset name'
```

## 5. 跑完整评估

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise assess `
  tmp\enterprise-demo.sqlite <CASE_ID> `
  --financial-audit examples\enterprise-assessment\complete-financial-audit.json `
  --course-catalog examples\enterprise-assessment\courses.csv `
  --policy-catalog examples\enterprise-assessment\policies.csv `
  --config config\enterprise-assessment.default.json `
  --sidecar-check `
  --actor analyst `
  --out outputs\enterprise-demo
```

产物：

- `enterprise-assessment.json`：机器可读完整报告；
- `enterprise-assessment.md`：便于 Claude / Codex 审阅；
- `enterprise-assessment.html`：本地展示报告；
- `case-snapshot.json`：对应版本主账本快照。

报告结尾固定包含“进 / 不进 / 补充信息后再议”的**建议**、核心理由、待人工确认项和若进时的资源推荐。建议不是决策。

## 6. Leader 点头或打回

```powershell
# analyst 提交
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise decision `
  tmp\enterprise-demo.sqlite <CASE_ID> submit --actor analyst

# leader 批准
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise decision `
  tmp\enterprise-demo.sqlite <CASE_ID> approve --actor leader

# 或 leader 打回；reason 强制必填
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli enterprise decision `
  tmp\enterprise-demo.sqlite <CASE_ID> reject --actor leader `
  --reason '收入确认口径与访谈口径需重新核对' `
  --eval-dir eval_cases
```

非法跳转（如 `draft → approved`）会被拒绝。被拒绝的版本写成不可静默覆盖的 JSON 回归样本。

## 配置与局部重算

默认配置位于 `config/enterprise-assessment.default.json`。可调整匹配权重、最低匹配值、必要画像字段和关键负面严重度；政策审核状态与过期硬过滤不会因配置关闭。

每个 Gap 都有 `route` 和 `recompute_scope`。后续补件中心可据此只重算受影响的维度、匹配或建议，不需要重跑无关模块。

## 尚未实现

- 企业端补件中心 UI、持久化补件状态机和 API；
- LLM 的受控语义抽取/叙事服务（当前报告叙事为确定性模板）；
- 自动实时访问官方公开来源的检索连接器；当前系统会生成实时官方检索缺口，并接纳人工/受控流程录入的可追溯官方证据；
- 多租户与企业级权限；
- RAG 内部结构改造或新建向量索引；
- 企业目录自动消歧；
- 财务其余四维、完整 ESG、清洁技术影响、ARL 1–9 分数或出海认证。

这些是路线图，不应在演示或报告中描述成已经自动化完成。
