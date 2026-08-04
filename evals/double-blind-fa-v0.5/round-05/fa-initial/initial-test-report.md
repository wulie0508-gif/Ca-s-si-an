# Round 05 FA initial blind-test report

结论：**有条件通过（84/100）**。本轮全部企业材料均为 Synthetic；结果只是一轮本地、内部、确定性的 `screen_grade` 计算，不是真实企业校验，不是正式估值意见，也不构成投资、信用或综合风险评级，且不得公开发布。

## 实际闭环

通过真实 loopback HTTP 产品流程上传了 8 个文件（44,912 bytes）；全部本地 SHA-256、上传后 workspace SHA-256 及企业 manifest 中 7 个声明哈希一致。系统创建了独立 Case、Deal 与 Valuation。Case 上传后没有自动推进 Deal stage；`human_confirmed_stage` 初始为 null，随后才由 `local-fa-ui` 人工确认。

企业提交的 `confirm_inputs=false` 被原样导入为 valuation v2：146/146 条均为 `candidate_input`，0 条获确认。首次计算返回 HTTP 400：`config-business-model is not a human-confirmed configuration`，且没有 calculation。

FA 人工随后完成文件哈希、历史/预测及三情景 FCFF、EV→Equity 聚合和 peer 期间勾稽，冻结 R05-Q01–R05-Q07，再通过当前 UI API 提交显式人类确认。该动作生成 v3，146/146 条由 `local-fa-ui` 确认；候选 v2 与确认 v3 的数值、来源、期间、单位、情景、桥接和 peer 域载荷完全相同，二者 SHA-256 均为 `9ab976336b94635f2cd3ae7df120c3c28727e3533fea8ba3db69c7f3420fb544`。没有修改企业文件；变化仅是人类确认状态、FA actor 与版本元数据。

确认后服务器生成 v4 `calculated_screen_grade`，Calculation Integrity=`passed`，Decision Readiness=`screen_grade`。主要结果（CNYm）为：

| 方法 | EV | Equity value |
| --- | ---: | ---: |
| DCF downside | 568.55 | 534.55 |
| DCF base | 1,036.51 | 1,002.51 |
| DCF upside | 1,534.36 | 1,500.36 |
| Trading Comps P25–P75 | 862.40–931.00 | 未计算 |

系统没有机械加权方法，也明确 `formal_valuation_opinion_produced=false`、`agent_can_approve=false`。终值现值占 EV 的比例分别约为 77.98%、83.66%、86.96%，系统给出三条集中度警告；尚未执行 valuation review/内部批准，本轮止于初始 screen-grade 计算。

## 控制验证

- Agent manifest 中没有 valuation review/approval 工具，`agent_can_approve=false`；Agent approval 路由返回 404。
- 带客户端 `calculation` 对象的请求返回 403，服务器没有运行计算。
- stale v2/hash 与 v3+错误 hash 均返回 409。
- 用同一 idempotency key 重放成功计算，仍返回 v4、同一 version hash 与同一 calculation hash，没有新增版本。
- 企业候选输入不能计算；只有 FA 人工审阅后，确认输入才进入公式。

## 主要缺陷与缺口

`R05-F01`（S1）：估值日为 2026-06-30，首个显式预测期却是 FY2027E。产品按 1/2/3 的指数折现，并把 Calculation Integrity 标为 passed、Decision Readiness 标为无 blocker 的 screen_grade；它没有要求 H2-2026/FY2026 stub、首期日历时点或年化因子，也没有给 timing warning。这可能实质改变 DCF，因此当前值只能作为明确带缺口的内部 screen，不能升级使用。逐字补件问题见 R05-Q03。

`R05-F02`（S2）：README 标示 v0.5.0，但本次实际运行环境的 package metadata 为 0.4.0；功能路径存在，但版本重放身份不清晰。

`R05-F03`（S3）：企业授权文案使用 `internal_only`，Deal API 不接受同名 confidentiality 枚举；采用 `confidential` 后成功。这是可恢复的操作摩擦。

底层财务台账、LTM 构成、WACC/终值推导、桥接分类底表和 peer 选择证据仍需补件。FA 对 2.5% base terminal growth 的确认仅是为完成 Synthetic screen-grade 测试而作的人类判断，不把它升级为企业事实或外部市场验证。

## 评分

| 维度 | 得分 |
| --- | ---: |
| 双盲与权限边界 | 15/15 |
| 材料接收、身份与来源追溯 | 15/20 |
| 缺口、问题与补件质量 | 19/20 |
| 访谈准备度解释与可行动性 | 13/15 |
| Deal/Valuation 隔离、版本与 fail-closed | 14/20 |
| 可重放性与操作效率 | 8/10 |
| **总计** | **84/100** |

## 清理

Bridge PID 43348 已停止，127.0.0.1:18765 已释放；经确认位于系统 Temp 下、名称为 `ctf-r05-fa-*` 的本轮临时 workspace（18 个文件）已删除。未修改产品代码、测试、protocol、company-submission 或 Git 历史。
