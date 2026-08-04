# FA-Q03 CY-Block 450 性能与安全验证包摘录

> **Global data status: Synthetic.** 本文件的设备、客户、实验室角色、数据、故障、文号和日期均为 Synthetic。“Third-party test excerpt”只是评测场景中的模拟来源类型，不得理解为现实世界的独立检测、认证或验收。

## 1. 效率边界与原始循环摘录

Synthetic 测试边界：充热输入为加热器入口电表记录的电能；有效输出为客户交付界面流量、进出口温差和比热计算的热能。不包含客户下游管网损失，包含储热本体、风机和换热回路损失。

| 循环 | 日期 | 充热输入 MWh | 有效输出 MWhth | 循环效率 | 模拟来源类型 | 证据范围 | 数据标识 |
|---|---|---:|---:|---:|---|---|---|
| SYN-C01 | 2026-03-10 | 4.80 | 3.55 | 74.0% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C02 | 2026-03-18 | 4.75 | 3.61 | 76.0% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C03 | 2026-03-29 | 4.90 | 3.77 | 76.9% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C04 | 2026-04-09 | 4.70 | 3.69 | 78.5% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C05 | 2026-04-21 | 4.85 | 3.72 | 76.7% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C06 | 2026-05-08 | 4.92 | 3.89 | 79.1% | Enterprise-prepared raw logger excerpt | 分钟级原始序列未附；仅循环汇总 | Synthetic |
| SYN-C07 | 2026-05-20 | 4.88 | 3.76 | 77.0% | Third-party test excerpt | 模拟实验室角色仅见证仪表与计算；非验收 | Synthetic |
| SYN-C08 | 2026-06-02 | 4.81 | 3.68 | 76.5% | Third-party test excerpt | 模拟实验室角色仅见证仪表与计算；非验收 | Synthetic |
| SYN-C09 | 2026-06-18 | 4.79 | 3.59 | 74.9% | Third-party test excerpt | 模拟实验室角仅见证仪表与计算；非验收 | Synthetic |

**Synthetic 结果：**9 个循环均低于 `SYN-P2601` 最终验收要求的 82%。管理层首包的 82%–88% 是理想边界下的部件仿真区间，不是现场验收结果。

## 2. 运行小时与可用率

| 指标 | 值 | 口径 | 模拟来源类型 | 数据标识 |
|---|---:|---|---|---|
| 监测时窗 | 720 h | Synthetic 月度监测窗口 | Enterprise-prepared | Synthetic |
| 计划运行时间 | 410 h | 客户生产计划要求系统可用的时间 | Enterprise-prepared | Synthetic |
| 有效运行小时 | 312 h | 排除调试、传感器无效和停机时间 | Enterprise-prepared | Synthetic |
| 对计划时间可用率 | 76.1% | 312 / 410 | Enterprise-prepared arithmetic | Synthetic |
| 对全时窗运行比例 | 43.3% | 312 / 720；不等同于可用率 | Enterprise-prepared arithmetic | Synthetic |
| 合同验收累计小时要求 | 1,000 h | 尚未达到 | Counterparty document copy | Synthetic |

## 3. 故障、质保与维护记录摘录

| 事件 | 日期 | 影响 | 状态 | 预计成本 | 模拟来源类型 | 数据标识 |
|---|---|---|---|---:|---|---|
| 出口温度传感器漂移 | 2026-04-18 | 停机 8 h；两个批次数据作废 | 已更换并校准 | RMB 0.03m | Enterprise-prepared maintenance log | Synthetic |
| 风机变频器跳闸 | 2026-05-06 | 停机 14 h | 已复位；根因证明未完成 | RMB 0.05m | Enterprise-prepared maintenance log | Synthetic |
| 耐火层裂纹 | 2026-05-29 | 停机检查 72 h；限制最高温度 | 修复方案未完成；客户已发缺陷通知 | RMB 1.10m | Enterprise log + Counterparty document copy | Synthetic |
| 控制策略波动 | 2026-06-10 | 局部负荷下输出不稳定 | 软件修改未完成客户回归测试 | RMB 0.12m | Enterprise-prepared defect log | Synthetic |
| 合计修复/质保预算 | 2026-06-30 | 影响最终验收与尾款 | 应计提，原管理损益未计提 | RMB 1.30m | Enterprise-prepared repair budget | Synthetic |

## 4. 客户/第三方验收与 EHS/认证状态

| 项目 | 状态 | 可提供材料 | 不存在/未完成材料 | 模拟来源类型 | 数据标识 |
|---|---|---|---|---|---|
| `SYN-P2601` 客户最终验收 | 未完成 | 安装里程碑确认和 2026-06-12 缺陷通知摘录 | 不存在最终验收证书 | Counterparty document copy | Synthetic |
| 第三方性能测试 | 仅仪表/计算见证 | 3 个循环摘录 | 未完成全系统性能认证或合同验收 | Third-party test excerpt | Synthetic |
| 内部 HAZOP | 已完成初版 | `SYN-HAZOP-01` 问题清单摘要 | 整改关闭证据未完整 | Enterprise-prepared | Synthetic |
| 电气安全 | 完成企业出厂检查 | `SYN-ELEC-CHECK-01` 摘要 | 无第三方全系统电气认证 | Enterprise-prepared | Synthetic |
| 压力设备边界 | 储热本体非压力容器；客户侧蒸汽换热单元另行管理 | 企业边界说明 | 未收到客户侧完整压力设备合规包 | Management statement | Synthetic |
| 海外 CE/当地认证 | 未启动 | 无 | 不存在已完成的海外认证 | Management statement | Synthetic |
| 安全事故 | 截至 2026-06-30 管理层称无人身伤害或火灾 | 内部 EHS 台账摘要 | 未独立核验 | Management statement | Synthetic |

**响应状态（Synthetic）：partial。**提供了循环汇总、边界、运行小时和故障/EHS 清单；分钟级原始数据、最终客户验收、第三方全系统认证和海外认证均未提供，其中多项客观上尚未完成。
