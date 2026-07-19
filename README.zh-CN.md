# CleanTech Finance（中文说明）

这是一个以金融研究为主线的清洁能源公司证据审计工具。v0.3 的正式产出不是自由分析，而是“单维度五格证据卡”。

输入公司年报和可选公开资料后，它会：

- 从合并财务报表中保守抽取关键数字并保留页码；
- 用本地公式计算收入增长、毛利率、自由现金流、资本开支强度等指标；
- 为两个已验证金融维度生成固定五格卡：子行业定位、事实、锁定的方法论框架、框架应用、缺口与人工项；
- 为其余四个金融维度编写带明确子行业范围的输入合约蓝图，但不把“已编写”说成“已验证”或“已实现”；
- 把证据不足、口径不明和必须人工判断的事项放入核验队列；
- 同时输出 JSON、Markdown、HTML 和 CSV。

默认核心流程离线运行，不调用模型、不上传年报，也不自动生成投资评级或 DOE ARL 分数。Agent Skill 只能准备带来源的子行业、对标和缺口语义输入，不能提交或覆盖红黄绿信号、规则、路径或理由；本地确定性规则引擎是唯一信号来源，并记录规则版本、范围、输入与哈希。因此“模型调用 0 次”只描述本地核心，不掩盖前置 Agent 研究。

## 当前真实完成度

- `盈利与单位经济性`：端到端验证完成，五格卡已实现；
- `现金流与资金缺口`：端到端验证完成，五格卡已实现；
- 其余四个金融维度：已有规则输入合约蓝图，但不可执行、没有判断卡，也未做公开公司端到端验证；
- 17 个商业化风险维度：只做候选证据检索，未实现判断卡或 ARL 评分。

29/29 与 28/28 只证明两维的事实抽取、页码、公式、引用和护栏通过测试，不代表投资判断准确。

v0.3 的正式五格卡将各格标题、锁定判断框架、规则路径与理由、信号说明、第 5 格缺口和底部免责声明中英并置；数字、页码、来源标题和链接保持原始口径。

## 最小演示

```bash
python -m pip install -e ".[pdf]"
$env:SEC_USER_AGENT="Your Name your-email@example.com"
python scripts/run_release_gate.py
```

阳光电源 2025 年报测试中，工具自动定位了收入、营业成本、净利润、经营现金流、资本开支和期末现金，并生成两张独立五格卡。完整方法和限制请阅读 [英文 README](README.md) 与 [方法文档](docs/methodology.md)。

## 发布前真实公司测试

测试不是“最后看一眼”，而是一条必须通过的发布门槛：

1. 先只用阳光电源跑“盈利与单位经济性”“现金流与资金缺口”两个维度，验证公开资料是否真的能提供证据、页码和缺口；
2. 失败就修通用规则并重跑，直到阳光电源通过；
3. 再跑完整产物与引用校验；
4. 最后用同类公司 Enphase 的美国 10-K 复现，不允许写公司名特例；任何失败都要同时回归两家公司。

当前公开数据回归结果：阳光电源抽取 29/29、卡片契约 27/27；Enphase 抽取 28/28、卡片契约 27/27。阳光电源两维均为绿色证据信号；Enphase 两维均为黄色证据信号。信号不是评级，必须与依据和缺口一起阅读。详见[测试协议](docs/evaluation.md)。

已下载并校验两份公开年报后，可用一个命令执行最终发布门槛：

```bash
python scripts/run_release_gate.py --skip-download
```

## 十家公司本地验证

v0.3 使用十家不同的公开公司完成了十轮泛化。每一轮都保留初始失败、一个通用优化、定向回归、最终产物和下一项残余风险。可运行严格注册表门槛并重建离线双语总览：

```powershell
.\.venv-new\Scripts\python.exe scripts\run_company_loop_registry.py
.\.venv-new\Scripts\python.exe scripts\build_company_loop_index.py
```

打开 `outputs/company-loops/index.html`，即可查看恰好十个已注册最终案例、相互独立的盈利与现金信号、校验状态、辅助来源状态，以及每家公司的双语报告。

辅助来源始终可选且不具信号权威。总览页面允许用户勾选来源并生成经过白名单校验的本地重跑命令，例如：

```powershell
.\.venv-new\Scripts\python.exe scripts\run_company_loop_case.py `
  --case albemarle `
  --aux-source albemarle-2025-results
```

运行器会拒绝未知来源，且只有所选事实通过校验后才重生成报告。切换辅助来源不能改变核心信号、规则哈希或输入哈希。

它会先跑阳光电源，失败则立即停止；通过后再跑 Enphase，并为两家公司分别生成完整报告和机器可读评估结果。

本项目仅用于研究辅助，不构成投资、会计、法律、工程、安全或监管建议。

## QA 企业进入诊断与分诊

QA 层接收人工指定企业的原话和人工提供的公开资料，形成产品/技术、子行业、目标市场、出海阶段、核心缺口、资源需求六项画像。问题会根据前一轮答案补问缺失字段，并按不同出海阶段进入市场依据、试点证据或商业可重复性分支，不是固定问卷。字段仍不完整时，同一个 `-clarification` 补问 ID 可以重复出现直至完整；每条回答的 `answer_id` 仍必须唯一，且不能与来源 ID 冲突。

每个画像字段必须引用来源中的精确原文。系统会按实际 router 顺序重放问答；原话支持的画像值必须等于对应 `response[field]`，文档支持的画像值必须有主体绑定的字段/值/引文 assertion。无出处、主体不符、值不符或原文不匹配时，字段正式值会清空，候选值保留并进入缺口队列；通过只证明可追溯结构，不证明企业陈述为真。

```powershell
cleantech-finance qa init qa-case.json
cleantech-finance qa next qa-case.json
cleantech-finance qa validate qa-case.json
cleantech-finance qa report qa-case.json --out outputs/qa-company
```

分诊只输出 Expert、Map、Radar 指向及其引用理由，三个下游 Agent 当前均不执行。可计数的五家公司交付还必须有外部确认的五家公司摘要、逐字段人工画像 ground truth、五个案例哈希、五个画像 ground truth 哈希和哈希链重跑历史；库内 `contract_test` 即使五次执行全过也不能计数。有年报案例继续使用既有两项财务 ground truth，无年报案例必须有人工 waiver。五家公司中至少一家必须是 `annual_report_status=available` 并通过财务合同；五家全部 waiver 会得到 `financial_not_exercised`，不能宣称财务溯源或完整交付。

在仓库根目录先预览并固定人工提供的选择材料：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --selection-digest-only
```

即使十个声明哈希尚未填写，该命令也会输出五个实际案例哈希、五个实际画像 ground truth 哈希、聚合的 `case_set_sha256` 和明确未确认的 attestation 模板。哈希缺失或不匹配时，JSON 仍会打印，但退出码为 `2`。把十个实际哈希复制回注册表并重跑，直到 `ready_for_human_attestation=true`；这只表示材料可以交给人核对，不表示已经有人确认。人工逐一核对五家公司后再填写 attestation。它仍是未附加密码学签名的人类声明，不是声明者身份的密码学证明；`qa_delivery` 结果顶层 `human_attestation_assurance` 明示 `status=unsigned_claim_only`、`cryptographic_identity_verified=false`。

填写 attestation 后先做可丢弃预检，再做正式运行：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --preflight `
  --out D:\private-results\qa-company-loops

& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --out D:\private-results\qa-company-loops
```

`--preflight` 在临时目录执行生产路径，正常返回时删除临时制品和临时历史；其中可选的 `--out` 只检查拟用目录在项目树外，不会创建正式目录。正式运行必须显式提供项目树外的 `--out`。公司特例检查会扫描整个 QA rule bundle 的决策字面量，包括 Python 控制流/字典键和 Schema `const` / `enum`，发现当前公司身份特例即失败关闭。企业只能由人指定。详见 [QA 诊断与循环说明](docs/qa-diagnostic-loop.md)。

结果与历史的 `regression_evidence` 按每家公司最近一次既有执行通过记录观察到的 required、executed、passed、failed、missing、input-changed 集合；只有非空基线在规则变化后以相同输入全部重跑通过才是 `complete=true`。若该次运行首错即停，同一规则摘要的后续重跑会继续保留这一待完成要求，直至完整基线通过。Markdown 与 HTML 同步显示其 `status` 和 `complete`。

## 作者归属

初始方法论与实现：Cassian。作者归属保留在仓库层；单张证据卡采用开源中性的方法论声明，不再展示个人署名。
