# Round 4 企业补件 · 修复前基线

## 结论

企业角色完整回应了 8 个逐字问题，但没有补造授权或一手证明：7 项 `answered`，访谈三项事实主张的 Q07 为 `partial`。修复前产品能原样接收 16 个文件并把 8 行回应保留为候选 receipt，却不能解释六类权限、撤回、限定范围或 Agent 越权，因此 Dashboard 仍错误建议“生成参考建议”。

## 企业实际补了什么

- 明确不进行新录音，旧录音授权不扩张。
- 列出 Synthetic 命名内部团队与命名 workspace，确认不外传、不作范围外训练。
- 撤回公开发布、翻译分发和 AI 媒体请求。
- 确认品牌仅用于未修改的内部审阅草稿。
- 将 3 项访谈主张继续标为 `Management Statement—Unverified`，记录一手材料缺口。
- 隔离并拒绝 Agent candidate/override request，确认没有下游动作。

这些都是企业准备的 Synthetic 候选记录，不是外部权威证明，也不自动关闭 FA 问题。响应覆盖 100%、按透明公式计算的证据包进度 93.75%，只描述补件工作流，不是企业或风险评分。

## 冻结旧代码的真实重放

Bridge 在工程修改前从 commit `7befde2` 启动并持续运行，端口为 8902。首包和补件共 16 个物理文件在一次 multipart 请求中原样上传，HTTP `201`，形成 case `case-20260804-d9b768b723` 与 16 个 artifacts；本地 SHA-256 与产品记录全部一致。

旧产品结果：

- 没有 `authorization_preflight` 或权限矩阵；原生授权问题数为 0。
- 证据控制层保留 8 个 candidate response receipts，但均未自动采信或关题。
- Dashboard 状态仍为 `materials_organized`，下一步仍为 `generate_reference_suggestions`，没有路由到授权复核。
- 没有 Deal、估值、财务计算、评级、发布、翻译、AI 媒体或授权变更。

这证明“通用候选边界没有失守”和“授权工作流已经实现”是两件不同的事：前者成立，后者在修复前不成立。

## 运行清理

监听进程 PID 40604 的命令行与专用临时 workspace 已先核实，再精确停止；8902 端口剩余监听数为 0。
