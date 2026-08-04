# Round 3 企业补件前修复基线报告

## 结论

本轮已在全新临时工作区通过 `http://127.0.0.1:8892` 真实提交 Round 3 初始材料和补件材料，使用默认 `company_intake`，请求同时携带同源 `Origin` 与 `Referer`。结果不是“补件已验收”，而是：**8 个 FA 问题都有企业回应，但只有 1 个 answered、3 个 partial、4 个 not_available；权威证据包仍不完整。**

产品的核心安全边界保持正确：没有自动接受事实、没有自动选择候选口径、没有财务计算、没有 Deal 或估值、没有投资/信用/综合风险评级，也没有公开发布授权。另一方面，补件包不能原样进入单一案例，补件状态机和问题绑定也尚未落地。

本报告只衡量证据工作流完整度，不评价企业质量或交易价值。全部业务数据均为 synthetic。

## 真实 HTTP 运行记录

- 21 个物理文件原样提交：HTTP 400，产品提示最多 20 个文件。
- 经评估方 SHA-256 验证，初始包和补件包中的 `07-artifact-provenance-and-duplicates.csv` 是完全相同的 3,411 字节文件。为进入后续观察，仅在主案例中折叠补件副本；这不是产品自动去重。
- 折叠后 20 文件仍被拒绝：产品不支持 `.jsonl`。
- 保留原字节、仅将两个 JSONL 传输名改为 `.jsonl.txt` 后，主案例创建成功：`case-20260804-cb065319bc`，20 个 artifact，revision 1。
- 单独建立双副本控制案例 `case-20260804-b122748436`：产品把相同 SHA-256 的两份 07 文件保存为两个独立 artifact，证明当前没有按内容哈希去重。
- 8892 的监听 PID 24808 已被精确停止；复核后剩余监听数为 0。

主案例中的 `.jsonl.txt` 只能按纯文本识别，不能视为结构化响应登记或系统事件。因此，本报告中的 Q01–Q08 分类是 FA 人工证据工作流判断，不是产品状态机输出。

## 八个问题的补件结果

| 问题 | 优先级 | 分类 | 本轮得到什么 | 仍缺什么 |
|---|---|---|---|---|
| R03-FA-Q01 | critical | partial | 修正后的包级 07 哈希、P2602 canonical 元数据指定 | 两份底层 PDF 均未提供，声明的底层哈希不能独立复算 |
| R03-FA-Q02 | critical | not_available | 明确说明验收/调试/缺陷关闭/保留款释放证据不可得，并撤回验收主张 | 没有交易对手级验收或释放证据 |
| R03-FA-Q03 | critical | not_available | P2602/P2603 对账表及订单/积压主张撤回 | 没有已执行 PO、有效订单排期、条款或对手方确认 |
| R03-FA-Q04 | critical | partial | 声明 v1.0 为基线，提供 v1.0→v1.1 行级桥接和来源优先顺序 | 缺董事会决议和签字页；产品也未识别版本、批准或 precedence |
| R03-FA-Q05 | critical | not_available | 明确说明银行/总账证据不可得，撤回 RMB 4.4m 可用现金主张 | 缺账户、主体、日期、受限状态和 GL 支持 |
| R03-FA-Q06 | high | partial | 提供 1.2→2.0 股权数值桥接 | 缺当前批准 cap table、股东批准、期权台账和权威登记 |
| R03-FA-Q07 | high | not_available | 列明 IP、质押解除和共同申请人证据缺口，撤回 free-and-clear 主张 | 缺官方登记、贷款人解除及转让/许可文件 |
| R03-FA-Q08 | high | answered | 按问题允许的替代路径，书面确认没有最终 SEA licence，MOU 不具约束力，并撤回许可主张 | 该确认仍是企业陈述，不是对手方确认或许可权利证明 |

这里的 `answered` 只表示问题要求的“无最终许可书面确认”已收到，不表示存在许可，也不表示该陈述已经被外部证明。

## 证据进度的透明计算

采用两项互不替代的流程指标：

1. 回应覆盖率 = 有可见企业回应的问题数 / 8 = 8 / 8 = **100%**。
2. 证据包进度 = `(1.0 × answered + 0.5 × partial + 0 × contradicted/not_available/open) / 8` = `(1 + 1.5) / 8` = **31.25%**。

第二项权重只用于透明表达“请求的证据包完成到什么程度”。它不是企业评分、投资评级、信用评级、综合风险评级或投资建议；`not_available` 虽对澄清主张很重要，但不等于请求的权威证据已经取得，所以本公式不给完成分。

## 哈希、重复与底层证据

初始 manifest 对 07 文件声明的 SHA-256 以 `...d0b4` 结尾，而实际字节、产品记录和补件 manifest 均以 `...d0b3` 结尾。产品正确记录了实际 SHA-256，但没有比较 manifest 声明值，也没有产生告警。

07 文件中的两条 P2602 记录声明相同底层 `artifact_content_sha256`：

`8c0f7a231c8d0449a4d622f24f0e37d1ebbd5cc3b2f96997d1dd65df5d1e930a`

因为底层 PDF 未随包提供，该值只能支持“企业提交了一个重复分组声明”，不能支持“底层合同已经验证”。产品也没有解析该底层哈希进行去重。控制案例进一步证明，即使两个上传文件的实际 pack-level SHA-256 完全相同，产品仍保留两个 artifact。

## 权威性、版本与冲突处理

产品保存了上传文件名、字节数、实际 SHA-256、候选路由角色和有限的财务口径候选；但没有把 `authority_class`、`version`、`approval_status`、`signature_status`、`effective_date` 与 `as_of_date` 分离成可审计的结构化证据控制。

具体表现：

- 材料中同时存在 forecast v1.0、v1.1、批准/签字声明和版本桥接，产品仍输出 `forecast.status = not_present`、0 个 forecast candidate。
- 补件中有明确来源优先顺序，产品仍输出 `source_precedence.status = not_declared`。
- 产品没有生成 P2601 验收、P2602/P2603 订单、现金、股权、IP、SEA licence 等跨表冲突结论或 R03 问题绑定。
- 企业的撤回声明应作为候选负面证据保留，不能覆盖原始材料，也不能自动升级为事实。

## 通用 `as_of_date` 的误触发

产品把 8 个 artifact 判为 `explicit_structured_financial_metadata_detected`，其中管理层主张、交易对手证据、公司登记和 provenance index 的通用 `as_of_date` 行也被当作财务口径记录。随后系统生成的是 R02-Q01、R02-Q03、R02-Q06、R02-Q08 四个通用财务口径问题，而不是本轮 R03-FA-Q01–Q08。

这说明当前预检的 fail-closed 结果是安全的——计算被阻断——但适用性识别过宽，会给非财务表格制造噪声。

## 自动状态与能力边界

主案例实际状态为：materials `complete`、evidence `awaiting_human`、analysis `blocked`，而 supplements/review/outputs 均为 `not_available`。补件文件虽然已经上传，系统仍没有把它们持久化为 `partially_submitted`、`submitted`、`needs_revision`、`accepted/rejected/waived` 等补件状态，也没有自动关闭任何 R03 问题。

这正是修复前应保留的基线：产品目前是“文件级摄取 + 候选识别 + 财务口径阻断”，还不是“问题—补件—版本—审核—局部重算”的补件中心。

## 文件索引

- `input_manifest.json`：21 个源文件的实际字节数、实际/声明哈希及透明传输映射。
- `events.jsonl`：HTTP 拒绝、主案例、重复控制、预检和监听释放事件。
- `question_register_after.jsonl`：8 个问题的逐项分类、剩余缺口与人工处置。
- `round_baseline_summary.json`：机器可读的完整基线摘要与进度公式。
- `run_manifest.json`：白名单、运行环境、边界和六个输出清单。

本轮没有修改任何产品源代码，也没有读取禁止目录、Git 历史或隐藏真值。
