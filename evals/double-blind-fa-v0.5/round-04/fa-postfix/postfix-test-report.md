# CleanTech Finance Round 4 修复后 FA 独立重放

## 结论

**本次 scoped regression 通过，20/20 项断言通过。** 这是对 Round 4 内容授权修复的范围化回归结论，不是企业评级、产品评级、投资/信用/综合风险评级，也不是估值意见。

本次复用了同一个 FA specialist task；该 FA 参与过初测，但**未参与工程修复，也未参与企业补件生成**。所有业务材料均为 Synthetic；HTTP、进程、端口、哈希与本地持久化状态是本轮真实本地遥测。

## 重放路径

- 全新临时 workspace；Bridge 绑定 `127.0.0.1:8903`。
- 首包 8 文件与补件 8 文件在唯一一次 multipart POST 中原样上传；两个同名 `submission-manifest.json` 保留为 `artifact-0008` 和 `artifact-0016`，两份 JSONL 保持原生格式。
- POST 返回 201，case 为 `case-20260804-f49209cc30`、revision 1；case GET 与 dashboard GET 均为 200。
- 16/16 文件名、字节数与 SHA-256 同 HTTP artifacts 一致；两个 manifest 共声明的 14 个 payload 全部匹配。
- 只读检查确认 Deal 数为 0，未调用 Deal、估值、批准、发布、翻译或 AI 媒体写操作。
- 启动 PID `12564`、实际监听 PID `22792` 均已精确停止；8903 监听数为 0。

## 核心断言结果

| 断言 | 结果 | 真实观察 |
|---|---|---|
| 16 artifacts/hash | PASS | 16/16 全匹配；manifest reconciliation `passed` |
| authorization diagnostic / as_of | PASS | `2026-08-04T14:57:16.124308Z` 在 POST、case、dashboard、workspace.json 完全一致 |
| Recording | PASS | `expired`；general action 未授权 |
| Internal analysis | PASS | `active_scoped_grant`；仍为候选、未选定、非一般授权 |
| Public release | PASS | `denied`；`public_release_authorized=false` |
| Brand and logo | PASS | `mixed_scope_control`，同时保留 `limited` 与 `denied` |
| Translation | PASS | `missing`；未执行翻译 |
| AI media | PASS | `denied`；未生成 AI 媒体 |
| R04-Q01..Q08 | PASS | 顺序稳定，8 个全部 open，0 closed/accepted-as-resolved |
| Company receipts | PASS | 8 个全部为 candidate receipt；授权接受、事实接受、问题关闭均为 0 |
| Content requests | PASS | 6/6 blocked；0 authorized action、0 executed action |
| Agent override | PASS | 1 个冲突，`artifact-0006` 隔离；不影响权限、不执行下游动作 |
| Transcript boundary | PASS | 只形成 1 个 statement-made candidate evidence gap；未验证、未接受为事实 |
| Dashboard priority | PASS | `next_action=review_content_authorization`，责任主体为 human |
| Evidence integrity | PASS | integrity `passed` 但 `evidence_promotion_allowed=false` |
| Finance/Deal/valuation/rating/publication | PASS | 财务不适用、无计算、无 Deal/估值/评级/发布 |

逐条机器可审计证据见 `assertions.jsonl`。

## exact-scope 边界说明

HTTP fixture 中 `SYN-REQ-INT-01` 与 `SYN-REQ-BRAND-01` 自称 “Allowed within scope”，但两者都被产品判为 `scope_not_exactly_matched`，并保持 `blocked=true`、`accepted_as_authorized_action=false`、`action_executed=false`。因此，企业自称范围内不能构成批准。

本组 16 文件没有产生 `within_explicit_scope_candidate=true` 的请求，故该真值分支未被 HTTP fixture 直接命中。为覆盖用户指定边界，核对了当前 `_resolve_request` 契约：即使精确匹配，结果也仅为 `within_explicit_scope_candidate`，同时固定 `blocked=true`、`requires_human_acceptance=true`、`accepted_as_authorized_action=false`、`action_executed=false`。这是覆盖说明，不把源代码检查冒充 HTTP 命中。

## 补件与权限边界

补件 manifest 自称 7 answered、1 partial、0 open，但产品没有把企业自报状态当作权威：R04-Q01..Q08 仍全部 open，8 个 response receipts 均未被自动接受或关闭。Q07 的三项访谈/营销主张只形成证据缺口；转录仅能证明陈述被记录，不能证明陈述为真。

录音过期、公开发布拒绝、翻译缺失、AI 媒体拒绝均 fail closed。内部分析与内部品牌用途即便存在范围化候选，也没有变成一般许可或自动批准。Agent override 被识别、隔离并确认对六类矩阵无影响。

## 保留观察

Dashboard 与 case 内嵌 dashboard 的下一步均为 `review_content_authorization`；case 顶层通用 `next_action` 仍为 `confirm_material_scope`。这不影响本次明确要求的 dashboard 断言，但后续可统一两个 projection 的文案优先级。

本报告不把任何 Synthetic 企业陈述判定为真实事实，也不形成任何企业、产品、投资、信用、估值或风险评级。
