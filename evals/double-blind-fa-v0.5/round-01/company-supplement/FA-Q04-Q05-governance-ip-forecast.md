# FA-Q04/FA-Q05 公司治理、股权/IP 与预测补充包

> **Global data status: Synthetic.** 本文件的主体、角色、股东、专利号、文件、金额、预测和日期全部为 Synthetic，不对应、不影射任何真实企业或个人。“登记副本”“银行副本”均是 Synthetic 评测场景的模拟来源类别，不是现实世界独立证据。

## 1. 法律主体和登记副本

| 字段 | 值 | 模拟来源类型 | 证据状态 | 数据标识 |
|---|---|---|---|---|
| 法定实体 | 澄岳热储科技（上海）有限公司 | Enterprise-held simulated registry copy | 与 `SYN-REG-COPY-01` 一致 | Synthetic |
| Synthetic 登记号 | `SYN-USCC-CYTS-2023-001`（非现实有效统一信用代码） | Enterprise-held simulated registry copy | Synthetic 标识 | Synthetic |
| 注册资本/实缴 | RMB 10.0m / RMB 8.5m | Enterprise-prepared capital register | 未独立核验 | Synthetic |
| 未实缴认缴 | CEO 创始人角色 RMB 1.5m，约定 2028 年前缴付 | Enterprise-prepared capital register | 未缴付 | Synthetic |

## 2. 全稀释股权、UBO 和关联方

| 持有人/平台 | 全稀释比例 | UBO/关联关系 | 特别权利或未完成项 | 模拟来源类型 | 数据标识 |
|---|---:|---|---|---|---|
| CEO 创始人角色 | 43.5% | UBO；法定代表；关联方借款人 | 对公司提供 RMB 3.5m 可随时要求偿还借款；尚未实缴 RMB 1.5m | Enterprise-prepared cap table | Synthetic |
| CTO 创始人角色 | 18.0% | 关联方；专利共同申请人 | 1 项 Synthetic 专利申请转让未完成 | Enterprise-prepared cap table | Synthetic |
| SYN-Angel SPV-A | 16.0% | Synthetic 机构股东 | 1x 非参与型清算优先权、跟投权；对超过 RMB 5m 新增债务有否决权 | Enterprise-held shareholder agreement | Synthetic |
| SYN-Industrial SPV-B | 12.5% | Synthetic 机构股东 | 信息权 | Enterprise-held shareholder agreement | Synthetic |
| 员工期权平台 | 10.0% | Synthetic 员工持股平台 | 4.0% 已承诺；部分授予尚未完成董事会程序；6.0% 未分配 | Enterprise-prepared option register | Synthetic |
| 合计 | 100.0% | 全稀释口径 | 不代表已发行股本比例 | Enterprise-prepared arithmetic | Synthetic |

**Synthetic 治理异常：**RMB 6.0m Synthetic 银行贷款超过股东协议的 RMB 5.0m 否决权门槛，公司档案中不存在 SYN-Angel SPV-A 的书面同意。

## 3. 7 项申请和 2 项授权的 Synthetic IP 清单

| 申请号 | 授权号 | Synthetic 名称 | 类型/状态 | 申请人/权利人 | 许可 | 质押 | 模拟来源类型 | 数据标识 |
|---|---|---|---|---|---|---|---|---|
| SYN-PAT-A01 | SYN-UM-G01 | 模块化固体储热芯体结构 | 实用新型/已授权 | 公司 | 无对外许可 | 已质押给 SYN-BANK-A | Enterprise-prepared IP register + simulated bank copy | Synthetic |
| SYN-PAT-A02 | SYN-UM-G02 | 高温风道密封与膨胀补偿结构 | 实用新型/已授权 | 公司 | 无对外许可 | 已质押给 SYN-BANK-A | Enterprise-prepared IP register + simulated bank copy | Synthetic |
| SYN-PAT-A03 | 无 | 储热模块温度场控制方法 | 发明申请/实质审查 | 公司 + CEO 创始人角色 | 无 | 无 | Enterprise-prepared IP register | Synthetic |
| SYN-PAT-A04 | 无 | 多模块热流分配方法 | 发明申请/实质审查 | 公司 + CTO 创始人角色 | 无 | 无 | Enterprise-prepared IP register | Synthetic |
| SYN-PAT-A05 | 无 | 耐火介质热应力预警方法 | 发明申请/初审 | 公司 + CEO 创始人角色 | 无 | 无 | Enterprise-prepared IP register | Synthetic |
| SYN-PAT-A06 | 无 | 工业蒸汽储热换热控制系统 | 发明申请/初审 | 公司 | 无 | 无 | Enterprise-prepared IP register | Synthetic |
| SYN-PAT-A07 | 无 | 储热系统调度与故障隔离方法 | 发明申请/受理 | 公司 | 无 | 无 | Enterprise-prepared IP register | Synthetic |

**Synthetic IP 缺口：**A03–A05 的创始人权利转让未完成；没有对外许可合同；A01–A02 存在质押。

## 4. 雇员与外协 IP 归属

| 人员类型 | 人数 | IP 条款状态 | 缺口 | 模拟来源类型 | 数据标识 |
|---|---:|---|---|---|---|
| 在册雇员 | 28 | 28 份劳动合同含职务成果归属条款 | 未对每个代码/图纸完成创作人链条核验 | Enterprise-prepared HR register | Synthetic |
| 长期外协/承包人员 | 6 | 4 份合同含 IP 转让条款 | 2 份合同缺少 IP 转让；公司首包将这 6 人计入 34 人团队口径 | Enterprise-prepared contractor register | Synthetic |

## 5. Synthetic 管理层预测（as-of 2026-06-30）

> 本预测为 **Management statement / Enterprise-prepared draft**，未经董事会批准，未经第三方验证。2027–2029 无已签订单覆盖。

### 收入拆分，RMB million

| 年度/模式 | 项目或收入类型 | 合同状态 | 收入预测 | 假设 ID | 负责角色 | as-of | 数据标识 |
|---|---|---|---:|---|---|---|---|
| FY2026 | H1 已验收项目 | 已交付/已调整 | 8.8 | SYN-ACTUAL-H1 | 财务负责人 | 2026-06-30 | Synthetic |
| FY2026 | SYN-P2601 尾款 | 有合同但验收有争议 | 1.1 | SYN-A01 | COO | 2026-06-30 | Synthetic |
| FY2026 | SYN-P2602 | 无 PO；管理层假设转化 | 9.4 | SYN-A02 | CEO/COO | 2026-06-30 | Synthetic |
| FY2026 | SYN-P2603 | 无已签 PO/技术协议；管理层假设转化 | 8.6 | SYN-A03 | CEO/COO | 2026-06-30 | Synthetic |
| FY2026 | 质保后服务 | 未签 | 0.1 | SYN-A04 | COO | 2026-06-30 | Synthetic |
| FY2026 | 合计 | 仅 9.9 与已交付/附条件合同相关 | 28.0 | SYN-SUM-26 | 财务负责人 | 2026-06-30 | Synthetic |
| FY2027 | 设备销售 | 无已签覆盖 | 62.0 | SYN-A05 | CEO/COO | 2026-06-30 | Synthetic |
| FY2027 | 工程设计 | 无已签覆盖 | 6.0 | SYN-A05 | COO | 2026-06-30 | Synthetic |
| FY2027 | 运维服务 | 无已签长期合同 | 4.0 | SYN-A06 | COO | 2026-06-30 | Synthetic |
| FY2027 | 合计 | 管理层假设 | 72.0 | SYN-SUM-27 | 财务负责人 | 2026-06-30 | Synthetic |
| FY2028 | 设备/工程/服务 | 无已签覆盖 | 122.0 / 13.0 / 10.0 | SYN-A07 | CEO/COO | 2026-06-30 | Synthetic |
| FY2028 | 合计 | 管理层假设 | 145.0 | SYN-SUM-28 | 财务负责人 | 2026-06-30 | Synthetic |
| FY2029 | 设备/工程/服务 | 无已签覆盖 | 185.0 / 25.0 / 20.0 | SYN-A08 | CEO/COO | 2026-06-30 | Synthetic |
| FY2029 | 合计 | 管理层假设 | 230.0 | SYN-SUM-29 | 财务负责人 | 2026-06-30 | Synthetic |

### 损益、CapEx、营运资金和融资缺口，RMB million

| 期间 | 收入 | 毛利 | 费用 | EBITDA | CapEx | 营运资金现金流出 | 其他主要现金流 | 融资前现金变动 | 为维持 RMB 2.0m 最低现金的融资缺口 | 负责角色 | 数据标识 |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---|
| FY2026 全年 | 28.0 | 4.0 | 19.5 | -15.5 | 3.5 | 5.5 | 含 2026-09-30 银行本金 6.0 | -28.9 | 参见 H2 剩余期口径 | 财务负责人 | Synthetic |
| H2 2026 剩余期 | 19.2 | 3.7 | 11.5 | -7.8 | 1.1 | 2.5 | 银行本金 6.0 + 利息 0.4 | -17.8 | 17.3；若退还 P2602 预留款则 19.7 | CEO/财务负责人 | Synthetic |
| FY2027 | 72.0 | 19.4 | 24.0 | -4.6 | 6.0 | 8.0 | 融资租赁本金 0.6 | -19.2 | 19.2 | CEO/财务负责人 | Synthetic |
| FY2028 | 145.0 | 46.4 | 34.0 | 12.4 | 8.0 | 11.0 | 无重大已签债务假设 | -6.6 | 6.6 | CEO/财务负责人 | Synthetic |
| FY2029 | 230.0 | 78.2 | 50.0 | 28.2 | 10.0 | 13.0 | 无重大已签债务假设 | 5.2 | 0.0 | CEO/财务负责人 | Synthetic |

### 关键假设与缺口

| 假设 ID | 假设 | 合同支持 | 风险/替代说明 | 负责角色 | as-of | 数据标识 |
|---|---|---|---|---|---|---|
| SYN-A01 | P2601 于 2026 年完成修复与验收 | 有合同，但当前未达性能条件 | 若失败，1.1 收入和回款延迟或丧失 | COO | 2026-06-30 | Synthetic |
| SYN-A02 | P2602 的 9.4 剩余金额于 H2 转为订单 | 无 PO | 如未下 PO，2.4 预留款可退还 | CEO/COO | 2026-06-30 | Synthetic |
| SYN-A03 | P2603 的 8.6 于 H2 签约并交付 | 无已签 PO/技术协议 | 客户预算和技术条件尚未批准 | CEO/COO | 2026-06-30 | Synthetic |
| SYN-A05/A07/A08 | 销售放量至 72/145/230 | 2027–2029 无已签订单覆盖 | 为管理层目标，不是 backlog | CEO | 2026-06-30 | Synthetic |
| SYN-GM | 毛利率由 2026 的 14.3% 提升至 2029 的 34.0% | 无标准化量产实证 | 依赖供应链降本、设计定型和质保率下降 | CTO/COO | 2026-06-30 | Synthetic |
| SYN-WC | 收入增长需要持续增加存货与应收 | 无供应链融资承诺 | 已将 2027–2029 营运资金流出 8/11/13 纳入 | 财务负责人 | 2026-06-30 | Synthetic |
| SYN-FIN | 外部股权融资 | 只有 2026 年 7 月的非约束性 RMB 12.0m 条款清单，未签署 | 2026–2028 累计基准融资缺口约 43.1，条款清单即使成交仍少 31.1 | CEO | 2026-06-30 | Synthetic |

**FA-Q05 响应状态（Synthetic）：partial。**已给出收入模式、毛利、费用、CapEx、营运资金、现金消耗、融资缺口、合同状态、假设、负责角色和 as-of；但预测未经董事会批准，2027–2029 没有已签合同支持。
