# CleanTech Finance｜Deal Execution Cockpit P0 实现与复核说明

日期：2026-08-03
依据：`CleanTech_FA_交易执行与估值模块优化需求_v0.1.md`
用途：项目负责人验收、同事试运行、Claude 独立代码审视

## 1. 结论先行

本轮把原先“材料覆盖提示”向前推进成了一个本地可运行的交易与估值闭环：FA 可以建立独立交易、人工确认交易阶段、建立估值案例、确认带来源的输入、运行服务端确定性计算、查看独立状态、保留不可覆盖版本、完成人工复核与内部批准，并导出带公式和审计信息的 XLSX。

这个闭环仍然是 **screen-grade 的内部工作工具**，不是正式估值意见、公平性意见、投资评级或董事会批准工具。当前没有团队身份认证，因此对外批准被主动关闭；本地 UI 中的操作身份只是服务端固定的本地 FA 身份断言，不能冒充企业级权限系统。

## 2. 对象边界

```text
Company
├── Case：材料、主张、证据、诊断、访谈与补件上下文
└── Deal：一项独立交易
    ├── Human-confirmed Stage
    ├── Workplan / Materials / Issues / Decisions
    └── Valuation Case
        └── Immutable Versions
            ├── Inputs + Sources
            ├── Deterministic Calculation
            ├── Review
            └── Internal Approval
```

四个标识不得混用：

- `company_id`：企业主体；
- `case_id`：一次材料与证据工作区；
- `deal_id`：一项具体交易，独立保存买方、交易范围、币种和估值日；
- `valuation_id`：该交易下的一项估值案例。

同一企业可以有多笔 Deal；同一 Deal 可以有多个 Valuation Case；每次输入变化、计算、复核或批准都会生成新版本，不覆盖旧版本。

## 3. 已实现的 P0

### 3.1 交易事实源与状态机

- 独立 `deal_id` 和 Deal Header；
- 人工确认的八阶段交易阶段，材料覆盖不能自动推进；
- Workplan、材料、问题、决策和完整审计字段；
- 乐观并发：`expected_revision / expected_record_hash`；
- 幂等键；
- 估值版本号、版本哈希和前序哈希；
- 旧值、新值、修改人、时间和理由审计；
- 估值状态：

```text
draft
→ inputs_incomplete
→ calculated_screen_grade
→ fa_reviewed
→ approved_for_internal_use
→ approved_for_external_use
→ superseded
```

`approved_for_external_use` 在存储服务中保留为未来状态，但当前本地 HTTP API 永远不允许进入该状态。

其中 Workplan、Materials、Issues 和 Decisions 本轮只完成了存储对象与领域方法，尚未接入人工 HTTP API 和 Deals UI；可操作的补件、Q&A、任务和决策驾驶舱属于需求文件定义的 P1，不能把这些字段误报为已经可在页面使用。

### 3.2 输入与可信计算

- 浏览器不能提交或覆盖计算结果；底层公开计算方法也不再接受调用方传入的 `calculation` 字典，而是从指定不可变版本内部调用确定性引擎；
- `calculate` 端点只接受版本号、版本哈希、幂等键和修改理由；
- 服务端从已持久化版本重新构建全部计算；
- 数值统一使用十进制计算，拒绝二进制浮点输入；
- 每个模型输入包含来源、定位、期间、币种、单位、as-of、录入人和复核人；
- 可选完整财务合同覆盖至少三年历史、一个 LTM 和 3–5 年预测，以及 Revenue、EBITDA、EBIT、Tax、D&A、CapEx、Change in NWC、FCFF 八项序列；
- Reported / Adjusted / Management / Analyst Estimate 可在同一期间并存，覆盖数量按唯一期间计算，不会用多口径行虚增年数；
- 每个财务字段可单独绑定 `source_id / locator / as_of`，整行来源只作为明确兜底；
- 根来源、财务字段来源和可比公司资本结构字段来源都会递归校验本地 workspace 归属；嵌套字段不能用不存在或跨案例的 artifact 冒充出处；
- 完整合同会检查 FCFF 公式勾稽，并把 EBITDA 与 EBIT + D&A 的差异保留为口径复核提示；
- 材料抽取或 Agent 输入只能是 `candidate_input`；
- Deal Store 已有 Agent 候选输入约束，但当前公开 Agent Manifest 尚未暴露估值输入工具；这是一项领域合同，不是现成的 Agent 产品入口；
- 只有显式 `human_confirmed=true` 的输入可以进入公式；
- 金额单位与股数尺度分开保存，`USDm` 默认对应 `million_shares`，不一致时硬失败；
- 结果固定为 `screen_grade_only`，不生成正式估值意见。

### 3.3 估值方法

已运行：

- EV-to-Equity Bridge；
- Trading Comparable Companies；
- FCFF DCF；
- Base / Downside / Upside；
- Period-end 与 Mid-year discounting；
- 永续增长终值；
- 退出倍数交叉验证；
- WACC × Terminal Growth 敏感性；
- WACC × Exit Multiple 敏感性；
- 清洁技术商业模式适用性路由。

Trading Comps 已处理：

- `core_peer / secondary_peer / aspirational_peer / excluded_peer`；
- 纳入/排除理由；
- EV/Revenue、EV/EBITDA、EV/EBIT 和 P/E 口径；
- 负数、零或接近零分母的 `N/M`；
- 缺失值 `N/A`；
- 样本数、中位数、均值、P25、P75、IQR 异常值；
- 目标自身 baseline 与外部可比样本分离；
- 不用全样本最低/最高值机械制造区间。
- 上市可比公司可由带来源的股价 × 完全摊薄股数推导 Equity Value，再通过现金、债务、非经营资产和其他索偿推导 EV；
- 同一可比公司不得同时混用衍生资本结构路径与直接 EV / Equity Value 输入。

DCF 已处理：

- `FCFF = EBIT × (1-tax) + D&A - CapEx - ΔNWC`；
- 显式预测期现值和终值现值；
- 直接 WACC 或核心计算层的 WACC 构成；
- 三情景完整性和方向性；
- Terminal Value 占比提示；
- `WACC <= Terminal Growth` 硬失败；
- 缺少现金和债务桥接时仅显示 EV，不伪造 Equity Value；
- 缺少有效股数时不显示每股价值。

### 3.4 两个独立状态

首页和导出不得把以下状态合并：

- `Calculation Integrity`：公式、单位、桥接、方向性和机械检查；
- `Decision Readiness`：来源、预测、方法适用性、复核和批准是否足以支持内部决策。

复核与批准会生成新版本并重新派生 `Decision Readiness`：无阻断项时从 `screen_grade` 进入 `fa_reviewed` / `fa_reviewed_with_caveats`，再进入 `approved_for_internal_use`；有硬失败、placeholder、计算完整性失败或 readiness blocker 时保持 `not_ready`，内部批准被拒绝。

同时，以下四类交易工作状态也保持独立：

- Candidate Material Readiness；
- Verified Evidence Readiness；
- Human-confirmed Transaction Stage；
- Valuation Readiness。

系统没有总分，也不会把红/黄/绿或不同估值方法秘密加权成单点。

## 4. 本地 UI 与 API

入口：`http://127.0.0.1:8765/?view=deals`

人工 UI API：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET / POST | `/api/ui/deals` | 列出或建立 Deal |
| GET | `/api/ui/deals/{deal_id}` | Deal 详情 |
| POST | `/api/ui/deals/{deal_id}/stage` | 人工确认交易阶段 |
| GET / POST | `/api/ui/deals/{deal_id}/valuations` | 列出或建立估值案例 |
| GET | `/api/ui/valuations/{valuation_id}` | 估值与完整版本历史 |
| POST | `/api/ui/valuations/{valuation_id}/inputs` | 保存候选或人工确认输入 |
| POST | `/api/ui/valuations/{valuation_id}/calculate` | 服务端确定性计算 |
| POST | `/api/ui/valuations/{valuation_id}/review` | FA 人工复核 |
| POST | `/api/ui/valuations/{valuation_id}/approve/internal` | 内部用途批准 |
| GET | `/api/ui/valuations/{valuation_id}/export.xlsx` | 导出指定或当前版本 |

所有写操作要求幂等键和对应的 revision/hash。客户端提交 `actor`、`role`、`created_by`、`reviewed_by`、`approved_by` 等身份字段会被拒绝。

页面在一次逻辑操作失败重试期间复用同一个幂等键；只有确认成功并刷新到新版本后才清除。该保护存在于当前页面会话内，不跨浏览器刷新持久化。

Agent Manifest 没有估值复核或批准工具。当前 Agent 不具备外部批准、发布、报价、NDA、IOI 或 LOI 发送能力。

## 5. XLSX 审计工作簿

导出工作簿包含：

1. `Dashboard`；
2. `Financials`；
3. `Trading Comps`；
4. `Precedents`；
5. `DCF`；
6. `Sensitivities`；
7. `Sources & Assumptions`；
8. `Checks`；
9. `Versions`。

`Precedents` 在 P0 中明确标记为未实现，而不是留空冒充完成。`Financials` 同时保留期间类型、财务口径、期末日和输入分组；历史/LTM 台账不会被误接成 DCF 情景预测。工作簿保存公式、Python 确定性引擎输出、来源台账、检查和版本哈希；不包含宏、VBA、外部工作簿链接或隐藏占位符。XLSX 是派生输出，JSON Deal Store 才是本地事实源。

## 6. 角色与批准边界

存储层采用角色能力矩阵：普通 FA、分析师、复核人、Deal Lead、Approver 和 Admin 的能力不同；Agent 永远不能复核或批准。

当前本地 HTTP 服务没有登录、SSO 或可验证个人身份，因此：

- UI 操作记录为服务端固定的 `local-fa-ui / deal_lead`；
- 这只能用于单机试运行的操作审计，不能证明现实中的个人身份；
- 内部批准用于本地流程演示和内部讨论版本标记；
- 内部批准不会接受硬失败、placeholder、未通过的 Calculation Integrity 或 Decision Readiness 阻断项；
- 外部批准被关闭；
- 要开放外部用途，必须先接入真实身份、角色、四眼原则和发布审批。

## 7. 合成场景回归与验收覆盖

当前自动化以合成 fixture 覆盖三类清洁技术业务；这不是独立真实交易盲测：

| 类型 | 预期 |
|---|---|
| 成熟盈利设备/制造企业 | Trading Comps + FCFF DCF 可运行 |
| 亏损但有收入的早期商业化企业 | Revenue Comps 可运行，负利润不伪装成 EBITDA 倍数 |
| 项目型或尚未商业化技术企业 | P0 fail-closed，明确不适用传统企业 DCF/EV-EBITDA |

主要测试文件：

- `tests/test_valuation.py`；
- `tests/test_deal_service.py`；
- `tests/test_valuation_workflow.py`；
- `tests/test_agent_bridge_valuation.py`；
- `tests/test_valuation_export.py`。

测试通过证明代码合同、公式和边界在样例中成立，不证明真实交易估值正确。真实企业材料、独立参考模型和 FA 审阅仍是正式试运行的下一道门。

2026-08-03 最终工程门禁：

- 完整测试：357 项通过；
- Ruff：通过；
- `git diff --check`：通过；
- Sungrow → Enphase 有序发布门禁通过：29/29、28/28 抽取检查，双方 27/27 卡片检查，新增网络下载 0、模型调用 0；
- 估值专项回归：服务端重算、计算注入拒绝、内部批准阻断和 lifecycle readiness 均有回归；
- 浏览器 QA：桌面主路径通过，390px 移动视口无全页横向溢出，宽表只在局部滚动，控制台 0 error / 0 warning；
- XLSX：九张可见工作表、92 个公式、结构校验通过，公式错误扫描 0 命中，并完成 Dashboard、Sources & Assumptions、Checks 的渲染复核。

## 8. P0 仍未实现

以下能力没有被包装成“已完成”：

- Precedent Transactions 计算与样本维护；
- 项目级 DCF / NAV；
- 未商业化技术的里程碑情景或重置成本模型；
- Reverse DCF；
- 收入增长 × EBIT Margin 敏感性；
- 浏览器 UI 中完整历史/LTM/预测及多口径财务合同的可视化编辑器（领域合同与 HTTP 输入已支持；旧页面未提供时会明确产生 readiness warning）；
- UI 中完整 WACC 构成录入（核心计算器支持，当前简化界面主要使用直接 WACC）；
- 租赁、优先股、少数股东权益、养老金的独立明细 UI（P0 以 debt-like / other claims 汇总）；
- 协同模型、融资模型和回报分析；
- 多用户数据库、WAL、团队账号、SSO、细粒度授权和四眼审批；
- Workplan、Materials、Issues、Requests 和 Decisions 的人工 API / UI（当前仅有存储层对象）；
- 公开 Agent 估值候选输入工具（当前 Manifest 不暴露该能力）；
- 外部批准与客户/投委会发布；
- 独立参考 Excel 金标模型对账；
- 真实交易数据的端到端效用验证。

本地 Deal Store 采用原子写入、乐观并发和哈希链 JSON，适合单机低并发 P0。哈希链只能称为 tamper-evident，不能称为数字签名；正式多人部署应迁移到带事务和身份审计的数据库。

当前写锁仅在单个 `DealStore` 实例内有效；不得让两个服务进程共享同一 JSON workspace。多人或云部署前必须迁移到 SQLite/Postgres 事务，或增加可验证的跨进程锁与冲突恢复。

## 9. 建议 Claude 重点审视

1. 确认浏览器和底层公开 Deal Store 都不存在可注入计算结果或身份字段的路径；
2. 版本号、版本哈希、输入哈希和幂等键是否覆盖所有写操作；
3. Candidate Input 是否可能绕过人工确认进入公式；
4. 股数尺度、金额单位、币种和期间是否可能静默错配；
5. EV-to-Equity 是否在缺桥接时正确 fail-closed；
6. DCF 三情景、WACC/g 和敏感性方向性检查是否充分；
7. Trading Comps 是否错误纳入目标自身 baseline、N/M 或 excluded peer；
8. Calculation Integrity 与 Decision Readiness 是否在 API、UI 和 XLSX 中始终独立；
9. 本地固定身份和内部批准的提示是否足够避免被误认为真实权限系统；
10. 哪些 JSON 持久化边界必须在团队试运行前迁移到 SQLite/Postgres。

## 10. 下一步真实验证

建议用一笔脱敏真实交易做 shadow run：

1. 录入真实交易范围、估值日和币种；
2. 让系统抽取候选输入，但由 FA 逐项确认来源、期间和口径；
3. 与团队现有 Excel 独立计算结果对账；
4. 记录每个差异是公式 bug、单位问题、口径选择还是专业判断；
5. 验证新材料是否只生成新版本，并能解释区间变化；
6. 在不启用外部批准的前提下完成一次内部复核演练。

只有完成真实数据对账，才能判断该模块是否从“工程闭环”进入“FA 可用”。
