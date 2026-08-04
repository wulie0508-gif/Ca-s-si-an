"use strict";

const API = Object.freeze({
  health: "/api/health",
  manifest: "/api/agent/manifest",
  dashboard: "/api/ui/dashboard",
  cases: "/api/ui/cases",
  deals: "/api/ui/deals",
  resources: "/api/ui/resources",
  policyReferences: "/api/ui/policy-references",
  authorizationRequests: "/api/ui/authorization-requests",
  consent: "/api/consent",
  revoke: "/api/revoke",
  strictPolicyMatch: "/api/agent/policy-match",
});

const TAG_DIMENSIONS = Object.freeze([
  "industry",
  "stage",
  "need",
  "technology",
  "geography",
  "market",
]);

const RESOURCE_PLURALS = Object.freeze({
  policy: "policies",
  course: "courses",
  mentor: "mentors",
});
const RESOURCE_KINDS = Object.freeze(["policy", "course", "mentor"]);
const CASE_CONSENT_SCOPES = Object.freeze([
  "case:read",
  "material:read",
  "rag:query",
]);

const DEAL_STAGE_LABELS = Object.freeze({
  strategy_and_mandate: "收购战略与委托确认",
  industry_research_and_longlist: "产业研究与 Longlist",
  shortlist_and_preliminary_valuation: "Shortlist 与初步估值",
  initial_contact_and_nda: "初步接触与 NDA",
  ioi_loi_and_exclusivity: "IOI / LOI 与排他",
  diligence_and_transaction_structure: "尽调与交易结构",
  signing_approval_and_closing: "签约、审批与交割",
  post_merger_integration: "并购后整合",
});

const VALUATION_STATUS_LABELS = Object.freeze({
  draft: "草稿",
  inputs_incomplete: "输入已保存",
  calculated_screen_grade: "初步计算完成",
  fa_reviewed: "FA 已复核",
  approved_for_internal_use: "已批准内部使用",
  approved_for_external_use: "已批准外部使用",
  superseded: "已被新版本替代",
});

const VALUATION_STATE_LABELS = Object.freeze({
  passed: "通过",
  warning: "有提示",
  failed: "未通过",
  screen_grade: "Screen-grade",
  not_ready: "尚不可用于决策",
  ready_for_human_review: "可进入人工复核",
});

const VALUATION_SCENARIOS = Object.freeze([
  Object.freeze({ id: "downside", label: "Downside" }),
  Object.freeze({ id: "base", label: "Base" }),
  Object.freeze({ id: "upside", label: "Upside" }),
]);

const FORECAST_FIELDS = Object.freeze([
  Object.freeze({ id: "ebit", label: "EBIT" }),
  Object.freeze({ id: "tax_rate", label: "税率" }),
  Object.freeze({ id: "depreciation_amortization", label: "D&A" }),
  Object.freeze({ id: "capex", label: "CapEx" }),
  Object.freeze({ id: "change_in_nwc", label: "NWC 变动" }),
]);

const COMPS_METRICS = Object.freeze({
  ev_ltm_revenue: Object.freeze({ field: "ltm_revenue", label: "LTM Revenue", numeratorField: "enterprise_value", numeratorLabel: "Enterprise value" }),
  ev_ntm_revenue: Object.freeze({ field: "ntm_revenue", label: "NTM Revenue", numeratorField: "enterprise_value", numeratorLabel: "Enterprise value" }),
  ev_ltm_ebitda: Object.freeze({ field: "ltm_ebitda", label: "LTM EBITDA", numeratorField: "enterprise_value", numeratorLabel: "Enterprise value" }),
  ev_ntm_ebitda: Object.freeze({ field: "ntm_ebitda", label: "NTM EBITDA", numeratorField: "enterprise_value", numeratorLabel: "Enterprise value" }),
  ev_ltm_ebit: Object.freeze({ field: "ltm_ebit", label: "LTM EBIT", numeratorField: "enterprise_value", numeratorLabel: "Enterprise value" }),
  price_earnings: Object.freeze({ field: "ltm_net_income", label: "LTM Net Income", numeratorField: "equity_value", numeratorLabel: "Equity value" }),
});

const ROLE_LABELS = Object.freeze({
  company_identity: "企业画像",
  financial_core: "财务与现金流",
  esg_impact: "ESG 与清洁技术影响",
  technology_arl: "技术成熟度",
  market_export: "市场与出海",
  policy_resource: "政策资源",
  governance_legal: "治理与合规",
  generic_supporting: "综合材料",
});

const WORKFLOW_LABELS = Object.freeze({
  not_started: "尚未启用",
  ready: "可开始",
  running: "处理中",
  blocked: "等待前序",
  awaiting_human: "待确认",
  complete: "已完成",
  not_available: "尚未启用",
  not_applicable: "不适用",
});

const MATURITY_LABELS = Object.freeze({
  validated_end_to_end: "端到端已验证",
  input_blueprint_only: "输入蓝图",
  evidence_framework_only: "证据框架",
  retrieval_scaffold_only: "检索脚手架",
  candidate_matching_only: "参考建议",
});

const appState = {
  health: null,
  manifest: null,
  dashboard: null,
  deals: [],
  dealsState: "idle",
  dealsError: null,
  currentDeal: null,
  currentValuation: null,
  resources: null,
  resourcesState: "idle",
  resourcesError: null,
  currentCase: null,
  selectedFiles: [],
  accessToken: null,
  tokenExpiresAt: null,
  pendingAuthorization: null,
  automaticReferenceCase: null,
};

const elements = {
  main: document.querySelector("#app-main"),
  views: Array.from(document.querySelectorAll("[data-view]")),
  globalRoutes: Array.from(document.querySelectorAll("[data-route]")),
  serviceStatus: document.querySelector("#service-status"),
  serviceStatusDot: document.querySelector("#service-status > span:first-child"),
  serviceStatusLabel: document.querySelector("#service-status-label"),
  servicePopover: document.querySelector("#service-popover"),
  bridgeDetail: document.querySelector("#bridge-detail"),
  ragDetail: document.querySelector("#rag-detail"),
  ragDocuments: document.querySelector("#rag-documents"),
  ragChunks: document.querySelector("#rag-chunks"),
  policyReferenceCount: document.querySelector("#policy-reference-count"),
  uploadForm: document.querySelector("#upload-form"),
  caseName: document.querySelector("#case-name"),
  declaredNeed: document.querySelector("#declared-need"),
  caseOwner: document.querySelector("#case-owner"),
  caseType: document.querySelector("#case-type"),
  workflowType: document.querySelector("#workflow-type"),
  materialFiles: document.querySelector("#material-files"),
  dropZone: document.querySelector("#drop-zone"),
  uploadQueue: document.querySelector("#upload-queue"),
  createCase: document.querySelector("#create-case"),
  uploadError: document.querySelector("#upload-error"),
  recentList: document.querySelector("#recent-list"),
  dashboardTruth: document.querySelector("#dashboard-truth"),
  metricEnterprises: document.querySelector("#metric-enterprises"),
  metricCriticalGaps: document.querySelector("#metric-critical-gaps"),
  metricInterviews: document.querySelector("#metric-interviews"),
  metricCases: document.querySelector("#metric-cases"),
  metricMaterials: document.querySelector("#metric-materials"),
  dashboardFreshness: document.querySelector("#dashboard-freshness"),
  dashboardSearch: document.querySelector("#dashboard-search"),
  dashboardTypeFilter: document.querySelector("#dashboard-type-filter"),
  dashboardStatusFilter: document.querySelector("#dashboard-status-filter"),
  companyTableBody: document.querySelector("#company-table-body"),
  companyTableEmpty: document.querySelector("#company-table-empty"),
  toggleDealCreate: document.querySelector("#toggle-deal-create"),
  closeDealCreate: document.querySelector("#close-deal-create"),
  dealCreatePanel: document.querySelector("#deal-create-panel"),
  dealCreateForm: document.querySelector("#deal-create-form"),
  dealCompanyId: document.querySelector("#deal-company-id"),
  dealCompanyOptions: document.querySelector("#deal-company-options"),
  dealTarget: document.querySelector("#deal-target"),
  dealBuyer: document.querySelector("#deal-buyer"),
  dealOwner: document.querySelector("#deal-owner"),
  dealValuationDate: document.querySelector("#deal-valuation-date"),
  dealCurrency: document.querySelector("#deal-currency"),
  dealConfidentiality: document.querySelector("#deal-confidentiality"),
  dealScope: document.querySelector("#deal-scope"),
  dealCreateReason: document.querySelector("#deal-create-reason"),
  createDeal: document.querySelector("#create-deal"),
  dealCreateError: document.querySelector("#deal-create-error"),
  refreshDeals: document.querySelector("#refresh-deals"),
  dealSearch: document.querySelector("#deal-search"),
  dealCount: document.querySelector("#deal-count"),
  dealList: document.querySelector("#deal-list"),
  dealEmpty: document.querySelector("#deal-empty"),
  dealWorkbench: document.querySelector("#deal-workbench"),
  dealRecordId: document.querySelector("#deal-record-id"),
  dealRecordTitle: document.querySelector("#deal-record-title"),
  dealRecordScope: document.querySelector("#deal-record-scope"),
  dealRecordOwner: document.querySelector("#deal-record-owner"),
  dealRecordDate: document.querySelector("#deal-record-date"),
  dealRecordCurrency: document.querySelector("#deal-record-currency"),
  dealRecordRevision: document.querySelector("#deal-record-revision"),
  readinessMaterial: document.querySelector("#readiness-material"),
  readinessMaterialNote: document.querySelector("#readiness-material-note"),
  readinessEvidence: document.querySelector("#readiness-evidence"),
  readinessEvidenceNote: document.querySelector("#readiness-evidence-note"),
  readinessStage: document.querySelector("#readiness-stage"),
  readinessStageNote: document.querySelector("#readiness-stage-note"),
  readinessValuation: document.querySelector("#readiness-valuation"),
  readinessValuationNote: document.querySelector("#readiness-valuation-note"),
  dealStageCurrent: document.querySelector("#deal-stage-current"),
  dealStageForm: document.querySelector("#deal-stage-form"),
  dealStageSelect: document.querySelector("#deal-stage-select"),
  dealStageReason: document.querySelector("#deal-stage-reason"),
  confirmDealStage: document.querySelector("#confirm-deal-stage"),
  dealStageError: document.querySelector("#deal-stage-error"),
  toggleValuationCreate: document.querySelector("#toggle-valuation-create"),
  valuationCreatePanel: document.querySelector("#valuation-create-panel"),
  valuationCreateForm: document.querySelector("#valuation-create-form"),
  valuationTargetEntity: document.querySelector("#valuation-target-entity"),
  valuationDate: document.querySelector("#valuation-date"),
  valuationCurrency: document.querySelector("#valuation-currency"),
  valuationMethodPlan: document.querySelector("#valuation-method-plan"),
  valuationScope: document.querySelector("#valuation-scope"),
  valuationCreateReason: document.querySelector("#valuation-create-reason"),
  createValuation: document.querySelector("#create-valuation"),
  valuationCreateError: document.querySelector("#valuation-create-error"),
  valuationList: document.querySelector("#valuation-list"),
  valuationWorkbench: document.querySelector("#valuation-workbench"),
  valuationRecordId: document.querySelector("#valuation-record-id"),
  valuationRecordTitle: document.querySelector("#valuation-record-title"),
  valuationRecordStatus: document.querySelector("#valuation-record-status"),
  valuationExport: document.querySelector("#valuation-export"),
  calculationIntegrity: document.querySelector("#calculation-integrity"),
  calculationIntegrityNote: document.querySelector("#calculation-integrity-note"),
  decisionReadiness: document.querySelector("#decision-readiness"),
  decisionReadinessNote: document.querySelector("#decision-readiness-note"),
  valuationInputPanel: document.querySelector("#valuation-input-panel"),
  valuationInputForm: document.querySelector("#valuation-input-form"),
  valuationSourceId: document.querySelector("#valuation-source-id"),
  valuationSourceLocator: document.querySelector("#valuation-source-locator"),
  valuationSourceDate: document.querySelector("#valuation-source-date"),
  valuationUnit: document.querySelector("#valuation-unit"),
  valuationBusinessModel: document.querySelector("#valuation-business-model"),
  valuationDiscountConvention: document.querySelector("#valuation-discount-convention"),
  scenarioInputs: document.querySelector("#scenario-inputs"),
  bridgeCash: document.querySelector("#bridge-cash"),
  bridgeDebt: document.querySelector("#bridge-debt"),
  bridgeAssets: document.querySelector("#bridge-assets"),
  bridgeClaims: document.querySelector("#bridge-claims"),
  bridgeShares: document.querySelector("#bridge-shares"),
  tradingCompsInputs: document.querySelector("#trading-comps-inputs"),
  valuationCompsMode: document.querySelector("#valuation-comps-mode"),
  valuationCompsMetric: document.querySelector("#valuation-comps-metric"),
  valuationCompsTargetMetric: document.querySelector("#valuation-comps-target-metric"),
  valuationCompsTargetPeriod: document.querySelector("#valuation-comps-target-period"),
  valuationCompsBody: document.querySelector("#valuation-comps-body"),
  compsNumeratorHeading: document.querySelector("#comps-numerator-heading"),
  compsDenominatorHeading: document.querySelector("#comps-denominator-heading"),
  compsBoundary: document.querySelector("#comps-boundary"),
  valuationConfirmInputs: document.querySelector("#valuation-confirm-inputs"),
  valuationInputReason: document.querySelector("#valuation-input-reason"),
  saveValuationInputs: document.querySelector("#save-valuation-inputs"),
  valuationInputError: document.querySelector("#valuation-input-error"),
  valuationCalculateForm: document.querySelector("#valuation-calculate-form"),
  valuationCalculateReason: document.querySelector("#valuation-calculate-reason"),
  calculateValuation: document.querySelector("#calculate-valuation"),
  valuationCalculateError: document.querySelector("#valuation-calculate-error"),
  valuationReviewForm: document.querySelector("#valuation-review-form"),
  valuationReviewNote: document.querySelector("#valuation-review-note"),
  valuationReviewReason: document.querySelector("#valuation-review-reason"),
  reviewValuation: document.querySelector("#review-valuation"),
  valuationReviewError: document.querySelector("#valuation-review-error"),
  valuationApproveForm: document.querySelector("#valuation-approve-form"),
  valuationApproveReason: document.querySelector("#valuation-approve-reason"),
  valuationApproveConfirm: document.querySelector("#valuation-approve-confirm"),
  approveValuation: document.querySelector("#approve-valuation"),
  valuationApproveError: document.querySelector("#valuation-approve-error"),
  valuationMethodResults: document.querySelector("#valuation-method-results"),
  valuationChecks: document.querySelector("#valuation-checks"),
  valuationSourceList: document.querySelector("#valuation-source-list"),
  valuationVersionList: document.querySelector("#valuation-version-list"),
  resourcesTruth: document.querySelector("#resources-truth"),
  resourceLibrary: document.querySelector("#resource-library"),
  resourcePolicyList: document.querySelector("#resource-policy-list"),
  resourceCourseList: document.querySelector("#resource-course-list"),
  resourceMentorList: document.querySelector("#resource-mentor-list"),
  resourceSearch: document.querySelector("#resource-search"),
  resourceTypeFilter: document.querySelector("#resource-type-filter"),
  resourceFilterSummary: document.querySelector("#resource-filter-summary"),
  resourceTemplateDownload: document.querySelector(
    "#resource-template-download",
  ),
  resourceRows: Array.from(
    document.querySelectorAll("[data-resource-kind]"),
  ),
  refreshResources: document.querySelector("#refresh-resources"),
  caseTypeBadge: document.querySelector("#case-type-badge"),
  caseIdLabel: document.querySelector("#case-id-label"),
  caseTitle: document.querySelector("#case-title"),
  caseNeed: document.querySelector("#case-need"),
  caseNeedSource: document.querySelector("#case-need-source"),
  caseStatus: document.querySelector("#case-status"),
  caseOwnerLabel: document.querySelector("#case-owner-label"),
  caseMaterialCount: document.querySelector("#case-material-count"),
  caseUpdatedAt: document.querySelector("#case-updated-at"),
  caseTabs: Array.from(document.querySelectorAll("[data-case-tab]")),
  casePanels: Array.from(document.querySelectorAll("[data-case-panel]")),
  nextActionTitle: document.querySelector("#next-action-title"),
  nextActionReason: document.querySelector("#next-action-reason"),
  nextActionButton: document.querySelector("#next-action-button"),
  evidenceControlState: document.querySelector("#evidence-control-state"),
  evidenceControlSummary: document.querySelector("#evidence-control-summary"),
  evidenceControlSignals: document.querySelector("#evidence-control-signals"),
  evidenceControlResponses: document.querySelector("#evidence-control-responses"),
  contentAuthorizationState: document.querySelector(
    "#content-authorization-state",
  ),
  contentAuthorizationSummary: document.querySelector(
    "#content-authorization-summary",
  ),
  contentAuthorizationPermissions: document.querySelector(
    "#content-authorization-permissions",
  ),
  contentAuthorizationRequests: document.querySelector(
    "#content-authorization-requests",
  ),
  financialBasisState: document.querySelector("#financial-basis-state"),
  financialBasisSummary: document.querySelector("#financial-basis-summary"),
  financialBasisDimensions: document.querySelector(
    "#financial-basis-dimensions",
  ),
  financialBasisResponses: document.querySelector("#financial-basis-responses"),
  acquisitionState: document.querySelector("#acquisition-state"),
  acquisitionStageTrack: document.querySelector("#acquisition-stage-track"),
  acquisitionCurrentStage: document.querySelector(
    "#acquisition-current-stage",
  ),
  acquisitionGapCount: document.querySelector("#acquisition-gap-count"),
  acquisitionGapSummary: document.querySelector("#acquisition-gap-summary"),
  acquisitionInterview: document.querySelector("#acquisition-interview"),
  acquisitionInterviewReason: document.querySelector(
    "#acquisition-interview-reason",
  ),
  keyQuestionCount: document.querySelector("#key-question-count"),
  keyQuestionList: document.querySelector("#key-question-list"),
  companyPolicyResources: document.querySelector("#company-policy-resources"),
  companyCourseResources: document.querySelector("#company-course-resources"),
  companyMentorResources: document.querySelector("#company-mentor-resources"),
  companyCourseCandidateList: document.querySelector(
    "#company-course-candidate-list",
  ),
  companyMentorCandidateList: document.querySelector(
    "#company-mentor-candidate-list",
  ),
  caseTopicList: document.querySelector("#case-topic-list"),
  workflowList: document.querySelector("#workflow-list"),
  materialList: document.querySelector("#material-list"),
  moduleList: document.querySelector("#module-list"),
  catalogConfirmationLabel: document.querySelector(
    "#catalog-confirmation-label",
  ),
  ragReferenceStatus: document.querySelector("#rag-reference-status"),
  ragReferenceCount: document.querySelector("#rag-reference-count"),
  ragQueryForm: document.querySelector("#rag-query-form"),
  ragQuestion: document.querySelector("#rag-question"),
  runRagQuery: document.querySelector("#run-rag-query"),
  ragError: document.querySelector("#rag-error"),
  ragResults: document.querySelector("#rag-results"),
  policyReferenceStatus: document.querySelector("#policy-reference-status"),
  policyResultCount: document.querySelector("#policy-result-count"),
  policyForm: document.querySelector("#policy-form"),
  policyAsOf: document.querySelector("#policy-as-of"),
  runPolicyReference: document.querySelector("#run-policy-reference"),
  policyError: document.querySelector("#policy-error"),
  policyResults: document.querySelector("#policy-results"),
  openConsent: document.querySelector("#open-consent"),
  revokeConsent: document.querySelector("#revoke-consent"),
  consentDialog: document.querySelector("#consent-dialog"),
  consentForm: document.querySelector("#consent-form"),
  consentDescription: document.querySelector("#consent-description"),
  closeConsent: document.querySelector("#close-consent"),
  declineConsent: document.querySelector("#decline-consent"),
  consentActor: document.querySelector("#consent-actor"),
  consentProgress: document.querySelector("#consent-progress"),
  consentError: document.querySelector("#consent-error"),
  grantConsent: document.querySelector("#grant-consent"),
  authorizationRequestContext: document.querySelector(
    "#authorization-request-context",
  ),
  authorizationRequestActor: document.querySelector(
    "#authorization-request-actor",
  ),
  authorizationRequestPurpose: document.querySelector(
    "#authorization-request-purpose",
  ),
  authorizationRequestCase: document.querySelector(
    "#authorization-request-case",
  ),
  liveRegion: document.querySelector("#live-region"),
};

const capabilityCheckboxes = [
  document.querySelector("#allow-case-read"),
  document.querySelector("#allow-material-read"),
  document.querySelector("#allow-rag-query"),
  document.querySelector("#allow-resource-read"),
  document.querySelector("#allow-resource-match"),
  document.querySelector("#allow-policy-read"),
  document.querySelector("#allow-policy-reference"),
  document.querySelector("#allow-candidate-match"),
];
const boundaryCheckbox = document.querySelector("#acknowledge-human-review");
const allConsentCheckboxes = [...capabilityCheckboxes, boundaryCheckbox];
const SCOPE_INPUTS = Object.freeze({
  "case:read": "#allow-case-read",
  "material:read": "#allow-material-read",
  "rag:query": "#allow-rag-query",
  "resource:read": "#allow-resource-read",
  "resource:match": "#allow-resource-match",
  "policy:read": "#allow-policy-read",
  "policy:reference": "#allow-policy-reference",
  "policy:match": "#allow-candidate-match",
});

function node(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = String(text);
  }
  return element;
}

function setMessage(element, message) {
  element.textContent = message || "";
  element.hidden = !message;
}

function announce(message) {
  elements.liveRegion.textContent = "";
  window.requestAnimationFrame(() => {
    elements.liveRegion.textContent = message;
  });
}

function errorMessage(error, fallback) {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function setBusy(button, busy, busyLabel, idleLabel) {
  button.disabled = busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
  button.textContent = busy ? busyLabel : idleLabel;
}

async function requestJson(path, options = {}) {
  const headers = new Headers(options.headers || {});
  let body = options.body;
  if (options.authorized) {
    if (!appState.accessToken) {
      throw new Error("当前没有 Agent 访问令牌。");
    }
    headers.set("Authorization", `Bearer ${appState.accessToken}`);
  }
  if (
    body !== undefined &&
    !(body instanceof FormData) &&
    typeof body !== "string"
  ) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    body,
    cache: "no-store",
  });
  const responseText = await response.text();
  let payload = {};
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      throw new Error(`本地服务返回了无法解析的响应（HTTP ${response.status}）。`);
    }
  }
  if (!response.ok) {
    const message =
      payload?.message ||
      payload?.detail ||
      payload?.error ||
      `请求失败（HTTP ${response.status}）`;
    throw new Error(String(message));
  }
  return payload;
}

function formatCount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return new Intl.NumberFormat("zh-CN", {
    notation: number >= 100000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(number);
}

function optionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = number;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDate(value) {
  if (!value) {
    return "未记录";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "时间未知";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function localDateValue(date = new Date()) {
  const localTime = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localTime.toISOString().slice(0, 10);
}

function caseUrl(caseId, tab = "overview") {
  return `/?view=case&case_id=${encodeURIComponent(caseId)}#${encodeURIComponent(tab)}`;
}

function currentRoute() {
  const url = new URL(window.location.href);
  const requestedView = url.searchParams.get("view");
  const caseId = url.searchParams.get("case_id");
  if (["case", "company"].includes(requestedView) && caseId) {
    const tab = url.hash.replace(/^#/, "") || "overview";
    return { view: "case", caseId, tab };
  }
  if (["dashboard", "companies"].includes(requestedView)) {
    return { view: "dashboard", caseId: null, tab: null };
  }
  if (requestedView === "deals") {
    return {
      view: "deals",
      dealId: url.searchParams.get("deal_id"),
      valuationId: url.searchParams.get("valuation_id"),
      caseId: null,
      tab: null,
    };
  }
  if (requestedView === "resources") {
    return { view: "resources", caseId: null, tab: null };
  }
  return { view: "home", caseId: null, tab: null };
}

function routeUrl(
  view,
  {
    caseId = null,
    tab = "overview",
    dealId = null,
    valuationId = null,
  } = {},
) {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("view", view);
  if (view === "case" && caseId) {
    url.searchParams.set("case_id", caseId);
    url.hash = tab;
  } else if (view === "deals" && dealId) {
    url.searchParams.set("deal_id", dealId);
    if (valuationId) {
      url.searchParams.set("valuation_id", valuationId);
    }
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

async function navigate(view, options = {}) {
  const {
    caseId = null,
    tab = "overview",
    dealId = null,
    valuationId = null,
    replace = false,
  } = options;
  const target = routeUrl(view, { caseId, tab, dealId, valuationId });
  if (replace) {
    window.history.replaceState({}, "", target);
  } else {
    window.history.pushState({}, "", target);
  }
  await renderRoute({ focus: true });
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
}

function showView(viewName) {
  elements.views.forEach((view) => {
    view.hidden = view.dataset.view !== viewName;
  });
  const primaryRoute = viewName === "case" ? "dashboard" : viewName;
  elements.globalRoutes.forEach((link) => {
    if (link.dataset.route === primaryRoute) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function focusViewTitle(view) {
  const title = document.querySelector(`#${view}-title`);
  if (title) {
    window.requestAnimationFrame(() => title.focus({ preventScroll: true }));
  }
}

async function renderRoute({ focus = false } = {}) {
  const route = currentRoute();
  showView(route.view);
  if (route.view === "home") {
    document.title = "CleanTech Finance｜资料入口";
    renderRecentCases();
  } else if (route.view === "dashboard") {
    document.title = "CleanTech Finance｜企业总看板";
    if (!appState.dashboard) {
      await refreshDashboard();
    } else {
      renderDashboard();
    }
  } else if (route.view === "deals") {
    document.title = "CleanTech Finance｜交易工作台";
    if (appState.dealsState === "idle") {
      await refreshDeals({ loadSelection: false });
    } else {
      renderDealList();
    }
    if (route.dealId) {
      try {
        if (appState.currentDeal?.deal_id !== route.dealId) {
          await loadDeal(route.dealId, route.valuationId);
        } else {
          selectValuation(route.valuationId, { updateUrl: false });
          renderDealWorkbench();
        }
      } catch (error) {
        announce(errorMessage(error, "交易无法载入。"));
        await navigate("deals", { replace: true });
        return;
      }
    } else {
      appState.currentDeal = null;
      appState.currentValuation = null;
      renderDealList();
      renderDealWorkbench();
    }
  } else if (route.view === "resources") {
    document.title = "CleanTech Finance｜资源库";
    if (appState.resourcesState === "idle") {
      await refreshResources();
    } else {
      renderResources();
    }
  } else {
    try {
      if (appState.currentCase?.case_id !== route.caseId) {
        renderCaseLoadingState();
        await loadCase(route.caseId);
      }
      setCaseTab(route.tab);
      document.title =
        `${appState.currentCase?.case_name || "企业"}｜CleanTech Finance`;
    } catch (error) {
      announce(errorMessage(error, "企业无法载入。"));
      await navigate("dashboard", { replace: true });
      return;
    }
  }
  updateConsentProgress();
  if (focus) {
    focusViewTitle(route.view);
  }
}

function dealPath(dealId = null, suffix = "") {
  if (!dealId) {
    return API.deals;
  }
  return `${API.deals}/${encodeURIComponent(dealId)}${suffix}`;
}

function valuationPath(valuationId, suffix = "") {
  return `/api/ui/valuations/${encodeURIComponent(valuationId)}${suffix}`;
}

const pendingIdempotencyKeys = new Map();

function idempotencyHeaders(prefix, body) {
  const fingerprint = JSON.stringify(body);
  const pending = pendingIdempotencyKeys.get(prefix);
  if (pending?.fingerprint === fingerprint) {
    return { "Idempotency-Key": pending.key };
  }
  const suffix = typeof window.crypto?.randomUUID === "function"
    ? window.crypto.randomUUID()
    : `${Date.now()}-${performance.now().toFixed(3)}`;
  const key = `${prefix}-${suffix}`;
  pendingIdempotencyKeys.set(prefix, { fingerprint, key });
  return { "Idempotency-Key": key };
}

function clearIdempotencyKey(prefix, body) {
  const pending = pendingIdempotencyKeys.get(prefix);
  if (pending?.fingerprint === JSON.stringify(body)) {
    pendingIdempotencyKeys.delete(prefix);
  }
}

function latestValuationVersion(valuation) {
  const versions = Array.isArray(valuation?.versions) ? valuation.versions : [];
  return versions.length ? versions[versions.length - 1] : null;
}

function shortHash(value) {
  const text = String(value || "");
  return text.length > 18 ? `${text.slice(0, 10)}…${text.slice(-6)}` : text || "-";
}

function valueLabel(value, fallback = "未记录") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function formatRecordDate(value) {
  const text = String(value || "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return text;
  }
  return formatDate(value);
}

function statusLabel(status) {
  return VALUATION_STATUS_LABELS[String(status || "")] || valueLabel(status, "未开始");
}

function stateLabel(status) {
  return VALUATION_STATE_LABELS[String(status || "")] || valueLabel(status, "尚未生成");
}

function createDecimalInput(id, label, required = true) {
  const wrapper = node("label", "forecast-field");
  const caption = node("span", null, label);
  const input = document.createElement("input");
  input.id = id;
  input.type = "text";
  input.inputMode = "decimal";
  input.autocomplete = "off";
  input.required = required;
  wrapper.append(caption, input);
  return wrapper;
}

function buildScenarioInputs() {
  elements.scenarioInputs.replaceChildren();
  VALUATION_SCENARIOS.forEach((scenario) => {
    const details = node("details", "scenario-block");
    details.dataset.scenario = scenario.id;
    details.open = scenario.id === "base";
    const summary = node("summary", null, scenario.label);
    const assumptions = node("div", "scenario-assumptions");
    assumptions.append(
      createDecimalInput(`${scenario.id}-wacc`, "WACC"),
      createDecimalInput(`${scenario.id}-terminal-growth`, "永续增长率"),
      createDecimalInput(`${scenario.id}-terminal-metric`, "终值口径（可选）", false),
      createDecimalInput(`${scenario.id}-exit-multiple`, "退出倍数（可选）", false),
    );

    const tableWrap = node("div", "forecast-table-wrap");
    const table = node("table", "forecast-table");
    const caption = node("caption", "sr-only", `${scenario.label} 三年 FCFF 输入`);
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["期间", ...FORECAST_FIELDS.map((field) => field.label)].forEach((label) => {
      const cell = node("th", null, label);
      cell.scope = "col";
      headRow.append(cell);
    });
    head.append(headRow);
    const body = document.createElement("tbody");
    for (let year = 1; year <= 3; year += 1) {
      const row = document.createElement("tr");
      const periodCell = document.createElement("th");
      periodCell.scope = "row";
      const periodInput = document.createElement("input");
      periodInput.id = `${scenario.id}-y${year}-period`;
      periodInput.type = "text";
      periodInput.value = `Year ${year}`;
      periodInput.maxLength = 40;
      periodInput.required = true;
      periodInput.setAttribute("aria-label", `${scenario.label} 第 ${year} 期名称`);
      periodCell.append(periodInput);
      row.append(periodCell);
      FORECAST_FIELDS.forEach((field) => {
        const cell = document.createElement("td");
        const input = document.createElement("input");
        input.id = `${scenario.id}-y${year}-${field.id}`;
        input.type = "text";
        input.inputMode = "decimal";
        input.autocomplete = "off";
        input.required = true;
        input.setAttribute(
          "aria-label",
          `${scenario.label} 第 ${year} 期 ${field.label}`,
        );
        cell.append(input);
        row.append(cell);
      });
      body.append(row);
    }
    table.append(caption, head, body);
    tableWrap.append(table);
    details.append(summary, assumptions, tableWrap);
    elements.scenarioInputs.append(details);
  });
}

function buildTradingCompsRows() {
  elements.valuationCompsBody.replaceChildren();
  for (let index = 1; index <= 5; index += 1) {
    const row = document.createElement("tr");
    row.dataset.peerIndex = String(index);
    const nameCell = document.createElement("td");
    const name = document.createElement("input");
    name.id = `comps-peer-${index}-name`;
    name.type = "text";
    name.maxLength = 160;
    name.setAttribute("aria-label", `可比公司 ${index} 名称`);
    nameCell.append(name);

    const classificationCell = document.createElement("td");
    const classification = document.createElement("select");
    classification.id = `comps-peer-${index}-classification`;
    classification.setAttribute("aria-label", `可比公司 ${index} 分类`);
    [
      ["core_peer", "Core"],
      ["secondary_peer", "Secondary"],
      ["aspirational_peer", "Aspirational"],
      ["excluded_peer", "Excluded"],
    ].forEach(([value, label]) => {
      const option = node("option", null, label);
      option.value = value;
      classification.append(option);
    });
    classificationCell.append(classification);

    const rationaleCell = document.createElement("td");
    const rationale = document.createElement("input");
    rationale.id = `comps-peer-${index}-rationale`;
    rationale.type = "text";
    rationale.maxLength = 500;
    rationale.setAttribute("aria-label", `可比公司 ${index} 选择依据`);
    rationaleCell.append(rationale);

    const evCell = document.createElement("td");
    const ev = document.createElement("input");
    ev.id = `comps-peer-${index}-ev`;
    ev.type = "text";
    ev.inputMode = "decimal";
    ev.setAttribute("aria-label", `可比公司 ${index} enterprise value`);
    evCell.append(ev);

    const denominatorCell = document.createElement("td");
    const denominator = document.createElement("input");
    denominator.id = `comps-peer-${index}-denominator`;
    denominator.type = "text";
    denominator.inputMode = "decimal";
    denominator.setAttribute("aria-label", `可比公司 ${index} 倍数分母`);
    denominatorCell.append(denominator);
    row.append(nameCell, classificationCell, rationaleCell, evCell, denominatorCell);
    elements.valuationCompsBody.append(row);
  }
}

function compsPeerControls(index) {
  return {
    name: document.querySelector(`#comps-peer-${index}-name`),
    classification: document.querySelector(`#comps-peer-${index}-classification`),
    rationale: document.querySelector(`#comps-peer-${index}-rationale`),
    enterpriseValue: document.querySelector(`#comps-peer-${index}-ev`),
    denominator: document.querySelector(`#comps-peer-${index}-denominator`),
  };
}

function updateCompsControls() {
  const valuation = appState.currentValuation;
  const planned = Array.isArray(valuation?.methods)
    ? valuation.methods.includes("trading_comps")
    : false;
  const hasStoredComps = Boolean(
    latestValuationVersion(valuation)?.inputs?.some(
      (item) => item.input_id === "config-comps-metric",
    ),
  );
  elements.valuationCompsMode.value = planned ? "on" : "off";
  elements.valuationCompsMode.disabled = true;
  const enabled = planned;
  const metric = COMPS_METRICS[elements.valuationCompsMetric.value];
  elements.compsNumeratorHeading.textContent = metric?.numeratorLabel || "价值分子";
  elements.compsDenominatorHeading.textContent = metric?.label || "倍数分母";
  elements.compsBoundary.textContent = !planned
    ? "该估值案例未计划 Trading Comps。如需增加该方法，请新建估值案例，避免静默改变方法范围。"
    : hasStoredComps
      ? "Trading Comps 已进入版本链，不能在当前案例中静默移除。可把不参与统计的公司标为 Excluded。"
      : "该案例已选择组合方法，可比公司输入为必填。浏览器只提交价值分子与分母；倍数、N/M、区间和检查全部由服务端计算。P/E 使用股权价值，其余口径使用企业价值；Excluded 行不参与统计。";
  [
    elements.valuationCompsMetric,
    elements.valuationCompsTargetMetric,
    elements.valuationCompsTargetPeriod,
  ].forEach((control) => {
    control.disabled = !enabled;
  });
  elements.valuationCompsTargetMetric.required = enabled;
  elements.valuationCompsTargetPeriod.required = enabled;
  for (let index = 1; index <= 5; index += 1) {
    const controls = compsPeerControls(index);
    controls.enterpriseValue.setAttribute(
      "aria-label",
      `可比公司 ${index} ${metric?.numeratorLabel || "价值分子"}`,
    );
    Object.values(controls).forEach((control) => {
      control.disabled = !enabled;
    });
    const excluded = controls.classification.value === "excluded_peer";
    controls.name.required = enabled;
    controls.rationale.required = enabled;
    controls.enterpriseValue.required = enabled && !excluded;
    controls.denominator.required = enabled && !excluded;
    controls.enterpriseValue.closest("td").dataset.optional = excluded ? "true" : "false";
    controls.denominator.closest("td").dataset.optional = excluded ? "true" : "false";
  }
}

function tradingCompsPayload() {
  if (elements.valuationCompsMode.value !== "on") {
    return null;
  }
  const metricId = elements.valuationCompsMetric.value;
  const metric = COMPS_METRICS[metricId];
  const peers = [];
  for (let index = 1; index <= 5; index += 1) {
    const controls = compsPeerControls(index);
    const peer = {
      name: controls.name.value.trim(),
      classification: controls.classification.value,
      rationale: controls.rationale.value.trim(),
      is_target_baseline: false,
    };
    const numeratorValue = controls.enterpriseValue.value.trim();
    const denominator = controls.denominator.value.trim();
    if (numeratorValue) {
      peer[metric.numeratorField] = numeratorValue;
    }
    if (denominator) {
      peer[metric.field] = denominator;
    }
    peers.push(peer);
  }
  return {
    metric: metricId,
    target_metric: elements.valuationCompsTargetMetric.value.trim(),
    target_metric_period: elements.valuationCompsTargetPeriod.value.trim(),
    peers,
  };
}

function scenarioPayload(scenarioId) {
  const periods = [];
  for (let year = 1; year <= 3; year += 1) {
    const period = {
      period: document.querySelector(`#${scenarioId}-y${year}-period`).value.trim(),
    };
    FORECAST_FIELDS.forEach((field) => {
      period[field.id] = document
        .querySelector(`#${scenarioId}-y${year}-${field.id}`)
        .value.trim();
    });
    periods.push(period);
  }
  const scenario = {
    wacc: document.querySelector(`#${scenarioId}-wacc`).value.trim(),
    terminal_growth: document
      .querySelector(`#${scenarioId}-terminal-growth`)
      .value.trim(),
    periods,
  };
  const terminalMetric = document
    .querySelector(`#${scenarioId}-terminal-metric`)
    .value.trim();
  const exitMultiple = document
    .querySelector(`#${scenarioId}-exit-multiple`)
    .value.trim();
  if (terminalMetric || exitMultiple) {
    scenario.terminal_metric = terminalMetric;
    scenario.exit_multiple = exitMultiple;
  }
  return scenario;
}

function fillCompanyOptions() {
  elements.dealCompanyOptions.replaceChildren();
  const cases = Array.isArray(appState.dashboard?.cases)
    ? appState.dashboard.cases
    : [];
  cases.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(item.case_id || item.company_id || "");
    option.label = valueLabel(item.case_name || item.company_name, option.value);
    if (option.value) {
      elements.dealCompanyOptions.append(option);
    }
  });
}

function setDealCreateOpen(open) {
  elements.dealCreatePanel.hidden = !open;
  elements.toggleDealCreate.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    window.requestAnimationFrame(() => elements.dealCompanyId.focus());
  }
}

function dealCollection(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.deals)) {
    return payload.deals;
  }
  if (Array.isArray(payload?.items)) {
    return payload.items;
  }
  return [];
}

async function refreshDeals({ loadSelection = true } = {}) {
  appState.dealsState = "loading";
  appState.dealsError = null;
  elements.dealList.setAttribute("aria-busy", "true");
  renderDealList();
  try {
    const payload = await requestJson(API.deals);
    appState.deals = dealCollection(payload);
    appState.dealsState = "ready";
    fillCompanyOptions();
    renderDealList();
    const route = currentRoute();
    if (loadSelection && route.view === "deals" && route.dealId) {
      await loadDeal(route.dealId, route.valuationId);
    }
  } catch (error) {
    appState.dealsState = "error";
    appState.dealsError = errorMessage(error, "本地交易清单无法读取。");
    renderDealList();
  } finally {
    elements.dealList.setAttribute("aria-busy", "false");
  }
}

function dealSearchText(deal) {
  const header = deal?.deal_header || {};
  return [
    deal?.deal_id,
    deal?.company_id,
    header.target,
    header.buyer,
    header.owner,
    header.transaction_scope,
  ].join(" ").toLocaleLowerCase("zh-CN");
}

function renderDealList() {
  elements.dealList.replaceChildren();
  if (appState.dealsState === "loading") {
    elements.dealCount.textContent = "正在读取本地交易";
    elements.dealList.append(
      node("div", "deal-list-skeleton", "正在加载交易清单"),
    );
    return;
  }
  if (appState.dealsState === "error") {
    elements.dealCount.textContent = "读取失败";
    const error = node("div", "deal-list-error");
    error.append(
      node("strong", null, "交易清单暂不可用"),
      node("p", null, appState.dealsError),
    );
    elements.dealList.append(error);
    return;
  }
  const query = elements.dealSearch.value.trim().toLocaleLowerCase("zh-CN");
  const deals = appState.deals.filter(
    (deal) => !query || dealSearchText(deal).includes(query),
  );
  elements.dealCount.textContent = `${deals.length} 项交易`;
  if (!deals.length) {
    const empty = node("div", "deal-list-empty");
    empty.append(
      node("strong", null, query ? "没有匹配的交易" : "还没有交易"),
      node(
        "p",
        null,
        query ? "调整搜索条件。" : "点击“新建交易”建立第一项工作区。",
      ),
    );
    elements.dealList.append(empty);
    return;
  }
  deals.forEach((deal) => {
    const header = deal?.deal_header || {};
    const link = node("a", "deal-list-item");
    link.href = routeUrl("deals", { dealId: deal.deal_id });
    link.dataset.dealId = deal.deal_id;
    if (appState.currentDeal?.deal_id === deal.deal_id) {
      link.setAttribute("aria-current", "page");
    }
    const heading = node("span", "deal-list-title");
    heading.append(
      node("strong", null, valueLabel(header.target, "未命名标的")),
      node("small", null, valueLabel(header.buyer, "未记录买方")),
    );
    const stage = deal?.human_confirmed_stage?.stage;
    const meta = node("span", "deal-list-meta");
    meta.append(
      node(
        "span",
        "deal-state-label",
        stage ? DEAL_STAGE_LABELS[stage] || stage : "阶段待确认",
      ),
      node("small", null, formatRecordDate(deal.updated_at)),
    );
    link.append(heading, meta);
    elements.dealList.append(link);
  });
}

async function loadDeal(dealId, valuationId = null) {
  const payload = await requestJson(dealPath(dealId));
  appState.currentDeal = payload?.deal || payload?.result || payload;
  if (!appState.currentDeal?.deal_id) {
    throw new Error("本地服务未返回有效交易记录。");
  }
  const listedIndex = appState.deals.findIndex(
    (item) => item.deal_id === appState.currentDeal.deal_id,
  );
  if (listedIndex >= 0) {
    appState.deals.splice(listedIndex, 1, appState.currentDeal);
  } else {
    appState.deals.unshift(appState.currentDeal);
  }
  selectValuation(valuationId, { updateUrl: false });
  renderDealList();
  renderDealWorkbench();
}

async function reloadCurrentDeal({ valuationId = null } = {}) {
  if (!appState.currentDeal?.deal_id) {
    return;
  }
  await loadDeal(
    appState.currentDeal.deal_id,
    valuationId || appState.currentValuation?.valuation_id || null,
  );
}

function selectValuation(valuationId, { updateUrl = true } = {}) {
  const valuations = Array.isArray(appState.currentDeal?.valuations)
    ? appState.currentDeal.valuations
    : [];
  appState.currentValuation =
    valuations.find((item) => item.valuation_id === valuationId) ||
    valuations[valuations.length - 1] ||
    null;
  if (updateUrl && appState.currentDeal) {
    window.history.pushState(
      {},
      "",
      routeUrl("deals", {
        dealId: appState.currentDeal.deal_id,
        valuationId: appState.currentValuation?.valuation_id || null,
      }),
    );
  }
  renderValuationList();
  renderValuationWorkbench();
}

function renderDealReadiness(deal) {
  const materials = Array.isArray(deal?.materials) ? deal.materials : [];
  const verified = materials.filter((item) =>
    ["accepted", "verified", "human_verified", "reviewed"].includes(
      String(item?.review_status || "").toLowerCase(),
    ),
  );
  elements.readinessMaterial.textContent = materials.length
    ? `${materials.length} 份已登记`
    : "尚未登记";
  elements.readinessMaterialNote.textContent = materials.length
    ? "仅表示交易材料引用存在。"
    : "材料覆盖不会自动确认交易阶段。";
  elements.readinessEvidence.textContent = verified.length
    ? `${verified.length} 份已核验`
    : "待人工核验";
  elements.readinessEvidenceNote.textContent = materials.length
    ? `${materials.length - verified.length} 份仍未达到核验状态。`
    : "没有可用于核验的交易材料引用。";

  const stage = deal?.human_confirmed_stage;
  elements.readinessStage.textContent = stage
    ? DEAL_STAGE_LABELS[stage.stage] || stage.stage
    : "待确认";
  elements.readinessStageNote.textContent = stage
    ? `由 ${valueLabel(stage.confirmed_by?.id, "本地 FA")} 于 ${formatRecordDate(stage.confirmed_at)} 确认。`
    : "不会根据候选材料自动推断。";

  const valuation = appState.currentValuation;
  const active = latestValuationVersion(valuation);
  const readiness = active?.calculation?.decision_readiness;
  elements.readinessValuation.textContent = readiness
    ? stateLabel(readiness.status)
    : valuation
      ? statusLabel(valuation.status)
      : "未开始";
  const blockers = Array.isArray(readiness?.blocking_reasons)
    ? readiness.blocking_reasons
    : [];
  elements.readinessValuationNote.textContent = blockers.length
    ? `${blockers.length} 项决策可用性缺口。`
    : valuation
      ? "仍需按状态完成人工复核与内部批准。"
      : "先建立估值案例并录入可追溯输入。";
}

function renderDealWorkbench() {
  const deal = appState.currentDeal;
  elements.dealEmpty.hidden = Boolean(deal);
  elements.dealWorkbench.hidden = !deal;
  if (!deal) {
    return;
  }
  const header = deal.deal_header || {};
  elements.dealRecordId.textContent = `${deal.deal_id} · ${valueLabel(deal.company_id, "企业未绑定")}`;
  elements.dealRecordTitle.textContent = valueLabel(header.target, "未命名标的");
  elements.dealRecordScope.textContent = valueLabel(header.transaction_scope);
  elements.dealRecordOwner.textContent = valueLabel(header.owner, "未分配");
  elements.dealRecordDate.textContent = formatRecordDate(header.valuation_date);
  elements.dealRecordCurrency.textContent = valueLabel(header.currency, "-");
  elements.dealRecordRevision.textContent = String(deal.revision || "-");
  const stage = deal.human_confirmed_stage;
  elements.dealStageCurrent.textContent = stage
    ? DEAL_STAGE_LABELS[stage.stage] || stage.stage
    : "尚未确认";
  elements.dealStageCurrent.dataset.state = stage ? "ready" : "warning";
  elements.dealStageSelect.value = stage?.stage || "";
  elements.dealStageReason.value = "";
  elements.valuationTargetEntity.value = valueLabel(header.target, "");
  elements.valuationDate.value = header.valuation_date || localDateValue();
  elements.valuationCurrency.value = header.currency || "CNY";
  elements.valuationScope.value = header.transaction_scope || "";
  renderValuationList();
  renderValuationWorkbench();
  renderDealReadiness(deal);
}

function renderValuationList() {
  elements.valuationList.replaceChildren();
  const valuations = Array.isArray(appState.currentDeal?.valuations)
    ? appState.currentDeal.valuations
    : [];
  if (!valuations.length) {
    const empty = node("div", "valuation-list-empty");
    empty.append(
      node("strong", null, "尚未建立估值"),
      node("p", null, "建立 FCFF DCF 初步估值后，再录入三情景输入。"),
    );
    elements.valuationList.append(empty);
    return;
  }
  valuations.forEach((valuation) => {
    const button = node("button", "valuation-list-item");
    button.type = "button";
    button.dataset.valuationId = valuation.valuation_id;
    if (valuation.valuation_id === appState.currentValuation?.valuation_id) {
      button.setAttribute("aria-pressed", "true");
    } else {
      button.setAttribute("aria-pressed", "false");
    }
    const label = node("span", null);
    label.append(
      node("strong", null, valueLabel(valuation.target_legal_entity, "估值案例")),
      node("small", null, `${valuation.valuation_date} · ${valuation.base_currency}`),
    );
    const status = node("span", "deal-state-label", statusLabel(valuation.status));
    status.dataset.state = valuation.status;
    button.append(label, status);
    elements.valuationList.append(button);
  });
}

function inputById(version) {
  const values = Array.isArray(version?.inputs) ? version.inputs : [];
  return new Map(values.map((item) => [String(item.input_id || ""), item]));
}

function setInputValue(selector, value) {
  const input = document.querySelector(selector);
  if (input) {
    input.value = value === null || value === undefined ? "" : String(value);
  }
}

function populateValuationInputForm(valuation, version) {
  const inputs = Array.isArray(version?.inputs) ? version.inputs : [];
  const byId = inputById(version);
  const first = inputs[0] || {};
  const amountInput = inputs.find(
    (item) => !["ratio", "multiple", "shares", "text"].includes(item.unit),
  );
  elements.valuationSourceId.value = first.source_id || "";
  elements.valuationSourceLocator.value = first.locator || "";
  elements.valuationSourceDate.value = first.as_of || valuation.valuation_date || localDateValue();
  elements.valuationUnit.value = amountInput?.unit || "million";
  elements.valuationBusinessModel.value =
    byId.get("config-business-model")?.value || "mature_equipment_manufacturing";
  elements.valuationDiscountConvention.value =
    byId.get("config-discount-convention")?.value || "period_end";
  VALUATION_SCENARIOS.forEach((scenario) => {
    setInputValue(
      `#${scenario.id}-wacc`,
      byId.get(`${scenario.id}-wacc`)?.value,
    );
    setInputValue(
      `#${scenario.id}-terminal-growth`,
      byId.get(`${scenario.id}-terminal-growth`)?.value,
    );
    setInputValue(
      `#${scenario.id}-terminal-metric`,
      byId.get(`${scenario.id}-terminal-metric`)?.value,
    );
    setInputValue(
      `#${scenario.id}-exit-multiple`,
      byId.get(`${scenario.id}-exit-multiple`)?.value,
    );
    for (let year = 1; year <= 3; year += 1) {
      const firstFieldId = `${scenario.id}-y${year}-${FORECAST_FIELDS[0].id}`;
      const storedFirstId = firstFieldId.replaceAll("_", "-");
      setInputValue(
        `#${scenario.id}-y${year}-period`,
        byId.get(storedFirstId)?.period || `Year ${year}`,
      );
      FORECAST_FIELDS.forEach((field) => {
        const storedId = `${scenario.id}-y${year}-${field.id}`.replaceAll("_", "-");
        setInputValue(
          `#${scenario.id}-y${year}-${field.id}`,
          byId.get(storedId)?.value,
        );
      });
    }
  });
  elements.bridgeCash.value = byId.get("bridge-cash-like")?.value || "";
  elements.bridgeDebt.value = byId.get("bridge-debt-like")?.value || "";
  elements.bridgeAssets.value = byId.get("bridge-non-operating-assets")?.value || "";
  elements.bridgeClaims.value = byId.get("bridge-other-claims")?.value || "";
  elements.bridgeShares.value = byId.get("bridge-fully-diluted-shares")?.value || "";
  const storedMetric = byId.get("config-comps-metric")?.value || "ev_ltm_ebitda";
  elements.valuationCompsMetric.value = COMPS_METRICS[storedMetric]
    ? storedMetric
    : "ev_ltm_ebitda";
  elements.valuationCompsMetric.dataset.previousValue =
    elements.valuationCompsMetric.value;
  elements.valuationCompsTargetMetric.value = byId.get("target-comps-metric")?.value || "";
  elements.valuationCompsTargetPeriod.value =
    byId.get("target-comps-metric")?.period || valuation.valuation_date || "";
  for (let index = 1; index <= 5; index += 1) {
    const controls = compsPeerControls(index);
    controls.name.value = "";
    controls.classification.value = "core_peer";
    controls.rationale.value = "";
    controls.enterpriseValue.value = "";
    controls.denominator.value = "";
  }
  const peerIds = [...new Set(
    inputs.filter((item) => item.peer_id).map((item) => String(item.peer_id)),
  )].sort();
  peerIds.slice(0, 5).forEach((peerId, offset) => {
    const controls = compsPeerControls(offset + 1);
    const peerInputs = inputs.filter((item) => String(item.peer_id || "") === peerId);
    const peerFields = new Map(peerInputs.map((item) => [String(item.field || ""), item]));
    controls.name.value = valueLabel(peerInputs[0]?.peer_name, peerId);
    controls.classification.value = peerFields.get("peer_classification")?.value || "core_peer";
    controls.rationale.value = peerFields.get("peer_rationale")?.value || "";
    const currentMetric = COMPS_METRICS[elements.valuationCompsMetric.value];
    controls.enterpriseValue.value = peerFields.get(currentMetric.numeratorField)?.value || "";
    controls.denominator.value = peerFields.get(COMPS_METRICS[elements.valuationCompsMetric.value].field)?.value || "";
  });
  elements.valuationCompsMode.value = storedMetric && byId.has("config-comps-metric")
    ? "on"
    : "off";
  elements.tradingCompsInputs.open = byId.has("config-comps-metric");
  updateCompsControls();
  elements.valuationConfirmInputs.checked = false;
  elements.valuationInputReason.value = "";
}

function renderValuationStatus(version) {
  const calculation = version?.calculation || null;
  const integrity = calculation?.calculation_integrity || null;
  const readiness = calculation?.decision_readiness || null;
  elements.calculationIntegrity.textContent = integrity
    ? stateLabel(integrity.status)
    : "尚未计算";
  elements.calculationIntegrity.dataset.state = integrity?.status || "pending";
  const failedChecks = Array.isArray(integrity?.failed_check_ids)
    ? integrity.failed_check_ids
    : [];
  const warningChecks = Array.isArray(integrity?.warning_check_ids)
    ? integrity.warning_check_ids
    : [];
  elements.calculationIntegrityNote.textContent = integrity
    ? failedChecks.length
      ? `${failedChecks.length} 项计算检查未通过。`
      : warningChecks.length
        ? `${warningChecks.length} 项计算提示需复核。`
        : "服务端检查未发现计算错误。"
    : "服务端尚未生成检查结果。";

  elements.decisionReadiness.textContent = readiness
    ? stateLabel(readiness.status)
    : "尚未计算";
  elements.decisionReadiness.dataset.state = readiness?.status || "pending";
  const blockers = Array.isArray(readiness?.blocking_reasons)
    ? readiness.blocking_reasons
    : [];
  const warnings = Array.isArray(readiness?.warnings) ? readiness.warnings : [];
  elements.decisionReadinessNote.textContent = readiness
    ? blockers.length
      ? `${blockers.length} 项缺口阻止进入决策使用。`
      : warnings.length
        ? `${warnings.length} 项判断提示需人工处理。`
        : "仍需 FA 人工复核与受控批准。"
    : "必须独立完成 FA 人工复核。";
}

function valuationAmount(value, valuation, version) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  const amountInput = (version?.inputs || []).find(
    (item) => !["ratio", "multiple", "shares", "text"].includes(item.unit),
  );
  const suffix = [valuation.base_currency, amountInput?.unit]
    .filter(Boolean)
    .join(" ");
  return `${String(value)}${suffix ? ` ${suffix}` : ""}`;
}

function renderMethodResults(valuation, version) {
  elements.valuationMethodResults.replaceChildren();
  const calculation = version?.calculation;
  if (!calculation) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", null, "尚未生成方法结果"),
      node("p", null, "保存人工确认输入后，请求服务端运行计算。"),
    );
    elements.valuationMethodResults.append(empty);
    return;
  }
  const dcfResults = calculation?.methods?.dcf?.suite?.scenario_results;
  if (Array.isArray(dcfResults) && dcfResults.length) {
    const group = node("section", "method-result-group");
    group.append(node("h6", null, "Corporate FCFF DCF"));
    const grid = node("div", "scenario-results-grid");
    dcfResults.forEach((result) => {
      const article = node("article", "scenario-result");
      const scenario = String(result.scenario || "");
      const bridge = calculation?.methods?.dcf?.ev_to_equity?.[scenario] || {};
      article.append(
        node(
          "span",
          null,
          VALUATION_SCENARIOS.find((item) => item.id === scenario)?.label || scenario,
        ),
        node(
          "strong",
          null,
          valuationAmount(result.enterprise_value_perpetuity, valuation, version),
        ),
        node("small", null, "Enterprise value"),
      );
      if (bridge.equity_value !== null && bridge.equity_value !== undefined) {
        article.append(
          node(
            "p",
            null,
            `股权价值 ${valuationAmount(bridge.equity_value, valuation, version)}`,
          ),
        );
      } else {
        article.append(node("p", null, "股权价值桥接尚不完整"));
      }
      grid.append(article);
    });
    group.append(grid);
    elements.valuationMethodResults.append(group);
  }

  const compsResult = calculation?.methods?.trading_comps?.result;
  if (compsResult?.statistics) {
    const targetMetricStatus =
      calculation.methods.trading_comps.target_metric_status || "N/A";
    const group = node("section", "method-result-group comps-result-group");
    const heading = node("div", "comps-result-heading");
    heading.append(
      node("h6", null, "Trading Comps"),
      node(
        "small",
        null,
        `${valueLabel(compsResult.metric, "倍数口径未记录")} · ${formatCount(compsResult.statistics.sample_count)} 个有效样本 · 标的口径 ${targetMetricStatus}`,
      ),
    );
    const statistics = node("dl", "comps-statistics");
    [
      ["P25", compsResult.statistics.p25],
      ["Median", compsResult.statistics.median],
      ["P75", compsResult.statistics.p75],
      ["Mean", compsResult.statistics.mean],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      item.append(
        node("dt", null, label),
        node("dd", null, value === null || value === undefined ? "N/A" : `${value}x`),
      );
      statistics.append(item);
    });
    group.append(heading, statistics);
    const observations = Array.isArray(compsResult.observations)
      ? compsResult.observations
      : [];
    if (observations.length) {
      const list = node("div", "comps-observation-list");
      observations.forEach((observation) => {
        const row = node("div");
        row.append(
          node("strong", null, valueLabel(observation.peer_name, observation.peer_id)),
          node("span", null, valueLabel(observation.display_value, "N/A")),
          node(
            "small",
            null,
            observation.included_in_statistics ? "纳入样本" : valueLabel(observation.reason, "未纳入样本"),
          ),
        );
        list.append(row);
      });
      group.append(list);
    }
    elements.valuationMethodResults.append(group);
  }

  const ranges = Array.isArray(calculation.method_ranges)
    ? calculation.method_ranges
    : [];
  ranges.forEach((range) => {
    const row = node("article", "method-range-row");
    const heading = node("div");
    heading.append(
      node("strong", null, valueLabel(range.method, "估值方法")),
      node(
        "small",
        null,
        `${valueLabel(range.value_basis, "enterprise_value")} · ${valueLabel(range.range_basis, "区间依据未说明")}`,
      ),
    );
    const values = node("dl");
    [
      ["Low", range.value_low ?? range.enterprise_value_low ?? range.equity_value_low],
      ["Base", range.value_base ?? range.enterprise_value_base ?? range.equity_value_base],
      ["High", range.value_high ?? range.enterprise_value_high ?? range.equity_value_high],
    ].forEach(([label, value]) => {
      if (value === undefined) {
        return;
      }
      const item = document.createElement("div");
      item.append(
        node("dt", null, label),
        node("dd", null, valuationAmount(value, valuation, version)),
      );
      values.append(item);
    });
    row.append(heading, values);
    elements.valuationMethodResults.append(row);
  });
  if (!elements.valuationMethodResults.childElementCount) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", null, "当前方法不适用或未返回结果"),
      node("p", null, "请查看方法适用性、计算检查和决策可用性说明。"),
    );
    elements.valuationMethodResults.append(empty);
  }
}

function renderValuationChecks(version) {
  elements.valuationChecks.replaceChildren();
  const calculation = version?.calculation;
  if (!calculation) {
    return;
  }
  const groups = [
    ["硬失败", calculation.hard_failures, "danger"],
    ["计算与判断提示", calculation.warnings, "warning"],
    ["决策可用性缺口", calculation.decision_readiness?.blocking_reasons, "warning"],
    ["尚未实现", calculation.not_implemented, "neutral"],
  ];
  groups.forEach(([title, rawItems, state]) => {
    const items = Array.isArray(rawItems) ? rawItems : [];
    if (!items.length) {
      return;
    }
    const section = node("section", "valuation-check-group");
    section.dataset.state = state;
    section.append(node("h6", null, title));
    const list = document.createElement("ul");
    items.forEach((item) => list.append(node("li", null, String(item))));
    section.append(list);
    elements.valuationChecks.append(section);
  });
}

function renderValuationTrace(version) {
  elements.valuationSourceList.replaceChildren();
  elements.valuationVersionList.replaceChildren();
  const valuation = appState.currentValuation;
  const inputs = Array.isArray(version?.inputs) ? version.inputs : [];
  const sourceKeys = new Set();
  inputs.forEach((input) => {
    const key = [input.source_id, input.locator, input.as_of].join("|");
    if (sourceKeys.has(key)) {
      return;
    }
    sourceKeys.add(key);
    const item = node("article", "source-trace-item");
    item.append(
      node("strong", null, valueLabel(input.source_id, "来源未记录")),
      node("span", null, valueLabel(input.locator, "定位未记录")),
      node("small", null, `截至 ${valueLabel(input.as_of, "未记录")}`),
    );
    elements.valuationSourceList.append(item);
  });
  if (!sourceKeys.size) {
    elements.valuationSourceList.append(node("p", "trace-empty", "尚无输入来源。"));
  }

  const versions = Array.isArray(valuation?.versions) ? valuation.versions : [];
  const list = document.createElement("ol");
  list.className = "version-trace-list";
  [...versions].reverse().forEach((item) => {
    const entry = document.createElement("li");
    const top = node("div");
    top.append(
      node("strong", null, `v${String(item.version_number).padStart(4, "0")}`),
      node("span", "deal-state-label", statusLabel(item.status)),
    );
    entry.append(
      top,
      node("small", null, `${formatRecordDate(item.created_at)} · ${shortHash(item.version_hash)}`),
      node("p", null, valueLabel(item.reason, "未记录变更原因")),
    );
    list.append(entry);
  });
  elements.valuationVersionList.append(list);
}

function renderValuationWorkbench() {
  const valuation = appState.currentValuation;
  elements.valuationWorkbench.hidden = !valuation;
  if (!valuation) {
    renderDealReadiness(appState.currentDeal);
    return;
  }
  const version = latestValuationVersion(valuation);
  elements.valuationRecordId.textContent = `${valuation.valuation_id} · v${String(version?.version_number || 1).padStart(4, "0")}`;
  elements.valuationRecordTitle.textContent = valueLabel(
    valuation.target_legal_entity,
    "估值案例",
  );
  elements.valuationRecordStatus.textContent = statusLabel(valuation.status);
  elements.valuationRecordStatus.dataset.state = valuation.status || "draft";
  elements.valuationExport.hidden = !version?.calculation;
  elements.valuationExport.href = version
    ? `${valuationPath(valuation.valuation_id, "/export.xlsx")}?version_number=${encodeURIComponent(version.version_number)}`
    : "#";
  populateValuationInputForm(valuation, version);
  renderValuationStatus(version);
  renderMethodResults(valuation, version);
  renderValuationChecks(version);
  renderValuationTrace(version);
  renderDealReadiness(appState.currentDeal);

  const editable = !["approved_for_external_use", "superseded"].includes(
    valuation.status,
  );
  elements.saveValuationInputs.disabled = !editable;
  elements.calculateValuation.disabled = ![
    "inputs_incomplete",
    "calculated_screen_grade",
  ].includes(valuation.status);
  elements.reviewValuation.disabled = valuation.status !== "calculated_screen_grade";
  elements.approveValuation.disabled = valuation.status !== "fa_reviewed";
  elements.valuationInputPanel.open = ["draft", "inputs_incomplete"].includes(
    valuation.status,
  );
}

async function createDeal(event) {
  event.preventDefault();
  setMessage(elements.dealCreateError, "");
  setBusy(elements.createDeal, true, "建立中", "建立交易");
  const idempotencyScope = "create-deal";
  const body = {
    company_id: elements.dealCompanyId.value.trim(),
    buyer: elements.dealBuyer.value.trim(),
    target: elements.dealTarget.value.trim(),
    transaction_scope: elements.dealScope.value.trim(),
    currency: elements.dealCurrency.value.trim().toUpperCase(),
    valuation_date: elements.dealValuationDate.value,
    owner: elements.dealOwner.value.trim(),
    confidentiality_level: elements.dealConfidentiality.value,
    reason: elements.dealCreateReason.value.trim(),
  };
  try {
    const payload = await requestJson(API.deals, {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    const deal = payload?.deal || payload?.result || payload;
    if (!deal?.deal_id) {
      throw new Error("本地服务未返回交易 ID。");
    }
    appState.currentDeal = deal;
    appState.currentValuation = null;
    await refreshDeals({ loadSelection: false });
    await navigate("deals", { dealId: deal.deal_id });
    clearIdempotencyKey(idempotencyScope, body);
    elements.dealCreateForm.reset();
    elements.dealValuationDate.value = localDateValue();
    elements.dealCurrency.value = "CNY";
    setDealCreateOpen(false);
    announce(`已建立 ${valueLabel(deal.deal_header?.target, "交易")} 的交易工作区。`);
  } catch (error) {
    setMessage(
      elements.dealCreateError,
      errorMessage(error, "交易工作区未能建立。"),
    );
  } finally {
    setBusy(elements.createDeal, false, "", "建立交易");
  }
}

async function confirmDealStage(event) {
  event.preventDefault();
  const deal = appState.currentDeal;
  if (!deal) {
    return;
  }
  setMessage(elements.dealStageError, "");
  setBusy(elements.confirmDealStage, true, "确认中", "确认阶段");
  const idempotencyScope = `confirm-stage:${deal.deal_id}`;
  const body = {
    stage: elements.dealStageSelect.value,
    reason: elements.dealStageReason.value.trim(),
    expected_revision: deal.revision,
    expected_record_hash: deal.record_hash,
  };
  try {
    const payload = await requestJson(dealPath(deal.deal_id, "/stage"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    const updated = payload?.deal || payload?.result || payload;
    const valuationId = appState.currentValuation?.valuation_id || null;
    appState.currentDeal = updated;
    const index = appState.deals.findIndex((item) => item.deal_id === updated.deal_id);
    if (index >= 0) {
      appState.deals.splice(index, 1, updated);
    }
    selectValuation(valuationId, { updateUrl: false });
    renderDealList();
    renderDealWorkbench();
    clearIdempotencyKey(idempotencyScope, body);
    announce("交易阶段已由本地 FA 身份确认。");
  } catch (error) {
    setMessage(
      elements.dealStageError,
      errorMessage(error, "交易阶段未能确认。"),
    );
  } finally {
    setBusy(elements.confirmDealStage, false, "", "确认阶段");
  }
}

async function createValuation(event) {
  event.preventDefault();
  const deal = appState.currentDeal;
  if (!deal) {
    return;
  }
  setMessage(elements.valuationCreateError, "");
  setBusy(elements.createValuation, true, "建立中", "建立估值");
  const idempotencyScope = `create-valuation:${deal.deal_id}`;
  const body = {
    target_legal_entity: elements.valuationTargetEntity.value.trim(),
    transaction_scope: elements.valuationScope.value.trim(),
    valuation_date: elements.valuationDate.value,
    base_currency: elements.valuationCurrency.value.trim().toUpperCase(),
    methods: elements.valuationMethodPlan.value === "dcf_only"
      ? ["dcf_fcff"]
      : ["dcf_fcff", "trading_comps"],
    reason: elements.valuationCreateReason.value.trim(),
    expected_deal_revision: deal.revision,
    expected_deal_hash: deal.record_hash,
  };
  try {
    const payload = await requestJson(dealPath(deal.deal_id, "/valuations"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    const valuation = payload?.valuation || payload?.result || payload;
    if (!valuation?.valuation_id) {
      throw new Error("本地服务未返回估值 ID。");
    }
    elements.valuationCreatePanel.hidden = true;
    elements.toggleValuationCreate.setAttribute("aria-expanded", "false");
    await reloadCurrentDeal({ valuationId: valuation.valuation_id });
    window.history.replaceState(
      {},
      "",
      routeUrl("deals", {
        dealId: deal.deal_id,
        valuationId: valuation.valuation_id,
      }),
    );
    clearIdempotencyKey(idempotencyScope, body);
    announce("估值案例已建立。请录入并核对三情景输入。");
  } catch (error) {
    setMessage(
      elements.valuationCreateError,
      errorMessage(error, "估值案例未能建立。"),
    );
  } finally {
    setBusy(elements.createValuation, false, "", "建立估值");
  }
}

function valuationBridgePayload() {
  const values = {
    cash_like: elements.bridgeCash.value.trim(),
    debt_like: elements.bridgeDebt.value.trim(),
    non_operating_assets: elements.bridgeAssets.value.trim(),
    other_claims: elements.bridgeClaims.value.trim(),
    fully_diluted_shares: elements.bridgeShares.value.trim(),
  };
  return Object.values(values).some(Boolean) ? values : null;
}

async function saveValuationInputs(event) {
  event.preventDefault();
  const valuation = appState.currentValuation;
  const version = latestValuationVersion(valuation);
  if (!valuation || !version) {
    return;
  }
  setMessage(elements.valuationInputError, "");
  setBusy(elements.saveValuationInputs, true, "保存中", "保存为新版本");
  try {
    const source = {
      source_id: elements.valuationSourceId.value.trim(),
      locator: elements.valuationSourceLocator.value.trim(),
      as_of: elements.valuationSourceDate.value,
    };
    if (String(appState.currentDeal?.company_id || "").startsWith("case-")) {
      source.workspace_case_id = appState.currentDeal.company_id;
    }
    const body = {
      unit: elements.valuationUnit.value.trim(),
      confirm_inputs: elements.valuationConfirmInputs.checked,
      source,
      business_model: elements.valuationBusinessModel.value,
      discount_convention: elements.valuationDiscountConvention.value,
      scenarios: Object.fromEntries(
        VALUATION_SCENARIOS.map((scenario) => [
          scenario.id,
          scenarioPayload(scenario.id),
        ]),
      ),
      reason: elements.valuationInputReason.value.trim(),
      expected_version_number: version.version_number,
      expected_version_hash: version.version_hash,
    };
    const bridge = valuationBridgePayload();
    if (bridge) {
      body.bridge = bridge;
    }
    const tradingComps = tradingCompsPayload();
    if (tradingComps) {
      body.trading_comps = tradingComps;
    }
    const idempotencyScope = `valuation-inputs:${valuation.valuation_id}`;
    await requestJson(valuationPath(valuation.valuation_id, "/inputs"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    await reloadCurrentDeal({ valuationId: valuation.valuation_id });
    clearIdempotencyKey(idempotencyScope, body);
    announce("估值输入已保存为新的不可变版本。");
  } catch (error) {
    setMessage(
      elements.valuationInputError,
      errorMessage(error, "估值输入未能保存。"),
    );
  } finally {
    setBusy(elements.saveValuationInputs, false, "", "保存为新版本");
  }
}

async function calculateValuation(event) {
  event.preventDefault();
  const valuation = appState.currentValuation;
  const version = latestValuationVersion(valuation);
  if (!valuation || !version) {
    return;
  }
  setMessage(elements.valuationCalculateError, "");
  setBusy(elements.calculateValuation, true, "计算中", "运行计算");
  const idempotencyScope = `valuation-calculate:${valuation.valuation_id}`;
  const body = {
    reason: elements.valuationCalculateReason.value.trim(),
    expected_version_number: version.version_number,
    expected_version_hash: version.version_hash,
  };
  try {
    await requestJson(valuationPath(valuation.valuation_id, "/calculate"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    await reloadCurrentDeal({ valuationId: valuation.valuation_id });
    clearIdempotencyKey(idempotencyScope, body);
    announce("服务端计算完成。请分别检查计算完整性与决策可用性。");
  } catch (error) {
    setMessage(
      elements.valuationCalculateError,
      errorMessage(error, "服务端估值计算未完成。"),
    );
  } finally {
    setBusy(elements.calculateValuation, false, "", "运行计算");
  }
}

async function reviewValuation(event) {
  event.preventDefault();
  const valuation = appState.currentValuation;
  const version = latestValuationVersion(valuation);
  if (!valuation || !version) {
    return;
  }
  setMessage(elements.valuationReviewError, "");
  setBusy(elements.reviewValuation, true, "复核中", "完成人工复核");
  const idempotencyScope = `valuation-review:${valuation.valuation_id}`;
  const body = {
    review: {
      decision: "accepted",
      notes: elements.valuationReviewNote.value.trim(),
    },
    reason: elements.valuationReviewReason.value.trim(),
    expected_version_number: version.version_number,
    expected_version_hash: version.version_hash,
  };
  try {
    await requestJson(valuationPath(valuation.valuation_id, "/review"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    await reloadCurrentDeal({ valuationId: valuation.valuation_id });
    clearIdempotencyKey(idempotencyScope, body);
    announce("FA 人工复核已绑定当前估值版本。");
  } catch (error) {
    setMessage(
      elements.valuationReviewError,
      errorMessage(error, "FA 复核未能完成。"),
    );
  } finally {
    setBusy(elements.reviewValuation, false, "", "完成人工复核");
  }
}

async function approveValuation(event) {
  event.preventDefault();
  const valuation = appState.currentValuation;
  const version = latestValuationVersion(valuation);
  if (!valuation || !version) {
    return;
  }
  setMessage(elements.valuationApproveError, "");
  setBusy(elements.approveValuation, true, "批准中", "批准内部使用");
  const idempotencyScope = `valuation-approve-internal:${valuation.valuation_id}`;
  const body = {
    use: "internal",
    reason: elements.valuationApproveReason.value.trim(),
    expected_version_number: version.version_number,
    expected_version_hash: version.version_hash,
  };
  try {
    await requestJson(valuationPath(valuation.valuation_id, "/approve"), {
      method: "POST",
      headers: idempotencyHeaders(idempotencyScope, body),
      body,
    });
    await reloadCurrentDeal({ valuationId: valuation.valuation_id });
    clearIdempotencyKey(idempotencyScope, body);
    announce("当前版本已批准供内部交易团队使用。外部批准仍不可用。");
  } catch (error) {
    setMessage(
      elements.valuationApproveError,
      errorMessage(error, "内部批准未能完成。"),
    );
  } finally {
    setBusy(elements.approveValuation, false, "", "批准内部使用");
  }
}

function updateHealth(health) {
  appState.health = health;
  const bridgeReady = String(health?.status || "").toLowerCase() === "ok";
  const rag = health?.rag || {};
  const ragReady = rag.available === true && rag.ready_for_query === true;
  const overallState = bridgeReady && ragReady
    ? "ready"
    : bridgeReady
      ? "warning"
      : "error";
  elements.serviceStatusDot.dataset.state = overallState;
  elements.serviceStatusLabel.textContent =
    overallState === "ready"
      ? "本地服务已就绪"
      : bridgeReady
        ? "工作台在线，知识库降级"
        : "本地服务不可用";
  elements.bridgeDetail.textContent = bridgeReady
    ? "企业工作台在线"
    : "企业工作台状态异常";
  elements.ragDetail.textContent = ragReady
    ? "NEX 本地知识网关已连接"
    : String(rag.warning || "知识库暂不可查询，材料流程仍可使用");
  elements.ragDocuments.textContent = formatCount(rag.documents);
  elements.ragChunks.textContent = formatCount(rag.chunks);

  const catalog = health?.catalog || {};
  const referenceReady =
    catalog.reference_state === "ready" &&
    catalog.reference_confirmation?.state === "confirmed";
  const referenceCount = Number(catalog.reference_count);
  elements.policyReferenceCount.textContent = Number.isFinite(referenceCount)
    ? String(referenceCount)
    : "-";
  elements.catalogConfirmationLabel.textContent = referenceReady
    ? "项目方复核声明已绑定"
    : "政策参考声明未就绪";
  elements.catalogConfirmationLabel.dataset.state = referenceReady
    ? "ready"
    : "warning";
  const excluded = Number(
    catalog.reference_excluded_reason_counts?.expired || 0,
  );
  elements.policyReferenceStatus.textContent = referenceReady
    ? `${formatCount(referenceCount)} 条可用于参考建议${excluded ? `，${excluded} 条过期记录已排除` : ""}`
    : "需要与当前文件哈希一致的项目方声明后才能生成政策参考";
  elements.runPolicyReference.disabled = !referenceReady;
  elements.ragReferenceStatus.textContent = ragReady
    ? "NEX 本地知识网关已就绪"
    : "知识库暂不可用";
  elements.runRagQuery.disabled =
    !ragReady || !appState.currentCase;
}

function renderUploadQueue() {
  elements.uploadQueue.replaceChildren();
  if (appState.selectedFiles.length === 0) {
    elements.uploadQueue.append(node("p", "", "尚未选择文件"));
    return;
  }
  appState.selectedFiles.forEach((file) => {
    const row = node("div", "queue-item");
    row.append(
      node("strong", "", file.name),
      node("span", "", formatBytes(file.size)),
    );
    elements.uploadQueue.append(row);
  });
}

function setSelectedFiles(files) {
  appState.selectedFiles = Array.from(files || []);
  renderUploadQueue();
  setMessage(elements.uploadError, "");
}

async function createCase(event) {
  event.preventDefault();
  setMessage(elements.uploadError, "");
  if (appState.selectedFiles.length === 0) {
    setMessage(elements.uploadError, "请至少选择一份企业材料。");
    elements.materialFiles.focus();
    return;
  }
  const formData = new FormData();
  formData.append("case_name", elements.caseName.value.trim());
  formData.append("declared_need", elements.declaredNeed.value.trim());
  formData.append("owner", elements.caseOwner.value.trim());
  formData.append("case_type", elements.caseType.value);
  formData.append("workflow_type", elements.workflowType.value);
  appState.selectedFiles.forEach((file) => {
    formData.append("materials", file, file.name);
  });

  setBusy(elements.createCase, true, "正在本地整理", "开始整理");
  announce("正在计算材料哈希并识别工作范围。");
  try {
    const payload = await requestJson(API.cases, {
      method: "POST",
      body: formData,
    });
    appState.currentCase = null;
    appState.selectedFiles = [];
    elements.materialFiles.value = "";
    renderUploadQueue();
    await refreshDashboard();
    await navigate("case", {
      caseId: payload.case_id,
      tab: "overview",
    });
    announce(`已创建 ${payload.case_name}，正在生成资源建议。`);
    runAutomaticReferences(payload.case_id);
  } catch (error) {
    setMessage(
      elements.uploadError,
      errorMessage(error, "企业创建未完成，请检查材料后重试。"),
    );
    announce("企业创建未完成。");
  } finally {
    setBusy(elements.createCase, false, "", "开始整理");
  }
}

async function refreshDashboard() {
  try {
    appState.dashboard = await requestJson(API.dashboard);
    renderRecentCases();
    renderDashboard();
  } catch (error) {
    appState.dashboard = null;
    elements.recentList.replaceChildren();
    const message = node("div", "result-empty");
    message.append(
      node("strong", "", "无法读取本机企业"),
      node("p", "", errorMessage(error, "请确认本地 Bridge 正在运行。")),
    );
    elements.recentList.append(message);
    [
      elements.metricEnterprises,
      elements.metricCriticalGaps,
      elements.metricInterviews,
      elements.metricCases,
      elements.metricMaterials,
    ].forEach((metric) => {
      metric.textContent = "-";
    });
    elements.dashboardFreshness.textContent = "本机清单读取失败";
    elements.dashboardTruth.hidden = false;
    elements.dashboardTruth.textContent =
      "无法读取企业状态；页面不会沿用上一次结果。";
    elements.companyTableBody.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "无法读取企业，请确认本地 Bridge 正在运行。";
    row.append(cell);
    elements.companyTableBody.append(row);
    elements.companyTableEmpty.hidden = true;
  }
}

function resourceCategory(payload, kind) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const plural = RESOURCE_PLURALS[kind] || `${kind}s`;
  const candidates = [
    payload.resources?.[kind],
    payload.resources?.[plural],
    payload[kind],
    payload[plural],
  ];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      return candidate;
    }
  }
  return null;
}

function resourceCollection(payload, kind) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const category = resourceCategory(payload, kind);
  if (Array.isArray(category?.items)) {
    const primaryItems = category.items.map((item) => ({
      ...item,
      resource_layer:
        kind === "policy" ? "confirmed_reference" : "connected_catalog",
    }));
    if (kind === "policy" && Array.isArray(category?.updates?.items)) {
      const updateItems = category.updates.items.map((item) => ({
        ...item,
        resource_layer: "official_update_candidate",
      }));
      return [...primaryItems, ...updateItems];
    }
    return primaryItems;
  }
  const plural = RESOURCE_PLURALS[kind] || `${kind}s`;
  const candidates = [
    payload[plural],
    payload[kind],
    payload.resources?.[plural],
    payload.resources?.[kind],
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  const combined = Array.isArray(payload.items)
    ? payload.items
    : Array.isArray(payload.resources)
      ? payload.resources
      : null;
  if (!combined) {
    return null;
  }
  return combined.filter((item) => {
    const category = String(item?.category || item?.type || "").toLowerCase();
    return category === kind;
  });
}

function resourceCategoryStatus(payload, kind) {
  const category = resourceCategory(payload, kind);
  if (typeof category?.status === "string" && category.status.trim()) {
    return category.status.trim().toLowerCase();
  }
  return Array.isArray(resourceCollection(payload, kind)) ? "ready" : null;
}

function resourceCategoryTemplate(payload, kind) {
  const category = resourceCategory(payload, kind);
  return (
    category?.template_url ||
    payload?.template_urls?.[kind] ||
    payload?.resources?.template_urls?.[kind] ||
    null
  );
}

function topLevelResourceTemplate(payload) {
  const value = payload?.template_url || payload?.resources?.template_url;
  return typeof value === "string" ? value : null;
}

function safeExternalUrl(value, { allowRelative = false } = {}) {
  if (!value) {
    return null;
  }
  const raw = String(value).trim();
  const explicitHttp = /^https?:\/\//i.test(raw);
  if (!explicitHttp && (!allowRelative || !raw.startsWith("/"))) {
    return null;
  }
  try {
    const url = new URL(raw, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function resourceStatusCopy(status, kind) {
  const kindLabel = {
    policy: "政策",
    course: "课程",
    mentor: "导师",
  }[kind] || "资源";
  const messages = {
    not_connected: {
      title: `${kindLabel}目录尚未接入`,
      body: "本地服务尚未配置该类真实目录，不会生成演示数据。",
    },
    empty_catalog: {
      title: `${kindLabel}目录已接入，当前为空`,
      body: "真实目录已经连接，但目录中没有资源记录。",
    },
    no_eligible_entries: {
      title: "当前没有通过硬门槛的导师",
      body: "目录中没有同时满足可用性、授权、利益冲突和有效期要求的导师。",
    },
    attestation_required: {
      title: "政策目录待人工确认",
      body: "目录哈希尚未确认可用于参考，因此不展示政策条目。这不是资格认定。",
    },
    no_current_entries: {
      title: "当前没有可作参考的政策条目",
      body: "目录记录未通过当前日期筛选，仍需回到官方实时信息核验。",
    },
    no_browsable_entries: {
      title: `${kindLabel}目录没有可显示条目`,
      body: "目录已连接，但记录未满足基本身份或浏览条件。",
    },
  };
  return messages[status] || null;
}

function flattenResourceSearchValues(value, depth = 0) {
  if (value === null || value === undefined || depth > 3) {
    return [];
  }
  if (["string", "number", "boolean"].includes(typeof value)) {
    return [String(value)];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenResourceSearchValues(item, depth + 1));
  }
  if (typeof value === "object") {
    return Object.values(value).flatMap((item) =>
      flattenResourceSearchValues(item, depth + 1),
    );
  }
  return [];
}

function resourceSearchText(item) {
  if (!item || typeof item !== "object") {
    return "";
  }
  const values = [
    item.title,
    item.name,
    item.display_name,
    item.label,
    item.id,
    item.item_id,
    item.mentor_id,
    item.provider,
    item.source,
    item.review_status,
    item.effective_status,
    item.description,
    item.summary,
    item.category,
    item.type,
    item.tags,
    item.keywords,
    item.expertise_tags,
    item.industry_tags,
    item.stage_tags,
    item.geography_tags,
    item.market_tags,
    item.languages,
    item.source_reference,
  ];
  return values
    .flatMap((value) => flattenResourceSearchValues(value))
    .join(" ")
    .toLocaleLowerCase();
}

function filteredResourceCollection(payload, kind, query) {
  const items = resourceCollection(payload, kind);
  if (!Array.isArray(items) || !query) {
    return items;
  }
  return items.filter((item) => resourceSearchText(item).includes(query));
}

function configureTemplateLink(link, value, title) {
  const href = safeExternalUrl(value, { allowRelative: true });
  link.hidden = !href;
  link.removeAttribute("download");
  link.removeAttribute("target");
  link.removeAttribute("rel");
  link.removeAttribute("aria-label");
  if (!href) {
    link.removeAttribute("href");
    return false;
  }
  link.href = href;
  link.setAttribute("aria-label", title);
  const templateUrl = new URL(href);
  if (templateUrl.origin === window.location.origin) {
    link.setAttribute("download", "");
  } else {
    link.target = "_blank";
    link.rel = "noreferrer noopener";
  }
  return true;
}

function renderResourceCollection(
  target,
  kind,
  items,
  { filtered = false, status = null, templateUrl = null } = {},
) {
  target.replaceChildren();
  const categoryTemplate = node(
    "a",
    "resource-template-link",
    "下载目录模板",
  );
  if (
    configureTemplateLink(
      categoryTemplate,
      templateUrl,
      "下载该类别的资源目录模板",
    )
  ) {
    const categoryActions = node("div", "resource-category-actions");
    categoryActions.append(categoryTemplate);
    target.append(categoryActions);
  }
  const statusMessage = resourceStatusCopy(status, kind);
  if (statusMessage) {
    const statusEmpty = node("div", "resource-empty");
    statusEmpty.append(
      node("strong", "", statusMessage.title),
      node("p", "", statusMessage.body),
    );
    target.append(statusEmpty);
    if (!Array.isArray(items) || items.length === 0) {
      return;
    }
  }
  if (items === null) {
    const unavailable = node("div", "resource-empty");
    const policyReferenceReady =
      kind === "policy" &&
      appState.health?.catalog?.reference_state === "ready";
    unavailable.append(
      node(
        "strong",
        "",
        policyReferenceReady ? "目录浏览尚未接入" : "尚未接入",
      ),
      node(
        "p",
        "",
        policyReferenceReady
          ? "企业工作区仍可运行已确认目录的政策参考。"
          : "本地接口未返回该类正式目录。",
      ),
    );
    target.append(unavailable);
    return;
  }
  if (items.length === 0) {
    const empty = node("div", "resource-empty");
    empty.append(
      node(
        "strong",
        "",
        filtered ? "没有符合当前筛选的资源" : "目录已接入，当前没有可显示资源",
      ),
      node(
        "p",
        "",
        filtered ? "调整搜索词或类型筛选。" : "空结果不会被补成演示数据。",
      ),
    );
    target.append(empty);
    return;
  }
  function buildResourceItem(item) {
    const entry = node("li", "resource-item");
    const copy = node("div", "resource-item-copy");
    const title =
      item?.title ||
      item?.name ||
      item?.display_name ||
      item?.label ||
      item?.id ||
      item?.item_id ||
      item?.mentor_id ||
      "未命名资源";
    const titleLine = node("div", "resource-title-line");
    titleLine.append(node("strong", "", title));
    if (item?.simulation_only === true) {
      titleLine.append(node("span", "resource-disclosure is-synthetic", "模拟数据"));
    } else if (item?.resource_layer === "official_update_candidate") {
      titleLine.append(node("span", "resource-disclosure is-update", "更新候选"));
    }
    copy.append(titleLine);
    const reviewLabel =
      item?.simulation_only === true
        ? "仅用于模拟"
        : item?.resource_layer === "official_update_candidate"
          ? "尚未进入已确认参考库"
          : item?.review_status;
    const mentorGateLabels = {
      available: "当前可用",
      consented: "已授权用于匹配",
      clear: "冲突状态已核查",
    };
    const mentorGateLabel =
      kind === "mentor" && item?.simulation_only !== true
        ? [
            mentorGateLabels[item?.availability_status],
            mentorGateLabels[item?.consent_status],
            mentorGateLabels[item?.conflict_status],
          ]
            .filter(Boolean)
            .join(" · ")
        : null;
    const declaredSource =
      item?.simulation_only === true && kind === "mentor"
        ? "模拟导师库"
        : item?.source_reference?.declared_source;
    const metadata = [
      item?.disclosure_label,
      reviewLabel,
      item?.provider,
      item?.issuer,
      item?.source,
      declaredSource,
      mentorGateLabel,
      item?.effective_status_label_zh || item?.effective_status,
    ]
      .filter(Boolean)
      .map(String)
      .slice(0, 3)
      .join("，");
    if (metadata) {
      copy.append(node("small", "", metadata));
    }
    if (item?.summary || item?.profile_summary) {
      copy.append(
        node("p", "resource-summary", item.summary || item.profile_summary),
      );
    }
    entry.append(copy);
    const actions = node("div", "resource-item-actions");
    const href = safeExternalUrl(
      item?.source_url || item?.url || item?.source_reference?.source_url,
    );
    if (href) {
      const link = node("a", "resource-source-link", "查看来源");
      link.href = href;
      link.target = "_blank";
      link.rel = "noreferrer noopener";
      actions.append(link);
    }
    const templateLink = node("a", "resource-template-link", "下载模板");
    if (
      configureTemplateLink(
        templateLink,
        item?.template_url,
        `下载${title}模板`,
      )
    ) {
      actions.append(templateLink);
    }
    if (actions.childElementCount > 0) {
      entry.append(actions);
    }
    return entry;
  }

  const list = node("ul", "resource-item-list");
  items.slice(0, 8).forEach((item) => list.append(buildResourceItem(item)));
  target.append(list);
  if (items.length > 8) {
    const more = node("details", "resource-more");
    more.append(
      node("summary", "", `查看其余 ${items.length - 8} 条资源`),
    );
    const moreList = node("ul", "resource-item-list resource-item-list-more");
    items.slice(8).forEach((item) => moreList.append(buildResourceItem(item)));
    more.append(moreList);
    target.append(more);
  }
}

function renderResources() {
  const state = appState.resourcesState;
  const query = elements.resourceSearch.value.trim().toLocaleLowerCase();
  const requestedKind = elements.resourceTypeFilter.value;
  const selectedKind = RESOURCE_KINDS.includes(requestedKind)
    ? requestedKind
    : "all";
  const visibleKinds = RESOURCE_KINDS.filter(
    (kind) => selectedKind === "all" || selectedKind === kind,
  );
  elements.resourceRows.forEach((row) => {
    row.hidden = !visibleKinds.includes(row.dataset.resourceKind);
  });
  elements.resourceLibrary.setAttribute(
    "aria-busy",
    state === "loading" ? "true" : "false",
  );
  configureTemplateLink(
    elements.resourceTemplateDownload,
    state === "ready" ? topLevelResourceTemplate(appState.resources) : null,
    "下载资源目录模板",
  );
  if (state === "loading" || state === "idle") {
    elements.resourceFilterSummary.textContent = "";
    elements.resourcesTruth.dataset.state = "loading";
    elements.resourcesTruth.textContent = "正在检查本地资源接口";
    [
      elements.resourcePolicyList,
      elements.resourceCourseList,
      elements.resourceMentorList,
    ].forEach((target) => {
      target.replaceChildren(node("p", "resource-loading", "正在检查接口"));
    });
    return;
  }
  if (["unavailable", "error"].includes(state)) {
    elements.resourcesTruth.dataset.state = state;
    elements.resourcesTruth.textContent =
      state === "unavailable"
        ? "资源库列表接口尚未接入。政策参考仍可在企业工作区运行，课程与导师不生成占位数据。"
        : `资源库读取失败：${appState.resourcesError || "本地接口暂不可用"}`;
  } else {
    elements.resourcesTruth.dataset.state = "ready";
    elements.resourcesTruth.textContent =
      "资源接口已接入。真实政策、官方更新候选和模拟资源均以不同标签展示。";
  }
  const targets = {
    policy: elements.resourcePolicyList,
    course: elements.resourceCourseList,
    mentor: elements.resourceMentorList,
  };
  let visibleResultCount = 0;
  RESOURCE_KINDS.forEach((kind) => {
    const items = filteredResourceCollection(appState.resources, kind, query);
    if (visibleKinds.includes(kind) && Array.isArray(items)) {
      visibleResultCount += items.length;
    }
    renderResourceCollection(targets[kind], kind, items, {
      filtered: Boolean(query),
      status: resourceCategoryStatus(appState.resources, kind),
      templateUrl: resourceCategoryTemplate(appState.resources, kind),
    });
  });
  elements.resourceFilterSummary.textContent =
    state === "ready"
      ? `当前筛选显示 ${visibleResultCount} 条目录记录。模拟条目不代表真人或真实课程。`
      : "资源接口不可用，筛选不会生成替代数据。";
}

async function refreshResources() {
  appState.resourcesState = "loading";
  appState.resourcesError = null;
  renderResources();
  setBusy(elements.refreshResources, true, "正在检查", "重新检查");
  try {
    appState.resources = await requestJson(API.resources);
    appState.resourcesState = "ready";
  } catch (error) {
    appState.resources = null;
    appState.resourcesError = errorMessage(error, "本地资源接口暂不可用");
    appState.resourcesState = /404|not found|resource not found|未找到/i.test(
      appState.resourcesError,
    )
      ? "unavailable"
      : "error";
  } finally {
    renderResources();
    setBusy(elements.refreshResources, false, "", "重新检查");
  }
}

function renderRecentCases() {
  if (!appState.dashboard) {
    return;
  }
  const cases = Array.isArray(appState.dashboard.cases)
    ? appState.dashboard.cases
    : [];
  elements.recentList.replaceChildren();
  if (cases.length === 0) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", "", "还没有本地企业"),
      node("p", "", "把第一批资料拖到上方即可开始。"),
    );
    elements.recentList.append(empty);
    return;
  }
  cases.slice(0, 4).forEach((caseItem) => {
    const link = node("a", "recent-item");
    link.href = caseUrl(caseItem.case_id);
    link.dataset.caseId = caseItem.case_id;
    const copy = node("div");
    copy.append(
      node("h3", "", caseItem.case_name || "未命名企业"),
      node(
        "p",
        "",
        `${caseItem.operational_status?.label_zh || "状态未知"}，${caseItem.material_count || 0} 份材料`,
      ),
    );
    link.append(
      copy,
      node("span", "", caseItem.next_action?.label_zh || "打开"),
    );
    elements.recentList.append(link);
  });
}

function renderDashboard() {
  if (!appState.dashboard) {
    return;
  }
  const metrics = appState.dashboard.metrics || {};
  elements.metricEnterprises.textContent = formatCount(metrics.enterprise_count);
  elements.metricCriticalGaps.textContent = formatCount(
    metrics.critical_gap_company_count,
  );
  elements.metricInterviews.textContent = formatCount(
    metrics.interview_schedulable_count,
  );
  elements.metricCases.textContent = formatCount(metrics.case_count);
  elements.metricMaterials.textContent = formatCount(metrics.material_count);
  elements.dashboardFreshness.textContent =
    `本机清单读取于 ${formatDate(appState.dashboard.generated_at)}`;
  const enterpriseCount = Number(metrics.enterprise_count || 0);
  const demoCount = Number(metrics.demo_count || 0);
  const unclassifiedCount = Number(metrics.unclassified_count || 0);
  if (
    enterpriseCount === 0 &&
    (demoCount > 0 || unclassifiedCount > 0)
  ) {
    elements.dashboardTruth.hidden = false;
    const parts = [];
    if (demoCount > 0) {
      parts.push(`${demoCount} 个演示或 QA 记录`);
    }
    if (unclassifiedCount > 0) {
      parts.push(`${unclassifiedCount} 个类型待确认记录`);
    }
    elements.dashboardTruth.textContent =
      `当前记录为 ${parts.join("、")}，尚未登记真实企业；正式外部校验状态不由本看板推断。`;
  } else {
    elements.dashboardTruth.hidden = false;
    elements.dashboardTruth.textContent =
      enterpriseCount > 0
        ? `看板中的 ${enterpriseCount} 家真实企业来自用户标记，不等于正式外部验证样本。`
        : "尚无本地企业；正式外部校验状态不由本看板推断。";
  }
  filterDashboard();
}

function caseMatchesFilters(caseItem) {
  const query = elements.dashboardSearch.value.trim().toLocaleLowerCase();
  const typeFilter = elements.dashboardTypeFilter.value;
  const statusFilter = elements.dashboardStatusFilter.value;
  const isDemo = ["demo", "qa"].includes(caseItem.case_type);
  if (typeFilter === "enterprise" && caseItem.case_type !== "enterprise") {
    return false;
  }
  if (typeFilter === "demo" && !isDemo) {
    return false;
  }
  if (
    typeFilter === "unclassified" &&
    caseItem.case_type !== "unclassified"
  ) {
    return false;
  }
  if (
    statusFilter !== "all" &&
    caseItem.operational_status?.id !== statusFilter
  ) {
    return false;
  }
  if (!query) {
    return true;
  }
  const topicText = (caseItem.focus_topics || [])
    .map((topic) => topic.label_zh)
    .join(" ");
  const haystack = [
    caseItem.case_name,
    caseItem.current_need?.text,
    caseItem.owner,
    topicText,
  ]
    .join(" ")
    .toLocaleLowerCase();
  return haystack.includes(query);
}

function tableCell(label) {
  const cell = document.createElement("td");
  if (label) {
    cell.dataset.label = label;
  }
  return cell;
}

function renderCompanyRow(caseItem) {
  const row = document.createElement("tr");
  const nameCell = tableCell("企业");
  const nameBlock = node("div", "company-name-cell");
  const link = node("a", "", caseItem.case_name || "未命名企业");
  link.href = caseUrl(caseItem.case_id);
  link.dataset.caseId = caseItem.case_id;
  const typeLabel =
    caseItem.case_type === "enterprise"
      ? "真实企业"
      : caseItem.case_type === "demo"
        ? "演示"
        : caseItem.case_type === "qa"
          ? "QA"
          : "未分类";
  const type = node("small", "", typeLabel);
  type.className = "type-badge";
  nameBlock.append(link, type);
  nameCell.append(nameBlock);

  const statusCell = tableCell("状态");
  const status = node(
    "span",
    "status-badge",
    caseItem.operational_status?.label_zh || "状态未知",
  );
  status.dataset.state = caseItem.operational_status?.id || "unknown";
  const processStatus = node(
    "small",
    "process-status",
    `${caseItem.process_status?.stage_label_zh || "流程"} · ${
      caseItem.process_status?.state_label_zh || "状态未知"
    }`,
  );
  statusCell.append(status, processStatus);

  const needCell = tableCell("当前需求或关注");
  const need = node("div", "need-cell");
  need.append(
    node("span", "", caseItem.current_need?.text || "未声明"),
    node(
      "small",
      "",
      caseItem.current_need?.source === "declared_by_user"
        ? "用户声明"
        : "材料路由提示",
    ),
  );
  needCell.append(need);

  const materialCell = tableCell("材料");
  const materialSummary = node("div", "material-coverage-cell");
  const acquisition =
    caseItem.acquisition && typeof caseItem.acquisition === "object"
      ? caseItem.acquisition
      : null;
  const coveragePercent = optionalNumber(acquisition?.material_readiness_percent);
  const criticalGapCount = optionalNumber(acquisition?.critical_gap_count);
  const acquisitionNotApplicable =
    acquisition?.applicability?.status === "not_applicable";
  materialSummary.append(
    node("strong", "", `${formatCount(caseItem.material_count || 0)} 份`),
    node(
      "small",
      "",
      acquisitionNotApplicable
        ? "收购工作流不适用"
        : coveragePercent !== null
        ? `材料覆盖 ${formatCount(coveragePercent)}%`
        : "材料覆盖尚未生成",
    ),
    node(
      "small",
      "",
      acquisitionNotApplicable
        ? "不生成收购缺口"
        : criticalGapCount !== null
        ? `关键缺口 ${formatCount(criticalGapCount)}`
        : "关键缺口尚未生成",
    ),
  );
  materialCell.append(materialSummary);

  const ownerCell = tableCell("负责人");
  ownerCell.textContent = caseItem.owner || "未分配";

  const updatedCell = tableCell("更新时间");
  updatedCell.textContent = formatDate(caseItem.updated_at);

  const actionCell = tableCell("下一步");
  const action = node(
    "a",
    "action-link",
    caseItem.next_action?.label_zh || "打开企业",
  );
  action.href = caseUrl(caseItem.case_id);
  action.dataset.caseId = caseItem.case_id;
  actionCell.append(action);

  row.append(
    nameCell,
    statusCell,
    needCell,
    materialCell,
    ownerCell,
    updatedCell,
    actionCell,
  );
  return row;
}

function filterDashboard() {
  if (!appState.dashboard) {
    return;
  }
  const cases = (appState.dashboard.cases || []).filter(caseMatchesFilters);
  elements.companyTableBody.replaceChildren();
  cases.forEach((caseItem) => {
    elements.companyTableBody.append(renderCompanyRow(caseItem));
  });
  elements.companyTableEmpty.hidden = cases.length > 0;
}

function materialRoleLabel(role) {
  return ROLE_LABELS[role] || String(role || "未分类");
}

function renderMaterials(artifacts) {
  elements.materialList.replaceChildren();
  if (!artifacts.length) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", "", "当前企业没有材料"),
      node("p", "", "返回首页添加企业资料。"),
    );
    elements.materialList.append(empty);
    return;
  }
  artifacts.forEach((artifact) => {
    const recognition = artifact?.recognition || {};
    const row = node("article", "material-row");
    const suffix = String(artifact?.file_name || "")
      .split(".")
      .pop()
      .slice(0, 5);
    const glyph = node("span", "file-glyph", suffix || "file");
    const nameBlock = node("div", "material-name");
    nameBlock.append(
      node("strong", "", artifact?.file_name || "未命名材料"),
      node(
        "code",
        "",
        `${formatBytes(artifact?.byte_size)}  SHA ${String(artifact?.sha256 || "").slice(0, 16)}…`,
      ),
    );
    const roles = node("div", "role-stack");
    const candidateRoles = Array.isArray(recognition.candidate_roles)
      ? recognition.candidate_roles
      : [];
    candidateRoles.forEach((role) => {
      roles.append(node("span", "role-chip", materialRoleLabel(role)));
    });
    const recognitionState = node(
      "span",
      "recognition-state",
      recognition.status === "awaiting_human"
        ? "需要 OCR 或确认"
        : "识别范围已生成",
    );
    recognitionState.dataset.state = String(recognition.status || "unknown");
    row.append(glyph, nameBlock, roles, recognitionState);
    elements.materialList.append(row);
  });
}

function renderTopics(topics) {
  elements.caseTopicList.replaceChildren();
  if (!topics.length) {
    elements.caseTopicList.append(node("span", "topic-item", "等待材料识别"));
    return;
  }
  topics.forEach((topic) => {
    const item = node(
      "span",
      "topic-item",
      `${topic.label_zh || topic.id}  ${topic.artifact_count || 0} 份`,
    );
    elements.caseTopicList.append(item);
  });
}

function renderWorkflow(workflow) {
  elements.workflowList.replaceChildren();
  (workflow || []).forEach((step) => {
    const item = node("li", "workflow-item");
    const state = ["supplements", "review", "outputs"].includes(step.id)
      ? "not_available"
      : step.state;
    item.dataset.state = state || "unknown";
    item.append(
      node("i"),
      node("strong", "", step.label || step.id),
      node("span", "", WORKFLOW_LABELS[state] || "状态未知"),
    );
    elements.workflowList.append(item);
  });
}

function renderModules(modules) {
  elements.moduleList.replaceChildren();
  (modules || []).forEach((module) => {
    const item = node("article", "module-item");
    const copy = node("div");
    copy.append(
      node("h3", "", module.label || module.id),
      node("p", "", module.summary || "暂无说明"),
    );
    const state = node(
      "span",
      "module-state",
      MATURITY_LABELS[module.maturity] || module.maturity || "状态未知",
    );
    state.dataset.state = module.maturity || "unknown";
    item.append(copy, state);
    elements.moduleList.append(item);
  });
}

function buildRagQuestion(casePayload) {
  const topics = (casePayload.dashboard?.focus_topics || [])
    .slice(0, 3)
    .map((topic) => topic.label_zh)
    .join("、");
  const scope = topics || "企业背景与当前需求";
  return `请为“${casePayload.case_name}”检索与${scope}相关的行业、政策和尽调参考资料，并保留来源与定位。`;
}

function prefillPolicyTags(casePayload) {
  const tags = casePayload.profile_hints?.tags || {};
  TAG_DIMENSIONS.forEach((dimension) => {
    const input = elements.policyForm.elements.namedItem(dimension);
    if (input) {
      const values = Array.isArray(tags[dimension]) ? tags[dimension] : [];
      input.value = values.join("，");
    }
  });
}

function resetReferenceResults(casePayload) {
  elements.ragResults.replaceChildren();
  const ragEmpty = node("div", "result-empty");
  const activity = casePayload.reference_activity;
  if (activity) {
    ragEmpty.append(
      node("strong", "", "上次参考检索已记录"),
      node(
        "p",
        "",
        `${activity.last_result_count || 0} 条结果，${formatDate(activity.last_queried_at)}。重新运行可查看当前结果。`,
      ),
    );
    elements.ragReferenceCount.textContent =
      `${activity.last_result_count || 0} 条上次结果`;
  } else {
    ragEmpty.append(
      node("strong", "", "参考问题已准备"),
      node("p", "", "系统会在新企业创建后自动运行一次，也可以手动更新。"),
    );
    elements.ragReferenceCount.textContent = "尚未运行";
  }
  elements.ragResults.append(ragEmpty);

  elements.policyResults.replaceChildren();
  const policyEmpty = node("div", "result-empty");
  const profileTags = casePayload.profile_hints?.tags || {};
  const hasTags = Object.values(profileTags).some(
    (values) => Array.isArray(values) && values.length > 0,
  );
  policyEmpty.append(
    node(
      "strong",
      "",
      hasTags ? "已从材料读取参考标签" : "未识别到结构化政策标签",
    ),
    node(
      "p",
      "",
      hasTags
        ? "新企业会自动生成一次政策参考，也可以调整标签后更新。"
        : "展开标签区域后补充至少一个行业、技术、地区或需求标签。",
    ),
  );
  elements.policyResults.append(policyEmpty);
  elements.policyResultCount.textContent = "尚未运行";
}

function displayLabel(value) {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  if (!value || typeof value !== "object") {
    return null;
  }
  const label =
    value.label_zh ||
    value.name_zh ||
    value.title_zh ||
    value.question_zh ||
    value.label ||
    value.title ||
    value.name ||
    value.text ||
    value.id;
  return label ? String(label) : null;
}

function diagnosticStageState(value) {
  const state = String(value || "").toLowerCase();
  if (
    [
      "complete",
      "completed",
      "done",
      "accepted",
      "candidate_coverage_complete",
    ].includes(state)
  ) {
    return "complete";
  }
  if (["current", "active", "running", "in_progress"].includes(state)) {
    return "current";
  }
  if (state === "candidate_coverage_partial") {
    return "partial";
  }
  if (["blocked", "needs_revision", "rejected"].includes(state)) {
    return "blocked";
  }
  if (
    [
      "pending",
      "ready",
      "not_started",
      "queued",
      "candidate_coverage_missing",
    ].includes(state)
  ) {
    return "pending";
  }
  return "unavailable";
}

function diagnosticResourceValue(diagnostic, kind) {
  const resources =
    diagnostic?.resource_recommendations ||
    diagnostic?.resources ||
    diagnostic?.matching ||
    null;
  if (!resources || typeof resources !== "object") {
    return null;
  }
  const plural = RESOURCE_PLURALS[kind] || `${kind}s`;
  return resources[plural] ?? resources[kind] ?? null;
}

function caseResourceValue(casePayload, diagnostic, kind) {
  const recommendations = casePayload?.resource_recommendations;
  if (recommendations && typeof recommendations === "object") {
    const plural = RESOURCE_PLURALS[kind] || `${kind}s`;
    if (Object.prototype.hasOwnProperty.call(recommendations, kind)) {
      return recommendations[kind];
    }
    if (Object.prototype.hasOwnProperty.call(recommendations, plural)) {
      return recommendations[plural];
    }
  }
  return diagnosticResourceValue(diagnostic, kind);
}

function resourceRecommendationSummary(value, kind, unavailableLabel) {
  const kindLabel = {
    policy: "政策",
    course: "课程",
    mentor: "导师",
  }[kind] || "资源";
  if (typeof value === "string" && value.trim()) {
    return value === "catalog_not_supplied" ? "正式目录尚未接入" : value;
  }
  if (Array.isArray(value)) {
    return value.length === 0
      ? "当前没有候选"
      : `${value.length} 条候选，需人工确认`;
  }
  if (value && typeof value === "object") {
    const status = String(value.status || "").trim().toLowerCase();
    if (status === "not_connected") {
      return `${kindLabel}目录尚未接入`;
    }
    if (status === "empty_catalog") {
      return `${kindLabel}目录已接入，当前为空`;
    }
    if (kind === "policy") {
      const policyMessages = {
        available_for_explicit_reference_query:
          "政策参考查询可用，尚未自动检索",
        attestation_required: "政策目录待人工确认，尚未自动检索",
        no_current_entries: "当前没有可供参考的政策目录记录",
      };
      if (policyMessages[status]) {
        return policyMessages[status];
      }
    }
    if (kind === "course") {
      const matches = Array.isArray(value.matches) ? value.matches : [];
      if (matches.length > 0) {
        return `${matches.length} 条课程候选，需人工确认`;
      }
      if (status === "insufficient_profile") {
        return "当前画像标签为空，暂不生成课程候选";
      }
      if (status === "no_high_match") {
        return "当前没有达到目录标签相关性门槛的课程候选";
      }
      if (status === "matched") {
        return "当前没有课程候选";
      }
    }
    if (kind === "mentor") {
      const candidates = Array.isArray(value.candidate_matches)
        ? value.candidate_matches
        : [];
      if (candidates.length > 0) {
        return `${candidates.length} 位候选导师，未排名，需人工确认`;
      }
      if (status === "insufficient_profile") {
        return "当前画像标签为空，暂不生成导师候选";
      }
      if (status === "no_candidate_matches") {
        const eligibleCount = optionalNumber(value.summary?.eligible_rows);
        return eligibleCount === 0
          ? "当前没有通过可用性、授权、利益冲突和有效期检查的导师"
          : "当前没有与画像标签重合的导师候选";
      }
    }
    if (Array.isArray(value.matches)) {
      return value.matches.length === 0
        ? value.message || "当前没有候选"
        : `${value.matches.length} 条候选，需人工确认`;
    }
    return value.message || displayLabel(value) || unavailableLabel;
  }
  return unavailableLabel;
}

function resourceCandidateCollection(value, kind) {
  if (!value || typeof value !== "object") {
    return [];
  }
  const source = kind === "mentor" ? value.candidate_matches : value.matches;
  return Array.isArray(source) ? source : [];
}

function resourceCandidateDimensions(item, kind) {
  const dimensionLabels = {
    industry: "行业",
    stage: "企业阶段",
    need: "当前需求",
    technology: "技术",
    geography: "地区",
    market: "目标市场",
    expertise: "专业方向",
  };
  const source =
    kind === "mentor" ? item?.matched_dimensions : item?.rationale;
  if (!Array.isArray(source)) {
    return [];
  }
  return source
    .map(
      (entry) =>
        entry?.label_zh || dimensionLabels[entry?.dimension] || entry?.dimension,
    )
    .filter(Boolean)
    .map(String)
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 4);
}

function renderCompanyResourceCandidates(target, value, kind) {
  target.replaceChildren();
  const candidates = resourceCandidateCollection(value, kind);
  if (candidates.length === 0) {
    target.append(
      node(
        "li",
        "company-candidate-empty",
        resourceRecommendationSummary(
          value,
          kind,
          kind === "mentor" ? "导师目录尚未接入" : "课程目录尚未接入",
        ),
      ),
    );
    return;
  }
  candidates.slice(0, 3).forEach((item) => {
    const entry = node("li", "company-candidate-item");
    const titleLine = node("div", "company-candidate-title");
    titleLine.append(
      node(
        "strong",
        "",
        item?.title || item?.display_name || item?.item_id || item?.mentor_id,
      ),
    );
    if (item?.simulation_only === true) {
      titleLine.append(node("span", "resource-disclosure is-synthetic", "模拟数据"));
    }
    entry.append(titleLine);
    const detail = item?.summary || item?.profile_summary;
    if (detail) {
      entry.append(node("p", "company-candidate-summary", String(detail)));
    }
    const dimensions = resourceCandidateDimensions(item, kind);
    if (dimensions.length > 0) {
      const dimensionList = node("div", "company-candidate-dimensions");
      dimensions.forEach((dimension) =>
        dimensionList.append(node("span", "", dimension)),
      );
      entry.append(dimensionList);
    }
    const disclosure = item?.disclosure_label;
    if (disclosure) {
      entry.append(node("small", "company-candidate-disclosure", disclosure));
    }
    const href = safeExternalUrl(
      item?.source_url || item?.source_reference?.source_url,
    );
    if (href) {
      const sourceLink = node("a", "resource-source-link", "查看来源");
      sourceLink.href = href;
      sourceLink.target = "_blank";
      sourceLink.rel = "noreferrer noopener";
      entry.append(sourceLink);
    }
    target.append(entry);
  });
  if (candidates.length > 3) {
    target.append(
      node(
        "li",
        "company-candidate-more",
        `另有 ${candidates.length - 3} 条候选，可在资源页检索。`,
      ),
    );
  }
}

function renderAcquisitionStages(diagnostic) {
  if (diagnostic?.applicability?.status === "not_applicable") {
    elements.acquisitionStageTrack.replaceChildren();
    const item = node("li", "acquisition-stage");
    item.dataset.state = "unavailable";
    item.append(
      node("span", "stage-index", "—"),
      node("strong", "", "未启用跨境收购八阶段"),
    );
    elements.acquisitionStageTrack.append(item);
    return;
  }
  const stageSources = [
    diagnostic?.stages,
    diagnostic?.stage_progress,
    diagnostic?.stage_diagnostics,
    diagnostic?.progress?.stages,
    diagnostic?.pipeline,
  ];
  const suppliedStages = stageSources.find(Array.isArray) || [];
  const firstIncompleteIndex = suppliedStages.findIndex(
    (stage) => stage?.coverage_status !== "candidate_coverage_complete",
  );
  const currentStage = displayLabel(
    diagnostic?.current_stage ||
      diagnostic?.current_stage_label ||
      (firstIncompleteIndex >= 0 ? suppliedStages[firstIncompleteIndex] : null),
  );
  elements.acquisitionStageTrack.replaceChildren();
  for (let index = 0; index < 8; index += 1) {
    const stage = suppliedStages[index] || null;
    const label = displayLabel(stage);
    const item = node("li", "acquisition-stage");
    let state = diagnosticStageState(
      stage?.state || stage?.status || stage?.coverage_status,
    );
    if (stage?.coverage_status && index === firstIncompleteIndex) {
      state = "current";
    }
    if (
      state === "unavailable" &&
      label &&
      currentStage &&
      label === currentStage
    ) {
      state = "current";
    }
    item.dataset.state = diagnostic ? state : "unavailable";
    item.append(
      node("span", "stage-index", String(index + 1).padStart(2, "0")),
      node("strong", "", label || "未返回"),
    );
    elements.acquisitionStageTrack.append(item);
  }
}

function renderKeyQuestions(diagnostic) {
  const rawQuestions =
    diagnostic?.key_questions ||
    diagnostic?.questions ||
    diagnostic?.interview_questions ||
    null;
  const questions = Array.isArray(rawQuestions) ? rawQuestions.slice(0, 8) : [];
  elements.keyQuestionList.replaceChildren();
  elements.keyQuestionCount.textContent = `${questions.length} / 8`;
  if (diagnostic?.applicability?.status === "not_applicable") {
    elements.keyQuestionList.append(
      node("li", "question-empty", "企业首包整理不生成买方或交易问题。"),
    );
    return;
  }
  if (!diagnostic || !Array.isArray(rawQuestions)) {
    const empty = node("li", "question-empty", "准备度诊断尚未生成关键问题。");
    elements.keyQuestionList.append(empty);
    return;
  }
  if (questions.length === 0) {
    elements.keyQuestionList.append(
      node("li", "question-empty", "当前诊断没有返回关键问题。"),
    );
    return;
  }
  questions.forEach((question) => {
    elements.keyQuestionList.append(
      node("li", "", displayLabel(question) || "问题内容未返回"),
    );
  });
}

function financialBasisValue(value) {
  if (value && typeof value === "object") {
    return [value.label, value.start, value.end].filter(Boolean).join(" / ") ||
      "结构化候选";
  }
  return String(value || "未说明");
}

function renderEvidenceControlDiagnostic(casePayload) {
  const diagnostic =
    casePayload?.evidence_control_diagnostic &&
    typeof casePayload.evidence_control_diagnostic === "object"
      ? casePayload.evidence_control_diagnostic
      : null;
  const applicable = diagnostic?.applicability?.status === "applicable";
  elements.evidenceControlSignals.replaceChildren();
  if (!applicable) {
    elements.evidenceControlState.textContent = diagnostic ? "不适用" : "尚未生成";
    elements.evidenceControlState.dataset.state = "unavailable";
    elements.evidenceControlSummary.textContent = diagnostic
      ? "未检测到明示的清单、文档控制、重复索引或结构化回复。"
      : "正在读取清单、实际哈希与版本控制字段。";
    elements.evidenceControlSignals.append(
      node("li", "question-empty", "系统没有从自由正文或文件名推断证据权威。"),
    );
    elements.evidenceControlResponses.textContent = "";
    return diagnostic;
  }

  const integrity = diagnostic?.integrity_gate?.status || "not_declared";
  const reconciliation = diagnostic?.manifest_reconciliation || {};
  const statusCounts = reconciliation?.status_counts || {};
  const actualDuplicates = Array.isArray(
    diagnostic?.actual_payload_duplicate_groups,
  )
    ? diagnostic.actual_payload_duplicate_groups
    : [];
  const declaredDuplicates = Array.isArray(
    diagnostic?.declared_underlying_candidate_groups,
  )
    ? diagnostic.declared_underlying_candidate_groups
    : [];
  const families = Array.isArray(diagnostic?.document_control_families)
    ? diagnostic.document_control_families
    : [];
  const selectionFamilies = families.filter(
    (family) => family?.requires_human_selection === true,
  );
  const conflicts = Array.isArray(diagnostic?.structured_conflicts)
    ? diagnostic.structured_conflicts
    : [];
  const questions = Array.isArray(diagnostic?.questions)
    ? diagnostic.questions
    : [];
  const receipts = Array.isArray(diagnostic?.candidate_response_receipts)
    ? diagnostic.candidate_response_receipts
    : [];
  const quarantined = Array.isArray(reconciliation?.quarantined_artifact_ids)
    ? reconciliation.quarantined_artifact_ids
    : [];

  elements.evidenceControlState.textContent =
    integrity === "blocked"
      ? "输入完整性阻断"
      : questions.length
        ? "待人工复核"
        : "候选控制已整理";
  elements.evidenceControlState.dataset.state =
    integrity === "blocked" ? "unavailable" : "available";
  elements.evidenceControlSummary.textContent =
    `${questions.length} 个控制问题；${quarantined.length} 份材料处于隔离。` +
    " 系统未自动修正哈希、选择权威版本或解决冲突。";

  const signalRows = [
    [
      "清单核验",
      `matched ${statusCounts.matched || 0} · mismatch ${statusCounts.mismatch || 0}`,
    ],
    [
      "重复候选",
      `实际字节组 ${actualDuplicates.length} · 底层声明组 ${declaredDuplicates.length}`,
    ],
    ["版本与权威", `${selectionFamilies.length} 个 family 等待人工选择`],
    ["显式结构冲突", `${conflicts.length} 项 unresolved`],
  ];
  signalRows.forEach(([label, value]) => {
    const item = node("li");
    item.append(node("strong", "", label), node("span", "", value));
    elements.evidenceControlSignals.append(item);
  });
  elements.evidenceControlResponses.textContent = receipts.length
    ? `已记录 ${receipts.length} 个候选回复回执；均未自动接受为事实或关闭问题。`
    : "尚未收到结构化问题回复；上传材料不会自动关闭问题。";
  return diagnostic;
}

function renderContentAuthorizationDiagnostic(casePayload) {
  const diagnostic =
    casePayload?.authorization_diagnostic &&
    typeof casePayload.authorization_diagnostic === "object"
      ? casePayload.authorization_diagnostic
      : null;
  const applicable = diagnostic?.applicability?.status === "applicable";
  elements.contentAuthorizationPermissions.replaceChildren();
  if (!applicable) {
    elements.contentAuthorizationState.textContent = diagnostic
      ? "不适用"
      : "尚未生成";
    elements.contentAuthorizationState.dataset.state = "unavailable";
    elements.contentAuthorizationSummary.textContent = diagnostic
      ? "未检测到 CSV、JSON 或 JSONL 明示的内容使用授权字段。"
      : "正在读取结构化授权、内容使用请求与 authority 边界。";
    elements.contentAuthorizationPermissions.append(
      node("li", "question-empty", "系统没有从 Markdown、访谈或营销正文推断许可。"),
    );
    elements.contentAuthorizationRequests.textContent = "";
    return diagnostic;
  }

  const matrix = Array.isArray(diagnostic?.permission_matrix)
    ? diagnostic.permission_matrix
    : [];
  const questions = Array.isArray(diagnostic?.questions)
    ? diagnostic.questions
    : [];
  const requests = Array.isArray(diagnostic?.content_use_requests)
    ? diagnostic.content_use_requests
    : [];
  const blockedRequests = requests.filter((request) => request?.blocked === true);
  const conflicts = Array.isArray(diagnostic?.override_conflicts)
    ? diagnostic.override_conflicts
    : [];
  const receipts = Array.isArray(diagnostic?.candidate_response_receipts)
    ? diagnostic.candidate_response_receipts
    : [];
  const blocked = diagnostic?.authorization_status?.status === "blocked";
  elements.contentAuthorizationState.textContent = blocked
    ? "授权阻断"
    : "待人工复核";
  elements.contentAuthorizationState.dataset.state = blocked
    ? "unavailable"
    : "available";
  elements.contentAuthorizationSummary.textContent =
    `${questions.length} 个授权问题；${blockedRequests.length} 个请求保持 blocked；` +
    `${conflicts.length} 个无 authority override candidate 已隔离。`;

  const statusLabels = {
    expired: "已过期",
    active_scoped_grant: "限域有效候选",
    denied: "已拒绝",
    limited: "有限授权候选",
    mixed_scope_control: "分范围授权 / 拒绝并存",
    missing: "缺失 / 未授权",
    not_yet_effective: "尚未生效",
    unrecognized: "状态无法识别",
  };
  matrix.forEach((permission) => {
    const item = node("li");
    item.append(
      node("strong", "", permission?.label_zh || permission?.permission || "权限"),
      node(
        "span",
        "",
        `${statusLabels[permission?.status] || permission?.status || "未知"} · ` +
          `${permission?.candidate_count || 0} 个未核验候选`,
      ),
    );
    elements.contentAuthorizationPermissions.append(item);
  });
  elements.contentAuthorizationRequests.textContent =
    `诊断时点 ${diagnostic?.diagnostic_as_of || "未说明"}。` +
    `候选回复 ${receipts.length} 个；未自动接受、关闭问题、发布、翻译或生成 AI 媒体。`;
  return diagnostic;
}

function renderFinancialBasisPreflight(casePayload) {
  const diagnostic =
    casePayload?.financial_basis_preflight &&
    typeof casePayload.financial_basis_preflight === "object"
      ? casePayload.financial_basis_preflight
      : null;
  const applicable = diagnostic?.applicability?.status === "applicable";
  elements.financialBasisDimensions.replaceChildren();
  if (!applicable) {
    elements.financialBasisState.textContent = diagnostic ? "不适用" : "尚未生成";
    elements.financialBasisState.dataset.state = "unavailable";
    elements.financialBasisSummary.textContent = diagnostic
      ? "未检测到 CSV/JSON 明示的财务口径元数据。"
      : "正在读取结构化财务口径。";
    elements.financialBasisDimensions.append(
      node("li", "question-empty", "没有从自由正文或文件名推断财务口径。"),
    );
    elements.financialBasisResponses.textContent = "";
    return diagnostic;
  }

  const calculationStatus = diagnostic?.calculation_status?.status;
  const questions = Array.isArray(diagnostic?.questions)
    ? diagnostic.questions
    : [];
  elements.financialBasisState.textContent =
    calculationStatus === "blocked" ? "计算已阻断" : "待人工复核";
  elements.financialBasisState.dataset.state =
    calculationStatus === "blocked" ? "unavailable" : "available";
  elements.financialBasisSummary.textContent =
    `${questions.length} 个口径问题；系统未选择最新、最大或名称相近的候选值。`;

  const dimensionLabels = {
    entity_scope: "主体范围",
    component_entity: "组成主体",
    reporting_period: "报告期间",
    currency: "币种",
    unit: "单位",
    vat_basis: "VAT 口径",
    cash_as_of: "现金时点",
    cash_restriction: "现金限制",
    cash_availability: "现金可用性",
  };
  Object.entries(diagnostic?.dimensions || {}).forEach(([key, dimension]) => {
    const candidates = Array.isArray(dimension?.candidates)
      ? dimension.candidates.map((item) => financialBasisValue(item?.value))
      : [];
    const item = node("li");
    item.append(
      node("strong", "", dimensionLabels[key] || key),
      node(
        "span",
        "",
        `${dimension?.status || "unknown"}：${candidates.join("；") || "未说明"}`,
      ),
    );
    elements.financialBasisDimensions.append(item);
  });
  const receipts = Array.isArray(diagnostic?.candidate_response_receipts)
    ? diagnostic.candidate_response_receipts
    : [];
  elements.financialBasisResponses.textContent = receipts.length
    ? `已收到 ${receipts.length} 个候选回复映射；均未自动接受或关闭问题。`
    : "尚未收到显式 question_id 补件映射。";
  renderKeyQuestions(diagnostic);
  return diagnostic;
}

function renderAcquisitionDiagnostic(casePayload) {
  const diagnostic =
    casePayload?.acquisition_diagnostic &&
    typeof casePayload.acquisition_diagnostic === "object"
      ? casePayload.acquisition_diagnostic
      : null;
  const completenessPercent = optionalNumber(diagnostic?.completeness?.percent);
  const acquisitionNotApplicable =
    diagnostic?.applicability?.status === "not_applicable";
  elements.acquisitionState.textContent =
    acquisitionNotApplicable
      ? "跨境收购工作流不适用"
      : diagnostic && completenessPercent !== null
      ? `候选材料覆盖 ${formatCount(completenessPercent)}%`
      : diagnostic
        ? "候选材料覆盖已生成"
        : "尚未生成";
  elements.acquisitionState.dataset.state = acquisitionNotApplicable
    ? "unavailable"
    : diagnostic
      ? "available"
      : "unavailable";
  renderAcquisitionStages(diagnostic);

  const currentStage = displayLabel(
    diagnostic?.current_stage ||
      diagnostic?.current_stage_label ||
      (Array.isArray(diagnostic?.stage_diagnostics)
        ? diagnostic.stage_diagnostics.find(
            (stage) =>
              stage?.coverage_status !== "candidate_coverage_complete",
          ) || diagnostic.stage_diagnostics.at(-1)
        : null),
  );
  elements.acquisitionCurrentStage.textContent = acquisitionNotApplicable
    ? "不适用"
    : currentStage || "尚未生成";

  const rawGaps =
    diagnostic?.material_gaps ??
    diagnostic?.key_material_gaps ??
    diagnostic?.critical_gaps ??
    null;
  const gaps = Array.isArray(rawGaps) ? rawGaps : null;
  elements.acquisitionGapCount.textContent = acquisitionNotApplicable
    ? "不适用"
    : gaps
    ? `${gaps.length} 项`
    : "尚未生成";
  elements.acquisitionGapSummary.textContent = acquisitionNotApplicable
    ? "未显式选择跨境收购工作流，不生成伪缺口。"
    : gaps
    ? gaps
        .slice(0, 2)
        .map((gap) => displayLabel(gap))
        .filter(Boolean)
        .join("；") || "当前未返回缺口说明"
    : "";

  const interview =
    diagnostic?.interview_recommendation ||
    diagnostic?.business_model_interview_readiness ||
    diagnostic?.interview ||
    null;
  const recommendation =
    typeof diagnostic?.interview_recommended === "boolean"
      ? diagnostic.interview_recommended
      : typeof interview?.recommended === "boolean"
        ? interview.recommended
        : null;
  elements.acquisitionInterview.textContent =
    displayLabel(interview) ||
    (recommendation === true
      ? "建议安排"
      : recommendation === false
        ? "当前不建议"
        : "尚未生成");
  elements.acquisitionInterviewReason.textContent =
    displayLabel(
      interview?.basis_zh || interview?.reason || diagnostic?.interview_reason,
    ) || "";

  renderKeyQuestions(diagnostic);
  elements.companyPolicyResources.textContent = resourceRecommendationSummary(
    caseResourceValue(casePayload, diagnostic, "policy"),
    "policy",
    diagnostic ? "尚未生成" : "尚未生成",
  );
  elements.companyCourseResources.textContent = resourceRecommendationSummary(
    caseResourceValue(casePayload, diagnostic, "course"),
    "course",
    "尚未接入",
  );
  elements.companyMentorResources.textContent = resourceRecommendationSummary(
    caseResourceValue(casePayload, diagnostic, "mentor"),
    "mentor",
    "尚未接入",
  );
  renderCompanyResourceCandidates(
    elements.companyCourseCandidateList,
    caseResourceValue(casePayload, diagnostic, "course"),
    "course",
  );
  renderCompanyResourceCandidates(
    elements.companyMentorCandidateList,
    caseResourceValue(casePayload, diagnostic, "mentor"),
    "mentor",
  );
  return diagnostic;
}

function renderCaseLoadingState() {
  elements.caseTypeBadge.textContent = "企业";
  elements.caseIdLabel.textContent = "记录载入中";
  elements.caseTitle.textContent = "正在载入企业";
  elements.caseNeed.textContent = "正在读取当前需求";
  elements.caseNeedSource.textContent = "";
  elements.caseStatus.textContent = "正在载入";
  elements.caseOwnerLabel.textContent = "-";
  elements.caseMaterialCount.textContent = "-";
  elements.caseUpdatedAt.textContent = "-";
  elements.nextActionTitle.textContent = "正在读取下一步";
  elements.nextActionReason.textContent = "";
  elements.caseTopicList.replaceChildren(
    node("span", "topic-item", "正在读取识别主题"),
  );
  elements.workflowList.replaceChildren(
    node("li", "workflow-item loading-row", "正在读取内部流程"),
  );
  elements.materialList.replaceChildren(
    node("div", "result-empty", "正在读取企业材料"),
  );
  elements.moduleList.replaceChildren(
    node("div", "result-empty", "正在读取能力边界"),
  );
  renderAcquisitionDiagnostic({});
  renderEvidenceControlDiagnostic({});
  renderFinancialBasisPreflight({});
}

function renderCase(casePayload) {
  appState.currentCase = casePayload;
  const summary = casePayload.dashboard || {};
  const artifacts = Array.isArray(casePayload.artifacts)
    ? casePayload.artifacts
    : [];
  const isEnterprise = casePayload.case_type === "enterprise";
  elements.caseTypeBadge.textContent = isEnterprise
    ? "企业"
    : casePayload.case_type === "qa"
      ? "QA 记录"
      : casePayload.case_type === "demo"
        ? "演示记录"
        : "未分类记录";
  elements.caseIdLabel.textContent =
    `${casePayload.case_id || "记录编号未知"}  rev ${casePayload.revision || "-"}`;
  elements.caseTitle.textContent = casePayload.case_name || "未命名企业";
  elements.caseNeed.textContent =
    summary.current_need?.text || "当前需求尚未声明";
  elements.caseNeedSource.textContent =
    summary.current_need?.source === "declared_by_user"
      ? "用户声明"
      : "材料路由提示，不代表已验证事实";
  elements.caseStatus.textContent =
    summary.operational_status?.label_zh || "状态未知";
  elements.caseOwnerLabel.textContent = summary.owner || "未分配";
  elements.caseMaterialCount.textContent = `${artifacts.length} 份`;
  elements.caseUpdatedAt.textContent = formatDate(casePayload.updated_at);
  const diagnostic = renderAcquisitionDiagnostic(casePayload);
  renderEvidenceControlDiagnostic(casePayload);
  renderContentAuthorizationDiagnostic(casePayload);
  renderFinancialBasisPreflight(casePayload);
  const diagnosticNextAction =
    displayLabel(diagnostic?.next_action) || diagnostic?.next_action_label;
  elements.nextActionTitle.textContent =
    summary.next_action?.label_zh || diagnosticNextAction || "查看资源建议";
  elements.nextActionReason.textContent =
    summary.operational_status?.id === "materials_need_processing"
      ? "至少一份材料无法提取文本，需要 OCR 或确认。"
      : summary.next_action?.id === "review_evidence_control_questions"
        ? "声明哈希、重复材料、版本权威或显式结构冲突需要人工复核。"
      : summary.next_action?.id === "review_content_authorization"
        ? "内容使用请求受到过期、拒绝、缺失、有限范围或无 authority 候选的约束。"
      : summary.next_action?.id === "review_financial_basis_questions"
        ? "主体、期间、单位、税基、现金或预测口径需要人工确认。"
        : "材料已归档，可以查看知识库与政策参考。";
  elements.nextActionButton.textContent =
    summary.next_action?.id === "review_evidence_control_questions"
      ? "查看证据控制"
      : summary.next_action?.id === "review_content_authorization"
      ? "查看授权控制"
      : summary.next_action?.id === "review_financial_basis_questions"
      ? "查看口径问题"
      : summary.operational_status?.id === "reference_search_run"
      ? "更新资源建议"
      : "查看资源建议";
  renderTopics(summary.focus_topics || []);
  renderWorkflow(casePayload.workflow || []);
  renderMaterials(artifacts);
  renderModules(casePayload.modules || []);
  elements.ragQuestion.disabled = false;
  elements.ragQuestion.value = buildRagQuestion(casePayload);
  elements.runRagQuery.disabled =
    appState.health?.rag?.ready_for_query !== true;
  prefillPolicyTags(casePayload);
  resetReferenceResults(casePayload);
}

async function loadCase(caseId) {
  const payload = await requestJson(`${API.cases}/${encodeURIComponent(caseId)}`);
  renderCase(payload);
}

function setCaseTab(rawTab) {
  const available = new Set(
    elements.casePanels.map((panel) => panel.dataset.casePanel),
  );
  const tab = available.has(rawTab) ? rawTab : "overview";
  elements.casePanels.forEach((panel) => {
    panel.hidden = panel.dataset.casePanel !== tab;
  });
  elements.caseTabs.forEach((link) => {
    if (link.dataset.caseTab === tab) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function evidenceTitle(item) {
  return String(
    item?.source ||
      item?.title ||
      item?.metadata?.title ||
      item?.metadata?.source_title ||
      "未命名来源",
  );
}

function evidenceClaim(item) {
  return String(
    item?.claim ||
      item?.snippet ||
      item?.metadata?.snippet ||
      "该参考结果没有可展示的摘录。",
  );
}

function evidenceLocator(item) {
  return String(item?.locator || item?.metadata?.locator || "定位未提供");
}

function renderRagReferences(result) {
  const evidence = Array.isArray(result?.evidence) ? result.evidence : [];
  const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
  elements.ragResults.replaceChildren();
  elements.ragReferenceCount.textContent = `${evidence.length} 条参考`;
  const summary = node(
    "div",
    "reference-summary",
    evidence.length
      ? `找到 ${evidence.length} 条带来源的参考资料。`
      : "本次没有找到满足来源要求的参考资料。",
  );
  elements.ragResults.append(summary);
  evidence.forEach((item) => {
    const article = node("article", "reference-item");
    article.append(
      node("h4", "", evidenceTitle(item)),
      node("p", "", evidenceClaim(item)),
    );
    const meta = node("div", "reference-meta");
    meta.append(
      node("span", "", evidenceLocator(item)),
      node("span", "", "知识库参考"),
    );
    article.append(meta);
    elements.ragResults.append(article);
  });
  if (!evidence.length) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", "", "零命中也是有效结果"),
      node(
        "p",
        "",
        "可以调整问题、补充材料，或对时效性问题进行官方实时检索。",
      ),
    );
    elements.ragResults.append(empty);
  }
  warnings.forEach((warning) => {
    elements.ragResults.append(
      node("div", "reference-warning", String(warning)),
    );
  });
}

async function executeRagReference({ automatic = false } = {}) {
  if (!appState.currentCase) {
    throw new Error("请先载入企业。");
  }
  const question = elements.ragQuestion.value.trim();
  if (!question) {
    throw new Error("请填写参考问题。");
  }
  setMessage(elements.ragError, "");
  setBusy(
    elements.runRagQuery,
    true,
    automatic ? "正在自动检索" : "正在检索",
    "更新知识库建议",
  );
  elements.ragReferenceCount.textContent = "正在整理";
  try {
    const result = await requestJson(
      `${API.cases}/${encodeURIComponent(appState.currentCase.case_id)}/rag-query`,
      {
        method: "POST",
        body: {
          question,
          mode: "hybrid",
          purpose: "industry_background",
          top_k: 5,
        },
      },
    );
    renderRagReferences(result);
    await refreshDashboard();
    return result;
  } finally {
    setBusy(
      elements.runRagQuery,
      false,
      "",
      "更新知识库建议",
    );
  }
}

async function runRagQuery(event) {
  event.preventDefault();
  try {
    const result = await executeRagReference();
    const count = Array.isArray(result?.evidence) ? result.evidence.length : 0;
    announce(`知识库参考已更新，共 ${count} 条。`);
  } catch (error) {
    setMessage(
      elements.ragError,
      errorMessage(error, "知识库参考未完成。"),
    );
  }
}

function splitTags(rawValue) {
  return Array.from(
    new Set(
      String(rawValue || "")
        .split(/[,，;；\n]+/)
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  );
}

function collectPolicyPayload() {
  const profileTags = {};
  let tagCount = 0;
  TAG_DIMENSIONS.forEach((dimension) => {
    const input = elements.policyForm.elements.namedItem(dimension);
    const tags = splitTags(input?.value);
    profileTags[dimension] = tags;
    tagCount += tags.length;
  });
  if (tagCount === 0) {
    throw new Error("请至少提供一个行业、阶段、技术、地区或需求标签。");
  }
  if (!elements.policyAsOf.value) {
    throw new Error("请选择参考日期。");
  }
  return {
    profile_tags: profileTags,
    as_of: elements.policyAsOf.value,
  };
}

function renderPolicyReferences(result) {
  const suggestions = Array.isArray(result?.suggestions)
    ? result.suggestions
    : [];
  elements.policyResults.replaceChildren();
  elements.policyResultCount.textContent = `${suggestions.length} 条参考`;
  elements.companyPolicyResources.textContent = suggestions.length
    ? `${suggestions.length} 条参考，需人工确认`
    : "当前没有高相关候选";
  elements.policyResults.append(
    node(
      "div",
      "reference-summary",
      result?.message || `返回 ${suggestions.length} 条政策参考建议。`,
    ),
  );
  suggestions.forEach((suggestion) => {
    const item = node("article", "reference-item");
    item.append(
      node("h4", "", suggestion.title || suggestion.item_id || "未命名政策"),
    );
    const matchedTags = (suggestion.rationale || [])
      .flatMap((reason) => reason.matched_tags || [])
      .join("、");
    item.append(
      node(
        "p",
        "",
        matchedTags
          ? `相关标签：${matchedTags}`
          : "该条目达到当前相关性阈值。",
      ),
    );
    const meta = node("div", "reference-meta");
    meta.append(
      node(
        "span",
        "",
        `${suggestion.source_sheet || "政策库"} 第 ${suggestion.source_row || "-"} 行`,
      ),
      node("span", "", "需回到官方原文确认"),
    );
    item.append(meta);
    elements.policyResults.append(item);
  });
  if (!suggestions.length) {
    const empty = node("div", "result-empty");
    empty.append(
      node("strong", "", "当前标签没有高相关建议"),
      node("p", "", "可以调整识别标签，不会自动扩展成硬推荐。"),
    );
    elements.policyResults.append(empty);
  }
}

async function executePolicyReference({ automatic = false } = {}) {
  const payload = collectPolicyPayload();
  setMessage(elements.policyError, "");
  setBusy(
    elements.runPolicyReference,
    true,
    automatic ? "正在自动匹配" : "正在匹配",
    "更新政策建议",
  );
  elements.policyResultCount.textContent = "正在整理";
  try {
    const result = await requestJson(API.policyReferences, {
      method: "POST",
      body: payload,
    });
    renderPolicyReferences(result);
    return result;
  } finally {
    setBusy(
      elements.runPolicyReference,
      false,
      "",
      "更新政策建议",
    );
  }
}

async function runPolicyReference(event) {
  event.preventDefault();
  try {
    const result = await executePolicyReference();
    const count = Array.isArray(result?.suggestions)
      ? result.suggestions.length
      : 0;
    announce(`政策参考已更新，共 ${count} 条。`);
  } catch (error) {
    setMessage(
      elements.policyError,
      errorMessage(error, "政策参考未完成。"),
    );
  }
}

function hasPolicyTags() {
  return TAG_DIMENSIONS.some((dimension) => {
    const input = elements.policyForm.elements.namedItem(dimension);
    return splitTags(input?.value).length > 0;
  });
}

async function runAutomaticReferences(caseId) {
  if (
    appState.automaticReferenceCase === caseId ||
    appState.currentCase?.case_id !== caseId
  ) {
    return;
  }
  appState.automaticReferenceCase = caseId;
  const tasks = [];
  if (appState.health?.rag?.ready_for_query === true) {
    tasks.push(
      executeRagReference({ automatic: true })
        .then(() => true)
        .catch((error) => {
          setMessage(
            elements.ragError,
            errorMessage(error, "知识库自动参考未完成，可稍后手动更新。"),
          );
          return false;
        }),
    );
  }
  if (
    appState.health?.catalog?.reference_state === "ready" &&
    hasPolicyTags()
  ) {
    tasks.push(
      executePolicyReference({ automatic: true })
        .then(() => true)
        .catch((error) => {
          setMessage(
            elements.policyError,
            errorMessage(error, "政策自动参考未完成，可稍后手动更新。"),
          );
          return false;
        }),
    );
  }
  const taskResults = await Promise.all(tasks);
  const completedCount = taskResults.filter(Boolean).length;
  if (appState.currentCase?.case_id === caseId) {
    await refreshDashboard();
    const summary = (appState.dashboard?.cases || []).find(
      (item) => item.case_id === caseId,
    );
    if (summary) {
      elements.caseStatus.textContent =
        summary.operational_status?.label_zh || "状态未知";
      elements.nextActionTitle.textContent =
        summary.next_action?.label_zh || "查看资源建议";
      elements.nextActionButton.textContent = "更新资源建议";
    }
    setCaseTab("suggestions");
    window.history.replaceState(
      {},
      "",
      routeUrl("case", { caseId, tab: "suggestions" }),
    );
    if (tasks.length === 0) {
      announce("当前没有可自动运行的参考源，请查看页面状态。");
    } else if (completedCount === tasks.length) {
      announce("自动参考建议已整理完成。");
    } else if (completedCount > 0) {
      announce("部分参考建议已完成，未完成项已标明原因。");
    } else {
      announce("自动参考建议未完成，页面已保留具体原因。");
    }
  }
}

async function openSuggestionsAndRun() {
  if (!appState.currentCase) {
    return;
  }
  await navigate("case", {
    caseId: appState.currentCase.case_id,
    tab: "suggestions",
  });
  appState.automaticReferenceCase = null;
  runAutomaticReferences(appState.currentCase.case_id);
}

async function handleNextAction() {
  if (
    appState.currentCase?.dashboard?.next_action?.id ===
    "review_evidence_control_questions"
  ) {
    setCaseTab("overview");
    elements.evidenceControlState.closest("section")?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
    return;
  }
  if (
    appState.currentCase?.dashboard?.next_action?.id ===
    "review_financial_basis_questions"
  ) {
    setCaseTab("overview");
    elements.financialBasisState.closest("section")?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
    return;
  }
  if (
    appState.currentCase?.dashboard?.next_action?.id ===
    "review_content_authorization"
  ) {
    setCaseTab("overview");
    elements.contentAuthorizationState.closest("section")?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
    return;
  }
  await openSuggestionsAndRun();
}

function activeCompanyWorkspaceCaseId() {
  const route = currentRoute();
  return route.view === "case" && route.caseId ? route.caseId : null;
}

function consentUsesCaseScope(scopes = selectedConsentScopes()) {
  return scopes.some((scope) => CASE_CONSENT_SCOPES.includes(scope));
}

function updateConsentProgress() {
  const capabilityCount = capabilityCheckboxes.filter(
    (checkbox) => checkbox.checked,
  ).length;
  const actorPresent = elements.consentActor.value.trim().length > 0;
  const acknowledged = boundaryCheckbox.checked;
  const policyMatchSelected =
    document.querySelector("#allow-candidate-match").checked;
  const policyReferenceSelected =
    document.querySelector("#allow-policy-reference").checked;
  const policyReadSelected =
    document.querySelector("#allow-policy-read").checked;
  const materialReadSelected =
    document.querySelector("#allow-material-read").checked;
  const caseReadSelected = document.querySelector("#allow-case-read").checked;
  const ragQuerySelected = document.querySelector("#allow-rag-query").checked;
  const resourceReadSelected = document.querySelector("#allow-resource-read").checked;
  const resourceMatchSelected = document.querySelector("#allow-resource-match").checked;
  const dependencyValid =
    (!(policyMatchSelected || policyReferenceSelected) ||
      policyReadSelected) &&
    (!resourceMatchSelected || resourceReadSelected) &&
    (!materialReadSelected || caseReadSelected);
  const needsCompanyWorkspace =
    !appState.pendingAuthorization &&
    (caseReadSelected || materialReadSelected || ragQuerySelected);
  const companyContextValid =
    !needsCompanyWorkspace || Boolean(activeCompanyWorkspaceCaseId());
  if (!companyContextValid) {
    elements.consentProgress.dataset.state = "attention";
    elements.consentProgress.textContent =
      "请先进入一家企业，再授权企业、材料或 RAG 能力。";
  } else {
    elements.consentProgress.dataset.state = "ready";
    elements.consentProgress.textContent =
      `${capabilityCount} 项能力已选择，${acknowledged ? "边界已确认" : "边界待确认"}`;
  }
  elements.grantConsent.disabled =
    capabilityCount === 0 ||
    !actorPresent ||
    !acknowledged ||
    !dependencyValid ||
    !companyContextValid;
}

function selectedConsentScopes() {
  return Object.entries(SCOPE_INPUTS)
    .filter(([, selector]) => document.querySelector(selector).checked)
    .map(([scope]) => scope);
}

function configureAuthorizationRequest(request) {
  appState.pendingAuthorization = request || null;
  allConsentCheckboxes.forEach((checkbox) => {
    checkbox.checked = false;
  });
  if (!request) {
    elements.authorizationRequestContext.hidden = true;
    elements.consentActor.disabled = false;
    capabilityCheckboxes.forEach((checkbox) => {
      checkbox.disabled = false;
    });
    elements.openConsent.textContent = "Agent 访问";
    elements.grantConsent.textContent = "授权本次会话";
    elements.consentDescription.textContent =
      "权限只保存在当前服务内存中，最长 30 分钟，可随时撤销。";
    updateConsentProgress();
    return;
  }
  elements.authorizationRequestContext.hidden = false;
  elements.authorizationRequestActor.textContent =
    request.actor || "未命名 Agent";
  elements.authorizationRequestPurpose.textContent =
    request.purpose || "未说明用途";
  elements.authorizationRequestCase.textContent =
    request.case_id || "未绑定企业记录";
  elements.consentActor.value = request.actor || "Agent";
  elements.consentActor.disabled = true;
  const requested = new Set(request.requested_scopes || []);
  Object.entries(SCOPE_INPUTS).forEach(([scope, selector]) => {
    const checkbox = document.querySelector(selector);
    checkbox.disabled = !requested.has(scope);
  });
  elements.openConsent.textContent = "审核 Agent 请求";
  elements.grantConsent.textContent = "批准所选权限";
  elements.consentDescription.textContent =
    "这是 Agent 发起、用户批准、Agent 一次性交换令牌的本地握手。";
  updateConsentProgress();
}

async function refreshAuthorizationRequests({ autoOpen = false } = {}) {
  try {
    const payload = await requestJson(API.authorizationRequests);
    const requests = Array.isArray(payload?.requests) ? payload.requests : [];
    configureAuthorizationRequest(requests[0] || null);
    if (autoOpen && requests.length > 0 && !elements.consentDialog.open) {
      elements.consentDialog.showModal();
      window.requestAnimationFrame(() => boundaryCheckbox.focus());
    }
  } catch {
    configureAuthorizationRequest(null);
  }
}

async function openConsentDialog() {
  await refreshAuthorizationRequests();
  setMessage(elements.consentError, "");
  if (!elements.consentDialog.open) {
    elements.consentDialog.showModal();
  }
  const focusTarget = appState.pendingAuthorization
    ? capabilityCheckboxes.find((checkbox) => !checkbox.disabled)
    : elements.consentActor;
  window.requestAnimationFrame(() => focusTarget?.focus());
}

function closeConsentDialog() {
  if (elements.consentDialog.open) {
    elements.consentDialog.close();
  }
}

function updateAuthorizationView() {
  const authorized = Boolean(appState.accessToken);
  elements.openConsent.hidden = authorized;
  elements.revokeConsent.hidden = !authorized;
}

async function grantConsent(event) {
  event.preventDefault();
  updateConsentProgress();
  const selectedScopes = selectedConsentScopes();
  const legacyCaseId = activeCompanyWorkspaceCaseId();
  if (
    !appState.pendingAuthorization &&
    consentUsesCaseScope(selectedScopes) &&
    !legacyCaseId
  ) {
    setMessage(
      elements.consentError,
      "请先关闭授权窗口并进入一家企业，再授权企业、材料或 RAG 能力。",
    );
    return;
  }
  if (elements.grantConsent.disabled) {
    setMessage(
      elements.consentError,
      "请选择至少一项能力，确认 Agent 边界，并满足权限依赖。",
    );
    return;
  }
  setBusy(elements.grantConsent, true, "正在授权", "授权本次会话");
  try {
    if (appState.pendingAuthorization) {
      const request = appState.pendingAuthorization;
      const result = await requestJson(
        `${API.authorizationRequests}/${encodeURIComponent(request.request_id)}/decision`,
        {
          method: "POST",
          body: {
            approve: true,
            approved_scopes: selectedConsentScopes(),
            acknowledge_human_review: boundaryCheckbox.checked,
          },
        },
      );
      appState.pendingAuthorization = null;
      elements.consentDialog.close();
      configureAuthorizationRequest(null);
      elements.openConsent.textContent = "Agent 请求已批准";
      announce(
        `${result.actor || "Agent"} 的请求已批准，等待 Agent 交换令牌。`,
      );
      return;
    }
    const payload = await requestJson(API.consent, {
      method: "POST",
      body: {
        actor: elements.consentActor.value.trim(),
        allow_case_read: document.querySelector("#allow-case-read").checked,
        allow_material_read: document.querySelector("#allow-material-read").checked,
        allow_rag_query: document.querySelector("#allow-rag-query").checked,
        allow_resource_read: document.querySelector("#allow-resource-read").checked,
        allow_resource_match: document.querySelector("#allow-resource-match").checked,
        allow_policy_read: document.querySelector("#allow-policy-read").checked,
        allow_policy_reference: document.querySelector(
          "#allow-policy-reference",
        ).checked,
        allow_candidate_match: document.querySelector("#allow-candidate-match")
          .checked,
        acknowledge_human_review: boundaryCheckbox.checked,
        case_id: consentUsesCaseScope(selectedScopes) ? legacyCaseId : null,
      },
    });
    if (!payload?.token) {
      throw new Error("授权响应没有包含短期令牌。");
    }
    appState.accessToken = payload.token;
    appState.tokenExpiresAt = payload.expires_at || null;
    elements.consentDialog.close();
    updateAuthorizationView();
    announce("本地 Agent 已获得所选短期权限。");
  } catch (error) {
    setMessage(elements.consentError, errorMessage(error, "授权未完成。"));
  } finally {
    setBusy(
      elements.grantConsent,
      false,
      "",
      appState.pendingAuthorization ? "批准所选权限" : "授权本次会话",
    );
    updateConsentProgress();
  }
}

async function declineConsent() {
  if (appState.pendingAuthorization) {
    const request = appState.pendingAuthorization;
    try {
      await requestJson(
        `${API.authorizationRequests}/${encodeURIComponent(request.request_id)}/decision`,
        {
          method: "POST",
          body: {
            approve: false,
            approved_scopes: [],
            acknowledge_human_review: false,
          },
        },
      );
      announce(`${request.actor || "Agent"} 的访问请求已拒绝。`);
    } catch (error) {
      setMessage(
        elements.consentError,
        errorMessage(error, "访问请求拒绝操作未完成。"),
      );
      return;
    }
    appState.pendingAuthorization = null;
    configureAuthorizationRequest(null);
  }
  closeConsentDialog();
}

async function revokeConsent() {
  if (!appState.accessToken) {
    return;
  }
  elements.revokeConsent.disabled = true;
  try {
    await requestJson(API.revoke, {
      method: "POST",
      authorized: true,
      body: {},
    });
    appState.accessToken = null;
    appState.tokenExpiresAt = null;
    allConsentCheckboxes.forEach((checkbox) => {
      checkbox.checked = false;
    });
    updateConsentProgress();
    updateAuthorizationView();
    announce("Agent 访问已撤销。");
  } catch (error) {
    announce(errorMessage(error, "Agent 访问撤销未完成。"));
  } finally {
    elements.revokeConsent.disabled = false;
  }
}

function wireDragAndDrop() {
  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.dataset.dragging = "true";
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropZone.dataset.dragging = "false";
    });
  });
  elements.dropZone.addEventListener("drop", (event) => {
    setSelectedFiles(event.dataTransfer?.files || []);
  });
}

function shouldHandleInternalNavigation(event, link) {
  const destination = new URL(link.href, window.location.href);
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey &&
    !link.hasAttribute("download") &&
    (!link.target || link.target === "_self") &&
    destination.origin === window.location.origin
  );
}

function wireRouting() {
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const routeLink = event.target.closest("a[data-route]");
    if (routeLink && shouldHandleInternalNavigation(event, routeLink)) {
      event.preventDefault();
      navigate(routeLink.dataset.route);
      return;
    }
    const caseLink = event.target.closest("a[data-case-id]");
    if (caseLink && shouldHandleInternalNavigation(event, caseLink)) {
      event.preventDefault();
      navigate("case", {
        caseId: caseLink.dataset.caseId,
        tab: "overview",
      });
      return;
    }
    const dealLink = event.target.closest("a[data-deal-id]");
    if (dealLink && shouldHandleInternalNavigation(event, dealLink)) {
      event.preventDefault();
      navigate("deals", { dealId: dealLink.dataset.dealId });
      return;
    }
    const valuationButton = event.target.closest("button[data-valuation-id]");
    if (valuationButton) {
      selectValuation(valuationButton.dataset.valuationId);
    }
  });
  elements.caseTabs.forEach((link) => {
    link.addEventListener("click", (event) => {
      if (!shouldHandleInternalNavigation(event, link)) {
        return;
      }
      event.preventDefault();
      const tab = link.dataset.caseTab;
      if (!appState.currentCase) {
        return;
      }
      window.history.pushState(
        {},
        "",
        routeUrl("case", {
          caseId: appState.currentCase.case_id,
          tab,
        }),
      );
      setCaseTab(tab);
    });
  });
  window.addEventListener("popstate", () => {
    renderRoute({ focus: true });
  });
}

async function bootstrap() {
  const healthPromise = requestJson(API.health)
    .then((payload) => updateHealth(payload))
    .catch((error) => {
      elements.serviceStatusDot.dataset.state = "error";
      elements.serviceStatusLabel.textContent = "本地服务不可用";
      elements.bridgeDetail.textContent = "无法读取工作台状态";
      elements.ragDetail.textContent = errorMessage(
        error,
        "请确认本地 Bridge 正在运行。",
      );
    });
  const manifestPromise = requestJson(API.manifest).then((payload) => {
    appState.manifest = payload;
  });
  const dashboardPromise = requestJson(API.dashboard).then((payload) => {
    appState.dashboard = payload;
    renderRecentCases();
    renderDashboard();
    fillCompanyOptions();
  });
  await Promise.allSettled([manifestPromise, dashboardPromise]);
  await renderRoute();
  await refreshAuthorizationRequests({ autoOpen: true });
  await healthPromise;
}

function wireEvents() {
  elements.materialFiles.addEventListener("change", (event) => {
    setSelectedFiles(event.target.files);
  });
  elements.uploadForm.addEventListener("submit", createCase);
  elements.ragQueryForm.addEventListener("submit", runRagQuery);
  elements.policyForm.addEventListener("submit", runPolicyReference);
  elements.nextActionButton.addEventListener("click", handleNextAction);
  elements.dashboardSearch.addEventListener("input", filterDashboard);
  elements.dashboardTypeFilter.addEventListener("change", filterDashboard);
  elements.dashboardStatusFilter.addEventListener("change", filterDashboard);
  elements.toggleDealCreate.addEventListener("click", () => {
    setDealCreateOpen(elements.dealCreatePanel.hidden);
  });
  elements.closeDealCreate.addEventListener("click", () => {
    setDealCreateOpen(false);
    elements.toggleDealCreate.focus();
  });
  elements.dealCreateForm.addEventListener("submit", createDeal);
  elements.dealSearch.addEventListener("input", renderDealList);
  elements.refreshDeals.addEventListener("click", async () => {
    setBusy(elements.refreshDeals, true, "刷新中", "刷新");
    await refreshDeals();
    setBusy(elements.refreshDeals, false, "", "刷新");
  });
  elements.dealStageForm.addEventListener("submit", confirmDealStage);
  elements.toggleValuationCreate.addEventListener("click", () => {
    const open = elements.valuationCreatePanel.hidden;
    elements.valuationCreatePanel.hidden = !open;
    elements.toggleValuationCreate.setAttribute(
      "aria-expanded",
      open ? "true" : "false",
    );
    if (open) {
      window.requestAnimationFrame(() => elements.valuationTargetEntity.focus());
    }
  });
  elements.valuationCreateForm.addEventListener("submit", createValuation);
  elements.valuationInputForm.addEventListener("submit", saveValuationInputs);
  elements.valuationCompsMode.addEventListener("change", updateCompsControls);
  elements.valuationCompsMetric.addEventListener("change", () => {
    const previous = elements.valuationCompsMetric.dataset.previousValue;
    if (previous && previous !== elements.valuationCompsMetric.value) {
      for (let index = 1; index <= 5; index += 1) {
        const controls = compsPeerControls(index);
        controls.enterpriseValue.value = "";
        controls.denominator.value = "";
      }
    }
    elements.valuationCompsMetric.dataset.previousValue =
      elements.valuationCompsMetric.value;
    updateCompsControls();
  });
  elements.valuationCompsBody.addEventListener("change", (event) => {
    if (event.target instanceof HTMLSelectElement) {
      updateCompsControls();
    }
  });
  elements.valuationCalculateForm.addEventListener("submit", calculateValuation);
  elements.valuationReviewForm.addEventListener("submit", reviewValuation);
  elements.valuationApproveForm.addEventListener("submit", approveValuation);
  elements.refreshResources.addEventListener("click", refreshResources);
  elements.resourceSearch.addEventListener("input", renderResources);
  elements.resourceTypeFilter.addEventListener("change", renderResources);
  elements.serviceStatus.addEventListener("click", () => {
    const open = elements.servicePopover.hidden;
    elements.servicePopover.hidden = !open;
    elements.serviceStatus.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("click", (event) => {
    if (
      !elements.servicePopover.hidden &&
      !elements.servicePopover.contains(event.target) &&
      !elements.serviceStatus.contains(event.target)
    ) {
      elements.servicePopover.hidden = true;
      elements.serviceStatus.setAttribute("aria-expanded", "false");
    }
  });
  elements.openConsent.addEventListener("click", openConsentDialog);
  elements.revokeConsent.addEventListener("click", revokeConsent);
  elements.closeConsent.addEventListener("click", closeConsentDialog);
  elements.declineConsent.addEventListener("click", declineConsent);
  elements.consentForm.addEventListener("submit", grantConsent);
  elements.consentActor.addEventListener("input", updateConsentProgress);
  allConsentCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", updateConsentProgress);
  });
  wireDragAndDrop();
  wireRouting();
}

function initialize() {
  elements.policyAsOf.value = localDateValue();
  elements.dealValuationDate.value = localDateValue();
  elements.valuationDate.value = localDateValue();
  elements.valuationSourceDate.value = localDateValue();
  buildScenarioInputs();
  buildTradingCompsRows();
  elements.valuationCompsMetric.dataset.previousValue =
    elements.valuationCompsMetric.value;
  renderUploadQueue();
  updateConsentProgress();
  updateAuthorizationView();
  wireEvents();
  bootstrap();
}

initialize();
