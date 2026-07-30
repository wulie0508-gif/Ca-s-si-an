# 企业评估与分诊系统｜集成实施与验收报告

**日期：2026-07-30**
**项目：CleanTech Finance v0.4.0**
**工作分支：`agent/enterprise-assessment-integration`**
**实施依据：企业评估与分诊系统总集成 Spec**

## 一、结论先行

本轮已经交付一套可本机运行、可追溯、可人工审批的企业评估与分诊 MVP。它把 Company、Case、统一证据、访谈、标准化财务指标、缺口、资源推荐和审批决策写入独立 SQLite 主账本；课程/政策使用正式 Excel/CSV 做确定性匹配；NEX 只作为证据检索侧车；报告输出 JSON、Markdown 和本地 HTML。

两条虚构企业全流程均已跑通：

- 信息充分企业：四项独立维度达到当前配置要求，建议为“进”；这仍只是供 Leader 点头的建议。
- 信息稀疏企业：财务证据不足、信息一致性不可评估、画像稀疏，诚实降级为“补充信息后再议”。

这不表示系统已经完成真实企业泛化验证。当前仍缺少用户指定的真实企业材料、人工真值和失败驱动迭代；真实企业验收是下一阶段，而不是本轮已经完成的能力。

## 二、实际交付

### 1. 权威主账本

`src/cleantech_finance/enterprise_store.py` 新建以下 SQLite 关系：

```text
Company
  └─ Case
      ├─ Evidence
      ├─ Interview
      ├─ Metrics
      ├─ Gaps
      ├─ Recommendations
      ├─ Decision
      └─ Case events
```

关键控制：

- Company canonical 名称与 registry ID 分别唯一；
- 名称和注册号指向不同主档时失败关闭，不自动消歧或合并；
- Evidence 必须归属命令指定的 Case，禁止跨 Case 偷渡；
- Metrics、Recommendations、Decision 版本化；
- Gap 带补充路径和局部重算范围；
- 决策只允许 `draft → pending_review → approved/rejected`；
- rejected 强制填写原因，并输出不可静默覆盖的 `eval_cases` 快照。

### 2. 统一证据与承重规则

`src/cleantech_finance/enterprise_evidence.py` 实现统一证据出口：

```json
{
  "claim": "...",
  "source": "...",
  "locator": "...",
  "date": "...",
  "entity_id": "...",
  "source_level": "L1|L2|L3|L4",
  "type": "fact|opinion|owner_statement",
  "confidence": "high|medium|low",
  "review_status": "verified|pending"
}
```

承重规则已经代码化：

- 一条或以上经核验 L1 独立来源可满足事实承重；
- 没有 L1 时，需要至少两条独立、经核验的 L2 来源；
- L3/L4 只进入参考区；
- owner statement 不证明为真；
- 缺 source 或 locator 的结果不能入账。

### 3. NEX 侧车边界

已核对并适配实际 NEX `/v1/query` citation 合约。适配层：

- 不使用 NEX 自然语言 answer 作为事实；
- citation 转成统一 Evidence 后才可入账；
- 命中项一律是 `pending` 候选；
- 明显代码、缓存、构建产物噪声被过滤；
- 腾讯研究背景不能当企业事实；
- 时效敏感信息强制标记“需实时官方复核”；
- 侧车不可用时返回显式降级，不静默失败。

2026-07-30 本机验收时 `127.0.0.1:8000` 未启动，两条 CLI 实跑都正确显示 `sidecar_unavailable / 本地缓存未使用`。本轮没有擅自启动或暴露 NEX 服务。

另有两个只读适配器：

- 174,494 条 NEX 企业目录只返回法律实体候选，必须人工确认；
- 238,030 条能源资产记录可转换为带来源、定位、哈希和 caveat 的候选证据。

### 4. 访谈

`src/cleantech_finance/enterprise_interview.py` 实现：

- 本机 `ffmpeg` 转单声道 16k PCM；
- `faster-whisper`，默认 base / CPU / int8；
- 保留段落与词级时间戳；
- 产物写入 Case 目录，不写 NEX RAG；
- 结构化口述点统一为 `owner_statement + pending`；
- 没有 consent reference 时不能入账访谈。

### 5. 财务适配

`src/cleantech_finance/enterprise_assessment.py` 只导入已通过原系统确定性 validation 的财务审计，并将原始输入逐条转换为带来源定位的 L1 Evidence，再写入版本化 Metrics。

保持的真实能力边界：

- 盈利/单位经济性：端到端已验证；
- 现金流/资金缺口：端到端已验证；
- 其余四个财务维度：没有被本轮升级，仍是输入蓝图；
- 不汇总红/黄/绿，不输出投资、信用或综合风险评级。

### 6. 课程与政策

`src/cleantech_finance/enterprise_matching.py` 用 Python 标准库读取 `.xlsx` / `.csv`，无强制 Excel 依赖。

- 标签交集与权重均显式、可配置；
- 匹配值只用于单条资源匹配，不是企业综合分；
- 政策复核未通过直接排除；
- 政策已过期直接排除；
- 无高匹配时输出“无高匹配”，不硬推。

测试目录中一条过期政策和一条待复核政策都被正确过滤，仅正式有效政策进入推荐。

### 7. 四项独立判断与报告

系统只输出：

1. 财务证据充分度；
2. 信息一致性；
3. 经复核负面项；
4. 数据完整度。

不生成总分或排名。未核验负面线索只显示并进入人工任务，不计入推断。

报告固定结尾包含：

- 建议：进 / 不进 / 补充信息后再议；
- 最多三条核心理由；
- 待人工确认项；
- 若进时的课程、政策和专家类型。

本地 HTML 使用黑白橙视觉系统，无远程资源依赖，并包含 800px 移动断点、页面横向溢出保护和表格局部横向滚动。

## 三、命令行入口

新增 `cleantech-finance enterprise`：

- `init-store`
- `create`
- `ingest-evidence`
- `transcribe`
- `add-interview`
- `sidecar-query`
- `assess`
- `decision`
- `show`
- `company-candidates`
- `asset-candidates`

完整操作说明见 `docs/enterprise-assessment-system.md`。

## 四、验收证据

### 自动化

- Ruff：通过；
- Python compileall：通过；
- 完整 pytest：`155/155` 通过；
- 新增企业系统测试：`10/10` 通过；
- JSON Schema Draft 2020-12 元校验：`9/9`；
- 示例 Manifest 校验：`15/15`；
- 完整/稀疏 intake 和统一 evidence 示例：Schema 通过。

### 既有财务发布门禁

严格保持原顺序：

1. Sungrow：
   - extraction `29/29`
   - cards `27/27`
   - citations `112`
   - model calls `0`
2. Enphase：
   - extraction `28/28`
   - cards `27/27`
   - citations `113`
   - model calls `0`

十企业注册表：`10/10` 通过，全部 model calls `0`。本地十企业索引已重新生成。

### 两条新流程

完整案例：

- 财务证据充分度：sufficient；
- 信息一致性：consistent on available evidence；
- 数据完整度：complete；
- 建议：进；
- 侧车：不可用但显式降级；
- 有效政策仅保留一条，过期/待复核政策被硬过滤。

稀疏案例：

- 财务证据充分度：insufficient；
- 信息一致性：unassessable；
- 数据完整度：sparse；
- 建议：补充信息后再议；
- 自动产生两项财务缺口、画像缺口、侧车降级缺口和正式目录缺口。

### HTML 静态 QA

完整与稀疏报告均通过：

- UTF-8 无替换字符；
- viewport meta 存在；
- 800px 移动断点存在；
- 页面横向溢出保护存在；
- 表格局部滚动存在；
- 无远程 CSS、JS 或图片；
- guardrail 明确为 `aggregate_score=false`、`automated_decision=false`。

受浏览器安全策略限制，自动控制无法导航本机 `file://` 报告。因此本轮不能宣称完成浏览器像素级桌面/375px 目视认证；没有绕过该限制。

## 五、当前真实缺口

### 不是 bug，而是明确未实现

- 真实企业失败驱动泛化；
- 自动实时访问官方公开来源的检索连接器；
- 受控 LLM 语义抽取和叙事服务；
- 企业补件中心的持久化状态机、企业端 UI 与 API；
- 多租户和企业级权限；
- 自动实体消歧；
- 完整 ESG、清洁技术影响、出海认证；
- ARL 1–9 自动评分；
- 其余四项财务维度的端到端规则与验证。

### 下一步验收建议

1. 由项目负责人指定至少两家真实企业：一家具备较完整财务/业务材料，一家信息稀疏；
2. 明确法律实体、授权范围和人工 ground truth；
3. 先跑 fail-first，不为单家公司添加特例；
4. 将真实失败转成通用规则和 rejected eval case；
5. 每次规则变化重新跑完整 155 项测试、顺序发布门禁和十企业注册表；
6. 真实浏览器中人工检查完整/稀疏 HTML 的桌面、375px、打印和中文字体。

## 六、给 Claude 的审视重点

建议 Claude 按以下顺序审查：

1. `enterprise_store.py` 的实体冲突、版本、外键和决策状态机；
2. `enterprise_evidence.py` 的 source/locator fail-closed、L1/L2 承重和 NEX 噪声过滤；
3. `enterprise_assessment.py` 是否有任何隐性总分或未经复核负面项进入推断；
4. `enterprise_matching.py` 的政策硬过滤是否有绕过路径；
5. `enterprise_reporting.py` 是否把“建议”误写成“决定”；
6. `test_enterprise_assessment.py` 是否覆盖完整、稀疏、侧车命中、侧车关闭、实体冲突和人工打回。

Claude 应继续区分 bug、工程债务、产品选择和路线图；没有复现证据时不要把路线图缺口描述成已实现功能的缺陷。
