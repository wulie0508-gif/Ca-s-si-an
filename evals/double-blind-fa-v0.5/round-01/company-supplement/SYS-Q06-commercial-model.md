# SYS-Q06 客户、收费、销售周期与收入依据

> **Global data status: Synthetic.** 本文件的客户代码、合同条款摘录、金额、周期和经济性数据全部为 Synthetic。模拟交易对手副本不是现实世界外部证据。

## 客户结构

| 口径 | 客户/行业 | H1 2026 调整后收入 | 占调整后收入 | 模拟来源类型 | 数据标识 |
|---|---|---:|---:|---|---|
| 已完成项目 | `SYN-CLOSE-021` / 化工 | RMB 4.1m | 46.6% | Enterprise-prepared ledger | Synthetic |
| 已完成项目 | `SYN-CLOSE-022` / 食品配料 | RMB 2.7m | 30.7% | Enterprise-prepared ledger | Synthetic |
| 已完成项目 | `SYN-CLOSE-023` / 纺织 | RMB 2.0m | 22.7% | Enterprise-prepared ledger | Synthetic |
| 合计 | 3 个 Synthetic 已完成项目 | RMB 8.8m | 100.0% | Enterprise-prepared ledger | Synthetic |

## 收费与销售周期

| 字段 | 口径 | 依据 | 模拟来源类型 | 数据标识 |
|---|---|---|---|---|
| 主收费模式 | 固定总价设备+集成合同，可含设计、运输、安装指导与调试 | 合同样本摘录 | Counterparty document copy | Synthetic |
| 典型里程碑收款 | 20% 预付、50% 交付、10% 安装完成、20% 最终验收 | `SYN-P2601` 样本；不代表所有项目 | Counterparty document copy | Synthetic |
| 质保后服务定价 | 管理层目标为设备价的 1.5%–2.0%/年 | 内部价格表；尚无已签长期服务合同 | Management statement | Synthetic |
| 实际 B2B 销售周期 | 首次接触至可执行订单约 9–18 个月 | CRM 内部记录摘要，未独立核验 | Enterprise-prepared | Synthetic |
| 订单后交付周期 | 管理层估计约 6–9 个月 | 项目计划；不是销售周期 | Management statement | Synthetic |

## 收入与单位经济性依据

| 主题 | 优先依据 | 本次提供情况 | 局限 | 数据标识 |
|---|---|---|---|---|
| 收入确认 | 可执行合同/PO、交付或验收文件、发票与回款 | 参见 `FA-Q02-project-document-register.csv` 和 `FA-Q02-h1-revenue-reconciliation.csv` | `SYN-P2603` 缺少已签文件，其收入被调减 | Synthetic |
| 直接成本 | 材料领用、外协采购、项目工时、运输、调试与质保 | 参见 `SYS-Q06-unit-economics.csv` | 工时和共享制造费用为企业分摊，未审计 | Synthetic |
| 项目毛利 | 可确认收入减可归属项目的全生命周期直接成本 | H1 2026 调整后毛利为 RMB 0.3m/3.4% | 包含 `SYN-P2601` RMB 1.3m 修复/质保预计负债 | Synthetic |

**已签/未签说明（Synthetic）：**`SYN-P2601` 存在已签设备合同；`SYN-P2602` 只有框架合作协议，不构成订单；`SYN-P2603` 没有已签 PO 或技术协议。
