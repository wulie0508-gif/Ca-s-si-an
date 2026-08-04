# Round 2 补件基线盲测报告

## 结论先行

本轮 9 个 Synthetic 文件经真实本地 HTTP 成功上传，HTTP 201；产品创建 `case-20260804-4ec053c985`，9/9 材料均记录 SHA-256、完成文本抽取并进入 `candidate_ready`。但产品目前只完成材料候选识别和工作流投影：证据阶段为 `awaiting_human`，`request_tracking_state=not_implemented`，`open_requests=null`，补件阶段为 `not_available`。

因此，产品原生检测/关闭问题数为 **0/8**。下面 Q01–Q08 的状态是 FA 对可见材料的人工对账，不是产品自动关闭。

## 方法与独立性说明

本轮因并发线程额度已满，复用了现有 specialist thread；没有新建线程，也不声称是全新线程。读取范围仅限 Round 2 的 `company-submission/`、`company-supplement/`、`fa-initial/question_register.jsonl`、运行所需产品代码、相关技能说明和本轮新鲜运行输出；未读取隐藏真值、其他轮次、初始报告/摘要/事件、工程输出或 Git 历史信息。

业务材料均为 **Synthetic**；HTTP 状态、耗时、PID、端口和服务停止结果是 **Real local telemetry**。本轮使用默认 `company_intake`，请求均携带同源 `Origin` 和 `Referer`。未进入 Deal/收购工作流，未执行估值、现金跑道、资金缺口或其他财务结论计算。

## FA 补件对账

| 问题 | FA 状态 | 核心判断 | 仍缺材料/边界 |
|---|---|---|---|
| R02-Q01 主体范围 | partial | 明确选 Standalone | 缺登记、组织结构和合并范围依据；禁止跨主体汇总 |
| R02-Q02 关联主体 | partial | 管理层陈述 SYN-OPS-01 独立并排除 2.0m 销售、0.6m 现金 | 缺法律控制、会计合并、关联交易和资金归属证明 |
| R02-Q03 报告期间 | partial | 锁定 H1 2026；H1 14.6m 与销售表对上，7 月单列 | 缺完整分月 R12M/受控桥；禁止趋势和估值基期 |
| R02-Q04 币种单位 | answered | RMB million 与三种单位换算规则完整 | 只关闭机械换算，不证明底层金额真实 |
| R02-Q05 VAT | partial | 选不含税口径，销售与预测提供 1.13 桥 | R12M 税基、发票/税表及受控 VAT 对账缺失 |
| R02-Q06 现金时点/受限 | partial | 锁定 2026-07-31，2.1m 不受限、1.7m 受限、0.6m 关联方分开 | 缺银行证明、质押协议和交易级现金桥；禁止跑道/缺口计算 |
| R02-Q07 预测版本 | not_available | 两版均未批准，明确不选 | 批准版、变更日志和批准记录不存在/未提供；禁止预测估值 |
| R02-Q08 来源优先级 | partial | 给出优先级及多表桥 | 缺高权威法律/银行/审计证据及完整 R12M 桥；冲突值仍是候选证据 |

计数：`answered=1`、`partial=6`、`contradicted=0`、`not_available=1`、`open=0`。按 `answered=1、partial=0.5、其余=0` 的透明进度公式，得分为 **4.0/8.0（50.0%）**；完全回答率为 **1/8（12.5%）**。这只是补件证据进度，不是投资、信用、估值、综合风险或企业评分。

## 产品行为核验

- 上传：9/9 接受，9/9 哈希记录，9/9 文本抽取，HTTP 201，耗时 0.043733 秒。
- 材料识别：3 个材料含 `financial_core` 候选角色；角色权威均为 `routing_hint_only`，需人工确认。
- 工作流：`materials=complete`、`evidence=awaiting_human`、`analysis=blocked`、`supplements/review/outputs=not_available`。
- 补件原生能力：没有生成 R02 问题登记、没有逐问题状态迁移、没有自动关闭；Dashboard 明确返回请求跟踪尚未实现。
- 能力边界：Agent 输出保持候选证据；未产生聚合评级，未自动升级事实，未授权公开发布。

## 基线判定

这一轮证明了“同一案例一次接收九份异构表格/清单、保留哈希并供人工核对”的通路可运行；尚未证明“补件中心”可运行。FA 侧可把 Q04 视为已回答，其余事项仍需要高权威来源或受控桥接。产品若要完成下一基线，必须原生持久化问题—提交—审核状态，并让自动校验结果与人工接受/退回相互独立、可追溯。

服务端监听 PID `17300` 已核验命令行后停止；启动包装 PID `37692` 也已停止，端口 8882 无残留监听。
