# Round 2 双盲迭代报告｜财务口径冲突与候选补件回执

日期：2026-08-04
版本：CleanTech Finance 0.5.0 working branch
结论：通过本轮范围门禁，但仍缺持久化补件中心与人工审核闭环

## Executive Summary

第二轮使用五张存在真实工作中常见口径冲突的 Synthetic 财务表和一份提交 manifest，测试主体范围、期间、单位、VAT、现金时点/限制、预测版本与来源优先级。初始产品能够接收 6/6 文件、记录哈希并阻止 Deal、估值和计算，但没有识别任何财务口径冲突，也没有生成一个系统问题，产品基线为 48/100。

FA 形成 R02-Q01–R02-Q08 八个精确问题后，企业侧提交两份受控回答和一份补件 manifest。人工对账结果是 answered 1、partial 6、not_available 1，透明证据进度为 50%，完全回答率为 12.5%。这不是企业评分。修复前产品仍然是原生检测 0/8、关闭 0/8，明确返回 `request_tracking_state=not_implemented`。

工程修复增加了确定性的 `company_intake` 财务口径预检。它只读取 CSV/JSON 明示字段，稳定生成八个问题；关键口径为 multiple、unknown 或预测未批准时，计算状态保持 blocked。补件 manifest 只产生 candidate response receipts，不自动接受事实或关闭问题。修复后两案真实 HTTP 重放通过 10/10 范围门禁：所有候选选择字段保持 null，8 个补件回执全部 `accepted_as_truth=false`、`question_closed=false`，下一步优先复核财务口径，Deal/估值/计算仍为 0。

本轮业务材料全部为 Synthetic。真实的是本地 HTTP、Case、哈希、状态、问题、进程和测试结果；本轮不是现实企业验证。

## 方法与隔离限制

- 初始操作由无历史上下文的 FA 子代理完成。其报告写入步骤卡住后被终止；本目录初始六文件由主协调者仅根据已返回遥测和持久化 `workspace.json` 转录，未重跑或增加观察。
- 全局 Agent 线程容量在补件阶段达到上限，补件基线和修复后重放使用未参与企业生成的既有 specialist thread，并施加严格文件白名单。报告明确不把它们称为“全新线程”。
- 各 specialist 未读取企业隐藏真值、其他轮次或工程结论。该方法限制记录在 `protocol-events.jsonl`。
- 企业隐藏真值不写入仓库。

## Phase 1｜初始财务包

产品通过真实 HTTP 创建 `case-20260804-a437a545de`：6/6 文件 ready/candidate_ready，系统 SHA-256 与输入一致。第一次写请求因为缺同源头被服务端以 400 `ui_origin_required` 拒绝；补充 Origin/Referer 后成功，说明写接口的同源保护生效。

输入明示包含八类问题：

1. Standalone 与包含 SYN-OPS-01 的 management group view 并存。
2. 关联主体的法律、控制、会计和资金归属未锁定。
3. H1、YTD、R12M 和 forecast 期间并存。
4. yuan、thousand、million 单位并存。
5. 不含 VAT、含 13% VAT、双列和未说明并存。
6. 现金时点、受限资金和可用余额口径不同。
7. 两个预测版本在日期、主体、单位、税基和数值上不同，且均未批准。
8. 没有跨表来源优先级与完整对账桥。

产品没有生成问题，只给出“确认材料识别范围/生成参考建议”。优点是 analysis 仍 blocked，Deal、估值和计算均为 0；缺点是用户必须自己发现全部口径风险。透明评分为 48/100。

## Phase 2｜企业补件与修复前基线

企业侧按八个问题提交两份 payload：问题回答登记与标准化/对账桥。映射状态为：

| 状态 | 数量 | 含义 |
|---|---:|---|
| answered | 1 | RMB million 的机械单位规则完整；不证明底层金额真实 |
| partial | 6 | 口径选择或管理层桥接已给出，仍缺法律、银行、审计、税务或完整底稿 |
| not_available | 1 | 两版预测均未批准，不存在可选的批准版 |
| contradicted / open | 0 | 没有被新材料直接推翻或完全未回应的问题 |

人工透明进度公式为 answered=1、partial=0.5、其余=0，得到 4/8（50%）；完全回答率 1/8（12.5%）。该指标只描述补件证据进度，不是投资、信用、估值、综合风险或企业评级。

修复前，9/9 文件虽被接收和哈希，但产品原生问题检测/关闭仍为 0/8；supplements 为 not_available。FA 没有执行现金跑道、资金缺口、预测估值或 Deal。

## 工程修复

| 问题 | 判定 | 处置 |
|---|---|---|
| R02-01 无财务口径预检 | 产品功能缺口 | 新增结构化 preflight，仅解析明示 CSV/JSON 字段 |
| R02-02 不生成精确问题 | 工作流 bug | 稳定生成 R02-Q01–R02-Q08，并保留优先级与维度 |
| R02-03 下一步被参考建议抢占 | 优先级 bug | `review_financial_basis_questions` 置于参考建议之前 |
| R02-04 存在静默选值风险 | 权威边界 | 不按最新、最大或名称相近值选取；所有 selected 字段为 null |
| R02-05 补件声明可能被误当事实 | 权威边界 | 只记录 candidate response receipt；不 accepted、不 close |
| R02-06 持久化 request/submission 状态机 | 路线图 | 本轮未冒充已实现 |
| R02-07 人工接受、退回、豁免与理由 | 路线图 | 本轮未实现 |
| R02-08 局部重算与版本依赖图 | 路线图 | 本轮未执行任何计算 |
| R02-09 外部证据核验 | 产品边界 | 未把企业准备材料升级为银行/审计/税务事实 |
| R02-10 SPA 路由保留旧滚动位置 | UI bug | 路由后回到页首，标题焦点使用 preventScroll；真实浏览器重放 scrollY=0 |

## Phase 3｜修复后独立角色重放

复用但文件隔离的门禁 specialist 通过真实 HTTP 创建两案：

- 初始 6 文件：`case-20260804-00814b4a0b`。
- 初始加补件 9 文件：`case-20260804-9a6d5fdd05`。

两案都满足：

- preflight applicability 为 applicable。
- R02-Q01–R02-Q08 顺序稳定。
- calculation status 为 blocked；没有计算。
- 所有 dimension `selected_candidate=null`。
- `forecast.selected_version=null`。
- `source_precedence.selected_precedence=null`。
- next action 为 `review_financial_basis_questions`。
- Deal API 返回 0；没有估值、聚合评级或发布。

补件案生成 8 个 candidate response receipts，但全部 `accepted_as_truth=false`、`question_closed=false`。本轮 scoped gate 得分 100/100，含义只是十项预设安全门禁全部通过，不代表产品完成度 100%。

## 验证门禁

- Python：370 项收集并全部通过，退出码 0。
- Ruff：通过。
- Node browser-local valuation：6 项全部通过。
- `git diff --check`：通过。
- 修复后服务的 `/`、CSS、JS 均真实返回 HTTP 200。主协调者随后用真实 Chromium 渲染 Dashboard 与企业详情，确认“财务口径预检”“计算已阻断”和 8/8 问题可见，console errors 为 0。
- 浏览器重放发现 SPA 从 Dashboard 进入企业时保留旧页面 209px 滚动位置；修复路由滚动与标题焦点后，在同一路径重新验证 `scrollY=0`，顶部不再被粘性导航遮挡。

## 仍然缺少的能力

- 补件中心的持久化状态机：gap_detected 到 accepted/rejected/waived。
- request、submission、artifact version、hash、责任人、截止时间与审核人的实体关系。
- 人工接受、退回原因、不适用/豁免理由和状态历史。
- 已接受输入到盈利/单位经济性、现金跑道和估值的局部重算依赖图。
- 银行、审计、税务、董事会批准等高权威证据的独立核验。
- 多用户、租户和组织权限。

这些能力没有被本轮候选回执包装成已经完成。

## 下一轮

Round 3 将测试来源权威、版本冲突、重复证据和提交者声明哈希。系统必须识别一个声明哈希不一致，不能让更新但未批准的版本覆盖旧但有效的批准版本，也不能把内容相同的两个文件当成两份独立证据。

## 证据索引

- 初始 FA：`fa-initial/`
- 企业补件：`company-supplement/`
- 修复前补件基线：`fa-supplement-baseline/`
- 工程处置：`engineering-review.md`
- 修复后重放：`fa-postfix/`
- 机器结果：`round-result.json`
