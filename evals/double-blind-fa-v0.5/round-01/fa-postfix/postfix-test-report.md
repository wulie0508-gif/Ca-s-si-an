# Round 1 修复后独立 FA 盲重放

结论：**88/100，带重要产品缺口通过。** 当前版本在工作流适用性、交易事实边界和估值门槛上保持了 fail-closed；13 个文件不会因数量自动抬升收购覆盖率，也没有自动创建 Deal 或估值。

## 重放范围

- 仅使用 `company-submission` 4 个文件与 `company-supplement` 9 个文件。
- 在 `127.0.0.1:8873` 通过带 `Origin`/`Referer` 的真实 same-origin HTTP multipart 请求，每个 Case 一次累计上传 13 个文件。
- 创建 company_intake Case `case-20260804-a4c809de2e`，并以相同材料创建显式 acquisition Case `case-20260804-e1d0b3efab`。
- 未读取被禁材料，未使用 Git，未修改产品代码。

## 关键观察

company_intake 中 acquisition applicability 为 `not_applicable`，percent 为 `null`，访谈 readiness 为 `not_applicable`，系统未生成收购买方问题。工作流为：材料完成、证据待人工、分析阻塞、补件/复核/输出不可用；下一步原样为“确认材料识别范围”。

显式 acquisition 中 applicability 为 `applicable`，但 13/13 文件只被接受为 routing candidates。由于 `requirement_candidates=[]` 且 profile hints 为空，覆盖率保持 `0.0%`，22 个 critical requirements 均未覆盖，访谈 readiness 为“尚不足”；系统原样生成 8 个入口问题，已逐条写入 `observed_questions.jsonl`。

路由总体合理：财务包进入 `financial_core`，技术验证进入 `technology_arl`/`market_export`/`governance_legal`，控制 manifest 保持 `generic_supporting`。但 `FA-Q02-project-revenue-pack.csv` 仅路由为 `policy_resource`，值得人工复核；全部 profile hint tags 为空。

Deal 接口返回空列表。没有买方、交易范围、预算/持股/资金来源、接触授权、NDA 或合格初步估值 requirement candidate，因此未建 Deal、未运行估值，符合门槛要求。`preliminary_valuation` 仍是 critical gap，系统问题为：“初步估值使用了哪些财务口径、预测假设和可比依据，区间如何形成？”

## 仍缺能力

1. company_intake 没有独立 readiness 百分比或补件问题，只能看到 acquisition 不适用。
2. 识别出的 artifact roles 无法在人工确认后显式晋级为 requirement candidates，造成“13 个文件已接收但 0% 覆盖”的断层。
3. profile hints 全空，限制了主体、行业、阶段与地域路由。
4. 下一步仍是通用“确认材料识别范围”，未优先展示五个收购入口门槛，也未解释 Deal 创建/估值解锁条件。
5. `FA-Q02-project-revenue-pack.csv` 的单一 `policy_resource` 路由可能漏掉财务或市场用途。

## 独立评分

- 适用性与 fail-closed：25/25
- 问题与 critical gap 可追溯性：23/25
- artifact routing / profile hints：17/25
- Deal 与估值门槛：23/25

总分：**88/100**。
