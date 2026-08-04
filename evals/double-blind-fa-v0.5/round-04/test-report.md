# Double-blind FA QA · Round 04

## 一句话结果

“文件已完整接收但权限边界不可操作”的缺陷，已迭代为独立的六类内容使用授权预检；修复后限定回归 20/20 通过，系统正确保持全部内容请求 blocked。这里的通过是授权控制回归通过，不代表企业资料为真、权限已获人工接受、产品总体验评分或任何投资结论。

## 角色与数据真实性

- 企业首包和补件全部为 **Synthetic**，不对应真实企业、个人、签字或授权。
- 初始 FA 只看到 Round 4 首包和运行产品；企业角色只看到首包及 8 个逐字问题；工程角色只看到首包、初测和代码；修复后 FA 才读取补件与修复方案。
- 企业回应使用 fresh no-history task；FA 初测/后测复用同一隔离角色 task，工程复用既有 specialist task，均通过严格文件白名单并在报告中披露。
- HTTP、case ID、文件哈希、进程、Dashboard、浏览器与测试结果来自真实本地执行。

## 初始 FA 盲测

初始 case `case-20260804-bc2e1cf6cc`。第一次 multipart 因非法 `case_type=enterprise_diligence` 返回 400，未创建 case；修正为允许的 `qa` 后，8 文件一次上传成功，HTTP `201`，case/dashboard 均为 `200`。

初始诊断 rubric 为 68/100、未通过本轮焦点；它只衡量本轮 QA 控制覆盖，不是企业或产品评级。产品原生做到：7/7 manifest payload 哈希匹配、材料均保持候选、分析 blocked、公开发布 false、无 Deal/估值/评级/发布。但它没有：

- 六类权限独立 gate；
- expired/denied/missing/limited 的动作语义；
- request 与 controlling authorization 的 exact reference/scope 对账；
- Agent override 冲突与隔离；
- 访谈“说过”与“为真”的证据缺口；
- Dashboard 授权复核优先级。

结果是原生授权问题数为 0，Dashboard 错误建议 `generate_reference_suggestions`。FA 留下 8 个逐字问题，依次覆盖录音、内部分析、公开发布、品牌、翻译、AI 媒体、访谈事实证据和 Agent candidate authority。

## 企业回应和修复前补件基线

企业角色逐项回显 8 个问题，提交 7 个 payload 与 1 个 manifest：

- `answered`: 7
- `partial`: 1（Q07 的三项访谈主张仍缺一手技术、交易和客户签署证据）
- 其他状态：0

企业没有补造新签署授权：确认不新录音；限定内部团队/workspace；撤回公开发布、分发翻译和 AI 媒体请求；保持品牌仅限未修改内部草稿；把三项访谈主张继续标为管理层未验证陈述；隔离 Agent candidate。响应覆盖 100%、证据包工作流进度 93.75%，均不是企业或风险评分。

修复前代码被提前冻结在独立 8902 进程。首包+补件 16 文件一次上传成功，16/16 本地与产品哈希一致；旧系统虽保留 8 个 candidate receipts，但无授权预检、无授权问题，Dashboard 仍为 `materials_organized → generate_reference_suggestions`。PID 精确停止，端口释放。

## 工程修复

新增 `company_intake_authorization.py`，只解析 CSV/JSON/JSONL 的显式结构字段，不从 Markdown 或正文猜授权。它提供：

- recording、internal analysis、public release、brand/logo、translation、AI media 六类矩阵；
- 持久化诊断 as-of 和独立 subject/content/scope/audience/effective/expires/authority/approval/signature/exclusions；
- request 到 authorization exact reference、permission 与 scope 的保守对账；
- stable `R04-Q01`–`R04-Q08` 与候选 receipts；
- Agent override 隔离；
- transcript 管理层陈述候选 gap；
- evidence integrity 之后、财务/检索之前的 Dashboard 授权优先级；
- 只读授权 UI 卡，不提供接受、发布、翻译或 AI 执行按钮。

协调层又加固了三点：分范围有限授权与拒绝并存时显示 `mixed_scope_control`；Agent 自我声明 authority 或仅有 override instruction 都不能绕过隔离；即使 exact-scope 匹配也在人工接受前保持 blocked。

## 修复后独立重放

最终 FA case 为 `case-20260804-f49209cc30`，16 文件单次原样上传，HTTP `201`，16/16 哈希匹配。20/20 限定断言通过：

- 六类状态分别为：recording `expired`、internal `active_scoped_grant`、public `denied`、brand `mixed_scope_control`、translation `missing`、AI `denied`；全部 general action authorization 为 false。
- `R04-Q01`–`R04-Q08` 全部稳定/open；8 个 candidate receipts 的 accepted/closed 均为 0。
- 6 个 content requests 全部 blocked，accepted/executed 均为 0。
- 1 个 Agent override conflict 被隔离，不影响权限矩阵；transcript 只形成 1 个候选证据 gap，未验证事实。
- Dashboard 路由 `review_content_authorization`，责任人为 human。
- 没有财务计算、Deal、估值、投资/信用/综合风险评级、发布、翻译或 AI 媒体动作。

HTTP fixture 没有命中“字段完全相等”的 exact-scope 分支；报告已如实披露。该分支由专项单元测试覆盖，并确认即使匹配也保持 `blocked=true`、`requires_human_acceptance=true`、不执行动作。

## 真实浏览器和门禁

第二个全新 case `case-20260804-595db94942` 在 8904 用于 Chromium QA。页面可见 16 份材料、授权阻断、8 个问题、6 个 blocked 请求、1 个隔离 override、六类分项状态及诊断时点；“查看授权控制”按钮唯一且可准确滚到授权卡。页面非空、无错误 overlay，浏览器 console 无 warn/error。浏览器和专用 PID 均已清理。

最终门禁：389 项 Python 测试、Ruff、6 项 Node 浏览器本地估值测试与 `git diff --check` 通过。

## 仍未实现 / 保留问题

- 补件中心的持久化状态机、企业权限账户、人工 accepted/closed 动作和 submission linkage 仍未实现；本轮 receipt 不能冒充这些能力。
- case 顶层 legacy `next_action=confirm_material_scope` 与嵌套 dashboard 的正确授权下一步仍有非阻断差异。
- 精确 scope 策略会保守阻断语义相近但字段不一致的记录；需要更规范的结构化模板与人工判断，不应改为自由文本猜测。
- 本轮只有 Synthetic 权限冲突包，仍不是现实企业、真实权利主体或真实法律授权验证。
- 财务、ESG、ARL、出海与无评级等既有能力边界没有扩张。
