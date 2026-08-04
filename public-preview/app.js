"use strict";

const VIEW_TITLES = {
  home: "Home",
  companies: "Companies",
  deals: "Deals",
  resources: "Resources",
};

const COMPANY_STATUS = {
  action: { label: "需行动", tone: "warning" },
  interview: { label: "可访谈", tone: "ready" },
  review: { label: "待复核", tone: "neutral" },
  organized: { label: "已整理", tone: "neutral" },
};

const COMPANIES = [
  {
    id: "SYN-C001",
    name: "澄湾热储演示公司",
    status: "action",
    need: "客户合同签署状态与回款依据",
    owner: "项目经理 A",
    updated: "2 小时前",
    next: "发起关键合同补件",
    evidence: "合同草案存在；签署页与回款证据缺失",
    scope: "商业、财务准备状态",
  },
  {
    id: "SYN-C002",
    name: "青屿电化学演示公司",
    status: "interview",
    need: "商业模式与客户获取路径",
    owner: "项目经理 B",
    updated: "昨天",
    next: "安排商业模式访谈",
    evidence: "材料足以开始访谈；不代表外部验证完成",
    scope: "商业访谈问题集",
  },
  {
    id: "SYN-C003",
    name: "北辰循环材料演示公司",
    status: "review",
    need: "单位经济性口径确认",
    owner: "分析师 C",
    updated: "2 天前",
    next: "人工确认收入与成本口径",
    evidence: "存在管理层口径；尚未完成规则校验",
    scope: "盈利与单位经济性",
  },
  {
    id: "SYN-C004",
    name: "微澜能源软件演示公司",
    status: "organized",
    need: "材料目录已整理，等待负责人判断",
    owner: "项目经理 D",
    updated: "本周一",
    next: "确认是否进入诊断",
    evidence: "仅完成文件分类与合成标签",
    scope: "材料目录",
  },
];

const DEALS = [
  {
    id: "SYN-D001",
    title: "澄湾热储演示交易",
    buyer: "买方演示主体",
    owner: "项目经理 A",
    updated: "2 小时前",
    stage: "初步接触",
    readiness: [
      { name: "商业", state: "warning", label: "材料不足", detail: "客户合同缺少签署页" },
      { name: "财务", state: "warning", label: "材料不足", detail: "回款与毛利口径待补充" },
      { name: "法务与监管", state: "review", label: "待人工复核", detail: "主体范围已记录" },
      { name: "技术与证据", state: "ready", label: "可开始分析", detail: "仅代表材料可读" },
    ],
  },
  {
    id: "SYN-D002",
    title: "北辰循环材料演示交易",
    buyer: "产业方演示主体",
    owner: "项目经理 B",
    updated: "昨天",
    stage: "委托与边界",
    readiness: [
      { name: "商业", state: "review", label: "待人工复核", detail: "客户集中度口径待确认" },
      { name: "财务", state: "warning", label: "材料不足", detail: "现金流明细尚未提供" },
      { name: "法务与监管", state: "review", label: "待人工复核", detail: "授权范围需确认" },
      { name: "技术与证据", state: "warning", label: "材料不足", detail: "验证报告缺少附件" },
    ],
  },
];

const RESOURCES = [
  {
    id: "SYN-P01",
    kind: "policy",
    title: "合成政策说明 P-01：早期清洁技术支持方向",
    description: "仅演示政策目录字段、适用阶段和核验状态，不对应任何真实政策。",
    tags: ["早期阶段", "政策结构样例", "非官方"],
    footer: "来源：Synthetic demo · 正式使用必须核验官方原文",
  },
  {
    id: "SYN-P02",
    kind: "policy",
    title: "合成政策说明 P-02：示范项目支持方向",
    description: "用于展示候选政策如何与已确认政策分层；页面不执行真实匹配。",
    tags: ["示范项目", "候选说明", "非官方"],
    footer: "状态：合成目录条目 · 无真实时效性",
  },
  {
    id: "SYN-C01",
    kind: "course",
    title: "课程样例 C-01：尽调材料口径整理",
    description: "面向项目团队的合成课程条目，用于演示阶段与能力缺口匹配。",
    tags: ["基础", "材料整理", "45 分钟"],
    footer: "提供方：合成课程机构 · 不代表真实开课",
  },
  {
    id: "SYN-C02",
    kind: "course",
    title: "课程样例 C-02：清洁技术单位经济性",
    description: "演示课程元数据、目标角色与建议前置知识的呈现方式。",
    tags: ["进阶", "财务", "60 分钟"],
    footer: "状态：Synthetic demo / 合成演示",
  },
  {
    id: "SYN-M01",
    kind: "mentor",
    title: "导师角色 M-01（虚构）：产业验证",
    description: "仅展示导师能力标签、冲突检查与匹配解释，不对应真实个人。",
    tags: ["产业验证", "试点", "虚构角色"],
    footer: "联系操作禁用 · 真实导师需单独授权",
  },
  {
    id: "SYN-M02",
    kind: "mentor",
    title: "导师角色 M-02（虚构）：交易准备",
    description: "用于演示专业背景、可用性和推荐理由字段。",
    tags: ["交易流程", "材料边界", "虚构角色"],
    footer: "状态：合成目录条目 · 不可联系",
  },
];

const elements = {
  views: Array.from(document.querySelectorAll("[data-view]")),
  viewLinks: Array.from(document.querySelectorAll("[data-view-link]")),
  companySearch: document.querySelector("#company-search"),
  companyStatus: document.querySelector("#company-status"),
  companyTableBody: document.querySelector("#company-table-body"),
  companyFilterSummary: document.querySelector("#company-filter-summary"),
  companyEmpty: document.querySelector("#company-empty"),
  companyInspectorTitle: document.querySelector("#company-inspector-title"),
  companyInspectorCopy: document.querySelector("#company-inspector-copy"),
  companyInspectorGrid: document.querySelector("#company-inspector-grid"),
  dealSearch: document.querySelector("#deal-search"),
  dealList: document.querySelector("#deal-list"),
  dealRecordTitle: document.querySelector("#deal-record-title"),
  dealRecordMeta: document.querySelector("#deal-record-meta"),
  dealStageChip: document.querySelector("#deal-stage-chip"),
  readinessGrid: document.querySelector("#readiness-grid"),
  dealTabs: Array.from(document.querySelectorAll("[data-deal-tab]")),
  dealPanels: Array.from(document.querySelectorAll("[data-deal-panel]")),
  resourceSearch: document.querySelector("#resource-search"),
  resourceTabs: Array.from(document.querySelectorAll("[data-resource-kind]")),
  resourceFilterSummary: document.querySelector("#resource-filter-summary"),
  resourceList: document.querySelector("#resource-list"),
  resourceEmpty: document.querySelector("#resource-empty"),
  valuationCalculatorForm: document.querySelector("#valuation-calculator-form"),
  valuationCurrency: document.querySelector("#valuation-currency"),
  valuationUnit: document.querySelector("#valuation-unit"),
  valuationFcff: [1, 2, 3, 4, 5].map((year) => document.querySelector(`#valuation-fcff-${year}`)),
  valuationWacc: document.querySelector("#valuation-wacc"),
  valuationTerminalGrowth: document.querySelector("#valuation-terminal-growth"),
  valuationDiscountConvention: document.querySelector("#valuation-discount-convention"),
  valuationCash: document.querySelector("#valuation-cash"),
  valuationDebt: document.querySelector("#valuation-debt"),
  valuationOtherClaims: document.querySelector("#valuation-other-claims"),
  valuationDilutedShares: document.querySelector("#valuation-diluted-shares"),
  valuationCompsEnabled: document.querySelector("#valuation-comps-enabled"),
  valuationCompsMetric: document.querySelector("#valuation-comps-metric"),
  valuationCompsTarget: document.querySelector("#valuation-comps-target"),
  valuationCompsLow: document.querySelector("#valuation-comps-low"),
  valuationCompsBase: document.querySelector("#valuation-comps-base"),
  valuationCompsHigh: document.querySelector("#valuation-comps-high"),
  runValuationCalculator: document.querySelector("#run-valuation-calculator"),
  resetValuationCalculator: document.querySelector("#reset-valuation-calculator"),
  valuationCalculatorError: document.querySelector("#valuation-calculator-error"),
  valuationOutput: document.querySelector("#valuation-output"),
  valuationIntegrityStatus: document.querySelector("#valuation-integrity-status"),
  valuationReadinessStatus: document.querySelector("#valuation-readiness-status"),
  valuationDcfEv: document.querySelector("#valuation-dcf-ev"),
  valuationDcfEquity: document.querySelector("#valuation-dcf-equity"),
  valuationDcfPerShare: document.querySelector("#valuation-dcf-per-share"),
  valuationTerminalShare: document.querySelector("#valuation-terminal-share"),
  valuationCompsResult: document.querySelector("#valuation-comps-result"),
  valuationCompsResultTitle: document.querySelector("#valuation-comps-result-title"),
  valuationCompsResultCopy: document.querySelector("#valuation-comps-result-copy"),
  valuationCompsLowOutput: document.querySelector("#valuation-comps-low-output"),
  valuationCompsBaseOutput: document.querySelector("#valuation-comps-base-output"),
  valuationCompsHighOutput: document.querySelector("#valuation-comps-high-output"),
  valuationSensitivityHead: document.querySelector("#valuation-sensitivity-head"),
  valuationSensitivityBody: document.querySelector("#valuation-sensitivity-body"),
  valuationWarningList: document.querySelector("#valuation-warning-list"),
  liveRegion: document.querySelector("#live-region"),
};

let selectedCompanyId = null;
let selectedDealId = DEALS[0].id;
let selectedResourceKind = "policy";

function node(tagName, className, text) {
  const item = document.createElement(tagName);
  if (className) {
    item.className = className;
  }
  if (text !== undefined) {
    item.textContent = text;
  }
  return item;
}

function announce(message) {
  elements.liveRegion.textContent = "";
  window.requestAnimationFrame(() => {
    elements.liveRegion.textContent = message;
  });
}

function routeName() {
  const requested = window.location.hash.replace(/^#/, "").trim().toLowerCase();
  return Object.hasOwn(VIEW_TITLES, requested) ? requested : "home";
}

function showView(viewName, { focus = false } = {}) {
  elements.views.forEach((view) => {
    view.hidden = view.dataset.view !== viewName;
  });
  elements.viewLinks.forEach((link) => {
    if (link.dataset.viewLink === viewName) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  document.title = `CleanTech Finance · ${VIEW_TITLES[viewName]} · Synthetic demo`;
  if (focus) {
    const title = document.querySelector(`#${viewName}-title`);
    if (title) {
      window.requestAnimationFrame(() => title.focus());
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }
}

function renderCompanyInspector(company) {
  elements.companyInspectorGrid.replaceChildren();
  if (!company) {
    elements.companyInspectorTitle.textContent = "选择一条企业记录";
    elements.companyInspectorCopy.textContent = "查看当前缺口、证据边界和建议动作。此处不会写入或保存更改。";
    return;
  }

  elements.companyInspectorTitle.textContent = company.name;
  elements.companyInspectorCopy.textContent = `当前下一步：${company.next}。所有字段均为 Synthetic demo / 合成演示。`;
  const fields = [
    ["记录编号", company.id],
    ["证据边界", company.evidence],
    ["局部影响范围", company.scope],
    ["责任人", company.owner],
  ];
  fields.forEach(([term, description]) => {
    const wrapper = node("div");
    wrapper.append(node("dt", null, term), node("dd", null, description));
    elements.companyInspectorGrid.append(wrapper);
  });
}

function companySearchText(company) {
  return [company.name, company.need, company.owner, company.next, company.evidence]
    .join(" ")
    .toLocaleLowerCase("zh-CN");
}

function renderCompanies() {
  const query = elements.companySearch.value.trim().toLocaleLowerCase("zh-CN");
  const status = elements.companyStatus.value;
  const visible = COMPANIES.filter((company) => {
    const matchesQuery = !query || companySearchText(company).includes(query);
    const matchesStatus = status === "all" || company.status === status;
    return matchesQuery && matchesStatus;
  });

  elements.companyTableBody.replaceChildren();
  visible.forEach((company) => {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.dataset.label = "企业";
    const companyButton = node("button", "company-name-button");
    companyButton.type = "button";
    companyButton.dataset.companyId = company.id;
    companyButton.setAttribute("aria-pressed", selectedCompanyId === company.id ? "true" : "false");
    companyButton.append(
      node("strong", null, company.name),
      node("small", null, `${company.id} · Synthetic demo`),
    );
    nameCell.append(companyButton);

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "状态";
    const statusInfo = COMPANY_STATUS[company.status];
    statusCell.append(node("span", `status-chip ${statusInfo.tone}`, statusInfo.label));

    const needCell = node("td", null, company.need);
    needCell.dataset.label = "关键需求";
    const ownerCell = node("td", null, company.owner);
    ownerCell.dataset.label = "负责人";
    const updatedCell = node("td", "table-subcopy", company.updated);
    updatedCell.dataset.label = "更新";
    const nextCell = node("td", "next-action", company.next);
    nextCell.dataset.label = "下一步";
    row.append(nameCell, statusCell, needCell, ownerCell, updatedCell, nextCell);
    elements.companyTableBody.append(row);
  });

  elements.companyFilterSummary.textContent = `显示 ${visible.length} / ${COMPANIES.length} 条合成企业记录`;
  elements.companyEmpty.hidden = visible.length !== 0;
  const selected = COMPANIES.find((company) => company.id === selectedCompanyId) || null;
  renderCompanyInspector(selected);
}

function selectCompany(companyId) {
  selectedCompanyId = companyId;
  renderCompanies();
  const company = COMPANIES.find((item) => item.id === companyId);
  if (company) {
    announce(`已选择 ${company.name}。详情为合成演示数据。`);
  }
}

function dealSearchText(deal) {
  return [deal.title, deal.buyer, deal.owner, deal.stage].join(" ").toLocaleLowerCase("zh-CN");
}

function renderDealList() {
  const query = elements.dealSearch.value.trim().toLocaleLowerCase("zh-CN");
  const visible = DEALS.filter((deal) => !query || dealSearchText(deal).includes(query));
  elements.dealList.replaceChildren();

  if (!visible.length) {
    const empty = node("div", "empty-state");
    empty.append(node("strong", null, "没有匹配的合成交易"), node("p", null, "调整搜索词。"));
    elements.dealList.append(empty);
    return;
  }

  visible.forEach((deal) => {
    const button = node("button", "deal-list-button");
    button.type = "button";
    button.dataset.dealId = deal.id;
    button.setAttribute("aria-pressed", selectedDealId === deal.id ? "true" : "false");
    const meta = node("span");
    meta.append(node("small", null, deal.stage), node("small", null, deal.updated));
    button.append(node("strong", null, deal.title), meta);
    elements.dealList.append(button);
  });
}

function renderReadiness(deal) {
  elements.readinessGrid.replaceChildren();
  deal.readiness.forEach((readiness) => {
    const card = node("article", "readiness-card");
    card.dataset.state = readiness.state;
    card.append(
      node("span", null, readiness.name),
      node("strong", null, readiness.label),
      node("p", null, readiness.detail),
    );
    elements.readinessGrid.append(card);
  });
}

function renderSelectedDeal() {
  const deal = DEALS.find((item) => item.id === selectedDealId) || DEALS[0];
  elements.dealRecordTitle.textContent = deal.title;
  elements.dealRecordMeta.textContent = `${deal.buyer} · 负责人：${deal.owner} · 更新于 ${deal.updated}`;
  elements.dealStageChip.textContent = deal.stage;
  renderReadiness(deal);
  renderDealList();
}

function selectDeal(dealId) {
  const deal = DEALS.find((item) => item.id === dealId);
  if (!deal) {
    return;
  }
  selectedDealId = dealId;
  renderSelectedDeal();
  announce(`已选择 ${deal.title}。四项准备状态独立显示，不生成总分。`);
}

function activateDealTab(tabName, { focusPanel = false } = {}) {
  elements.dealTabs.forEach((tab) => {
    const active = tab.dataset.dealTab === tabName;
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.tabIndex = active ? 0 : -1;
  });
  elements.dealPanels.forEach((panel) => {
    panel.hidden = panel.dataset.dealPanel !== tabName;
  });
  if (focusPanel) {
    const panel = elements.dealPanels.find((item) => item.dataset.dealPanel === tabName);
    if (panel) {
      panel.focus();
    }
  }
}

function moveTabFocus(tabs, currentIndex, key) {
  let nextIndex = currentIndex;
  if (key === "ArrowRight") {
    nextIndex = (currentIndex + 1) % tabs.length;
  } else if (key === "ArrowLeft") {
    nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  } else if (key === "Home") {
    nextIndex = 0;
  } else if (key === "End") {
    nextIndex = tabs.length - 1;
  } else {
    return false;
  }
  tabs[nextIndex].focus();
  tabs[nextIndex].click();
  return true;
}

function resourceKindLabel(kind) {
  return { policy: "政策说明", course: "课程", mentor: "导师" }[kind] || kind;
}

function resourceSearchText(resource) {
  return [resource.title, resource.description, resource.tags.join(" "), resource.footer]
    .join(" ")
    .toLocaleLowerCase("zh-CN");
}

function renderResources() {
  const query = elements.resourceSearch.value.trim().toLocaleLowerCase("zh-CN");
  const visible = RESOURCES.filter(
    (resource) => resource.kind === selectedResourceKind && (!query || resourceSearchText(resource).includes(query)),
  );
  elements.resourceList.replaceChildren();

  visible.forEach((resource) => {
    const item = node("li", "resource-item");
    const header = document.createElement("header");
    const titleBlock = document.createElement("div");
    titleBlock.append(
      node("span", "resource-code", resource.id),
      node("h3", null, resource.title),
    );
    header.append(titleBlock, node("span", "synthetic-label", "合成演示"));
    const meta = node("div", "resource-meta");
    resource.tags.forEach((tag) => meta.append(node("span", null, tag)));
    item.append(
      header,
      node("p", null, resource.description),
      meta,
      node("footer", null, resource.footer),
    );
    elements.resourceList.append(item);
  });

  elements.resourceFilterSummary.textContent = `${resourceKindLabel(selectedResourceKind)} · 显示 ${visible.length} 条合成目录记录`;
  elements.resourceEmpty.hidden = visible.length !== 0;
}

function activateResourceTab(kind) {
  selectedResourceKind = kind;
  elements.resourceTabs.forEach((tab) => {
    const active = tab.dataset.resourceKind === kind;
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.tabIndex = active ? 0 : -1;
  });
  renderResources();
  announce(`已切换到${resourceKindLabel(kind)}。当前内容全部为合成演示。`);
}

function valuationUnitLabel(unit) {
  return { million: "mn", billion: "bn" }[unit] || unit;
}

function formatValuationAmount(value, result, { perShare = false } = {}) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  const formatted = new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: Math.abs(value) < 10 ? 2 : 1,
    maximumFractionDigits: Math.abs(value) < 10 ? 2 : 1,
  }).format(value);
  const currency = result.input.currency;
  return perShare
    ? `${currency} ${formatted}`
    : `${currency} ${formatted} ${valuationUnitLabel(result.input.unit)}`;
}

function formatRate(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function valuationCalculatorPayload() {
  return {
    currency: elements.valuationCurrency.value,
    unit: elements.valuationUnit.value,
    fcff: elements.valuationFcff.map((input) => input.value),
    waccPct: elements.valuationWacc.value,
    terminalGrowthPct: elements.valuationTerminalGrowth.value,
    discountConvention: elements.valuationDiscountConvention.value,
    cash: elements.valuationCash.value,
    debt: elements.valuationDebt.value,
    otherClaims: elements.valuationOtherClaims.value,
    dilutedShares: elements.valuationDilutedShares.value,
    comps: {
      enabled: elements.valuationCompsEnabled.checked,
      metric: elements.valuationCompsMetric.value,
      targetMetric: elements.valuationCompsTarget.value,
      lowMultiple: elements.valuationCompsLow.value,
      baseMultiple: elements.valuationCompsBase.value,
      highMultiple: elements.valuationCompsHigh.value,
    },
  };
}

function renderSensitivity(result) {
  elements.valuationSensitivityHead.replaceChildren();
  elements.valuationSensitivityBody.replaceChildren();
  const corner = node("th", null, "WACC \\ g");
  corner.scope = "col";
  elements.valuationSensitivityHead.append(corner);
  result.sensitivity.columns.forEach((growth) => {
    const heading = node("th", null, formatRate(growth));
    heading.scope = "col";
    elements.valuationSensitivityHead.append(heading);
  });

  result.sensitivity.rows.forEach((wacc, rowIndex) => {
    const row = document.createElement("tr");
    const rowHeading = node("th", null, formatRate(wacc));
    rowHeading.scope = "row";
    row.append(rowHeading);
    result.sensitivity.cells[rowIndex].forEach((cell, columnIndex) => {
      const tableCell = node(
        "td",
        cell.status === "invalid" ? "invalid-cell" : null,
        cell.status === "invalid" ? "—" : formatValuationAmount(cell.value, result),
      );
      if (cell.status === "invalid") {
        tableCell.setAttribute(
          "aria-label",
          `${formatRate(wacc)} WACC 与 ${formatRate(result.sensitivity.columns[columnIndex])} 终值增长率：无效，WACC 必须高于增长率`,
        );
      }
      if (
        Math.abs(wacc - result.input.wacc) < 0.0000001 &&
        cell.status !== "invalid" &&
        Math.abs(result.sensitivity.columns[columnIndex] - result.input.terminalGrowth) < 0.0000001
      ) {
        tableCell.classList.add("base-cell");
        tableCell.setAttribute("aria-label", `${tableCell.textContent}，基准情景`);
      }
      row.append(tableCell);
    });
    elements.valuationSensitivityBody.append(row);
  });
}

function renderValuationResult(result) {
  elements.valuationOutput.hidden = false;
  elements.valuationIntegrityStatus.textContent =
    result.calculationIntegrity.status === "passed" ? "完整性：通过" : "完整性：失败";
  elements.valuationIntegrityStatus.dataset.state = result.calculationIntegrity.status;
  elements.valuationReadinessStatus.textContent =
    result.decisionReadiness.status === "screen_grade"
      ? "可用性：Screen-grade"
      : "可用性：Not ready";
  elements.valuationReadinessStatus.dataset.state = result.decisionReadiness.status;
  elements.valuationDcfEv.textContent = formatValuationAmount(result.dcf.enterpriseValue, result);
  elements.valuationDcfEquity.textContent = formatValuationAmount(result.bridge.equityValue, result);
  elements.valuationDcfPerShare.textContent = formatValuationAmount(
    result.bridge.valuePerShare,
    result,
    { perShare: true },
  );
  elements.valuationTerminalShare.textContent = formatRate(result.dcf.terminalValueShareOfEv);

  const comparable = result.comparable;
  elements.valuationCompsResult.hidden = comparable === null;
  if (comparable) {
    elements.valuationCompsResultTitle.textContent = `${comparable.metric} · 独立区间`;
    elements.valuationCompsResultCopy.textContent =
      "倍数与目标指标均来自当前手工输入；系统不抓取、选择或认可任何同业样本。";
    elements.valuationCompsLowOutput.textContent = formatValuationAmount(
      comparable.enterpriseValues.low,
      result,
    );
    elements.valuationCompsBaseOutput.textContent = formatValuationAmount(
      comparable.enterpriseValues.base,
      result,
    );
    elements.valuationCompsHighOutput.textContent = formatValuationAmount(
      comparable.enterpriseValues.high,
      result,
    );
  }

  renderSensitivity(result);
  elements.valuationWarningList.replaceChildren();
  result.warnings.forEach((warning) => elements.valuationWarningList.append(node("li", null, warning)));
}

function runValuationCalculator(event) {
  event.preventDefault();
  elements.valuationCalculatorError.hidden = true;
  elements.valuationCalculatorError.textContent = "";
  if (!elements.valuationCalculatorForm.reportValidity()) {
    return;
  }
  const calculator = window.CleanTechValuationCalculator;
  if (!calculator) {
    elements.valuationCalculatorError.textContent = "估值计算模块未加载，请刷新页面后重试。";
    elements.valuationCalculatorError.hidden = false;
    return;
  }

  const result = calculator.calculateDcfScreen(valuationCalculatorPayload());
  if (!result.ok) {
    elements.valuationOutput.hidden = true;
    elements.valuationCalculatorError.textContent = result.message;
    elements.valuationCalculatorError.hidden = false;
    announce(`估值未运行：${result.message}`);
    return;
  }

  renderValuationResult(result);
  announce("初步估值已在当前浏览器内完成。结果为 screen-grade，仍需来源和人工复核。 ");
}

function updateCompsCalculatorControls() {
  const enabled = elements.valuationCompsEnabled.checked;
  [
    elements.valuationCompsMetric,
    elements.valuationCompsTarget,
    elements.valuationCompsLow,
    elements.valuationCompsBase,
    elements.valuationCompsHigh,
  ].forEach((control) => {
    control.disabled = !enabled;
  });
}

function resetValuationCalculator() {
  elements.valuationCalculatorForm.reset();
  elements.valuationOutput.hidden = true;
  elements.valuationCalculatorError.hidden = true;
  elements.valuationCalculatorError.textContent = "";
  updateCompsCalculatorControls();
  announce("已恢复合成估值示例，尚未重新运行。 ");
}

function wireEvents() {
  window.addEventListener("hashchange", () => showView(routeName(), { focus: true }));
  elements.valuationCalculatorForm.addEventListener("submit", runValuationCalculator);
  elements.runValuationCalculator.addEventListener("click", runValuationCalculator);
  elements.resetValuationCalculator.addEventListener("click", resetValuationCalculator);
  elements.valuationCompsEnabled.addEventListener("change", updateCompsCalculatorControls);
  elements.valuationCalculatorForm.dataset.calculatorReady = "true";

  elements.companySearch.addEventListener("input", renderCompanies);
  elements.companyStatus.addEventListener("change", renderCompanies);
  elements.companyTableBody.addEventListener("click", (event) => {
    const button = event.target.closest("[data-company-id]");
    if (button) {
      selectCompany(button.dataset.companyId);
    }
  });

  elements.dealSearch.addEventListener("input", renderDealList);
  elements.dealList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-deal-id]");
    if (button) {
      selectDeal(button.dataset.dealId);
    }
  });

  elements.dealTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateDealTab(tab.dataset.dealTab));
    tab.addEventListener("keydown", (event) => {
      if (moveTabFocus(elements.dealTabs, index, event.key)) {
        event.preventDefault();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        activateDealTab(tab.dataset.dealTab, { focusPanel: true });
      }
    });
  });

  elements.resourceSearch.addEventListener("input", renderResources);
  elements.resourceTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateResourceTab(tab.dataset.resourceKind));
    tab.addEventListener("keydown", (event) => {
      if (moveTabFocus(elements.resourceTabs, index, event.key)) {
        event.preventDefault();
      }
    });
  });

}

function initialize() {
  renderCompanies();
  renderSelectedDeal();
  renderResources();
  activateDealTab("overview");
  updateCompsCalculatorControls();
  wireEvents();
  showView(routeName());
}

initialize();
