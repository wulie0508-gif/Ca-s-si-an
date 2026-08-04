# Round 3 工程修复记录

## 结论

Round 3 的五项已复现缺陷已经按最小确定性边界完成修复，并由独立 FA 重放验证。修复不是把补件“判真”，而是把完整性、文档控制、重复内容、结构化冲突和财务适用性变成显式门禁；所有权威选择、冲突裁决和候选证据接受仍留给人工。

本轮企业与业务数据全部为 **Synthetic**。HTTP、浏览器、哈希、诊断和测试结果来自真实本地程序运行。实现过程中，主工程 specialist 在完成诊断与接口勘察后未产出代码；协调 Agent 中止了停滞执行，并依据已记录的诊断和接口建议完成实现。该过程没有被计作独立工程复核；独立性来自随后由另一 FA specialist 对当前代码启动全新服务并重放。

## 已实现

- 新增 `company_intake_evidence_control.py`，仅解析显式 CSV/JSON/JSONL 控制字段，不从自由文本猜测事实。
- 按上传实际 SHA-256 与 manifest 声明值对账；支持 `matched`、`mismatch`、`missing_upload`、`unlisted_upload`、`invalid_digest`、`duplicate_manifest_entry` 等状态。mismatch 保持隔离，不自动修正。
- 相同实际 payload 只形成一个候选证据单元，但保留所有 artifact 与文件名别名；canonical 默认为空，accepted 数量为零。
- 对索引声明的底层哈希单独建候选组。底层文件缺失或来源索引被隔离时，候选/接受证据计数均为零。
- 独立保留版本、资料时点、生效日、失效日、批准、签字、来源权威和主张状态，不按“更新/更晚/已批准/已签字”自动选取权威文件。
- 只在显式稳定键上形成结构化 forecast、cap-table 等冲突；全部默认 `unresolved`、选择为空。
- 输出稳定问题 `R03-Q01`–`R03-Q04`；补件仅生成候选 receipt，`accepted_as_truth=false`、`question_closed=false`。
- 收紧财务预检适用性：通用 `as_of_date` 不再触发财务路径；只有符合受控财务 schema 的资料进入预检。Round 3 仅两份 board plan 被识别为 forecast，且版本不自动选择；“可用现金 4.4”不被提升为 treasury 候选。
- company-intake 单次文件上限由 20 调整为 32，并原生支持 `.jsonl`；同名文件作为不同 artifact 保留，由内容哈希层处理重复关系。
- Dashboard 增加证据控制摘要及人工复核下一步，输入完整性门优先于证据冲突，证据冲突优先于财务 basis。
- 前端增加证据控制卡片和定位动作，并修复本轮真实浏览器 Axe 检出的两项可访问性结构问题。

## 局部重算和禁止边界

每个问题都声明依赖 scope；重算只覆盖受影响的 manifest 对账、隔离、重复组、文档 family、稳定 claim key、对应问题和显式依赖门禁。不会因此重算无关主张，也不会启动估值、评级或发布。

以下行为仍被禁止：自动修正声明哈希、按元数据选“真版本”、把管理层陈述直接判真、把缺失底层文件计作证据、静默删除重复别名、在人工接受前计算或公开发布。

## 修复后独立验证

- 新建本地 workspace，真实 HTTP 单次原样上传 21 个物理文件，返回 `201`，保留 21 个 artifacts。
- 17/17 项限定证据控制断言通过；完整性门仍正确为 `blocked`，这不是企业通过或产品评分。
- 18 个 manifest 条目匹配、1 个保持 mismatch；两份 07 均隔离。
- 1 个实际重复组保留 2 个别名；唯一 P2602 底层哈希组为 missing，证据计数为零。
- 25 个结构化冲突保持 unresolved；34 个补件 receipt 全部为候选，未被接受或关闭问题。
- Dashboard 路由到 `review_evidence_control_questions`；未生成计算、Deal、估值、评级或公开发布。
- 真实 Chromium 验证 UI 状态、滚动定位和内容；控制台无错误，修复后 Axe `violations=0`、`incomplete=0`。
- 服务 PID 均精确停止，8892–8894 端口无残留监听。

非阻断观察：case endpoint 顶层旧 `next_action` 仍为 `confirm_material_scope`，而嵌套 dashboard 与 `/api/ui/dashboard` 已正确使用 `review_evidence_control_questions`。本轮门禁按 dashboard 合约验证，后续可统一顶层兼容字段。
