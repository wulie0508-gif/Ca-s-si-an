# Round 3 修复后 FA 独立重放报告

## 结论

**本次限定范围的证据控制回归门通过：17/17 项断言通过。** 这不是企业评分、产品总评级、投资/信用/综合风险评级或估值意见。案例的输入完整性门仍为 `blocked`，这是预期且正确的结果：修复后的系统没有用补件覆盖原始错误，也没有自动挑选“真值”。

本轮复用了安全/证据边界 specialist thread；该 specialist 未参与 Round 3 数据生成或工程修复。读取与写入均遵守指定白名单，未读取 Round 4/5、隐藏真值、Git diff/历史或其他代理输出，未改代码、未提交 Git。

## 真实重放

- 使用全新临时 workspace 与 `127.0.0.1:8893`。
- 单次 `company_intake` multipart 请求原样上传 21 个物理文件，HTTP `201`。
- 两份同名 `07-artifact-provenance-and-duplicates.csv`、两份同名 `submission-manifest.json` 及两份原生 `.jsonl` 均未改名、未折叠。
- `/api/ui/cases/case-20260804-aebb5f7120` 与 `/api/ui/dashboard` 均返回 `200`；21 个 artifact 全部保留并为候选材料。

## 完整性、重复与来源

初始 manifest 仍明确记录 07 的声明哈希 `...d0b4` 与实际哈希 `...d0b3` 为 `mismatch`。补件 manifest 对同一实际文件正确声明 `...d0b3` 并显示 `matched`，但没有抹除初始 mismatch；合并结果为 18 个 matched、1 个 mismatch，输入完整性门继续阻断。

两份 07 都进入 quarantine。它们因实际 SHA-256 相同，被保留为两个 alias、一个候选证据单元、零个已接受证据单元，且 canonical artifact 仍为空。按索引行身份去重后，只保留唯一的 P2602 declared-underlying group；其底层哈希 `8c0f...e930a` 没有对应上传 payload，且来源索引被隔离，因此状态为 `missing`、候选计数 0、接受计数 0。

## 权威、版本与冲突

系统独立保留 `version`、`as_of_date`、`effective_date`、`approval_status`、`signature_status`、`authority_class` 与 `assertion_status`。v1.0 与 v1.1 均可见，但 `selected_authoritative_artifact_id` 和财务预测 `selected_version` 都为 `null`。

共形成 25 个显式未决结构化冲突，其中 20 个为同一 FY 的预测指标冲突；CEO-founder 45.0/43.5 与 ESOP 8.5/10.0 也作为独立 cap-table 冲突保留。系统未按版本号、日期、批准或签字自动选赢家。

## 问题、回执与财务预检

证据控制问题稳定为 `R03-Q01`、`R03-Q02`、`R03-Q03`、`R03-Q04`，全部保持 open。34 个候选 response receipt 中，`accepted_as_truth=true` 与 `question_closed=true` 均为 0。

财务预检只识别两份 board plan：artifact-0003 与 artifact-0004。预测版本为 1.0、1.1，未选择版本；现金候选为 0；计算门为 `blocked`。管理层现金陈述没有被提升为账户级 treasury 事实。

## Dashboard 与安全边界

案例的嵌套 dashboard 与 `/api/ui/dashboard` 均给出：

- `next_action = review_evidence_control_questions`
- `operational_status = evidence_control_review_required`
- `responsible_actor_type = human`

案例顶层旧的通用 `next_action` 仍为 `confirm_material_scope`；本次指定 dashboard 合约已通过，该差异作为非阻断观察保留。

没有发生财务计算、Deal、估值、评级、自动事实接受、自动冲突/权威选择或公开发布。企业与业务材料均为 **Synthetic**；HTTP 状态、case ID、系统计算哈希、诊断与 dashboard 是 **真实本地产品遥测**。

最终 Bridge 进程 PID `42272` 已精确停止，8893 端口剩余监听数为 0。
