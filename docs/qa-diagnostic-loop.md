# CleanTech Evidence QA 诊断层与五家公司自迭代

## 定位与能力边界

QA 诊断层是 Expert、Map、Radar 的公共输入层，不是投资、信用、综合风险或认证工具。它把企业原话和人工作为输入提供的资料整理成可追溯画像，并只输出下游分诊留桩；三个下游 Agent 均未实现、不会执行。

盈利/单位经济性与现金流/资金缺口两项既有财务能力保持独立。只有本次输入明确声明年报可用，并同时提供人审 Manifest、抽取 ground truth、卡片 ground truth 及固定哈希时，QA loop 才调用既有离线财务内核。其余情况必须有人工 profile-only waiver，状态单列为 `profile_only_waived`，不会生成财务卡。

## QA 质量闸门

画像固定包含六个字段：产品/技术、子行业、目标市场、出海阶段、核心缺口、资源需求。

每个字段必须引用企业原话或人工提供的资料。确定性检查包括：

- 回答必须严格按照动态 router 实际发出的顺序记录；倒序、未知问题或未发问题失败关闭；
- 每个已提供的结构化 `response` 字段必须有且仅有一条 `response_assertions` 记录；断言中的 `value` 必须与 `response[field]` JSON 精确相等，`quote` 必须是企业 `statement` 的精确非空子串；布尔值和数字不能冒充文字证据；
- 企业原话引用的画像值必须精确等于对应 `response[field]`；
- 文档来源必须以 `subject_entity` 完整绑定当前企业的标识方案、值和法定名称，并有匹配的 `field/value/quote` 结构化 assertion；企业回答同样必须以 `respondent_entity` 绑定主体，且每个结构化 response 字段都要有精确原话 assertion；
- `quote` 必须是来源原文的精确非空子串；
- `core_gaps` 和 `resource_needs` 的字符串条目不得为空；对象条目必须有非空 `category` 与 `description`；
- 推断必须有 `rationale`；重复候选、无来源、主体不符或值不符均失败关闭。

失败字段的正式 `value` 为 `null`，原候选保留在 `candidate_value` 并进入 `gap_queue`。任何上游失败都会使 `triage.eligible=false`，Expert/Map/Radar 全部 `selected=false`，避免失败产物被下游误消费。

这些自动检查证明结构、主体、值和精确引用的一致性，不证明企业陈述为真，也不能自动判断自然语言在现实世界中的真实性。真实五家公司交付还必须提供独立的逐字段人工 traceability ground truth，review scope 为 `field_value_quote_and_entity_binding`；runner 按哈希绑定并逐字段比较完整主体、值、结论类型与精确引文。

## 动态问题图

```powershell
cleantech-finance qa init qa-case.json
cleantech-finance qa next qa-case.json
cleantech-finance qa validate qa-case.json
cleantech-finance qa report qa-case.json --out outputs/qa-company
```

问题先问产品、客户问题与子行业；缺字段时先定向追问，再进入目标市场。随后按已经完成的出海动作分支：

- `domestic_only` / `exploring`：首个市场依据与未来 12 个月里程碑；
- `market_validation` / `pilot`：客户验证、试点证据与商业转化条件；
- `early_commercial` / `scaling` / `established`：付费客户证据与可重复性。

最后追问核心缺口和资源需求，并把每项资源绑定到具体里程碑。问题不是固定问卷；完整会话会由 validator 从空状态逐条重放。字段仍不完整时，同一个以 `-clarification` 结尾的补问 `question_id` 可以再次出现，直到该字段完整；每条回答的 `answer_id` 仍必须唯一，且不得与来源 ID 冲突。

## 人工输入边界

- 企业必须由用户或其他外部人员指定；Agent 不得发现、筛选或补足企业。
- 企业和所有公开/案例来源均必须在输入中明确绑定稳定实体 ID。
- 私密材料必须放在仓库外，路径可以是本地绝对路径；`qa_delivery` 的输出目录也必须在项目树外。UNC、设备路径、映射远程盘和经过 reparse point 的输入路径失败关闭，避免把网络读取错误记为离线执行。
- 持久化产物标记为 `internal_restricted`，包含完成画像所需的精确引文；未经单独授权和人工审核不得公开。
- `actor_type=human` 加哈希只能形成一份未附加密码学签名的人类声明和可审计合同，不能密码学证明声明者身份。`--selection-digest-only` 输出的模板明确处于未确认状态；人工填写后也仍不是数字签名。`qa_delivery` 结果顶层以 `human_attestation_assurance.status=unsigned_claim_only` 和 `human_attestation_assurance.cryptographic_identity_verified=false` 明示该边界；需要强认证时应在仓库外增加 detached signature。

## 分诊留桩

- `Expert`：产品、技术、子行业和专业/认证语境；
- `Map`：目标市场、出海阶段、进入路径和资源匹配；
- `Radar`：核心缺口和待补证据。

每条有效分诊理由继承画像字段的 `evidence_refs`，JSON、Markdown、HTML 都显示精确出处；HTTP(S) 公开资料在两种人读报告中可一跳打开，非 URL 稳定来源 ID 以文本显示。输出状态始终为 `stub_only`。

## 五家公司注册表

`schemas/qa-loop.schema.json` 强制恰好五家公司、1–5 顺序、唯一案例/实体 ID，并区分两种模式：

- `qa_delivery`：可计数交付；必须有外部人工 selection attestation、五个案例输入哈希、五个 `qa-profile-ground-truth` 哈希，以及每家公司一份对应的人工复核文件；
- `contract_test`：仅供库内测试，需要代码显式开启，`passed` 永远为 `false`，即使五个执行全部通过也只能得到 `contract_fixture_only`。

状态分两层：`execution_passed` / `completed_execution_count` 只表示机制检查完成；`passed` / `completed_case_count` 只表示真实交付通过。因此 contract fixture 可以是 `execution_passed=true`，但每家公司、人工复核、财务汇总和顶层交付的 `passed` 都保持 `false`。

真实交付先准备五个案例和五份人工画像 ground truth。即使注册表中的十个声明哈希尚未填写，也可以先运行材料预览：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --selection-digest-only
```

命令会打印五个实际 `input_sha256`、五个实际 `profile_ground_truth_sha256`、聚合的 `case_set_sha256`，以及明确未确认的 `unconfirmed_attestation_template`；它不会修改注册表、选择公司或创建人工确认。声明哈希缺失或不匹配时，JSON 仍会打印，但进程退出码为 `2`。把十个实际哈希复制到对应注册表行后重复运行，直到 `ready_for_human_attestation=true`。

这个 `ready` 只表示十个声明哈希与可读取材料一致，材料已可交给人核对，不表示已经有人确认。人工必须逐一核对五家公司及其输入，再填写 `selection_attestation` 中的复核人、RFC 3339 时间、新的 batch ID、上述 `case_set_sha256` 和固定声明文本。当前 attestation 是未附加密码学签名的人工声明，不是身份的密码学证明。

正式写入任何输出前，可以用相同生产 runner 做一次可丢弃预检：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --preflight `
  --out D:\private-results\qa-company-loops
```

`--preflight` 在操作系统临时目录中按正式运行路径执行五家公司，保留首个失败即停止的语义；正常返回前删除临时制品和临时历史。这里的 `--out` 可省略；若提供，只检查拟用正式目录是否在项目树外，不创建该目录，也不创建正式 run 或正式历史。预检通过仍不证明人工声明者身份。

预检通过后才执行正式运行；正式模式必须显式提供位于项目树外的 `--out`：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --out D:\private-results\qa-company-loops
```

如果通用 QA 规则文件或 Schema 摘要发生变化，下一次运行必须同时给出双语通用修复说明：

```powershell
& .\.venv-new\Scripts\python.exe .\scripts\run_qa_loop.py `
  --registry D:\private-cases\qa-registry.json `
  --out D:\private-results\qa-company-loops `
  --change-note "General rule change; no company-name exception." `
  --change-note-zh "通用规则修复；未增加公司名特例。"
```

Runner 通过排他 `.qa-loop.lock` 串行执行；锁残留时失败关闭，由操作人员先核实是否仍有进程再处理。每次运行都从第一家公司开始、在首个执行失败处停止。锁定后，它把 registry、五份案例、画像 ground truth、财务 Manifest、两份财务 ground truth 及 Manifest 的全部角色来源一次性复制到仓库和输出目录之外的用户级易失临时区；摘要、字节数和 JSON 解析均来自同一次捕获的字节。audit 只读取重写到该内容寻址快照的 Manifest，来源摘要与抽取共享同一内存字节，两份 evaluator 也直接使用已解析的快照 ground truth，不再重读原路径。

快照不进入 `runs/.staging/`、最终制品、历史或 Git；提交历史前必须成功删除并确认目录不存在，否则运行失败且不提交历史。持久制品只保留逻辑引用、哈希和大小，并在提交前扫描临时路径与原始本地路径泄露。正常执行可抵御原始输入在运行中“替换后恢复”的 ABA；进程被强杀或断电时不能承诺未加密磁盘上的法证级擦除，高敏材料仍应放在受当前用户 ACL 与磁盘加密保护的本地卷。

Runner 同时拒绝 run storage 中的 symlink / Windows junction，并在提交前复核原 registry、案例、画像 ground truth、财务合同和 Manifest 所有来源文件的内容摘要；持续漂移时不提交历史。规则文件若与当前进程已导入的代码不一致，也要求用新进程重启运行。

Runner 先在 `runs/.staging/` 生成案例包和三份总报告，全部成功后计算逐文件 manifest 与整棵制品摘要，原子移动到唯一的 `runs/<number>-<rule-digest>-<timestamp>/`，最后才原子提交 `qa-loop-history.json`。历史 v2 同时校验前序哈希链、相对 run 路径和完整制品树；文件被改、删或新增都会在下一次加载时失败关闭。中途异常或未提交目录不会删除，而会在下一次运行移入 `_orphaned/` 留审计痕迹。顶层 `qa-loop-report.*` 只是可恢复的 latest alias；其更新失败不会否定已经提交且哈希固定的 run，返回值会标记 `latest_alias_status=partial_failure`。

同一 `qa_delivery` 历史固定 `run_mode`、selection batch、selection digest、五份案例输入和五份画像 ground truth；输入变化必须启用新的输出目录和 batch。contract 与 delivery 也必须分开输出目录。只有失败前后 `input_bundle_sha256` 相同、通用规则摘要改变且 delivery 后续通过时，才会生成 `generalization_issues`；输入修订单列为 `input_corrections`，不得冒充通用规则修复。规则摘要覆盖 QA 合同以及实际财务内核、报告器、Manifest Schema 和两份 evaluator。公司特例扫描覆盖整个 QA rule bundle：Python 的比较/控制流/断言/匹配及字典键等决策字面量，以及 Schema 的 `const` / `enum` 合同值；若它们精确写入当前五家公司的名称、实体 ID 或案例 ID，会失败关闭。

结果与历史中的 `regression_evidence` 以每家公司最近一次既有 `execution_passed` 为基线，记录 required、executed、passed、failed、missing、input-changed 等实际重跑集合；只有基线非空、规则已变化且所有基线案例均以相同输入重跑通过时才是 `complete=true`。若规则变更后的运行首错即停，同一规则摘要的后续重跑会继续继承未完成的回归要求，直至完整基线通过。Markdown 与 HTML 人读报告同步显示其 `status` 和 `complete`，不再用策略声明代替观察证据。

## 财务合同

`annual_report_status=available` 时必须同时满足：

- 两份 ground truth 分别通过 `financial-ground-truth.schema.json` 与 `card-ground-truth.schema.json`；
- QA、注册表、两份 ground truth、人工 review 与 Manifest 主体精确绑定；有稳定身份时同时比较 scheme、value、legal name；legacy Manifest 仅允许精确法律名称兜底；
- 人工 review 固定 Manifest、两份 ground truth、全部 `subject` 年报原文件，以及 benchmark / auxiliary / identity 在内的 `all_sources` 角色、ID 与 SHA-256；非 subject 来源变化同样会改变案例输入摘要，不能冒充规则泛化；
- 抽取 ground truth 是两个共同期间 × 五个最低事实，并含四个验证指标；
- evaluator 至少完成抽取 28 项、卡片 27 项检查，退出码为零；
- audit validation 通过，`model_calls=0`、`network_calls=0`。

五家公司中至少一家必须是 `annual_report_status=available` 并通过上述财务合同。若五家全部使用 profile-only waiver，执行状态会标为 `financial_not_exercised`；即使五份画像均通过，也不能宣称财务溯源已验证或完整 `qa_delivery` 已交付。

两项财务维度、抽取语义、规则和信号没有改变。`audit.py` / `ingest.py` 仅增加受控输入根与“同一来源字节同时用于摘要和抽取”的执行边界；Sungrow 与 Enphase 的人工值和信号保持原样。

## 输出与停止条件

每家输出画像、分诊、缺口、下一题和（如适用）财务证据包。总报告汇总：

- 每家公司画像卡、精确出处、分诊和缺口；
- 高频缺出处字段、计数和对应补问建议；
- 有年报案例的财务 checks 与 traceability 百分比；
- 从哈希链中机器验证的“失败 → 通用规则变更 → 通过”事件及已回归公司。
- 与规则泛化严格分开的输入修订记录，以及每次运行的完整制品树摘要。

只有真实 `qa_delivery` 的五家公司全部通过才能停止并称为完成。历史十家公司财务注册表、Sungrow/Enphase 基准、虚构 Demo 或复制的 contract fixture 均不能替代本轮五家人工指定企业。
