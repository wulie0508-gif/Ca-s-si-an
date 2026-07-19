# 本地企业证据工作台 / Local Company Evidence Workbench

这是 `cleantech-finance` 0.4 的本地优先企业入驻工作流。它与现有财务审计内核互补：先组织访谈、材料、授权和证据，再在适用时调用已有的财务确定性审计。

## 快速开始

```powershell
# 创建空白案例；不会覆盖已有文件
cleantech-finance case init case.json

# 用本地示例生成完整工作包
cleantech-finance case report examples/company-intake/demo-distributed-solar/case.json --out outputs/demo-intake

# 校验任何编辑后的案例
cleantech-finance case validate case.json

# 仅生成可选本地 Agent 的取证任务合约
cleantech-finance case agent-tasks case.json
```

打开 `outputs/demo-intake/workbench.html` 即可使用离线界面。界面没有 CDN、没有 `fetch`、没有外部 API 调用；可以编辑核心字段并下载新的 `case.json`。编辑后应通过命令行再次生成正式工作底稿和校验结果。

## 数据边界

- `case.json` 是案例的本地源记录；原始企业文件、访谈录音和网页快照应保存在案例目录的受控位置。
- 访谈原话是管理层陈述，不是事实。主张必须关联证据后才能被标记为 `verified`。
- E1 是管理层陈述，E2 是内部材料，E3 是交易/官方/外部材料，E4 是独立验证或多源确认。
- 关键主张默认至少需要 E3。Agent 返回只能是 E1 候选证据，即使抓取了官方网页，也要由人工审核并建立适当证据记录后才能被采用。
- `public_approved` 必须同时满足已验证、内容发布授权和身份/品牌授权。默认一切内容为内部。
- 同行比较只在相同子行业、阶段、商业模式、国家和期间中进行；少于五个样本时不输出百分位。

## 五道闸门

1. 授权：内部分析、录制和公开发布分别确认。
2. 主体与范围：法律主体、稳定标识、产品/技术、阶段和范围明确。
3. 最低证据：阶段对应的材料已提供，关键主张没有悬而未决。
4. 分析资格：只有前三道门通过，才进入可认证的分析工作流。
5. 发布：内容发布与尽调报告的审核、授权独立处理。

## 与现有财务内核的关系

当前已验证的自动财务能力仍只有盈利/单位经济性与现金流/资金缺口。完整 ESG、DOE ARL、出海准备度和统一评分在工作台内被表示为证据与流程框架，不能被表述成已经验证的自动评分。现有红黄绿财务证据信号也不会被加权或汇总成总分。

## 可选本地 Agent

设置 `agent_settings.enabled` 为 `true` 后，系统只生成白名单取证任务。每个任务要求返回原始产物、来源标识、获取时间、哈希、实体匹配、字段和错误信息。它不直接联网、不绕过验证码、不自动写入已验证事实，也不修改任何评分或规则。
