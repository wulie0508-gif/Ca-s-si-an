# Round 1 FA 初始测试报告

## 结论

本轮结论为 **conditional pass（73/100）**。产品能够接收四份材料、保留文件哈希和证据边界、明确显示访谈“尚不足”，并在材料不足时保持 Deal 数量为 0；因此本轮没有创建 Deal，也没有运行估值。

但系统给出的 71.25%“候选材料准备度”不能被当作真实交易准备度。角色识别被提交清单中的元数据和普通财务用语污染，导致 IOI/LOI、尽调、签约交割、并购后整合四个后期阶段在没有相应文件时仍显示 100% 候选覆盖。FA 必须人工过滤这些假覆盖后才能使用诊断结果。

访谈暂不安排，先补件。所有企业业务内容均为 **Management Statement—Unverified**，没有独立佐证；五个访谈入口要求全部缺失。

## 实际运行

- 服务：CleanTech Finance 0.5.0，Python 3.12.13，`127.0.0.1:8871`。
- 隔离工作区：`round-01/runtime/workspace`。
- 真实 HTTP：创建 Case 返回 201；Case、Dashboard、Cases、Deals 和静态 UI 均返回 200。
- Case：`case-20260804-b72e9fcae8`，revision 1。
- 四份上传材料全部为 `ready / candidate_ready`，没有解析 warning，均要求人工复核。
- 受控浏览器运行时没有可用浏览器实例，因此本轮完成真实 HTTP/API 与静态 HTML 检查，但没有完成渲染、点击和视觉可用性验证。
- 指定的 `round-01/runtime/bridge-audit.jsonl` 在 UI 写入后仍未生成。

完整顺序记录见 `events.jsonl`，运行参数见 `run_manifest.json`。

## 材料判断

材料只足以形成初始补件清单，不足以支持商业模式验证访谈，更不足以支持 Deal 或估值。

可确认的仅是文件完整性和算术一致性：

- FY2024、FY2025、H1 2026 的毛利与毛利率按展示精度重算一致；Adjusted EBITDA 减折旧摊销和财务费用可勾稽至净亏损。
- 六个管线机会合计 71.0 MWhth、总金额 74.5 百万元、剩余金额 67.6 百万元；概率加权原始值为 36.865 百万元，展示为 36.9 百万元。
- 这些重算不验证收入真实性、合同约束力、回款、技术性能或管线可实现性。

关键缺口包括：

- 法律主体、股权/UBO、关联方与 IP 权属；
- 资产负债表、现金流、银行流水、受限资金、债务和或有负债；
- 合同/PO、验收、发票、回款、取消/退款条款及收入逐笔勾稽；
- 性能测试边界、原始数据、运行小时、可用率、故障/质保、EHS 和认证；
- 2026 全年与 2027–2029 项目级预测、CapEx、营运资金、现金消耗和融资缺口。

## 系统问题与 FA 问题

系统原样提出的 8 个问题已全部保存在 `question_register.jsonl`。为保持有效问题不超过 8 个，本轮激活 3 个系统问题和 5 个 FA 补充问题：

- 激活系统问题：`SYS-Q03` 行业/技术路线/市场依据，`SYS-Q05` 主体与业务边界，`SYS-Q06` 商业模式与单位经济性。
- 激活 FA 问题：`FA-Q01` 财务来源与流动性，`FA-Q02` 收入和管线验证，`FA-Q03` 技术性能与安全，`FA-Q04` 主体/股权/IP，`FA-Q05` 预测和融资需求。
- 暂缓系统问题：`SYS-Q01`、`SYS-Q02`、`SYS-Q04`、`SYS-Q07` 缺少买方/交易上下文；`SYS-Q08` 更适合作为 FA 内部会议流程问题。

每个问题均记录了理由、所需材料、影响的决策和重算范围。当前 active question 数为 8。

## 主要问题

1. **S1 Critical — 后期阶段假覆盖。** 在没有 IOI/LOI、NDA、尽调、SPA、审批、Closing Checklist 或整合计划时，四个后期交易阶段仍显示 `candidate_coverage_complete=1.0`。
2. **S1 Critical — 元数据/关键词污染角色。** `submission-manifest.json` 因 customer/市场/revenue/legal/policy 被赋予四类业务角色；P&L 中 `Standalone legal entity` 的 legal 触发 governance_legal，并错误覆盖 NDA、授权、SPA、审批和整合要求。
3. **S2 Major — Profile hints 为空。** 公司简介中已有主体、技术、地域和市场描述，但四份材料处理后 `profile_hints={}`，造成重复提问且入口要求无法满足。
4. **S2 Major — 问题路由错位。** 8 个系统问题中 5 个偏买方收购命题、预算/持股、Longlist、交易接触授权或会议流程，挤占企业首包补件问题。
5. **S2 Major — 下一步优先级不当。** 系统显示 7 个 critical gaps 且访谈不足，但 Dashboard 下一步为 `generate_reference_suggestions`，没有优先补齐企业核心证据。
6. **S2 Major — UI 写操作审计文件缺失。** 启动时指定 `--audit-log`，完成 Case 写入后目标文件仍不存在。
7. **OBS — 补件状态机未实现。** `open_requests=null`、`request_tracking_state=not_implemented`，本轮只能使用外部问题登记表。
8. **S2 Test environment — 无浏览器实例。** 视觉和点击交互留待后续轮次复测。
9. **S3 Minor — 健康检查受 RAG 超时拖慢。** 首次 5 秒请求超时，后续请求约 8.3 秒成功；没有阻断上传。

## 评分

| 维度 | 得分 |
|---|---:|
| 盲测边界与证据权威 | 15 |
| 材料接收、身份与来源 | 15 |
| 缺口、问题与补件质量 | 8 |
| 访谈准备度解释 | 10 |
| Deal / 估值 fail-closed | 20 |
| 回放性与效率 | 5 |
| **总分** | **73** |

通过条件：FA 必须继续人工过滤假阶段覆盖与错路由问题；在独立主体、现金流/资产负债、合同验收、技术/IP 和可审计预测材料补齐前，不得把 71.25% 或后期阶段 100% 当作可交易、可访谈或可估值结论。

## 回放材料

- `run_manifest.json`：运行环境、服务、Case 与 API 记录。
- `input_manifest.json`：输入文件、哈希、证据权威与算术检查。
- `events.jsonl`：按序事件与实际观察。
- `question_register.jsonl`：系统原题、FA 新增问题、理由、材料和重算范围。
- `round_initial_summary.json`：机器可读结论、问题与评分。

本报告没有读取或引用公司私有材料、隐藏真值、其他轮次、其他 Agent 输出或工程审计结论。
