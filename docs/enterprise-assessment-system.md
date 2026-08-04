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

## 6. 本地案例工作台、NEX RAG 与 Codex Agent Bridge

Bridge 的主入口已经从“填写政策标签”调整为“创建案例并上传材料”。服务端在 Git 忽略的本地目录保存原文件，记录 SHA-256、版本与媒体类型，并对 PDF、OpenXML、文本、JSON 和 HTML 做受限文本抽取。材料角色只标记为 `routing_hint_only`；原文件、抽取文本和 Agent 解读都不会自动成为事实，也不会自动写入 NEX RAG。

NEX 默认通过 `http://127.0.0.1:8000` 只读接入。`/api/health` 分开返回 Bridge、政策目录和 RAG 状态；RAG 在线不代表当前案例一定命中合格证据。检索响应固定为 `candidate_only`，引用仍需人工复核。

政策解析器继续扫描工作簿全部 Sheet，在前 50 个非空行中识别同时包含政策 ID 和名称的正式表头；输出固定记录文件 SHA-256、Sheet、原始表头行和每条记录的原始行号。它不会默认把第一张封面或复核控制台当成政策表。

先做只读检查：

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli policy inspect `
  local-data\policies\catalog.xlsx --as-of 2026-07-31
```

如需让当前 Codex 会话使用自己的模型阅读经授权的材料文本、查询 NEX 候选证据并调用确定性政策匹配，无需另配模型 API。启动只监听本机回环地址的 Bridge：

```powershell
.\.venv-new\Scripts\python.exe -m cleantech_finance.cli bridge `
  local-data\policies\catalog.xlsx `
  --policy-attestation local-data\policy-confirmations\catalog.json `
  --course-catalog local-data\resources\courses.csv `
  --mentor-catalog local-data\resources\mentors.csv `
  --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765/`。Agent 先通过 `/api/agent/authorization-requests` 发起包含 actor、purpose、case 与 scopes 的请求；用户页面显示真实请求且授权项默认不勾选。请求密钥只交给 Agent，页面不接收最终 Bearer Token；批准后只能一次性交换 30 分钟短期令牌，并支持立即撤销。审计日志只保存不可逆指纹。

可授权的 Agent scope 为 `case:read`、`material:read`、`rag:query`、`policy:read`、`policy:match` 和 `policy:reference`。其中材料接口只返回受控抽取文本，不返回原始二进制；结果标记为 `source_material_not_verified_fact`。Bridge 不公开证据审核通过、补件接受、决策批准或发布接口。逐行政策硬匹配仍要求受控复核状态；项目方对目录作出的 SHA-256 绑定确认仅允许生成参考建议，不能确认单条申报资格，且始终要求按官方实时信息核验。

人类工作台使用 `Dashboard → Company Workspace → Next Action`。八阶段轨道表示候选材料准备度，不表示接触、LOI、签约、审批、交割或整合的真实交易进度；真实 deal stage 只能由有权用户确认。Dashboard 量化显示候选材料覆盖、关键缺口和商业模式验证性访谈的准备状态，所有百分比均不得解释为投资、信用或综合风险评分。

`Resources` 只浏览真实接入的政策、课程和导师目录。课程与导师未接入时明确显示 `not_connected`，空目录显示 `empty_catalog`，不填充示例。导师目录还必须通过可用性、授权、利益冲突和有效期硬门槛；匹配结果仅为候选，不打综合分、不自动分配或联系。课程和导师字段模板分别位于 `templates/course-catalog-template.csv` 与 `templates/mentor-catalog-template.csv`。

跨境并购的八阶段、五条贯穿工作流、每阶段材料/字段/责任/决策门和条件化中美监管门见 `docs/cross-border-acquisition-workflow-2026-08-02.md`。当前完整本地产品不能原样部署到 Vercel；源码体积不是阻断项，但本地持久工作区、私有 RAG、4.18 GB SQLite、模型与上传边界需要先拆分，详见 `docs/vercel-deployment-assessment-2026-08-02.md`。

完整案例 Skill 位于 `skills/cleantech-workflow-bridge/`；原政策专用 Skill 继续保留用于独立工作簿检查。

## 7. Leader 点头或打回

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
