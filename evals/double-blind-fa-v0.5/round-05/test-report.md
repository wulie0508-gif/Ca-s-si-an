# CleanTech Finance v0.5 双盲 QA · Round 05

## 一句话结论

第五轮完成了“企业材料 → FA 初测 → 逐字追问 → 企业补件 → 修复前冻结复现 → 定向工程修复 → 独立 HTTP/XLSX 重放 → Chromium UI → 完整门禁”的闭环。旧系统在 2026-06-30 估值日静默把 FY2027E–FY2029E 按 1/2/3 折现的 S1 问题已经修复；现在非年末估值必须使用来源化、人工确认的逐期 timing，否则在请求或计算边界 fail closed。

本轮企业、财务、授权、可比公司和估值材料全部为 **Synthetic**。本轮通过不等于真实企业数据验证、正式估值意见、投资/信用/综合风险评级或公开发布授权。

## 角色与方法

- 初始 FA：fresh no-history，只读取 Round 05 首包和运行中的产品。
- 企业响应：fresh no-history，只读取首包与 7 个逐字问题，不读取代码、工程报告或其他轮次。
- 工程修复：fresh no-history，只读取已冻结的初测、补件和修复前基线；不替 FA 作专业判断。
- 修复后 FA：fresh no-history，两个 fresh 只读子任务分别抽取允许材料和公开 HTTP 合约。
- 主协调：校验文件哈希、独立运行完整门禁和 Chromium；最终只提交 Round 05 相关改动。

修复后 FA 已完成真实重放，但其报告写入步骤停滞。协调者根据该任务的最终运行遥测与两个只读子任务的完整清单重建 6 个 postfix 文件，并逐一验证 JSON/JSONL 可解析。这是报告编制方法限制，不改变 case/deal/valuation IDs、HTTP 状态、数值、XLSX 公式、端口或哈希等真实执行证据。

## 初始盲测

8 个文件上传后建立 `case-20260804-99d9fc5072`，随后建立 `deal-20260804-6d3051b880f4` 和 `valuation-47603e4eba278a0e`。146 个输入首先按 candidate 保存，计算返回 400。测试 FA 再以固定 loopback UI 身份确认同一业务 payload，旧系统计算成功，但在估值日 2026-06-30、首期 FY2027E 的情况下直接使用 1/2/3 指数，并把 Calculation Integrity 标成 passed、Decision Readiness 标成 screen_grade。

初测 QA 得分 84/100，仅表示本轮焦点覆盖。三个问题：

- `R05-F01` S1：非年末 DCF 缺失 stub/逐期 timing，旧系统仍静默计算成功。
- `R05-F02` S2：源码/README 为 0.5.0，但旧 editable 安装元数据显示 0.4.0。
- `R05-F03` S3：授权用语 `internal_only` 被拒，测试需改用另一个枚举值。

安全控制在旧系统中已经有效：计算对象注入 403、旧版本或错误哈希 409、完全相同幂等重放一致、Agent approval 路由 404。

## 企业追问与补件

FA 留下 7 个逐字问题：主体与范围、财务底稿、H2 stub、WACC/终值假设、EV→Equity、可比公司集合和内部使用授权。企业角色补交 9 个文件；首包与补件合计 17 个文件。响应状态：2 answered、5 partial、0 not available。

关键补件提出：

- H2 2026E FCFF：downside 23.000、base 27.950、upside 31.500 CNYm；
- period end：2026-12-31、2027-12-31、2028-12-31、2029-12-31；
- discount exponent：0.5、1.5、2.5、3.5；
- EV→Equity 净调整：-34.000 CNYm；
- Comps 主统计建议只用三家 core，五家全样本只作交叉检查。

全部补件仍是 candidate，`confirm_inputs=false`。真实签署授权、底层账簿、银行函证、合同、资产权属、税务文件、真实市场数据和 FA 正式接受均没有被伪造。0 个补件被接受为事实，0 个问题自动关闭。

初始 Q02 把列出的七个期间写成“八项财务序列”。企业响应实际按七个期间、八个财务字段处理，代码计算未受影响；该文本错误记录为 S3 流程债务。

## 修复前冻结基线

在提交任何修复前，旧代码被单独冻结并运行于隔离端口。17 个文件建立 `case-20260804-d2dabeb8c4`、`deal-20260804-59505701df12`、`valuation-ea028e418defe4f1`，全部哈希一致。补件没有自动导入；原 146 个输入以测试身份确认后仍能按 1/2/3 计算，且没有 timing blocker 或 warning。`R05-F01` 被再次复现。

该基线同时确认：持久化补件状态机、request/submission linkage 和自动局部重算依赖图均尚未实现。

## 定向工程修复

工程修改保持在三个已证实问题范围内：

1. 每个 FCFF period 可保存结构化 `period_end` 和来源化 `discount_exponent`，指数单位为 years。
2. 请求时与不可变版本计算时都重新校验：3–5 期、完整覆盖、>0、≤100、严格递增、三情景完全一致。
3. 自由文本 `FY2027E` 永远不能推断日期或指数。
4. 唯一兼容路径是估值日为 12 月 31 日，且三情景都有人工确认的、连续年度 12 月 31 日结构化 period end；这时才允许 1..N。
5. 显式指数同时控制每期 FCFF 和终值折现，两组敏感性共用同一 timing。
6. 失败计算保持 `inputs_incomplete`，不能伪装成 `calculated_screen_grade`。
7. UI 支持 3/4/5 期，并明确补件不会自动导入或确认。
8. XLSX 显示指数、日期、input ID、source ID、locator、as-of 和公式。
9. `internal_only` 只作为输入 alias，落库仍是 canonical `internal`。
10. 刷新 editable 安装并增加源码/分发版本一致性测试，均为 0.5.0。

定向测试 101 项通过。

## 修复后独立回放

17 个原样文件建立：

- Case：`case-20260805-9dbb8c4a4e`
- Deal：`deal-20260805-c26ceb6c3711`
- Valuation：`valuation-cf48a22919308733`

48/48 个限定断言通过：

- 原 candidate 计算 400；
- 原 07 即使只改 `confirm_inputs=true`，缺 timing 仍 400 且版本不前进；
- 四期修正请求首次按 candidate 保存，计算仍 400；
- 用固定本地测试身份确认同一业务 payload 后才生成 v5；
- Calculation Integrity passed，Decision Readiness screen_grade；
- timing basis 为 `explicit_per_period`，指数为 0.5/1.5/2.5/3.5，终值使用 3.5；
- 注入 403、stale 409、wrong hash 409、幂等重放一致、Agent approval 404；
- `internal_only` 成功输入并规范化为 `internal`；
- FA review、内部批准和公开发布均未发生。

数值结果：

| 场景 | DCF EV（CNYm） | Equity value（CNYm） |
|---|---:|---:|
| Downside | 561.47 | 527.47 |
| Base | 1,017.23 | 983.23 |
| Upside | 1,503.27 | 1,469.27 |

Trading Comps EV 单独为 862.40–931.00 CNYm；没有进行方法加权或总分汇总。

XLSX 下载 200，9 张 sheet 可见，DCF 共 69 个公式。三个场景的指数分别位于 `C8:C11`、`C37:C40`、`C66:C69`；折现因子公式使用这些单元格，终值分别使用 `D11`、`D40`、`D69`；I 列保留 timing input ID、`artifact-0012`、JSON locator 和 2026-06-30。

## Chromium 与门禁

协调者在另一个全新 workspace 用真实 Chromium 打开 Deals：

- 3/4/5 期 selector 可见；
- 4、5 期选择后对应 period_end 与 discount_exponent 可见且 required；
- 切回 3 期后两行隐藏且 required 移除；
- 未确认输入前计算按钮禁用；
- 页面明确提示企业候选补件不会自动导入或确认；
- 页面自身日志为空，无 error overlay；
- 测试进程、端口、浏览器 tab 和临时目录已清理。

最终门禁：403 项 Python 测试、Ruff、6 项 Node 估值测试和 `git diff --check` 通过。

## 本轮结论与保留边界

协调层 QA 得分为 96/100，只评价本轮控制覆盖与可回放性。扣分来自补件中心仍非产品内持久对象、Q02 文本歧义和固定 loopback 身份，而不是对 Synthetic 企业的商业判断。

仍未实现：企业补件中心状态机、企业账户/UI、request–submission–evidence 原子关联、局部重算依赖图、真实身份/RBAC、真实企业数据试点、真实市场数据和正式 FA model tie-out。估值仍是受控 screen-grade 内部工具，不是正式估值意见。
