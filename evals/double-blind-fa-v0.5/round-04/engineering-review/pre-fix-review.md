# Round 4 授权控制工程诊断（修复前）

## 工程角色与范围披露

本次复用既有 `engineering_auditor` specialist task；该 task 不参与 Round 4 企业数据生成，也不参与 FA 首测或专业判断。诊断只读取了协议、`round-04/company-submission/`、`round-04/fa-initial/`、当前 `src/`、`tests/` 与相关 skill 指令。未读取 `round-04/company-supplement/`、`fa-postfix/`、Round 5、Git diff/history 或其他 Agent 输出。

## 结论

FA 报告中的授权缺口可复现。当前系统具备通用候选边界和 Round 3 证据完整性控制，因此没有实际发布、翻译、AI 媒体、Deal、估值或评级；但它没有独立的 company-intake 内容使用授权预检。结果是六类权限只被部分映射为通用 document-control 元数据，不能形成动作级 gate、请求—授权对账、稳定问题或正确 dashboard 下一步。

这不是现有短期 Agent API consent 的缺失。短期 API consent 解决的是调用接口的会话授权；本轮需要解决的是企业材料所载内容在录音、内部分析、公开发布、品牌、翻译和 AI 媒体场景中的独立使用权边界。

## 修复前根因

### 1. 六类 permission 没有独立 schema

`company_intake_evidence_control.py` 的 `_CONTROL_FIELDS`、`_document_control()` 和 `_parse_csv()` 只投影版本、日期、批准、签字、权威与 assertion 等通用轴，没有保留：

- `permission_type`
- `authorization_subject` / `content_subject`
- `decision` / `current_status`
- `scope` / `permitted_audience`
- `explicit_exclusions`
- `authorization_id` 与 request 的 exact reference 关系

因此 `01-authorization-register.csv` 只形成通用控制候选；`04-brand-logo-license.csv` 的 `license_id` schema 与 `07-content-use-requests.csv` 的 `request_id` schema 不会被授权逻辑识别。Markdown 中虽有人类可读限制，但确定性产品不应从 prose 猜许可。

### 2. expired、denied、missing、limited 没有动作语义

当前没有显式诊断 as-of，也没有日期有效性计算。Round 4 的正确候选状态应分别保持：

- Recording：原授权已过期，只覆盖历史指定录制，不授权新录音。
- Internal analysis：有期限且受主体、工作区、受众和排除项限制，不是一般处理许可。
- Public release：明确 denied。
- Brand and logo：limited，只限未修改资产与命名内部审阅草稿。
- Translation：missing / not authorized。
- AI media：明确 denied。

这些状态必须分别 fail closed。尤其 limited 只能在 request 与结构化 scope/audience/content exact 匹配时形成范围内候选；不能通过相似词、草稿状态、manifest summary 或管理层 register 扩张。

### 3. 内容使用 request 没有与 controlling authorization exact reference 对账

`07-content-use-requests.csv` 提供了 `required_permission` 与 `authorization_reference`，但当前没有 exact-reference resolver。请求本身是 workflow candidate，不具备授予权限的 authority；其 `request_status` 也不能替代被引用授权的 decision、有效期与 scope。拒绝、缺失、引用不存在、权限类型不匹配、过期或范围无法 exact 验证时都应 blocked。

### 4. Agent override attempt 只有通用护栏，没有结构化隔离

`06-agent-candidate.json` 明示：`source_authority=None`、未批准、未签字；其 `authority_boundary` 又逐项声明不得授予、验证、批准或覆盖。与此同时 `candidate_payload` 尝试把 public、brand、translation、AI media 设为 approved，并要求忽略 denied/expired/limited/missing。当前 JSON parser 不识别这组 exact fields，所以不会输出 override conflict、quarantine candidate 或 R04 问题。

最小修复只需检测这些显式键的矛盾；不需要解释自由文本。Agent candidate 必须隔离为无 authority 候选，永远不能进入 controlling authorization 集合。

### 5. 访谈原话没有独立的“说过”与“为真”边界输出

Markdown transcript 应继续不参与 permission 推断，也不应通过 NLP 自动拆主张。可以从 JSON manifest 的显式 `source_class=...transcript` 与 `assertion_status=Management Statement—Unverified` 输出候选 claim/evidence gap：系统仅确认存在一份管理层陈述材料，事实验证仍需一手证据。不得自动抽取或验证技术、客户、商业事实。

### 6. Dashboard next action 没有授权优先级

`workspace_service._case_summary()` 当前优先级覆盖材料提取、Round 3 evidence-control、财务口径、并购证据与参考建议；没有 authorization blocker 分支。因此 Round 4 在完整性 gate 已通过时仍显示 `generate_reference_suggestions`。正确顺序应为：

1. 材料无法提取；
2. evidence-control 的完整性 mismatch/quarantine；
3. 内容使用授权 review；
4. 财务口径或其他既有工作流；
5. 参考建议。

授权卡和下一步只表达 blocked/review，不得表示发布已批准。

## 最小确定性修复

新增独立 `company_intake_authorization.py`：

- 只解析 CSV/JSON/JSONL 的明示授权、request、Agent authority-boundary 和 candidate receipt 字段；`.md` 返回未检测。
- canonical permission 固定为 `recording`、`internal_analysis`、`public_release`、`brand_and_logo`、`translation`、`ai_media`。
- 诊断接受显式 `as_of`；未提供时使用带时区的 UTC 当前时间，并在输出中固定记录。workspace 创建时保存一次 as-of，后续读取复用，避免时间漂移。
- 所有来源记录均标记为 unverified candidate；manifest summary 或管理层 register 不自动成为外部真。
- request 只能按 exact `authorization_reference` 对账；不存在、类型不符、expired、denied、missing、not-effective 或 exact scope 未覆盖时 blocked。
- limited grant 只有在内容、受众和请求边界 exact 匹配时才能标为 `within_explicit_scope_candidate`，仍不自动 accepted。
- 显式 Agent 权限冲突形成隔离项，永不覆盖确定性授权结果。
- 稳定输出 R04-Q01…R04-Q08，并提供各自局部重算 scope；后续补件只形成 candidate receipt，`accepted_as_authorization=false`、`question_closed=false`。

## 禁止自动采信边界

- 不从 Markdown、营销文案、访谈原话或自由文本猜授权。
- 不把 manifest summary、管理层 register、workflow request 或 Agent candidate 视为外部真实授权。
- 不把录音许可推导为发布许可，不把内部分析推导为翻译/训练许可，不把品牌许可推导为公开发布许可。
- 不因签字、批准、版本或 `request_status=Allowed` 单轴自动放行。
- 不允许 expired、denied、missing、scope 外或 scope 无法 exact 验证的动作。
- 不自动接受补件、关闭问题、批准发布、执行翻译或生成 AI 媒体。
- 不创建 Deal、估值、评级或发布状态。

## 局部重算边界

| 变更 | 只重算 | 不自动影响 |
|---|---|---|
| 某 authorization record 更新 | 该 permission gate、引用它的 request、对应 R04 问题 | 其他 permission、事实主张、发布执行 |
| as-of 变化 | 生效/过期状态及依赖 request | decision、authority 或 scope 内容 |
| request 更新 | 该 request exact-reference/scope 对账 | controlling record 本身 |
| Agent candidate 更新 | override conflict 与隔离状态 | deterministic permission decisions |
| transcript/claim 补件 | 候选 claim gap 与人工复核状态 | 自动事实验证、估值或评级 |
| candidate response 上传 | receipt 与对应问题候选状态 | accepted/closed 或动作执行 |

## 拟加测试

1. Round 4 六类 permission 分离；在显式 2026-08-04 as-of 下分别得到 expired、scoped-active、denied、limited、missing、denied。
2. Markdown 中的授权句子不触发 permission。
3. request exact reference 成功定位候选；denied/missing/expired/unmatched/type mismatch 均 blocked。
4. limited request 只有 exact scope/content/audience 匹配才形成范围内候选；任一扩张都 blocked。
5. Agent payload 的无 authority 与 approval override 同时出现时生成隔离冲突，不改变 permission matrix。
6. transcript 只形成 unverified statement/evidence gap，不生成 verified fact。
7. R04-Q01…Q08 ID 与顺序不随文件顺序变化；receipt 永不 accepted/closed。
8. case 创建与再次读取复用同一 as-of；authorization blocker 优先于财务/参考建议，但完整性 mismatch 仍更高。
9. API case/detail/dashboard 透传授权诊断和紧凑投影；UI 卡显示六类状态、blocked requests、override conflict 与安全边界。
10. Round 2/3 company-intake preflight/evidence-control focused 回归保持通过。

本文件记录修复前状态；写入时尚未修改产品代码。
