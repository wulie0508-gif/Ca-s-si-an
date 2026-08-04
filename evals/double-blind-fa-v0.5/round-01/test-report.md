# Round 1 双盲迭代报告｜企业首包与补件路由

日期：2026-08-04
版本：CleanTech Finance 0.5.0 working branch
结论：通过，但仍有重要产品缺口
最终独立盲测分：88/100

## Executive Summary

第一轮完成了“企业初始提交 → FA 问询 → 企业补件 → FA 基线复测 → 工程修复 → 全新 FA 重放”的完整闭环。

初始系统能够正确保留管理层陈述边界，并在材料不足时拒绝创建 Deal 或估值；但粗粒度关键词把普通材料错误映射到后期交易阶段，使候选材料准备度被抬高到 71.25%，IOI/LOI、尽调、签约交割和并购后整合甚至显示为 100% 候选覆盖。补件增加到 13 份后，这个失真没有自行消失，产品基线分反而降至 53/100，因为真正回答的问题未被关闭、买方问题仍被错误置前。

工程修复后，同样 13 份材料在默认 company_intake 模式下明确显示“收购工作流不适用”，不再输出虚假的并购百分比或买方问题；在显式 acquisition 模式下，全部材料只作为 routing candidates，具体 requirement coverage 保持 0%，系统继续 fail-closed。修复后独立 FA 评分为 88/100，比补件后工程基线提高 35 分。

本轮材料全部为合成企业数据。真实的是本地软件执行、HTTP 请求、文件哈希、问题登记、补件状态、工程复现、测试结果和浏览器观察；本轮不能被描述为真实企业验证。

## 测试设计与隔离

- 企业侧只生成提交材料和按精确问题补件，不读取 FA 或工程产物。
- FA 侧只读取主协调者明确授权的材料路径，不读取隐藏真值或工程结论。
- 工程侧只读取 FA 可见报告、事件和产品代码，不读取企业隐藏真值。
- 一次 FA 父上下文因状态工具意外回显其他角色摘要而被动污染；该运行在读取补件前即停止，产物被排除，并由 fork_turns=none 的全新 Agent 从零重放。事件见上层 protocol-events.jsonl。
- 所有公司材料均标为 Synthetic；隐藏真值未写入仓库。

## Phase 1｜初始材料

企业侧提交 3 份业务材料和 1 份提交 manifest。4/4 文件的字节数和 SHA-256 独立复核一致。

FA 通过真实本地 HTTP 创建 Case，逐项保留系统原问题、FA 补充问题、所需材料、原因、影响判断与重算范围。8 个有效问题为：产业链/技术路线/市场依据、主体边界、商业模式、财务与流动性、收入与管线、技术性能、股权/IP、预测与融资缺口。

初始结论为 73/100、有条件通过：

- 正确行为：没有把管理层陈述升级为事实；访谈状态为尚不足；Deal 为 0；未执行估值。
- 关键缺陷：候选材料准备度 71.25%；四个后期阶段被错误显示为 100%；8 个系统问题中 5 个与无买方的企业首包错配；下一步优先参考检索而不是关键补件。

## Phase 2｜企业补件与工程修复前基线

企业侧仅依据 8 个精确问题补交 8 个 payload 和 1 个 supplement manifest。补件状态为 full 2、partial 6；不存在、未签署或未完成的材料被明确披露，没有为了提高分数而补造事实。

补件后，8 个问题由 FA 独立标记为：

| 状态 | 数量 | 含义 |
|---|---:|---|
| answered | 2 | 在 Synthetic 场景内逐字段回应，但不自动升级为现实独立事实 |
| partial | 3 | 已提供核心信息，仍缺审计、完整底稿、独立研究或正式批准 |
| contradicted | 3 | 新材料实质推翻首包中的商业、收入或技术口径 |
| open | 0 | 本轮没有完全未回应的问题 |

可观察重算包括：H1 2026 收入从 14.6m 调整为 8.8m，毛利率从 30.1% 调整为 3.4%；不受限现金为 2.5m，对应约 1.72 个月 OCF-only runway、含 CapEx 约 1.35 个月；现场九个循环效率均低于 82% 合同门槛。上述为合成材料的算术与情景判断，不是现实企业结论。

产品基线分降至 53/100，原因不是“补件让企业更差”，而是产品未能把补件映射回问题关闭和材料门槛：三个已有明确补件的 requirement 仍为 missing，全部八个系统问题原样重生，技术验证包未正确路由，补件状态只能保存在外部 question register。

## 工程处置

| 问题 | 工程判定 | 处置 |
|---|---|---|
| R01-01 粗角色直接形成阶段覆盖 | 规则契约 bug | 收购规则升至 1.2.0；只有当前版本的显式 requirement candidate 才可计覆盖 |
| R01-02 控制元数据/弱关键词污染 | 确定性路由 bug | manifest/index/readme/清单/目录不参与业务路由；单个弱通用词不再触发 |
| R01-04 无交易场景仍跑八阶段 | 工作流适用性 bug | 新增显式 workflow_type；company_intake 默认 fail-closed，acquisition 必须主动选择 |
| R01-05 参考建议抢占关键缺口 | 下一步优先级 bug | 抽取失败 > 关键证据/访谈不足 > 参考生成 |
| R01-03 Markdown profile hints | 产品格式契约 | 未用宽松正则猜事实；保留待设计 |
| R01-08 UI 写操作统一审计 | 路线图 | 未创建空 audit 文件冒充修复 |
| R01-09 RAG health 延迟 | 产品健康契约 | 未仅缩短 timeout 冒充架构修复 |

## Phase 3｜修复后独立重放

全新无历史 FA 使用同一批 13 份材料完成两条真实 HTTP 路径：

1. company_intake：acquisition applicability 为 not_applicable，percent 为 null，不生成收购买方问题；材料完成、证据待人工、分析阻断，未建 Deal、未估值。
2. 显式 acquisition：13/13 文件接收，但 requirement candidates 为 0，覆盖率为 0.0%，22 个 critical gaps 未关闭，访谈仍不足；未建 Deal、未估值。

最终盲测分 88/100。分数提高来自适用性、证据权威和 fail-closed 语义变得正确，不来自把材料或企业结论“调好看”。

## 验证门禁

- Python：366 项，全部通过。
- Node browser-local valuation：6 项，全部通过。
- Ruff：通过。
- git diff --check：通过。
- 真实浏览器：主页和 Companies 页面正常加载；非空白；无框架错误 overlay；捕获到的 console errors 为 0；工作流默认企业首包整理，显式收购选项可选择；导航正常。

## 仍然缺少的能力

- company_intake 独立 readiness、材料门槛和问题集；当前只明确表明 acquisition 不适用。
- artifact role 经人工确认后晋级为具体 requirement candidate 的受控桥梁。
- profile hints 的严格结构化输入合同。
- 企业补件中心持久状态机、request 与 submission 关联、责任人、截止日、版本、退回原因和 waived/not-applicable 理由。
- 统一 append-only 用户操作审计，以及问题/补件在产品内的 answered、partial、contradicted 生命周期。
- RAG liveness/readiness 拆分与异步健康状态。

这些缺口均未被本轮包装成已实现能力。

## 下一轮

Round 2 使用新的 Synthetic 多表导出测试期间、币种、单位、主体范围、含税/不含税、预测版本与受限现金冲突。系统和 FA 必须先锁定口径再计算；任何静默选择最大值、最新值或名称近似值都应 fail-closed。

## 证据索引

- 初始 FA：fa-initial/
- 补件后工程基线：fa-supplement-baseline/
- 工程复现与修复：engineering-review.md
- 修复后独立重放：fa-postfix/
- 机器结论：round-result.json
