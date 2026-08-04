# Round 2 FA 初测｜财务口径冲突

日期：2026-08-04
产品基线：`85798d0`
结论：需要工程修复
初测分：48/100

## 真实性与转录说明

企业材料全部为 Synthetic。Case 创建、HTTP 状态、文件接收、哈希、工作流状态、系统问题数、Deal/估值数量均来自真实本地执行。

本次操作由无历史上下文的干净 FA 子代理完成。该子代理在完成 Case 与观察后卡在报告写入阶段，主协调者终止了卡住进程，并仅依据已经返回的子代理遥测与持久化 `workspace.json` 转录本目录六个文件。没有重跑基线，也没有读取企业隐藏真值、Round 1、Round 3 或工程结论。

## 实际操作与结果

1. 在 `127.0.0.1:8881` 启动独立本地工作区并检查 health，HTTP 200，RAG 状态为 ok。
2. 第一次 Case 写请求因缺少同源头被拒绝，HTTP 400、`ui_origin_required`；补充 Origin/Referer 后成功。
3. 使用默认 `company_intake` 创建 `case-20260804-a437a545de`。
4. 5 份 CSV 与 1 份 manifest 全部接收，6/6 为 ready/candidate_ready，系统存储 SHA-256 与输入一致。
5. 系统问题数为 0。Case 的下一步仅为“确认材料识别范围”，Dashboard 为“生成参考建议”。
6. 工作流为 materials complete、evidence awaiting_human、analysis blocked；没有创建 Deal，没有执行估值或任何跨表计算。

## 输入中可见但系统未提示的冲突

- 主体：Standalone 与包含 SYN-OPS-01 的 management group view 并存。
- 期间：H1、截至 7 月的 YTD、R12M、FY2026E/FY2027E 并存。
- 单位：yuan、thousand、million 并存。
- 税基：不含 VAT、含 13% VAT、双列与未说明并存。
- 时点：现金至少包含 2026-06-30 与 2026-07-31 两个时点。
- 可用性：总现金、质押受限现金和 management-available 同时存在。
- 预测：V1 与 V2 的日期、主体、单位、税基和数值不同，且两版均未批准。
- 来源优先级：没有跨表对账桥，也没有授权系统按最新、最大或名称相近值静默选取。

## FA 精确追问

| ID | 优先级 | 要锁定的口径 |
|---|---|---|
| R02-Q01 | Critical | 本轮法律主体与合并范围 |
| R02-Q02 | Critical | SYN-OPS-01 的法律、控制和会计关系 |
| R02-Q03 | Critical | H1 / YTD / R12M / forecast 的可比期间 |
| R02-Q04 | Critical | RMB 的 yuan / thousand / million 统一单位 |
| R02-Q05 | Critical | 含税、不含税与双列 VAT 桥接 |
| R02-Q06 | Critical | 同一评估日的可用/受限现金 |
| R02-Q07 | Critical | 预测版本、主体、税基与批准状态 |
| R02-Q08 | High | 来源优先级与跨表对账 |

逐字问题、所需材料、未解决影响和局部重算范围见 `question_register.jsonl`。

## 正确行为

- 管理层或企业准备材料没有被升级为独立事实。
- 所有文件保留 SHA-256 和候选证据权威。
- `company_intake` 没有误跑收购八阶段。
- 在口径未锁定时没有建 Deal、估值或计算。

## 需要修复

1. 为企业首包增加确定性的财务口径预检，读取明确字段而不是猜测正文。
2. 对主体、期间、单位、VAT、时点、受限现金与预测版本形成结构化冲突列表。
3. 任何关键口径存在多个值或未说明时，明确输出 `calculation_status: blocked`。
4. 系统直接生成可提交给企业的精确追问，并让关键口径问题优先于参考建议。
5. 后续补件必须能逐项回答问题并触发限定范围的重算，而不是重新生成同一批开放问题。

这些改进不能把候选数据自动升级为事实，也不能绕过人工确认、正式估值意见或发布授权。
