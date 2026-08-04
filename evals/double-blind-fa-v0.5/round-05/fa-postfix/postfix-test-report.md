# Double-blind FA QA · Round 05 post-fix replay

## 结论

Round 05 的 S1 DCF timing 缺陷已经修复并完成真实 loopback HTTP、不可变版本、哈希、幂等、安全边界和 XLSX 公式回放。48/48 个限定断言通过；协调层 QA 得分为 96/100，仅衡量本轮控制覆盖，不是企业、产品、投资或风险评级。

企业材料、H2 stub、DCF 假设、Bridge 和可比公司均为 Synthetic。测试中的 `local-fa-ui` 是 loopback 服务固定记录的测试身份，不证明真实自然人已经接受假设。没有 FA review、内部批准、正式估值意见或公开发布。

## 隔离与材料

复测 FA 使用 fresh no-history 任务；两个 fresh 只读子任务分别提取允许材料和定位公开 HTTP 合约。复测只读取 Round 05 首包、补件、问题登记和修复后产品，没有读取其他轮次公司材料或隐藏真值。

17 个文件全部上传为一个全新 case，17/17 产品 artifact 哈希与本地字节一致。两份 manifest 共声明 15 个非 manifest 文件，15/15 匹配；manifest 自身按文件内政策排除 self-hash。Case 为 `case-20260805-9dbb8c4a4e`。

## 用户动作与补件状态

初始 7 个问题逐字保存在 `../fa-initial/question-register.json`。公司响应为 2 answered、5 partial；复测后的 `question-register-after.jsonl` 保留每个问题的剩余缺口、下一动作和重算范围。0 个响应被系统接受为事实，0 个问题自动关闭，企业补件没有自动导入估值输入。

初始 Q02 把列出的七个期间写成“八项财务序列”，但实际要求和公司响应均按八个财务字段处理。这是协调文本 S3 问题；未改变计算，但下个模板应写成“七个期间、八个财务字段”。

## HTTP 重放

新 Deal 为 `deal-20260805-c26ceb6c3711`；输入 `confidentiality_level=internal_only` 成功，持久化使用既有 canonical 值 `internal`。新估值为 `valuation-cf48a22919308733`。

真实状态顺序：

1. 原 07 请求以 `confirm_inputs=false` 保存为 candidate；计算返回 400，没有计算结果。
2. 只把原 07 改为 `confirm_inputs=true`、仍不提供逐期 timing，请求返回 400，版本号不前进。
3. FA 从可见补件独立构造 H2 2026E、FY2027E–FY2029E 的四期请求；第一次仍以 candidate 保存，计算继续 400。
4. 软件回归随后用固定本地测试身份保存同一业务 payload 的 `confirm_inputs=true` 版本。这一步只模拟“人工确认门”是否有效，不表示真实 FA 接受 Synthetic 假设。
5. 服务端计算返回 201，生成 v5 `calculated_screen_grade`；Calculation Integrity passed，Decision Readiness screen_grade，但 FA review 与任何批准仍为空。

修复后 timing 明确为 `explicit_per_period`：

| 期间 | Period end | 指数 |
|---|---|---:|
| H2 2026E | 2026-12-31 | 0.5 |
| FY2027E | 2027-12-31 | 1.5 |
| FY2028E | 2028-12-31 | 2.5 |
| FY2029E 与终值 | 2029-12-31 | 3.5 |

三个场景使用完全相同的有序 timing；每个指数都有 input ID 和来源字段，FCFF 和终值都由服务端使用这些指数重建。

## 结果

| 场景 | DCF EV（CNYm） | Equity（CNYm） |
|---|---:|---:|
| Downside | 561.47 | 527.47 |
| Base | 1,017.23 | 983.23 |
| Upside | 1,503.27 | 1,469.27 |

Trading Comps EV 单独为 862.40–931.00 CNYm。系统没有加权 DCF 与 Comps，也没有生成单一总价值、投资建议、信用结论或综合风险评级。

## 负向、安全与并发检查

- 浏览器提交 calculation 对象：403；计算只能由服务端从指定不可变版本重建。
- stale version：409。
- wrong version hash：409。
- 同一幂等键和同一 payload：返回同一版本，没有重复计算。
- Agent approval 路由：404；Agent manifest 不提供 review/approval 能力。
- 没有 FA review、internal approval 或 external approval。

## XLSX 检查

导出 HTTP 200，9 张工作表全部 visible，DCF 表共 69 个公式。抽查：

- Downside：`C8:C11 = 0.5/1.5/2.5/3.5`，`D8 = 1/(1+$B$5)^C8`，`B16=B15*D11`，`B20=B13+B19*D11`。
- Base：`C37:C40 = 0.5/1.5/2.5/3.5`，`D37 = 1/(1+$B$34)^C37`，`B45=B44*D40`，`B49=B42+B48*D40`。
- Upside：`C66:C69 = 0.5/1.5/2.5/3.5`，`D66 = 1/(1+$B$63)^C66`，`B74=B73*D69`，`B78=B71+B77*D69`。
- `I8:I11`、`I37:I40`、`I66:I69` 保留 timing input ID、`artifact-0012`、JSON locator 和 `2026-06-30`。

## 浏览器与最终门禁

协调层另用全新本地 workspace 和真实 Chromium 检查 Deals 页面。3/4/5 期 selector 可用；选择 4 或 5 期时新增 period_end 与 discount_exponent 字段可见并变为 required，切回 3 期后隐藏并移除 required。页面明确说明企业候选补件不会自动导入或确认；没有确认输入前“运行计算”禁用；页面自身日志为空。测试 case/deal/valuation、专用进程、端口与临时目录均已清理。

最终工程门禁：403 项 Python 测试通过；Ruff 通过；6 项 Node 估值测试通过；`git diff --check` 通过。安装元数据与源码版本均为 0.5.0。

## 尚未实现

本轮只修复受控估值 timing、版本标识和保密词汇摩擦。持久化补件中心状态机、企业账户与 UI、request/submission/evidence 关联、局部重算依赖图、真实身份与 RBAC、真实企业数据和真实市场数据仍未实现。当前结果只能用于内部 screen-grade 合成回归，不构成正式估值意见。
