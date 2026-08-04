# Round 3 首轮盲测工程诊断（修复前）

## 结论

本轮指定的五类缺陷均已复现并确认。它们不是同一个问题的不同表述，而是五个可分离的工程缺口：上传完整性未核验、文档控制轴未建模、证据去重未建模、跨文件主张未建图，以及财务预检适用性判定过宽。

本诊断只读取了 Round 3 的 `company-submission/`、`fa-initial/`，以及当前 `src/cleantech_finance/` 和 `tests/`。未读取 Round 4/5，未修改产品代码，未运行或重启服务。

| 缺陷 | 核实结果 | 直接后果 | 根因类别 |
|---|---|---|---|
| 清单声明哈希未与实际上传哈希对照 | 已确认 | 被篡改或清单录入错误的文件仍进入后续分析 | 输入完整性缺口 |
| 权威、批准、生效、签字与版本新旧未分离 | 已确认 | “更新”可能被误解为“更权威”；本轮两个财务计划甚至未被识别为 forecast | 文档控制模型缺口 |
| 底层哈希重复未折叠 | 已确认 | 同一底层证据可被不同文件名重复计数 | 证据计数与溯源缺口 |
| 跨文件主张矛盾未暴露 | 已确认 | 管理层、交易对手和公司登记材料之间的冲突没有形成可审阅问题 | 主张账本缺口 |
| 通用 `as_of_date` 对非财务 CSV 误触发财务预检 | 已确认 | 七份非同质 CSV 被当作财务依据，产生错误的 blocked 财务预检 | 适用性判定缺陷 |

## 关键证据

### 1. 上传清单哈希没有形成完整性门禁

`submission-manifest.json` 为每个 payload 声明了 `declared_sha256`。`07-artifact-provenance-and-duplicates.csv` 的实际上传 SHA-256 为：

`ac19fdbb06dee9cad677bb45288588f3fe395efbedee0ee71a5d1e6a0913d0b3`

清单声明值为：

`ac19fdbb06dee9cad677bb45288588f3fe395efbedee0ee71a5d1e6a0913d0b4`

其余六个已声明 payload 的值相符。当前 `workspace_service.create_case()` 会计算并保存实际 `sha256`，但只检查文件名重复；它没有把实际哈希与清单的 `files[].declared_sha256` 连接起来。`company_intake_preflight._parse_json()` 也只解析既有 Round 2 字段，不读取本轮的声明哈希与文档控制字段。因此，本轮报告没有暴露这个一位十六进制字符的差异。

这不是“把清单值改成实际值”可以自动处理的情况。声明值与实际值谁正确无法由系统自行判断。最小确定性修复应输出逐文件对账状态：`matched`、`mismatch`、`missing_upload`、`unlisted_upload`、`invalid_digest`、`duplicate_manifest_entry`。出现后五类状态时，输入完整性门禁保持 blocked；有 mismatch 的文件进入 quarantine，等待上传者重新提交或明确更正清单。

### 2. 文档控制的五个轴被混在一起或完全遗漏

本轮清单已经把 `authority_class`、`effective_date`、`as_of_date`、`version`、`approval_status`、`signature_status`、`assertion_status` 分开声明，但当前解析器没有消费这些字段。CSV forecast 识别函数只接受字段名 `forecast_version`，本轮两份董事会计划使用的是 `version`，所以初始结果错误地给出 forecast `not_present`。

两份计划恰好证明“较新”不能代替“权威”：

- v1.1 的 `as_of_date` 更新，但为 Draft、未批准、未签字、无生效日。
- v1.0 较旧，但带批准决议、生效日以及主席和秘书签字。

公司登记册也存在相同控制问题：v1.2 与 v2.0 的版本、日期、签字和权威说明不同，而且对 CEO/ESOP 持股、IP 权利负担及东南亚许可给出不同内容。

最小修复必须将版本、资料时点、生效、批准、签字、来源权威、验证状态作为独立字段展示。系统可以按明确的、版本化规则给出“可供人工选择的文档控制候选”，但不得自动选取最高版本、最新日期、已批准文件或已签字文件作为事实依据；已签字本身也不能证明其中的业务主张为真。最终 `selected_authoritative_artifact_id` 默认必须为 `null`，直到人工明确接受。

### 3. 文件名不同但底层内容哈希相同的证据没有折叠

`07-artifact-provenance-and-duplicates.csv` 中下列两个条目声明了相同的底层内容哈希：

- `P2602_框架协议_签署版.pdf`
- `P2602_contract_final_v3.pdf`
- `artifact_content_sha256 = 8c0f7a231c8d0449a4d622f24f0e37d1ebbd5cc3b2f96997d1dd65df5d1e930a`
- `duplicate_group = SYN-DUP-01`

当前 company-intake 路径只保证上传文件名唯一，没有按实际 payload SHA-256 或索引中的底层内容 SHA-256 建立证据单元。由此，同一内容可能因为别名不同而被重复计数。

但本轮还有两层更严格的边界：这两份 PDF 并未实际上传；并且承载这项声明的 `07` 文件自身存在清单哈希不匹配。因此当前只能记录一个“待核实的重复候选组”，不能据此确认两份底层文件相同，更不能把任一别名计为已验证证据。

最小修复应分开处理两种情况：

1. 对实际上传 payload 的 SHA-256，相同哈希形成一个证据单元，但保留所有 artifact 记录和文件名别名，不删除文件。
2. 对索引声明的 `artifact_content_sha256`，只形成候选溯源组；底层 payload 缺失时标记 `underlying_payload_status=missing`。如果索引文件被 quarantine，整组也必须 quarantine，不能影响证据计数或事实状态。

系统不得按文件名、版本号、日期或行序自动指定 canonical evidence。

### 4. 跨文件矛盾没有形成主张图

当前 preflight 主要聚合财务维度候选，没有对 `subject`、`related_subject`、`record_type`、`record_id` 建立稳定的主张键，也没有保留“主张—来源—控制状态—反向主张”的图。因此以下冲突没有被原生暴露：

- P2601：管理层称最终验收并投运；交易对手材料显示最终付款附带 1,000 小时和效率门槛，缺陷通知还显示验收及 110 万元留置款被暂停，缺失登记表称最终验收证不存在。
- P2602：管理层把 1,180 万元列为已签约 backlog；框架文件要求另行采购订单，缺失登记表称不存在可执行 PO。
- P2603：管理层称 860 万元 confirmed PO；邮件和 PO 草案显示预算、技术协议、签字和生效条件尚未完成。
- 计划：v1.0 与 v1.1 对 FY2026E 等期间数值不同，同时文档控制状态相反。
- 公司登记：v1.2 与 v2.0 对 CEO/ESOP 持股、A01/A02 质押、A03–A05 权属以及东南亚许可状态给出冲突记录。

最小确定性修复不是对自由文本做模糊 NLP 后自动裁决。应增加版本化、显式 schema adapter，只在有稳定标识符时建键，例如项目号、精确 `(record_type, record_id)`、精确 `(document_family, period)`；保留所有候选主张和来源。当现有字段不足以可靠表达主张语义时，应请求补充结构化 `assertion_code`，而不是从 `evidence_excerpt` 猜测真值。

冲突输出只表示“需要人工判断”，不得按来源类别、签字状态、日期或版本自动选赢家。修复后至少应稳定地产生与本轮八个 FA 问题对应的候选问题：输入完整性/重复、P2601、P2602/P2603、forecast 权威依据、cash 证明、持股、IP、许可。

### 5. 通用 `as_of_date` 被错误当成财务 schema 证据

`company_intake_preflight._basis_record()` 只要一行包含实体、component、period、`as_of_date`、currency、unit 或 VAT 中任一字段，就会生成 basis record。`_parse_csv()` 对所有 CSV 行无条件调用它，再以 `basis_records` 是否非空决定 `detected`。所以业务、法律、公司登记和溯源 CSV 只要带通用 `as_of_date` 就会触发财务预检。

这解释了初始报告为何把 0002–0008 七份 CSV 全部列为财务 detected artifacts，并错误地产生 blocked 财务预检。与此同时，真正的两份计划又因为 `version` 字段别名未被识别而显示 forecast `not_present`。

最小修复应把“文件可解析”与“适用于财务预检”分开。`as_of_date`、`version`、批准或签字字段都只能是控制元数据，单独出现永远不能使财务 preflight applicable。只有满足版本化的财务 schema archetype 才能进入，例如：

- P&L：明确的 `line_item`、数值、期间，以及货币/单位；
- sales ledger：明确的销售交易和金额字段；
- treasury：账户/余额及限制或可用性字段；
- forecast：财务指标列、期间、版本及相应控制元数据。

修复后，本轮两份董事会计划可作为 forecast 候选被识别；管理层、交易对手、公司登记及溯源文件不应仅因 `as_of_date` 被列为财务依据。管理层声称可用现金 440 万元仍只能是未验证主张，因为缺少账户、实体和限制状态证明，不能伪装成合格 treasury basis。

## 最小实现边界

建议把输入完整性、文档控制、重复和主张冲突放入独立的 deterministic evidence-integrity helper；不要继续扩张财务 preflight 使其兼任通用法律/权威判断。财务 preflight 只收紧适用性并增加 `version` 的受控 forecast schema 支持。

期望的新输出应包含：

- `manifest_reconciliation`：逐文件声明哈希与实际哈希状态，以及总门禁。
- `document_control_candidates`：版本、as-of、生效、批准、签字、权威和验证状态的独立轴；选择字段默认空。
- `duplicate_groups`：实际 payload 组和索引声明候选组分层，并保留全部别名。
- `claim_conflicts`：稳定 claim key、全部候选 assertion、来源和未解决状态。
- `questions`：稳定、顺序无关的问题 ID 和局部影响范围。

### 禁止自动采信边界

- 不得自动修正清单声明哈希，也不得把实际哈希反写为“正确声明”。
- mismatch、缺失 payload 或 invalid digest 不能被降级为 warning 后继续采信。
- quarantine 索引中的底层哈希、重复组和来源声明不得影响证据计数。
- 不得以较新版本、较晚 as-of、已批准、已生效或已签字中的任一单轴自动选择权威文件。
- 不得把管理层声明、文件名、索引记录或自由文本摘要直接提升为已验证事实。
- 不得因来源看似更权威就自动解决跨文件冲突。
- 不得把相同哈希的别名静默删除；应折叠计数但保留溯源。
- 不得在证据未人工接受前启动 valuation、rating、runway 或其他下游计算。

### 局部重算边界

| 变更事件 | 可以重算 | 不应自动重算或改写 |
|---|---|---|
| 清单或 payload 更正 | 完整性对账、该文件 quarantine、由该文件派生的重复组和问题 | 其他业务主张、估值、评级 |
| 文档控制字段更正 | 该 document family 的控制候选和选择问题 | 自动事实选择、无关项目 |
| 底层文件补交 | 对应哈希组、别名、证据单元计数 | 直接关闭主张冲突 |
| 某个主张得到人工回答 | 相同稳定 claim key、相关 readiness gate | 其他 claim key |
| 财务 schema 识别规则修正 | 财务文件路由、preflight 问题和 calculation gate | 自动归一化或计算数值 |
| 账户级现金证明补交并被接受 | cash basis/readiness | 在未接受前计算 runway |

## 拟加回归测试

1. 新增 evidence-integrity 单元测试：六个匹配和一个 mismatch 被精确识别；`07` 被 quarantine；系统不自动更正声明值。
2. 覆盖 `missing_upload`、`unlisted_upload`、无效 digest、重复 manifest filename，全部 fail closed。
3. 覆盖 v1.1 较新但 Draft/未签字，与 v1.0 较旧但批准/签字/生效；验证控制轴分离、选择仍为 `null`。
4. 覆盖公司登记 v1.2/v2.0 的控制轴，不把 “current” 或较高版本自动采信。
5. 覆盖两个不同文件名、相同实际 payload SHA-256：只计一个证据单元但保留两个 alias。
6. 覆盖本轮索引内 P2602 相同底层哈希：底层文件缺失时只形成候选组；索引 quarantine 时不能计为证据。
7. 覆盖 P2601、P2602、P2603、forecast、持股、IP、许可的稳定冲突键；输入顺序变化后 conflict/question ID 不变。
8. 覆盖缺少稳定 key 或显式 assertion code 时不做自由文本真值推断，而产生结构化补件问题。
9. 在 `test_company_intake_preflight.py` 增加：只有通用 `as_of_date` 的非财务 CSV 不 applicable。
10. 仅上传本轮管理层、交易对手、公司登记和溯源 CSV 时，财务 preflight 不 applicable；加入两份董事会计划后，只识别这两份 forecast 候选。
11. 验证 forecast 同时接受受控 schema 中的 `version` 与 `forecast_version`，但不自动选择其中之一。
12. 验证“Available cash 4.4”在缺少账户和限制字段时只是未验证主张，不成为 treasury candidate。
13. 桥接/API 测试验证完整性门禁优先于证据冲突，证据冲突优先于财务 basis；UI 明确显示 `quarantined`、`candidate` 和 `missing underlying payload`。
14. 保留现有 Round 2 preflight 回归，确认收紧 applicability 不破坏已支持的明确财务 schema。

## 修复顺序建议

1. 先实现 manifest reconciliation 与 quarantine，因为 `07` 的完整性状态决定其下游溯源声明能否使用。
2. 再收紧财务 applicability，消除通用 `as_of_date` 假阳性，并恢复对两份计划的受控识别。
3. 增加文档控制候选模型，保证版本、批准、生效、签字和权威独立展示且无自动选择。
4. 增加实际 payload 与索引声明两层 duplicate graph。
5. 最后增加基于显式稳定键的 claim conflict graph 和局部问题重算。

上述顺序只描述后续最小修复路径；本次评审没有实施任何产品代码变更。
