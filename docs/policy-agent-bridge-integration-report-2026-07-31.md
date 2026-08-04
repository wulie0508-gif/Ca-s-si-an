# CleanTech Finance Agent-first 工作流集成报告

**日期：2026-07-31**
**产品版本：0.4.0（未擅自改版本号）**
**当前分支：`agent/enterprise-assessment-integration`**
**用途：项目负责人确认、Claude 独立审视与后续实现交接**

## 结论先行

本轮不是把原政策匹配页继续堆成功能，而是完成了一个可运行的 Agent-first
纵向切片：

```text
用户上传企业材料
→ 本地保存、SHA-256、版本与受限文本抽取
→ 候选材料角色（人工复核）
→ Codex 经用户授权读取抽取文本
→ NEX RAG 候选检索
→ 成熟度分区路由
→ 政策候选匹配
→ 人工复核
```

RAG 现在确实接入 8765 Bridge，并完成了真实浏览器查询；但这不等于完整产品已完成：

- 企业上传资料尚未自动进入统一 Enterprise SQLite 主账本；
- 上传资料不会自动写入 NEX RAG；
- 补件中心目前仍是路线图投影，没有持久状态机、提交版本或局部重算；
- 没有真实企业交付验证，本次只使用仓库 demo case 做浏览器 QA；
- `samples.zip` 不是 ESG 源码，未被并入产品、案例或 RAG。

因此，当前最准确的定位是：

> 可演示、可上传、可由 Codex 在受控授权下读取材料并检索候选证据的本地案例工作台；尚不是完成真实企业泛化验收的自动尽调产品。

## 1. 审计前的真实状态

原 8765 页面只具备：

- 固定政策工作簿状态；
- 六类企业标签手工录入；
- 受控政策候选匹配；
- 页面内存短期令牌。

它没有：

- Case；
- 材料上传；
- 材料哈希或版本；
- NEX/RAG 调用；
- ESG 适配；
- 全流程工作区；
- Agent 能读取材料的工具；
- Agent 发起、用户批准、Agent 交换令牌的真实握手。

CleanTech 仓库虽然已经存在 `NexSidecarClient` 和
`enterprise sidecar-query`，但属于独立 CLI 手工路径；评估引擎与页面不会自动调用。

## 2. NEX RAG 的真实连接状态

独立知识库位于 `D:\NEX_企业知识库`，本轮只通过它公开的本地 API 调用，不直接改
RAG 数据库。

2026-07-31 实测 `GET http://127.0.0.1:8000/health`：

| 项目 | 实测 |
|---|---:|
| ready_for_query | `true` |
| documents | 4,061 |
| chunks | 512,599 |
| embedded_chunks | 274,569 |
| semantic_eligible_chunks | 100,075 |
| embedded_semantic_eligible_chunks | 100,075 |
| semantic embedding coverage | 100% |
| external research | 7,989 篇索引 / 6,906 篇有正文 |
| external LLM | 关闭 |
| health warnings | 0 |

两次真实查询说明了必须保留的差异：

1. 针对 “CleanTech Finance 当前验证了哪些财务维度” 的内部检索返回 0 条引用。
   这证明知识库在线不等于项目资料已被批准并收录。
2. 针对 demo distributed solar 案例的 hybrid 查询，在浏览器中返回 5 条候选引用，
   包含 IRENA、Fraunhofer ISE、Berkeley Lab 等来源，也包含相关性较弱的全球电厂
   数据片段。这证明真实召回已经发生，同时也证明不能绕过人工相关性复核。

Bridge 将 RAG 超时从适配器原有 5 秒提高为 90 秒。当前仍是同步请求；首次语义查询
可能较慢，异步 Run 是后续工程项。

## 3. 已实现：本地案例与材料纵向切片

新增 `src/cleantech_finance/workspace_service.py`：

- 默认写入 Git 忽略的 `local-data/agent-workspace/`；
- 每个案例生成不含用户输入路径的随机 Case ID；
- 每份材料记录 SHA-256、字节数、媒体类型、版本和创建时间；
- API 响应不返回本机绝对存储路径；
- 支持 `.pdf`、`.docx`、`.pptx`、`.xlsx`、`.csv`、`.txt`、`.md`、
  `.json`、`.html`、`.htm`；
- 单文件上限 20 MiB，单案例最多 20 份，合计上限 32 MiB；
- OpenXML 检查条目数、展开体积、加密标志和 XML 大小；
- PDF 无可提取文本时明确进入 `awaiting_human`，不伪装 OCR 成功；
- 抽取文本单独保存，原始二进制不通过 Agent API 返回；
- 材料角色只标记 `routing_hint_only` 与 `human_review_required=true`。

候选路由包括：

- 企业身份；
- 财务核心；
- ESG / 清洁技术影响；
- 技术 / ARL；
- 市场 / 出海；
- 政策资源；
- 治理 / 法务；
- 通用材料。

这些角色只回答“后续应进入哪个工作流”，不回答“材料中的主张是否为真”。

## 4. 已实现：真实 Agent 授权握手

新增内存授权请求状态：

```text
pending_user → approved / denied / expired → exchanged
```

流程：

1. Codex 调用 `POST /api/agent/authorization-requests`；
2. 服务端只向 Codex 返回 `request_secret`；
3. 页面展示 actor、purpose、case 和真实 requested scopes；
4. 所有 checkbox 默认不勾选；
5. 用户可批准 requested scopes 的子集或拒绝；
6. Codex 使用 request secret 一次性交换 30 分钟 Bearer Token；
7. 页面从未收到最终 Agent Token；
8. Agent 完成后调用 `/api/revoke`。

可请求 scope：

- `case:read`
- `material:read`（必须同时有 `case:read`）
- `rag:query`
- `policy:read`
- `policy:match`（必须同时有 `policy:read`）

显式不提供：

- `evidence:verify`
- `supplement:accept`
- `decision:approve`
- `public:publish`

请求 secret、Bearer Token 与原始企业全文不得进入 Git、聊天、审计日志或公开报告。

## 5. 已实现：Codex 使用自己的模型

网页本身没有模型，也没有获得 Codex 私有推理 API。正确架构是：

- Codex 是模型宿主与操作方；
- Bridge 是本地、受控、可审计的工具表面；
- 用户通过浏览器批准具体访问范围。

Agent 在取得 `material:read` 后可调用：

```text
GET /api/agent/cases/{case_id}/artifacts/{artifact_id}/text
```

返回：

- 文件名；
- 原始材料 SHA-256；
- 媒体类型；
- 受限抽取文本；
- `authority: source_material_not_verified_fact`；
- `human_review_required: true`。

这让用户可以直接使用当前 Codex 会话的模型与算力，不需要另行配置模型 API；
同时不会把浏览器宣传成自带模型。

仓库新增并验证：

`skills/cleantech-workflow-bridge/`

原政策专用 Skill 已更新为使用同一 Agent 授权握手。

## 6. 已实现：一环套一环的 UI

原政策页面已改为一个三栏案例工作台：

1. 材料
2. 证据
3. 分析
4. 补件
5. 复核
6. 输出

桌面结构：

- 左侧：流程轨与阶段状态；
- 中央：当前唯一主要动作；
- 右侧：下一步、哈希、授权与能力边界。

政策匹配降为“分析”中的资源模块，不再代表产品定位。

真实成熟度固定展示：

- 财务核心：2/6 项端到端已验证；
- 其余财务：输入蓝图；
- ESG：证据框架，不是自动认证；
- 清洁技术影响：需要基线、边界与方法；
- DOE ARL：17 维检索脚手架，不输出 1–9；
- 出海：证据与材料准备框架；
- 政策：候选匹配，受人工复核与有效期硬过滤。

页面没有外部字体、CDN、React 或构建步骤；保留 skip link、键盘焦点、
`aria-live`、reduced motion、加载/错误/空状态和响应式断点。

## 7. 政策目录状态

真实政策工作簿继续 fail closed：

| 字段 | 结果 |
|---|---|
| state | `quarantined` |
| source_sheet | `政策库` |
| header_row | 4 |
| record_count | 73 |
| eligible_count | 0 |
| review status | `待复核: 73` |
| excluded reason | `review_status_not_approved: 73` |

本轮没有为了演示而修改任何政策审核状态。

## 8. `samples.zip` 审计与处理决定

ZIP：

- 路径：用户提供的微信文件目录；
- 大小：28,760,046 bytes；
- SHA-256：
  `143902a40cff578e33917908ea68b755583169d97ddea26cece80d2cc9813b5`；
- 74 个条目，29,830,642 bytes 展开体积；
- 未发现路径穿越、绝对路径、符号链接、加密条目或压缩炸弹；
- 未解压、未执行其中 HTML。

有效内容是：

- 7 份静态 HTML；
- 1 份 Markdown；
- 1 份 XLSX；
- 24 张图片；
- 37 个 macOS 元数据条目。

它不是软件产品，没有后端、API、数据库、鉴权、构建、测试或 ESG 计算引擎。

风险与质量问题：

- 整包无 LICENSE / NOTICE；
- HTML 运行时依赖第三方 ECharts CDN，部分还有外部字体或 Amazon 图片；
- macOS 元数据含带 token 的飞书下载来源 URL；
- XLSX 元数据包含个人姓名和本机路径；
- 17/24 图片带 Google AI / trainedAlgorithmicMedia 标记；
- ESG 主张没有基线、边界、因子、LCA、证书编号或审验；
- 猫砂盆财务模型存在 32% 与约 50.1% 毛利冲突；
- 报告存在版本分叉、图片断链和无法复算指标。

决定：

> 不合并代码、不导入 RAG、不当作 ESG 或财务证据。只把“用户旅程、Persona、
> JTBD、原子参数到卖点规则”等概念作为未来市场/出海模块的设计参考；数值、图片、
> Amazon 数据与 ESG 主张全部拒绝直接复用。

## 9. 验证凭证

当前工作树实测：

| 检查 | 结果 |
|---|---|
| Ruff | All checks passed |
| 完整 pytest | 162 passed / 156.88s |
| Bridge / workspace 定向测试 | 7 passed |
| JavaScript Node 语法 | 通过 |
| 新 workflow Skill | `quick_validate.py` 通过 |
| 原 policy Skill | `quick_validate.py` 通过 |
| Sungrow 发布门禁 | extraction 29/29；cards 27/27；112 citations；0 model calls |
| Enphase 发布门禁 | extraction 28/28；cards 27/27；113 citations；0 model calls |
| 浏览器 console | 页面自身 0 error / warning |
| 1280px 页面横向溢出 | `scrollWidth == clientWidth` |
| 授权弹窗 | 真实 Agent 请求自动出现；0 项默认勾选；非请求 scope 禁用 |
| 真实 RAG 浏览器查询 | 返回 5 条 `candidate_only` 候选 |

发布门禁输出写入 Git 忽略的
`outputs/agent-workspace-release-gate-20260731/`，没有恢复或覆盖用户原有的两个
已删除报告。

## 10. 当前未完成项

### 产品路线图，不是本轮 bug

1. Enterprise SQLite 尚未成为上传 Case、Artifact、Run、Evidence、Gap、
   Submission 与 Output 的统一主账本。
2. 补件中心的完整状态机尚未持久化。
3. Submission Version、聚合哈希、自动校验、退回原因、waiver 理由未实现。
4. 接受补件后的局部重算边界未实现。
5. RAG 查询仍是同步调用，没有 Run/队列/取消/恢复。
6. 没有 OCR 服务；扫描 PDF 正确进入人工处理。
7. 浏览器页面没有聊天机器人；这是有意的 Agent-first 产品选择。
8. 没有真实企业授权材料、独立真值或五企泛化验收。

### 下一实现顺序

1. 将当前文件 Case 迁入/映射到 Enterprise SQLite Artifact 主账本；
2. 持久化 Agent Run 与幂等键、Case revision；
3. 实现补件工作项与 Submission Version；
4. 只在 accepted 后按 `recompute_scope` 做局部重算；
5. 把候选材料角色和 RAG Evidence 放入人工审核队列；
6. 用一条完整企业案例和一条稀疏案例完成授权端到端验证；
7. 最后再考虑正式 MCP transport 与外部部署安全层。

## 11. Git 与所有权边界

- 当前没有替用户提交、推送或合并本轮改动；
- 当前工作树仍有用户要求保留的未提交变更；
- `outputs/release-gate-v0.2.1/enphase/report.html` 与
  `outputs/release-gate-v0.2.1/sungrow/report.html` 的删除状态保持不动；
- 没有执行 `git reset --hard`、`git checkout --` 或覆盖用户修改；
- `local-data/`、QA 案例、审计日志与发布门禁输出都不进入 Git。

## Claude 审视重点

建议 Claude 优先审查：

1. `workspace_service.py` 的 OpenXML/PDF 输入安全与原子写入；
2. Agent authorization request 的并发、过期、一次性交换与撤销边界；
3. `material:read` 是否还需按 artifact 或保密等级细分；
4. 当前同步 RAG 是否应立即改为 Run；
5. 文件 Case 与 Enterprise SQLite 的唯一主账本迁移方案；
6. 补件状态机与局部重算，尤其不能继续“先关闭所有 Gap”；
7. 浏览器与 Agent 的权限面是否存在任何可升级为审核/发布的路径。

Claude 不应把测试通过、RAG 在线或 demo 查询成功解释为真实企业事实验证完成。
