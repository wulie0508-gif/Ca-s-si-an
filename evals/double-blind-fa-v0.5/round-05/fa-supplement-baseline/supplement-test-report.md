# Round 05 · 企业补件后修复前基线

## 结论

补件增加了可复核底表，但没有消除核心估值时点缺陷。17 份 Synthetic 文件经真实 HTTP 一次上传成功，17/17 workspace artifact 哈希一致；企业对 7 个问题给出 2 个 answered、5 个 partial 回应。所有回应继续是候选，系统接受为事实 0、关闭问题 0。

冻结在提交 `b64c66e` 的修复前 Bridge 先正确阻断 146/146 条 candidate inputs。为了复现缺陷，FA 仅对原 `07_valuation_workflow_input.json` 做显式人工确认；企业补件没有被自动合并或升级。服务端随后仍返回 HTTP 201、`calculated_screen_grade`、Calculation Integrity `passed` 和 Decision Readiness `screen_grade`。

## 核心复现

补件 `04_stub_and_dcf_assumptions.json` 已明确提出：

- H2 2026E 独立 stub；
- stub 折现指数 0.5；
- FY2027E / FY2028E / FY2029E 与 terminal 分别使用 1.5 / 2.5 / 3.5 年。

但修复前产品既不能把这些候选字段导入估值版本，也不会要求 FA 确认。它仍对 FY2027E–FY2029E 使用 1 / 2 / 3，且唯一警告是终值占比与尚未完成 FA review；没有 timing blocker 或 warning。这再次确认 `R05-F01` 为 S1：时点错误可能实质改变全部 DCF 现值，却被标记为计算完整性通过。

## 补件变化

- Q01：主体与范围可复核，但没有现实世界有权签署证据，partial。
- Q02：七个期间、八字段及 LTM 月度加总可重算；月度表为新 Synthetic 候选而非原始总账，partial。
- Q03：stub FCFF 与折现指数可重算，但未获 FA 接受且产品不支持，partial。
- Q04：WACC 与倍数候选推导可重算；没有外部市场验证，2.5% 永续增长仍待 FA 判断，partial。
- Q05：EV→Equity 净调整复核为 -34.0 CNYm；真实权属、受限与合同证据缺失，partial。
- Q06：五家 Synthetic peers 的底表和 core-only 主统计规则已提供，answered；产品当前仍统计全部五家，需 FA 决定是否重算。
- Q07：Synthetic 内部测试授权边界明确，answered；它不是现实授权，外部流转与公开发布继续禁止。

## 工程要求

估值流程必须在无法证明日历时点时 fail closed，或只接受 source-bearing、human-confirmed 的逐期显式 discount exponent，并在结果、版本和敏感性里披露实际指数。企业补件不能自行触发确认。补件中心持久状态机、request/submission linkage 与依赖图式局部重算仍是路线图，不能被本轮日志冒充为已实现。

本报告不是真实企业校验、正式估值意见、投资/信用/综合风险评级，也未执行批准或公开发布。
