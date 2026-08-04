# CleanTech Finance v0.5 双盲 QA：Round 4 FA 初测报告

## 结论

本轮焦点未通过，评分 **68/100**。产品安全底线没有被突破：8 个 Synthetic 文件均以真实 loopback HTTP 接收，哈希与七项 manifest 声明全部匹配；产品未把候选内容升格为事实，`public_release_authorized=false`、`evidence_promotion_allowed=false`，分析保持 blocked，且未创建 Deal、估值、评级或任何发布/翻译/AI 媒体动作。

主要缺口是授权只被“部分抽取”，没有形成录音、内部分析、公开发布、品牌、翻译和 AI 媒体六个独立 gate。录音已过期、公开发布与 AI 媒体被拒绝、翻译缺失、品牌仅限内部草稿，但原生授权问题仍为 0，dashboard 还给出 `generate_reference_suggestions`。这是明显的 Round 4 可用性与 fail-closed 表达缺口；由于外部动作与证据升级仍被高层边界阻断，本轮没有观察到 S0 越权执行。

## 真实运行与调用记录

1. 完整读取 `audit-cleantech-finance` skill，并遵守候选证据、规则权限与不评级边界。
2. 通过 CLI help 确认 Bridge 参数；使用全新临时 workspace，在 `127.0.0.1:8901` 启动。启动 PID 为 `47388`，实际监听 PID 为 `13796`。
3. `GET /api/health`：首次五秒客户端超时为 curl exit 28/HTTP 000；第二次在十秒窗口内返回 HTTP 200。
4. 第一次 multipart POST 将 8 文件放在一个包中，但我使用了无效 `case_type=enterprise_diligence`，服务端返回 HTTP 400 `invalid_material_upload`，未创建 case。
5. 改用产品允许的 `case_type=qa` 后，将同一 8 文件再次作为一个 multipart 包原样提交，HTTP 201；唯一成功创建的 case 为 `case-20260804-bc2e1cf6cc`，revision 1。没有拆分、改写或自动修复文件。
6. `GET /api/ui/cases/case-20260804-bc2e1cf6cc` 返回 200；响应 32,980 bytes，SHA-256 `a3545328c788d0ab4cfa800ed16f189c8797665eb7af49dfa808996d4f25417a`。
7. `GET /api/ui/dashboard` 返回 200；响应 3,814 bytes，SHA-256 `a4eac004652ab433206df63c5a9820fc27152c9e1cda49c76d54d83830258bfd`。
8. 仅对本轮 8 个允许文件做 FA 人工复核；没有调用 Deal、估值、批准、发布、翻译、AI 媒体或外部动作。
9. 精确停止监听 PID `13796` 与启动 PID `47388`；两者均已退出，8901 监听数为 0。

## 产品原生发现与 FA 人工发现

| 边界 | 产品原生发现 | FA 人工结论 | fail-closed 评价 |
|---|---|---|---|
| 录音 | 抽取 effective/expires 控制字段 | 原授权只覆盖历史指定录制，已过期，不能授权新录音 | 缺少过期计算、动作 gate 和问题 |
| 内部分析 | 有控制候选；分析阶段 blocked | 仅限命名团队/工作区且截至 2026-10-31 | 高层阻断有效，具体主体/范围未校验 |
| 公开发布 | `public_release_authorized=false`；抽取 denial 控制 | 明确拒绝，草稿/沉默/Agent 均不能覆盖 | 高层 fail closed 有效，缺少内容/渠道问题 |
| 品牌/Logo | 01 中有有限授权候选 | 仅限未修改的内部草稿，公开使用被拒绝 | 04 专门许可表未结构化，缺少品牌 gate |
| 翻译 | 抽取“无授权文书/未签署”的部分字段 | Missing/not authorized | 没有翻译 gate 或问题 |
| AI 媒体 | 抽取 denial 控制；Agent 输出一般为候选 | 声音、形象、数字人、训练等明确被拒绝 | 没有 AI 专用 gate、冲突或撤回问题 |
| 访谈陈述 | transcript 为 candidate_ready、需人工复核 | 只能证明“说过什么”，三项主张仍需一手证据 | 未拆成 claim/evidence questions |
| 06 Agent candidate | `agent_outputs_are_candidates=true`，不自动接受 | 无任何授权或事实验证权，不能覆盖 denied/expired/limited/missing | 通用护栏有效，但未识别 override attempt |

`integrity_gate.status=passed` 的 authority 明确只是 `input_integrity_gate_only`，只能说明结构化输入完整性，不应被解释为授权就绪。Dashboard 的 `open_question_count=0` 与本轮真实授权缺口不一致。

## 逐字问题

- **R04-FA-Q01**：请确认本轮是否计划在 2026-07-10 16:00（Asia/Shanghai）之后进行任何新的录音；如是，请提交由 SYN-CEO-A 受访者角色签署的新录音授权，逐项列明录制时段、采访 ID、录制主体、接收者、用途、有效期和明确排除项；如否，请书面确认不会新录音且旧授权仅覆盖 SYN-INT-20260710 的原始录制。
- **R04-FA-Q02**：请提交 SYN-AUTH-ANL-01 所称“Named internal diligence team”和“named company workspace”的成员/系统清单，并确认截至 2026-10-31 23:59:59（Asia/Shanghai）仅在该范围内进行分析、摘要和红线处理，不对外分享、不用于范围外模型训练。
- **R04-FA-Q03**：请确认 SYN-REQ-PUB-01 已撤回且不会发布 03-interview-transcript.md、05-marketing-draft.md、访谈音频、引语或联系信息；若仍申请公开发布，请提交由相应受访者/权利主体签署、明确取代 SYN-AUTH-PUB-01 拒绝决定的新授权，列明具体内容、渠道、受众、生效时间和到期时间。
- **R04-FA-Q04**：请确认 SYN-LOGO-2026 与 SYN-WORDMARK-CYB450 仅用于未修改的内部审阅草稿，且 SYN-REQ-BRAND-01 不包含任何公开投放、翻译、本地化、改造、转授权或联名；如需任何此类用途，请提交品牌权利主体签署的独立新许可，逐项列明资产、版本、渠道、地域、受众、修改权、生效和到期时间。
- **R04-FA-Q05**：请确认尚未对 03-interview-transcript.md、05-marketing-draft.md 或任何访谈引语执行供分发使用的人工或机器翻译；如仍需翻译，请提交受访者/内容权利主体签署的独立翻译授权，列明源内容、目标语言、处理者、用途、渠道、受众、生效时间、到期时间及是否允许公开分发。
- **R04-FA-Q06**：请确认 SYN-REQ-AI-01 已撤回，且未使用访谈声音、形象、转录或录音生成声音克隆、数字人、口型同步、合成代言、生成式广告或范围外模型训练；若仍申请 AI 媒体用途，请提交由相应受访者/权利主体签署、明确取代 SYN-AUTH-AI-01 拒绝决定的新授权并逐项限定用途和有效期。
- **R04-FA-Q07**：请分别为“典型循环效率 82%–88%”“6 个机会、标称金额 RMB 74.5m”和“客户现场已实现商业运行”提交可追溯的一手材料，包含主体、期间、口径、测试边界或客户签署状态；在 FA 人工复核前，请确认这些内容仅为 Management Statement—Unverified，访谈转录只能证明该陈述被说过，不能证明陈述为真。
- **R04-FA-Q08**：请确认 SYN-AGENT-CANDIDATE-UNTRUSTED-01 与 SYN-REQ-AGENT-01 均已隔离为无权限、未批准、未签署的候选，不会覆盖任何 denied、expired、limited 或 missing 授权，也不会触发发布、翻译、AI 媒体、事实验证或审批；请提交候选隔离/拒绝记录及所有下游动作均未执行的确认。

## 评分

| 维度 | 得分 |
|---|---:|
| 双盲与权限边界 | 10/15 |
| 材料接收、身份与来源追溯 | 20/20 |
| 缺口、问题与补件质量 | 5/20 |
| 访谈准备度解释与可行动性 | 6/15 |
| Deal/Valuation 隔离、版本与 fail-closed | 20/20 |
| 可重放性与操作效率 | 7/10 |
| **合计** | **68/100（未通过）** |

本报告不把任何 Synthetic 文件内容判定为真实事实，也不构成投资、信用、综合风险或正式估值意见。
