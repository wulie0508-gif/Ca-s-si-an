# Round 4 工程实施报告：公司进件内容使用授权预检

日期：2026-08-04

## 独立性与范围声明

- 本轮复用既有工程 specialist task `/root/engineering_auditor`；该 specialist 未参与 Round 4 企业材料生成，也未参与 FA 首测。
- 实施仅依据 Round 4 protocol、`company-submission/`、`fa-initial/`、当前 `src/`/`tests/` 及相关 skill 指令。
- 未读取 `company-supplement/`、`fa-postfix/`、Round 5、Git diff/history 或其他 Agent 产物。
- 使用 `audit-cleantech-finance` skill 约束候选材料边界：候选响应、Agent payload 与受限许可都不得被自动提升为批准、事实或可执行动作。

## 已实施内容

新增独立授权预检模块 `src/cleantech_finance/company_intake_authorization.py`，并接入 company-intake workspace、dashboard 和本地只读 UI。该实现：

- 仅解析 CSV、JSON、JSONL 的显式结构化授权字段；Markdown/prose 不产生授权。
- 支持授权登记、品牌许可、内容使用请求、standalone JSON/JSONL 直接授权/请求、候选响应回执、manifest 授权摘要与 transcript source metadata。
- 使用显式且持久化的 `authorization_diagnostic_as_of` 进行生效/过期判定；无效 `as_of` 会失败，不静默回退。
- 输出六类权限矩阵、八个固定问题 `R04-Q01` 至 `R04-Q08`、内容使用请求决议、Agent override 冲突隔离、transcript 证据缺口和安全边界。
- workspace 创建和加载时基于当前本地结构化 artifacts 重算诊断，并在 dashboard 暴露只读 projection。
- dashboard 下一步优先级为：材料提取 → Round 3 证据完整性阻断 → Round 4 内容授权阻断 → 财务基础/证据问题/检索。既有证据完整性阻断仍高于授权预检。
- UI 新增内容授权卡，展示六类状态、开放问题、被阻断请求、override 冲突和诊断时点；不提供接受、关闭、发布、翻译或 AI 媒体执行按钮。

## Round 4 诊断结果

在 `2026-08-04T00:00:00Z` 的确定性时点，六类状态为：

| 权限 | 状态 |
| --- | --- |
| recording | `expired` |
| internal_analysis | `active_scoped_grant` |
| public_release | `denied` |
| brand_and_logo | `mixed_scope_control`（内部有限授权与公开使用拒绝并存） |
| translation | `missing` |
| ai_media | `denied` |

当前六个内容使用请求全部被保守阻断。请求解析要求同时精确匹配 `authorization_reference`、permission、requested action/scope、source content/content subject 与 audience；字段缺失、语义相近但结构不等、范围扩大、过期、缺失或拒绝均 fail closed。即使受限许可完全精确匹配，也只生成 `within_explicit_scope_candidate`，在人工接受前仍保持 `blocked=true`，不会将其标记为已批准或执行动作。

`06-agent-candidate.json` 的无授权 override 尝试被隔离；Agent artifact 的 source-authority 自我声明不产生有效权威，单独出现 override instruction 也会触发隔离。其 public/brand/translation/AI-media 与事实确认声明不改变权限矩阵，不触发下游动作。候选 response receipts 只建立问题映射，不被接受为授权或事实，也不自动关闭问题。同一权限内 limited/active 与 denied 候选并存时显式输出 `mixed_scope_control`，保持不可执行，不以单一状态掩盖分范围控制。

transcript 正文没有被抽取为事实或权限。只有 manifest 中显式的 `source_class=Enterprise-prepared transcript` 与 `assertion_status=Management Statement—Unverified` 生成一个通用候选证据缺口，仍需 primary evidence 与人工复核。

## 明确未实现与边界

- 未实现 supplement 持久化、submission linkage、accepted/closed 状态机或完整问题响应工作流；`request_tracking_state` 仍为 `not_implemented`。
- 本地重算只消费当前 case 中受支持的结构化 artifacts，并保持原诊断时点；不会从 prose、声明式 request status、candidate receipt 或 Agent 指令推断授权。
- 精确相等策略会保守阻断语义相近但结构不一致的 scope；这类情况需要新的结构化授权材料与人工确认。
- UI 是诊断投影，不是审批或执行面。
- 未创建或修改 Deal，未计算 valuation/rating，未发布、翻译或生成 AI 媒体，未作外部动作。
- 未运行全量测试或浏览器回放；按分工留给 coordination Agent。

## 修改文件

- `src/cleantech_finance/company_intake_authorization.py`
- `src/cleantech_finance/workspace_service.py`
- `src/cleantech_finance/web/agent_bridge.html`
- `src/cleantech_finance/web/agent_bridge.js`
- `tests/test_company_intake_authorization.py`
- `tests/test_agent_bridge.py`
- `evals/double-blind-fa-v0.5/round-04/engineering-review/pre-fix-review.md`
- `evals/double-blind-fa-v0.5/round-04/engineering-review/fix-plan.json`
- `evals/double-blind-fa-v0.5/round-04/engineering-review/implementation-report.md`

## 验证

Focused regressions：

```text
.venv-new\Scripts\python.exe -m pytest tests\test_company_intake_preflight.py tests\test_company_intake_evidence_control.py tests\test_company_intake_authorization.py tests\test_agent_bridge.py::test_loopback_bridge_exposes_content_authorization_preflight tests\test_agent_bridge.py::test_workbench_is_local_accessible_and_defaults_to_no_consent -q
....................... [100%]
23 passed
```

其中 authorization 专项为 9/9 通过，覆盖六状态、六请求 fail-closed、limited exact-scope candidate、Markdown 负例、standalone JSON/JSONL、候选 receipts、transcript gap、顺序不变性、稳定时点/dashboard 优先级及 Round 3 integrity 优先级。

Ruff：

```text
.venv-new\Scripts\python.exe -m ruff check src\cleantech_finance\company_intake_authorization.py src\cleantech_finance\workspace_service.py tests\test_company_intake_authorization.py tests\test_agent_bridge.py
All checks passed!
```

`fix-plan.json` 已通过 PowerShell `ConvertFrom-Json` 校验。

## 协调层复核与加固

specialist 完成后，协调 Agent 又审查并收紧了三处 fail-closed 语义：

- limited/active 与 denied 同时存在时输出 `mixed_scope_control`，不让单一宽泛状态掩盖分范围授权和拒绝；
- Agent artifact 自我声明 source authority 不能产生有效权威，单独出现 override instruction 也必须隔离；
- exact-scope 匹配只标记为人工复核候选，`requires_human_acceptance=true`，在人工接受前始终 `blocked=true`。

加固后 focused 回归为 24/24；最终全套为 389 项 Python 测试、Ruff、6 项 Node 浏览器本地估值测试和 diff whitespace 门禁通过。真实 Chromium 另验证了授权卡、下一步定位、无错误覆盖层和空控制台错误。
