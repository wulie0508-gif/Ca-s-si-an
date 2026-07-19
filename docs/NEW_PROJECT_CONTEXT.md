# CleanTech Finance v0.4｜新项目启动上下文

## 项目根目录

`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance`

新任务应直接把这个目录作为工作区。不要复制成另一份脱离 Git 状态的目录，也不要执行 `git reset --hard`、`git checkout --` 或覆盖当前工作树。

## 当前状态

- 版本：`0.4.0`
- 分支：`main`
- 基线提交：`350d497`
- 当前 v0.4 仍包含未提交的本地变更，必须保留。
- 测试集合：75 项，当前全部通过。
- Ruff：通过。

## 产品一句话

这是一个本地优先、证据优先的清洁技术企业尽调系统。它把企业材料、30 分钟人工访谈、公开资料和受控 Agent 结果组织成可追溯的主张—证据链，再进入财务、ESG、清洁技术影响、ARL、出海准备度与同行比较流程。

## 必须保持的真实能力边界

- 端到端已验证的财务维度只有：盈利/单位经济性、现金流/资金缺口。
- 另外四个财务维度只有输入蓝图。
- DOE ARL 的 17 个维度只有检索脚手架，不输出 ARL 1–9 分数。
- 完整 ESG、清洁技术影响和出海准备度目前是证据框架，不是自动认证。
- 红/黄/绿是独立财务证据信号，不加权、不汇总为总分。
- 不输出投资、信用或综合风险评级。
- Agent 输出始终是候选证据，不能覆盖规则或自动升级为事实。
- 访谈原话只能证明“说过什么”，不能直接证明为真。
- 公开发布需要单独授权和人工审核。

## v0.4 已经实现

- 企业案例模板和 JSON Schema。
- 企业阶段路由：研发、试点、早期商业化、规模化、成熟。
- 分离的录音、内部分析、公开内容、品牌、翻译和 AI 媒体授权。
- 中英双语 30 分钟访谈提纲。
- 管理层陈述、原子主张和证据台账。
- E0–E4 证据等级和六种主张状态。
- 授权、主体范围、最低证据、分析资格、发布五道闸门。
- 阶段化材料请求。
- 白名单约束的本地 Agent 任务合约。
- 同行业同阶段比较边界；少于五个样本不输出百分位。
- 本地静态工作台和完整案例工作包。

## 下一阶段重点

设计并实现企业补件中心：

`gap_detected → request_drafted → request_sent → partially_submitted → submitted → needs_revision → accepted / rejected / waived`

补件中心需要处理字段、材料、证据等级、责任人、截止时间、提交版本、哈希、自动校验、人工审核、退回原因、不适用理由和局部重算范围。

当前只有阶段化材料请求，还没有补件中心的持久化状态机、企业端 UI 或 API。

## 首先阅读

1. `docs/CLAUDE_HANDOFF_v0.4.md`
2. `README.md`
3. `docs/product-overview-brief.md`
4. `docs/local-company-workbench.md`
5. `src/cleantech_finance/onboarding.py`
6. `schemas/company-case.schema.json`
7. `src/cleantech_finance/onboarding_reporting.py`
8. `src/cleantech_finance/cli.py`
9. `tests/test_onboarding.py`

## 核心文件绝对路径

- Claude 技术交接：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\docs\CLAUDE_HANDOFF_v0.4.md`
- 产品简介：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\docs\product-overview-brief.md`
- 本地工作台说明：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\docs\local-company-workbench.md`
- 企业案例核心：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\src\cleantech_finance\onboarding.py`
- 工作包生成：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\src\cleantech_finance\onboarding_reporting.py`
- CLI：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\src\cleantech_finance\cli.py`
- 案例 Schema：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\schemas\company-case.schema.json`
- 入驻测试：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\tests\test_onboarding.py`
- 企业示例：`D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance\examples\company-intake\demo-distributed-solar\case.json`

## 新任务可直接复制的提示词

```text
你正在接手 CleanTech Finance v0.4 本地项目。

工作区根目录：
D:\找回的文件_20260715\项目与资料\Nexus\cleantech-finance

首先完整阅读：
1. docs/NEW_PROJECT_CONTEXT.md
2. docs/CLAUDE_HANDOFF_v0.4.md
3. README.md
4. docs/product-overview-brief.md
5. docs/local-company-workbench.md

然后检查 git status。当前 v0.4 有未提交的本地变更，禁止 reset、checkout、覆盖或丢弃用户修改。

当前版本号为 0.4.0。两项端到端验证财务维度是盈利/单位经济性与现金流/资金缺口；其他财务维度、ESG、ARL 和出海能力必须按照文档中的真实成熟度描述。不要输出投资、信用或综合风险评级，不要汇总红黄绿信号，不允许 Agent 覆盖确定性规则。

下一阶段主线是企业补件中心。先审核现有 case、claim、evidence、gate 和 reporting 架构，再设计 submission 对象、状态机、权限、版本、幂等与局部重算边界。除非任务明确要求实现，否则先给出证据充分的设计或代码审核结论。

每次修改后运行 Ruff 和完整测试；涉及抽取、规则、Schema 或渲染边界时，还要遵守仓库发布门禁。请引用具体文件和代码位置，区分 bug、工程债务、产品选择和尚未实现的路线图。
```
