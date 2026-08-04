# 美国氢能企业收购中国标的：跨境并购工作流与规则 Spec

> 文档状态：供产品、FA、买方团队、律师及 Claude/Codex 审视的设计基线
> 规则基准日：2026-08-02
> 适用场景：美国氢能企业作为买方，收购中国境内非上市企业或其资产；国企、上市公司和特殊许可业务作为条件化分支
> 文档性质：产品与流程规格，不构成中美法律、税务、财务或投资意见

## 1. 规范用语与设计原则

本文中的“必须（MUST）”“应（SHOULD）”“可以（MAY）”用于约束产品行为，不代替律师对具体交易的判断。

1. 主流程固定为八个业务阶段，商业、财务估值融资、法律税务监管、技术 IP 质量 EHS、项目管理沟通整合五条工作流贯穿始终。
2. 中国和美国监管事项必须建模为条件化监管门。产品不得把 CFIUS、中国外商投资安全审查、经营者集中、HSR、数据出境、出口管制等显示成每笔交易必经的串行审批。
3. 每个监管结论必须保存适用事实、规则版本、计算或律师分析、证据、复核日期；不得只保存“适用/不适用”结论。
4. 最终报价、签约、监管申报、条件豁免和交割必须由获授权的人执行。Agent 可以整理、计算、提示和起草，不能代替授权或专业判断。
5. 所有阶段结论均采用“截至某日、基于哪些材料”的快照表达。尽调不是事实永久保证，发现的问题应映射至价格、交割条件、陈述保证、赔偿、托管或交割后承诺。

### 1.1 强制区分：材料准备度不等于真实交易进度

产品必须独立显示以下四个维度，不得合并为一个百分比：

| 维度 | 含义 | 可由什么推进 | 不能说明什么 |
|---|---|---|---|
| `candidate_material_readiness` | 已收到材料经受控抽取和角色识别后，对当前任务清单形成的候选覆盖程度 | 文件到位、可抽取、候选角色与字段提示形成 | 不代表材料内容为真、证据已验真、卖方有出售意愿或交易接近签约 |
| `verified_evidence_readiness` | 经人工确认且达到相应证据门槛的材料与主张覆盖程度 | 主体、期间、定位、来源、冲突和人工审核通过 | 不代表报价、签约、监管批准或交割已经发生 |
| `transaction_progress` | 交易在接触、报价、谈判、签约、交割和整合上的真实状态 | 有权主体作出决定或交易对方完成实质动作 | 不能由文件数量、VDR 页数、Agent 产出数量推断 |
| `regulatory_gate_status` | 某项监管门的事实收集、分析、申报和决定状态 | 律师分析、主管机关受理/决定、条件履行 | 不等同于商业可行性或董事会批准 |

例如：VDR 候选材料覆盖可达 95%，但其中内容尚未验真，且卖方可能拒绝排他或买方董事会尚未批准，真实交易进度仍不能标记为 `loi_agreed` 或 `signed`。反之，双方可能已签 LOI，但关键许可、数据和技术材料准备度仍很低。任何 Agent 不得以“文件齐全”“任务完成率高”推断证据已验证或交易已推进。

## 2. 角色与最终责任

| 角色 | 最终责任 |
|---|---|
| 买方董事会/投资委员会 | 战略、预算、最终报价、融资杠杆、签约、重大风险接受、交割及可豁免条件的豁免 |
| 买方交易负责人/业务 Sponsor | 收购命题、资源协调、商业优先级、内部升级和管理层建议 |
| FA Deal Lead / PM | 寻源、流程、估值协调、卖方沟通、竞价与谈判建议、时间表和问题闭环；无权代替买方批准 |
| 中美法律顾问 | 法律适用、监管申报、交易文件、特权、合同可执行性及法律风险意见 |
| 财务/税务/融资顾问 | QofE、净债务及营运资金、税务结构、资金来源和融资条件 |
| 技术/IP/质量/EHS 专家 | 技术可行性、IP/FTO、性能和良率、质量责任、危险化学品、特种设备和环境安全 |
| 卖方/标的管理层 | 提供准确资料、管理层陈述、披露、整改和交割配合 |
| 整合负责人 | Day 1、30/100 日计划、协同、人才、内控、许可、数据/技术访问控制和整改 |
| Agent | 证据抽取、字段校验、阈值计算、差异提示、清单和草稿；不得作最终法律结论或执行不可逆交易动作 |

## 3. 八阶段主流程规格

### 阶段 1：收购战略与委托确认

- **目标**：确认买方为何收购、收购什么、可承担什么风险，以及 FA 和各专业团队是否获得明确授权。
- **必需材料**：买方战略与预算；董事会/投资委员会授权；拟收购比例与控制权偏好；融资边界；买方及拟设收购载体的 UBO、政府所有权和法域；顾问委托书、利益冲突检查；初始行业和监管筛查。
- **核心字段**：`deal_id`、`buyer`、`acquisition_vehicle`、`buyer_ubo`、`government_ownership`、`target_profile`、`perimeter`、`control_rights`、`budget_range`、`funding_plan_v0`、`jurisdictions`、`red_lines`、`mandate_status`、`decision_rights`、`rule_as_of`。
- **决策门**：只有在授权、预算、标的边界、顾问职责和初始红线获得确认后才能进入系统性寻源；未知的重大监管事实必须登记为 `facts_requested`，不能默认为不适用。
- **责任人**：买方董事会/投资委员会最终批准；交易 Sponsor 负责命题；FA Deal Lead/PM 负责计划；中美律师和合规负责人负责初筛。
- **阶段证据**：签署的委托/SOW、冲突清查、董事会授权、收购命题、RACI、项目计划、jurisdiction nexus matrix、监管门 v0。

### 阶段 2：产业研究与 Longlist

- **目标**：建立可追溯、可解释的中国氢能目标公司宇宙，而不是只累积公司名称。
- **必需材料**：氢能价值链和技术路线；公开注册、股权及许可信息；产能、项目、客户、技术、融资和交易资料；卖方/股东关系路径；数据来源许可。
- **核心字段**：`target_id`、`legal_name`、`business_scope`、`value_chain_position`、`technology_route`、`capacity`、`projects`、`key_customers`、`shareholders`、`ubo`、`soe_flag`、`listed_flag`、`licenses`、`jurisdiction_footprint`、`source_id`、`source_date`、`confidence`、`contact_route`。
- **决策门**：进入 Longlist 的每个事实必须有来源、日期和置信度；无接触授权时不得自动外联；命中制裁、国企、上市、军工周边或敏感技术标签仅代表需升级，不等于自动淘汰。
- **责任人**：FA 行业负责人和分析师主责；技术专家验证技术分类；律师/合规复核高风险标签。
- **阶段证据**：产业地图、证据化 Longlist、信息冲突清单、关系路径图、初始标的风险标签。

### 阶段 3：Shortlist 与初步估值

- **目标**：把战略适配、价值、可交易性和监管可行性结合，形成有排序依据的优先目标。
- **必需材料**：Longlist；公开财务和运营信息；可比公司/交易案例；买方协同假设；初步融资条件；中国营业额及美国资产/销售等门槛事实。
- **核心字段**：`fit_score`、`commercial_score`、`technology_score`、`financial_score`、`regulatory_score`、`approachability_score`、`valuation_methods`、`valuation_range`、`assumptions`、`synergy_case`、`downside_case`、`turnover_cn`、`assets_us`、`sales_us`、`covered_activity_screen`、`priority_rank`。
- **决策门**：Shortlist 必须由授权人批准；估值展示区间、敏感性和数据缺口，不得输出伪精确单点价格；监管事实不足时只能给出条件化结论。
- **责任人**：FA Deal Lead 形成建议；行业、估值、融资和监管专家提供输入；买方 Sponsor/投资委员会作 go/hold/no-go 决定。
- **阶段证据**：Shortlist、评分依据、估值模型版本、协同模型、初始红旗、go/no-go memo、获批接触计划。

### 阶段 4：初步接触与 NDA

- **目标**：在控制保密、数据和技术披露风险的前提下验证卖方意愿、交易范围和初步信息。
- **必需材料**：获批接触名单和话术；关系路径；NDA 模板；初步资料清单；数据分类、出口管制和 VDR 权限方案。
- **核心字段**：`outreach_authorization`、`contact_person`、`channel`、`contact_timestamp`、`seller_intent`、`nda_status`、`nda_scope`、`residual_obligations`、`vdr_tier`、`data_classification`、`export_classification`、`redaction_status`、`access_log`、`next_action`。
- **决策门**：NDA 不替代 PIPL、数据安全或出口管制分析；未完成数据/技术分类前不得开放高敏感层；卖方仅表示愿意交流不能标记为 IOI/LOI 已进入谈判。
- **责任人**：FA 主导接触；买方 Sponsor 批准信息和立场；律师负责 NDA、数据和出口控制；标的负责授权披露。
- **阶段证据**：接触日志、NDA、process letter、资料清单、VDR 权限与访问记录、数据/技术披露 memo。

### 阶段 5：IOI、LOI 与排他

- **目标**：用经批准的价格、范围、结构和风险分配框架换取深入尽调及必要排他。
- **必需材料**：初步信息包；估值和协同模型；融资方案；结构与税务 memo；尽调范围；监管门更新；谈判权限。
- **核心字段**：`offer_type`、`price_or_range`、`currency`、`enterprise_to_equity_bridge`、`perimeter`、`consideration_form`、`earnout`、`funding_sources`、`dd_scope`、`exclusivity_start`、`exclusivity_end`、`long_stop`、`regulatory_cps`、`break_costs`、`binding_terms`、`approval_id`。
- **决策门**：必须明确哪些条款有约束力；报价、排他、费用和监管 CP 由授权人批准；未经批准不得由 Agent 自动发送或修改报价。
- **责任人**：买方董事会/投资委员会批准关键经济条件；FA 提供竞价与谈判建议；律师起草；融资和税务团队确认可执行性。
- **阶段证据**：获批 IOI/LOI、排他协议、批准记录、尽调计划、融资计划、监管申报计划、谈判问题清单。

### 阶段 6：尽调与交易结构

- **目标**：验证价值和事实，量化风险，并将每项重大问题映射至交易结构、价格、交割条件或合同救济。
- **必需材料**：分工作流尽调清单；VDR 和 Q&A；管理层访谈；现场和实验/性能资料；QofE 和税务资料；公司、许可、合同、数据、技术、EHS 资料；融资承诺。
- **核心字段**：`dd_issue_id`、`workstream`、`fact`、`source_id`、`severity`、`probability`、`financial_range`、`legal_effect`、`owner`、`remedy`、`price_impact`、`cp_link`、`rw_link`、`indemnity_link`、`covenant_link`、`residual_risk`、`risk_acceptor`、`privilege`。
- **决策门**：每个重大 issue 必须标记为 deal-breaker、可整改或可定价风险；无证据问题不得直接写成确定事实；律师判断监管和法律适用，Agent 不能给最终法律意见。
- **责任人**：各工作流负责人签署本线结论；FA PM 维护一体化 issue register；买方 Sponsor/委员会决定价格与风险接受；律师控制特权和法律结论。
- **阶段证据**：红旗/完整报告、Q&A 审计轨迹、更新估值、风险—救济矩阵、结构 memo、SPA/SHA/APA 草案、申报草案、Day 1/100 日蓝图。

### 阶段 7：签约、审批与交割

- **目标**：在授权、融资、监管决定和全部不可豁免条件满足后完成可审计的签约与交割。
- **必需材料**：最终交易文件和披露函；董事会/股东批准；融资文件；监管申报及决定；CP 清单；资金流；bring-down、无重大不利变化及交割证明；工商、外资信息、银行外汇和税务材料。
- **核心字段**：`signing_status`、`approval_id`、`cp_id`、`cp_owner`、`cp_evidence`、`waivable`、`waiver_authority`、`filing_receipt`、`clearance_decision`、`conditions`、`funds_flow_version`、`proof_of_funds`、`bring_down`、`closing_timestamp`、`shareholder_register`、`registration_status`、`fx_bank_record`、`tax_evidence`。
- **决策门**：状态依次为 `signed_pending_cp → ready_to_close → closed → registrations_complete`；不可豁免监管条件未满足时不得关闭；任何豁免必须记录授权人、理由和残余风险；系统不得自动签字、申报、汇款或交割。
- **责任人**：买方和卖方授权签字人；中美律师负责 closing checklist；FA PM 协调；银行/融资方执行资金；主管机关作监管决定。
- **阶段证据**：签署版本、批准/申报/决定文件、CP 证据包、资金流和银行回执、closing certificate/book、股东名册、营业执照、外汇和税务凭证。

### 阶段 8：并购后整合

- **目标**：保护业务连续性，落实监管及合同承诺，修复尽调风险并实现可验证协同。
- **必需材料**：closing book；DD issue register；监管条件；整合蓝图；组织、系统、许可、客户、供应商和人才清单；合规基线。
- **核心字段**：`integration_action_id`、`owner`、`baseline`、`target`、`deadline`、`day_1`、`day_30`、`day_100`、`synergy_kpi`、`control_change`、`license_action`、`data_access_control`、`export_control_plan`、`fcpa_remediation`、`ehs_remediation`、`condition_monitor`、`status`、`evidence`。
- **决策门**：交割不等于整合完成；只有许可更新、内控、技术/数据访问、监管条件、整改和关键业务连续性达到既定退出标准后才能标记 `integrated`。
- **责任人**：买方整合负责人最终负责；各职能负责人执行；FA 可继续担任 PM/顾问；律师和合规监控交割后义务。
- **阶段证据**：Day 1/30/100 日计划、协同看板、整改台账、许可更新、培训和审计记录、监管条件监控、经验复盘。

## 4. 八阶段 × 五工作流矩阵

| 阶段 | 商业与产业 | 财务、估值与融资 | 法律、税务与监管 | 技术、IP、质量与 EHS | PM、沟通与整合 |
|---|---|---|---|---|---|
| 1 战略/委托 | 收购命题、价值链和标的画像 | 预算、回报门槛、融资边界 | 买方/载体、负面清单和中美监管初筛 | 技术路线、关键性能和 EHS 红线 | SOW、RACI、决策权、计划和 clean-team |
| 2 产业/Longlist | 市场、企业、客户、项目和竞争图谱 | 公开财务、融资和规模代理指标 | 股权/UBO、国企/上市、许可、制裁和法域 | 技术路线、产能、项目表现、专利和安全标签 | 来源治理、联系路径、更新节奏 |
| 3 Shortlist/初估 | 战略适配、可交易性和协同 | 可比、DCF、重置成本、初始资金 | 控制、营业额、美国资产/销售和 covered activity | 技术成熟度、差异化、质量/EHS 红旗 | 评分、go/hold/no-go、接触审批 |
| 4 接触/NDA | 卖方意愿、范围和管理层初访 | 初步信息请求和估值校准 | NDA、PIPL/数据、出口管制、保密 | 分层披露技术资料、脱敏和 clean room | 接触日志、VDR 权限、Q&A 和节奏 |
| 5 IOI/LOI/排他 | 交易范围、商业假设和协同边界 | 报价、对价、earn-out、融资条件 | 结构、税务、排他、CP、long-stop | 技术/EHS 尽调范围和关键验证条件 | 批准、谈判权限、里程碑和升级规则 |
| 6 尽调/结构 | 市场、客户、订单、供应链和协同验证 | QofE、净债务、营运资金、CapEx、模型更新 | 公司、合同、劳动、税务、数据、出口、申报和制裁 | IP/FTO、性能、良率、质量、危化品、特种设备、环境安全 | Q&A、issue register、风险—救济映射、整合设计 |
| 7 签约/审批/交割 | 客户/供应商连续性和沟通 | 融资文件、资金流、价格调整 | 文件、批准、申报、CP、工商、外汇、税务 | 技术交付边界、许可/质量/EHS bring-down | closing room、签字权、证据包和 Day 1 准备 |
| 8 整合 | 客户、渠道、品牌和协同 | 报表、内控、预算、协同计量 | 治理、合规、许可、税务、监管条件 | IP/技术访问、质量、EHS 和产线提升 | Day 1/30/100、人才、文化、整改和复盘 |

矩阵单元是工作包，不是交易进度代理。某工作流材料齐全不代表该阶段已通过决策门。

## 5. 条件化中国监管门

| 监管门 | 触发事实 | 时点与主管机关 | 产品必须保存的证据 | 不得作出的默认假设 |
|---|---|---|---|---|
| 外资准入负面清单 | 标的业务命中 2024 版负面清单或行业持股/许可限制 | 结构设计和接触前；发改、商务及行业主管部门 | 业务事实、行业代码、清单版本、律师分析和许可清单 | 制造业限制已清零不等于所有氢能业务无行业限制 |
| 外商投资安全审查 | 军工及周边；或重要能源、资源、装备、基础设施、关键技术等且取得实际控制 | 原则上实施投资前；国家发改委、商务部工作机制办公室 | 行业/设施/技术、控制权、申报前咨询、受理、15/30/60 个工作日时钟、补件停钟和决定 | 氢能不能一律认定为“重要能源/关键技术”，也不能一律排除 |
| 经营者集中 | 取得控制或决定性影响，并达到门槛；未达门槛但可能排除限制竞争时也可能被要求申报 | 实施集中前；SAMR | 控制分析、上一会计年度营业额、计算范围、申报或不申报 memo、受理/停钟/决定 | 达到股权比例不必然等于取得控制；低于门槛也不是绝对安全港 |
| 数据出境 | CIIO 提供个人信息/重要数据；非 CIIO 提供重要数据或个人信息达到数量门槛 | VDR 或持续传输前；CAC | 数据地图、字段和主体数量、敏感/重要数据判断、脱敏、合法性基础、评估/标准合同/认证和访问日志 | NDA 不替代 PIPL；并购员工数据不自动落入 HR 豁免 |
| 出口管制与技术出口 | 向美国买方提供受控物项、软件、技术、服务或技术资料；命中清单、临时或兜底管制；命中禁止/限制出口技术目录 | VDR、访谈、技术许可和交付前；商务部等 | 资料级分类、清单/ECCN 对照、最终用户/用途、许可、披露审批和访问日志 | 出口管制不只是实物通关；技术资料披露也可能构成提供或转移 |
| 公司法、登记与外资信息/外汇 | 境内有限责任公司股权转让及外资进入 | 签约/交割及交割后；市场监管、商务信息报告系统、银行/外汇 | 外部转让通知、30 日优先购买权、章程、股东名册、出资实缴、营业执照、信息报告和银行外汇记录 | 股权交割不能替代登记；出资瑕疵责任不能只看旧营业执照 |
| 国有资产交易 | 标的或卖方属于国有/国有控股或实际控制 | 估值、签约前；国资监管机构和产权交易机构 | 审计、评估、批准、挂牌/竞价、信息披露和交易凭证 | 普通私企流程不能直接套用于国资交易 |
| A 股上市公司 | 收购 A 股股份或取得上市公司控制/重大权益 | 接触、签约和交割前；证监、交易所等 | 战略投资资格、中介意见、权益变动、要约/豁免和持续披露 | 非上市标的规则不能直接替代证券法程序 |
| 行业/EHS 许可 | 实际从事氢生产、储存、经营、运输，使用压力设备，或建设项目产生环境影响 | 尽调、结构和整合；应急、市场监管、生态环境等 | 危化品许可、安全评价、重大危险源、特种设备登记检验、环评验收、排污和事故记录 | “氢能公司”不必然需要全部许可，必须按设施和活动逐项判断 |

经营者集中现行主要营业额门槛为：上一会计年度所有经营者全球营业额合计超过人民币 120 亿元且至少两个经营者各自在中国境内超过 8 亿元；或所有经营者中国境内营业额合计超过 40 亿元且至少两个经营者各自在中国境内超过 8 亿元。

数据出境现行主要数量分层为：非 CIIO 自当年 1 月 1 日累计向境外提供 100 万人以上普通个人信息或 1 万人以上敏感个人信息，通常进入安全评估；10 万人以上、不满 100 万人普通个人信息，或不满 1 万人敏感个人信息，通常采用标准合同或认证；不足 10 万人普通且非敏感个人信息可能免于三类机制，但仍须履行 PIPL 义务。主管部门未告知或公开发布为重要数据的，可不按重要数据申报，但必须保存分类依据。

## 6. 条件化美国及其他法域监管门

| 监管门 | 触发事实 | 时点与主管机关 | 产品必须保存的证据 | 适用边界 |
|---|---|---|---|---|
| 美国对外投资 31 CFR Part 850 | 美国人交易涉及中国大陆、香港、澳门 covered foreign person 的特定半导体与微电子、量子或 AI 活动 | 承诺或实施交易前后按规则判断/通知；美国财政部 | U.S. person、covered foreign person、covered activity、子公司事实、reasonable and diligent inquiry、通知或禁止分析 | 现行范围不包含纯氢能；标的兼营受覆盖活动时重新分析；无逐案 clearance |
| CFIUS | 外国人取得美国业务控制，或取得 TID U.S. Business 的特定非控制权利 | 通常交割前；美国财政部 CFIUS | 外国人、美国业务、TID 属性、控制/信息/董事会/实质决策权、申报分析 | 美国买方直接买中国公司通常不属于 CFIUS；中国卖方滚存、外资控制载体或其他外国权利可能重启分析 |
| HSR | 外国发行人在美国资产或美国销售超过年度调整门槛，且一般 size-of-transaction/size-of-person 等测试满足 | 交割前申报和等待；FTC/DOJ | 美国资产、在美或向美销售、交易价值、年度门槛版本、豁免及等待期 | 2026 年调整后的相关基础门槛为 1.339 亿美元；门槛每年更新，超过外国发行人豁免门槛也不等于必然申报 |
| EAR | 受 EAR 管辖物项、软件或技术向中国主体出口、再出口、转移或释放 | 技术披露、交付和整合访问前；BIS | 管辖、ECCN/EAR99、目的地、最终用户/用途、Entity/MEU/UVL/Denied Persons 等筛查、许可 | EAR 不是并购批准，但 VDR、培训、源代码和工艺访问都可能触发 |
| OFAC | 交易方或其 50%以上所有权链属于封锁主体，或命中特定制裁项目 | 接触、付款和持续监控；OFAC | 名称、别名、UBO、所有权、银行、客户/供应商、筛查时间和结果 | 美国没有对中国的一揽子 OFAC 禁运；仍需逐主体和项目筛查 |
| FCPA | 标的存在政府客户、国企交易、代理人、牌照审批、礼品招待、账簿和内控风险 | 尽调和整合；DOJ/SEC | 风险评估、抽样、调查、账簿测试、整改、培训和披露决策 | 属反贿赂和继承责任风险，不是交易审批；DOJ 的 180 日披露/一年整改基线属于执法政策而非法定 CP |
| 其他国家 FDI screening | 标的集团在当地有实体、关键资产、许可证、敏感业务或当地控制权变化 | 各法域规定时点 | 法域实体树、资产/许可、控制变化、当地律师结论 | 不能仅因买方是美国企业、标的是中国企业而默认第三国审查适用 |

截至本规则基准日，2025-12-18 通过的 COINS Act 要求美国财政部在 450 日内制定新规则；财政部 2025-12-23 FAQ 明确，新规则发布前现行 Part 850 继续有效。产品必须为该监管门设置 `rule_version`、`as_of` 和 `recheck_date`，不能提前把可能扩围至其他先进制造等领域的政策方向当作现行禁止或通知义务。

## 7. 氢能专项尽调最小范围

1. **技术和性能**：电解槽、膜电极、催化剂、储运材料、系统集成、测试边界、衰减、效率、动态响应、良率、可维护性及第三方验证。
2. **IP 与 FTO**：发明人/雇员/高校或合作方权属链、许可、质押、共同开发、开源软件、商业秘密管理、离职人员和主要市场 FTO。
3. **项目和商业化**：在手订单、框架协议与可撤销性、补贴依赖、示范项目验收、客户集中、保修、LCOH 假设、产能利用率、关键供应商和材料价格风险。
4. **质量**：设计变更、供应商质量、试验报告、认证、退货、索赔、现场故障、召回、追溯和质量体系有效性。
5. **危险化学品与安全**：氢已列入《危险化学品目录（2015版）》；按生产、储存、经营、运输的真实活动核对许可、安全评价、重大危险源、应急预案和事故。
6. **特种设备**：储罐、压力容器、压力管道、气瓶等的设计制造资质、使用登记、检验、操作人员资质和历史缺陷。
7. **环境**：环评批复、竣工环保验收、排污许可、污染物、用水用能、危废、土壤地下水、处罚和整改。
8. **材料与出口**：如涉及镓、锗、锑、超硬材料、石墨或其他受控材料，检查中国对美专项出口限制；按具体物项和最终用途判断，不以“氢能”行业标签代替分类。

## 8. 建议状态机

### 8.1 交易阶段状态

```text
not_started
  → gathering
  → screening
  → in_review
  → conditional_go | go | hold | no_go
  → signed_pending_cp
  → ready_to_close
  → closed
  → registrations_complete
  → integrating
  → integrated
  → archived
```

`go` 只表示有权主体允许进入下一阶段，不表示监管清关、材料齐全或必然成交。`no_go`、`hold` 和任何豁免必须记录决定人、日期、依据和可否重启。

### 8.2 单项监管门状态

```text
unknown
  → facts_requested
  → counsel_analysis
  → filing_required | no_filing | not_applicable_with_evidence
  → filed
  → questions_or_stop_clock
  → cleared | cleared_with_conditions | prohibited
  → expired_recheck
```

禁止使用无说明的普通 `N/A`。`not_applicable_with_evidence` 至少需要事实、规则版本、分析人和复核日期。

### 8.3 尽调问题状态

```text
open
  → verifying
  → quantified
  → remedy_proposed
  → allocated_to_price | cp | rw | indemnity | covenant
  → resolved | accepted | authorized_waiver
```

## 9. 核心数据与证据模型

### 9.1 Deal

`deal_id`、买方/卖方/标的、收购载体、UBO、政府所有权、上市/国企/许可标签、交易范围、结构、比例、控制权、金额、币种、签约日、交割日、long-stop、实体与资产所在法域。

### 9.2 Fact 与 Evidence

每项关键事实必须能回溯到：

```text
fact_name, value, unit, period,
source_id, source_type, title, provider,
document_version, hash, exact_location_or_page,
publication_date, obtained_at, verified_by,
confidence, conflict_flag,
privilege, confidentiality, redaction, access_log
```

网页法规还必须保存 `jurisdiction`、`authority`、`citation/article`、`effective_date`、`status`、`as_of`、`recheck_date`。摘要不能替代原文定位；译文应连接原文并记录译者/版本。

### 9.3 Regulatory Gate

```text
gate_id, jurisdiction, authority, rule_version,
trigger_question, applicable_facts, threshold_calculation,
counsel_memo, consultation_or_filing, submission_id,
receipt, clock_start, stop_clock, restart,
status, decision, conditions, expiry, recheck_date,
linked_cp, linked_issue, owner, approver
```

### 9.4 阶段和任务

`stage_id`、`transaction_progress`、`material_readiness`、owner、approver、start/due、必需输入、输出证据、entry/exit criteria、依赖、blocker、next action。材料准备度应按“决策所需证据覆盖率”计算，而不是文件数。

## 10. 人工与 Agent 边界

### 10.1 Agent 可以做

- 从获授权材料抽取字段并显示来源定位；
- 检查材料缺口、日期过期、数字口径冲突和证据链断裂；
- 根据已确认事实计算经营者集中、HSR 等数值门槛并展示公式；
- 生成 Longlist 初稿、工作流清单、Q&A、会议纪要、issue register 和条款映射草案；
- 对规则更新发出 `expired_recheck`，提示律师复核；
- 对 VDR 下载、披露和访问执行已配置的权限与日志策略。

### 10.2 必须由人工完成

- FA：目标宇宙完整性、卖方动机、关系策略、协同判断、估值情景权重、竞价纪律、报价与谈判顺序；
- 买方董事会/管理层：最终报价、融资杠杆、重大风险接受、签约、交割、CP 豁免、人才和整合决策；
- 律师/监管专家：法律适用、FISR/经营者集中/Part 850/CFIUS/HSR/数据/出口申报必要性、申报内容、特权和合同效力；
- 主管机关：受理、批准、禁止或附条件决定。

### 10.3 Agent 禁止做

- 未经批准联系标的或卖方；
- 自动发送或修改 IOI/LOI/最终报价；
- 将缺少证据的推断写成已验证事实；
- 代表律师作最终法律意见或代表管理层接受风险；
- 自动提交监管文件、签署、汇款、豁免条件或交割；
- 以材料准备度、任务完成率或文档数量推断真实交易进度。

## 11. 官方和方法依据

### 中国

- [《中华人民共和国公司法》](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_067c072db6ef4679a2e0180996be4cf8.html)，全国人大常委会/国家市场监督管理总局，2023-12-29，2024-07-01 生效。
- [《外商投资安全审查办法》](https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=18525)，国家发展改革委、商务部，2020-12-19，2021-01-18 生效。
- [《外商投资准入特别管理措施（负面清单）（2024年版）》](https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/202409/t20240907_1392875_ext.html)，国家发展改革委、商务部，2024-09-08，2024-11-01 生效。
- [《国务院关于经营者集中申报标准的规定》](https://www.samr.gov.cn/fldes/jyzjzsbxbz/art/2024/art_eb4235b9a196486c8df15c7a61d51744.html)，国务院/国家市场监督管理总局，2024-01-26。
- [《经营者集中审查规定》](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_4c34a8aa4e62449ab38233bdbba172a7.html)，国家市场监督管理总局，2023-03-20，2023-04-15 生效。
- [《促进和规范数据跨境流动规定》](https://www.cac.gov.cn/2024-03/22/c_1712776612187994.htm)，国家互联网信息办公室，2024-03-22。
- [《数据出境安全管理政策问答（2025年5月）》](https://www.cac.gov.cn/2025-05/30/c_1750315283722063.htm)，国家互联网信息办公室，2025-05-30。
- [《中华人民共和国个人信息保护法》](https://www.npc.gov.cn/WZWSREL25wYy9jMi9jMzA4MzQvMjAyMTA4L3QyMDIxMDgyMF8zMTMwODguaHRtbD9yZWY9aW1i)，全国人大常委会，2021-08-20，2021-11-01 生效。
- [《中华人民共和国出口管制法》](https://exportcontrol.mofcom.gov.cn/article/zcfg/gnzcfg/flfg/202111/226.html)，全国人大常委会/商务部，2020-10-17，2020-12-01 生效。
- [《中华人民共和国两用物项出口管制条例》](https://xkzj.mofcom.gov.cn/tzgg/art/2024/art_49503f2524484d8d9488dfd37395a731.html)，国务院/商务部，2024-09-30，2024-12-01 生效。
- [《中国禁止出口限制出口技术目录》2023 年公告](https://fms.mofcom.gov.cn/zcfg/jsjckzcfg/art/2023/art_97622195446740f897a578c784579bd8.html)，商务部、科技部，2023-12-21。
- [关于加强相关两用物项对美国出口管制的公告](https://www.mofcom.gov.cn/zfxxgk/gkml/art/2024/art_99f5d51bbe6a412ca309d5818c4dee52.html)，商务部，2024-12-03。
- [《外商投资信息报告办法》](https://www.mofcom.gov.cn/zfxxgk/zc/gz/art/2021/art_d12db5f04f8444f894ec5723b7e0e0be.html)，商务部、国家市场监督管理总局，2019-12-30，2020-01-01 生效。
- [《资本项目外汇业务指引（2024年版）》](https://www.safe.gov.cn/safe/2024/0412/24226.html)，国家外汇管理局，2024-04-12，2024-05-06 生效。
- [《企业国有资产交易监督管理办法》](https://www.sasac.gov.cn/n2588035/n22302962/n22302967/c22692566/content.html?eqid=a8640e0b0002dc5b000000036454c579)，国务院国资委、财政部，2016-06-24。
- [《外国投资者对上市公司战略投资管理办法》](https://www.mofcom.gov.cn/zcfb/blgg/bl/2024/art/2024/art_8167f2ebe6b74777badb9abf8ed94039.html)，商务部等六部门，2024-11-01，2024-12-02 生效。
- [关于氢气危险化学品监管的答复](https://www.mem.gov.cn/gk/jytabljggk/rddbjydfzy/201912/t20191213_342225.shtml)，应急管理部，2019-12-13。
- [《危险化学品目录（2015版）》](https://www.miit.gov.cn/ssqqhxptyflhbqzdgz/fgzc/zywj/art/2023/art_0b9007c77d384fd2ac47da4e60231af9.html)，十部门，2015-03-09，2015-05-01 生效。

### 美国

- [31 CFR Part 800—Regulations Pertaining to Certain Investments in the United States by Foreign Persons](https://www.ecfr.gov/current/title-31/subtitle-B/chapter-VIII/part-800)，美国财政部/eCFR，当前版本访问于 2026-08-02。
- [Outbound Investment Security Program](https://home.treasury.gov/policy-issues/international/outbound-investment-program)，美国财政部，现行规则自 2025-01-02 生效。
- [Outbound Investment Frequently Asked Questions](https://home.treasury.gov/policy-issues/international/outbound-investment-program/frequently-asked-questions)，美国财政部，更新于 2025-12-23，包含 COINS Act 过渡说明。
- [16 CFR 802.51—Acquisitions of voting securities of a foreign issuer](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-H/part-802/section-802.51)，FTC/eCFR，当前版本访问于 2026-08-02。
- [Current HSR Thresholds](https://www.ftc.gov/enforcement/premerger-notification-program/current-thresholds)，美国联邦贸易委员会，2026 年门槛自 2026-02-17 生效。
- [Determine What Is Subject to the EAR](https://www.bis.gov/licensing/determine-what-is-subject-to-the-EAR)，美国商务部工业与安全局，访问于 2026-08-02。
- [Part 734—Scope of the Export Administration Regulations](https://www.bis.gov/regulations/ear/734)，美国商务部工业与安全局，当前版本访问于 2026-08-02。
- [OFAC Country List FAQ](https://ofac.treasury.gov/sanctions-programs-and-country-information/where-is-ofacs-country-list-what-countries-do-i-need-to-worry-about-in-terms-of-us-sanctions)，美国财政部 OFAC，访问于 2026-08-02。
- [FCPA Resource Guide](https://www.justice.gov/criminal/criminal-fraud/fcpa-resource-guide)，美国司法部、证券交易委员会，页面更新于 2024-12-16。
- [Justice Manual 9-47.000](https://www.justice.gov/jm/jm-9-47000-foreign-corrupt-practices-act-1977)，美国司法部，访问于 2026-08-02；其中并购披露和整改期限属于执法政策，不是法定交易审批。

### 流程方法参考（非强制规则）

- [《外资并购、跨境并购》](https://www.allbrightlaw.com/CN/11050.aspx)，上海市锦天城律师事务所，访问于 2026-08-02。
- [《以矛陷盾：谈国际并购中尽职调查与陈述与保证条款的关系》](https://www.zhonglun.com/research/articles/56254.html)，中伦律师事务所，2026-06-09。

上述律师事务所材料用于解释行业流程与尽调—合同救济关系，不属于法律或监管强制要求。

## 12. Claude/Codex 审视清单

- 是否把八阶段和五工作流全部覆盖，且没有用材料数量代替进度？
- 每个阶段是否同时具备目标、必需材料、核心字段、决策门、责任人和证据？
- 每个监管门是否有触发事实、主管机关、时点、证据、状态和规则复核日期？
- 是否错误地把 CFIUS、Part 850、FISR、经营者集中、HSR、数据出境或出口管制描述成每单必经？
- 是否把纯氢能默认归入 Part 850，或把所有氢能交易默认归入中国安全审查？
- 是否将“制造业负面清单清零”误写为全面免监管？
- 是否允许 Agent 自动接触、报价、申报、签约、豁免或交割？如是，必须阻断。
- 是否能从任一关键结论追溯到具体材料、版本、页码/位置、验证人和截至日期？
- 是否保留董事会、FA、律师、监管机关和 Agent 之间的最终责任边界？
