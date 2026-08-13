window.ADMIN_PANELS = ["overview", "resources", "reports", "users", "sessions", "plans", "plan-features", "models", "extended-models", "image-generation", "features", "system-prompts", "search-engines", "coupons", "subscription", "paypal", "google-oauth", "discord-oauth", "mail-server", "system-keys"];
const PLAN_IDS = ["free", "plus", "pro", "pro_plus", "max", "enterprise"];
const PAYMENT_STATUSES = [
  { value: "paid", label: "支払済" },
  { value: "pending", label: "保留" },
  { value: "refunded", label: "返金" },
  { value: "failed", label: "失敗" },
];
const PAYMENT_METHODS = [
  { value: "PayPal", label: "PayPal（チャージ）" },
  { value: "残高", label: "残高（プラン購入）" },
  { value: "クーポン", label: "クーポン" },
  { value: "管理者", label: "管理者調整" },
  { value: "銀行振込", label: "銀行振込" },
  { value: "その他", label: "その他" },
];
const BILLING_KIND_LABELS = {
  paypal_subscription: "PayPalサブスク",
  balance: "残高プラン",
  admin_grant: "管理者付与",
  entitlement: "プラン枠",
  legacy_plan: "レガシー",
  free: "無料",
};
const ENTITLEMENT_SOURCE_LABELS = {
  paypal: "PayPal",
  balance: "残高",
  coupon: "クーポン",
  admin: "管理者",
  legacy: "レガシー",
};

function formatBalanceJpy(amount) {
  const value = Math.round(Number(amount) || 0);
  return `¥${value.toLocaleString("ja-JP")}`;
}

function formatBalanceInteger(amount) {
  return formatBalanceJpy(amount);
}

const adminNavItems = document.querySelectorAll(".admin-nav-item");
const adminUsersLoading = document.getElementById("adminUsersLoading");
const adminUsersError = document.getElementById("adminUsersError");
const adminUsersTableWrap = document.getElementById("adminUsersTableWrap");
const adminUsersBody = document.getElementById("adminUsersBody");
const adminUsersEmpty = document.getElementById("adminUsersEmpty");
const adminUsersSearch = document.getElementById("adminUsersSearch");
const adminUsersFilterPlan = document.getElementById("adminUsersFilterPlan");
const adminUsersFilterBilling = document.getElementById("adminUsersFilterBilling");
const adminUsersFilterStatus = document.getElementById("adminUsersFilterStatus");
const adminUsersStats = document.getElementById("adminUsersStats");
const adminUsersListView = document.getElementById("adminUsersListView");
const adminUserDetailView = document.getElementById("adminUserDetailView");
const adminUserDetailBack = document.getElementById("adminUserDetailBack");
const adminUserDetailLoading = document.getElementById("adminUserDetailLoading");
const adminUserDetailError = document.getElementById("adminUserDetailError");
const adminUserDetailForm = document.getElementById("adminUserDetailForm");
const adminUserDetailMsg = document.getElementById("adminUserDetailMsg");
const detailPaymentsBody = document.getElementById("detailPaymentsBody");
const detailPaymentAdd = document.getElementById("detailPaymentAdd");
const detailBillingEventsBody = document.getElementById("detailBillingEventsBody");
const detailBillingEventsLoad = document.getElementById("detailBillingEventsLoad");
const detailBillingEventsCount = document.getElementById("detailBillingEventsCount");
const detailDeleteUser = document.getElementById("detailDeleteUser");
const adminPlansListView = document.getElementById("adminPlansListView");
const adminPlansBody = document.getElementById("adminPlansBody");
const adminPlanDetailView = document.getElementById("adminPlanDetailView");
const adminPlanDetailBack = document.getElementById("adminPlanDetailBack");
const adminPlanDetailLoading = document.getElementById("adminPlanDetailLoading");
const adminPlanDetailError = document.getElementById("adminPlanDetailError");
const adminPlanDetailForm = document.getElementById("adminPlanDetailForm");
const adminPlanDetailMsg = document.getElementById("adminPlanDetailMsg");
const adminPlanFeaturesLoading = document.getElementById("adminPlanFeaturesLoading");
const adminPlanFeaturesError = document.getElementById("adminPlanFeaturesError");
const adminPlanFeaturesForm = document.getElementById("adminPlanFeaturesForm");
const adminPlanFeaturesGroups = document.getElementById("adminPlanFeaturesGroups");
const adminPlanFeaturesMsg = document.getElementById("adminPlanFeaturesMsg");
const adminFeaturesForm = document.getElementById("adminFeaturesForm");
const adminFeaturesMsg = document.getElementById("adminFeaturesMsg");
const adminModelsForm = document.getElementById("adminModelsForm");
const adminModelsMsg = document.getElementById("adminModelsMsg");
const adminModelsList = document.getElementById("adminModelsList");
const adminModelsPeriod = document.getElementById("adminModelsPeriod");
const adminModelsActive = document.getElementById("adminModelsActive");
const adminModelsTotals = document.getElementById("adminModelsTotals");
const adminModelsChartRange = document.getElementById("adminModelsChartRange");
const adminModelsChartModel = document.getElementById("adminModelsChartModel");
const adminModelsChartRefresh = document.getElementById("adminModelsChartRefresh");
const adminModelsChartMeta = document.getElementById("adminModelsChartMeta");
const adminModelsChartTotals = document.getElementById("adminModelsChartTotals");
const adminModelsChartCanvas = document.getElementById("adminModelsChart");
const adminApiActiveBody = document.getElementById("adminApiActiveBody");
const adminApiLogBody = document.getElementById("adminApiLogBody");
const adminApiLiveStatus = document.getElementById("adminApiLiveStatus");
const adminProvidersFields = document.getElementById("adminProvidersFields");
const adminModelAddForm = document.getElementById("adminModelAddForm");
const adminModelAddMsg = document.getElementById("adminModelAddMsg");
const addModelProvider = document.getElementById("addModelProvider");
const adminDefaultModel = document.getElementById("adminDefaultModel");
const adminUserCreateForm = document.getElementById("adminUserCreateForm");
const adminUserCreateMsg = document.getElementById("adminUserCreateMsg");
const createPlanSelect = document.getElementById("createPlan");

let adminState = null;
let usersFilterQuery = "";
let planFeaturesState = null;
let currentDetailUser = null;
let currentDetailPlan = null;
let modelUsageChart = null;
let modelChartRefreshTimer = null;
let apiDashboardTimer = null;

const RESOURCE_POLL_MS = 5000;
const RESOURCE_HISTORY_MAX = 60;
let resourceTimer = null;
const resourceHistory = {
  cpu: [],
  mem: [],
  netRecv: [],
  netSent: [],
  labels: [],
};
const resourceCharts = {};

function showAdminMsg(el, text, isError) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden", "success", "error");
  el.classList.add(isError ? "error" : "success");
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toLocaleDateString("ja-JP");
}

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return `${iso}T23:59`;
    return "";
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatUsage(user) {
  const cost = Number(user.usage?.usage_cost_usd ?? 0);
  const budget = user.monthly_ai_budget_usd;
  const costStr = `$${cost.toFixed(4)}`;
  if (budget == null) {
    return `${costStr} / 無制限`;
  }
  const pct =
    user.usage_percent != null
      ? ` (${Number(user.usage_percent).toFixed(1)}%)`
      : "";
  return `${costStr} / $${Number(budget).toFixed(2)}${pct}`;
}

function formatEntitlementBudget(value) {
  if (value == null) return "無制限";
  return `$${Number(value).toFixed(2)}`;
}

function renderEntitlementRows(entitlements) {
  const body = document.getElementById("detailEntitlementsBody");
  if (!body) return;
  const list = Array.isArray(entitlements) ? entitlements : [];
  if (!list.length) {
    body.innerHTML =
      '<tr><td colspan="5" class="admin-table-empty">有効なプラン枠はありません</td></tr>';
    return;
  }
  body.innerHTML = list
    .map((ent) => {
      const plan = escapeHtml(ent.plan_id || "—");
      const qty = Number(ent.quantity) || 1;
      const budget = formatEntitlementBudget(ent.budget_usd);
      const expires = escapeHtml(ent.expires_at || "継続");
      const source = escapeHtml(formatEntitlementSource(ent.source));
      return `<tr>
        <td>${plan}</td>
        <td>×${qty}</td>
        <td>${escapeHtml(budget)}</td>
        <td>${expires}</td>
        <td>${source}</td>
      </tr>`;
    })
    .join("");
}

function parseAdminHash(hash) {
  const raw = (hash || "#overview").replace(/^#/, "");
  if (raw.startsWith("user/")) {
    return {
      panel: "users",
      username: decodeURIComponent(raw.slice(5)),
      planId: null,
    };
  }
  if (raw.startsWith("plan/")) {
    return {
      panel: "plans",
      username: null,
      planId: decodeURIComponent(raw.slice(5)),
    };
  }
  const panel = window.ADMIN_PANELS.includes(raw) ? raw : "overview";
  return { panel, username: null, planId: null };
}

function parseAdminUserHash(hash) {
  return parseAdminHash(hash);
}

function adminUserPath(username) {
  return username ? `/admin#user/${encodeURIComponent(username)}` : "/admin#users";
}

function adminPlanPath(planId) {
  return planId ? `/admin#plan/${encodeURIComponent(planId)}` : "/admin#plans";
}

function formatPlanLimit(value) {
  return value == null ? "無制限" : Number(value).toLocaleString();
}

function formatPlanBudget(value) {
  if (value == null) return "無制限";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toFixed(2)}`;
}

function showAdminPanel(panelId, options = {}) {
  const { syncUrl = true, adminUser = null, adminPlan = null } = options;
  if (!window.ADMIN_PANELS.includes(panelId)) panelId = "overview";
  document.documentElement.setAttribute("data-admin-panel", panelId);
  adminNavItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.panel === panelId);
  });

  if (panelId === "overview") {
    loadDeploymentOverview();
    loadServiceUrlsSettings();
    startDeploymentHealthRefresh();
  } else {
    stopDeploymentHealthRefresh();
  }
  if (panelId === "coupons") {
    loadCoupons();
  }
  if (panelId === "subscription") {
    loadSubscriptionSettings();
  }
  if (panelId === "search-engines") {
    loadSearchEnginesSettings();
  }
  if (panelId === "paypal") {
    loadPaypalSettings();
  }
  if (panelId === "google-oauth") {
    loadGoogleOauthSettings();
  }
  if (panelId === "discord-oauth") {
    loadDiscordOauthSettings();
  }
  if (panelId === "mail-server") {
    loadMailServerSettings();
  }
  if (panelId === "plan-features") {
    loadPlanFeatures();
  }
  if (panelId === "system-prompts") {
    loadSystemPrompts();
  }
  if (panelId === "system-keys") {
    loadSystemKeysSettings();
  }
  if (panelId === "models") {
    renderModels(adminState?.models);
    startModelChartRefresh();
    startApiDashboard();
    // パネル表示後にチャートをリサイズ（非表示中にサイズ0で描画された場合の対策）
    if (modelUsageChart) {
      setTimeout(() => modelUsageChart.resize(), 60);
    }
  } else {
    stopModelChartRefresh();
    stopApiDashboard();
  }
  if (panelId === "extended-models") {
    renderExtendedModels(adminState?.extended_models);
  }
  if (panelId === "image-generation") {
    renderImageGeneration(adminState?.image_generation);
  }
  if (panelId === "sessions") {
    startAdminSessionsMonitor();
  } else {
    stopAdminSessionsMonitor();
  }
  if (panelId === "resources") {
    startResourceMonitor();
  } else {
    stopResourceMonitor();
  }
  if (panelId === "reports") {
    loadAdminReports();
  }

  if (panelId !== "users" && adminUser) {
    closeUserDetail({ syncUrl: false });
  }
  if (panelId !== "plans" && adminPlan) {
    closePlanDetail({ syncUrl: false });
  }
  if (panelId === "users" && adminPlan) {
    closePlanDetail({ syncUrl: false });
  }
  if (panelId === "plans" && adminUser) {
    closeUserDetail({ syncUrl: false });
  }

  if (!syncUrl) return;
  let path = "/admin#overview";
  if (panelId === "users" && adminUser) path = adminUserPath(adminUser);
  else if (panelId === "plans" && adminPlan) path = adminPlanPath(adminPlan);
  else if (panelId !== "users") path = `/admin#${panelId}`;

  if (location.pathname === "/admin" || location.pathname === "/admin/") {
    if (location.pathname + location.hash !== path) {
      history.replaceState(history.state, "", path);
    }
  }
}

adminNavItems.forEach((item) => {
  item.addEventListener("click", () => {
    closeUserDetail({ syncUrl: false });
    closePlanDetail({ syncUrl: false });
    showAdminPanel(item.dataset.panel);
  });
});

async function fetchAdminState() {
  const res = await fetch("/api/admin/state");
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
  adminState = data;
  return data;
}

async function fetchUserDetail(username) {
  const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
  return data.user;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, "&#39;");
}

function billingKindBadge(user) {
  const billing = user.billing || {};
  const kind = billing.kind || "free";
  const label = billing.label || BILLING_KIND_LABELS[kind] || kind;
  return `<span class="admin-billing-badge admin-billing-badge--${escapeAttr(kind)}">${escapeHtml(label)}</span>`;
}

function formatEntitlementSource(source) {
  const key = String(source || "").trim();
  return ENTITLEMENT_SOURCE_LABELS[key] || key || "—";
}

function userMatchesFilters(user) {
  const q = usersFilterQuery.trim().toLowerCase();
  if (q) {
    const hay = [
      user.username,
      user.display_name,
      user.full_name,
      user.email,
    ]
      .map((v) => String(v || "").toLowerCase())
      .join(" ");
    if (!hay.includes(q)) return false;
  }
  const planFilter = adminUsersFilterPlan?.value || "";
  if (planFilter && user.plan !== planFilter) return false;
  const billingFilter = adminUsersFilterBilling?.value || "";
  if (billingFilter && (user.billing?.kind || "free") !== billingFilter) return false;
  const statusFilter = adminUsersFilterStatus?.value || "";
  if (statusFilter === "blocked" && !user.blocked) return false;
  if (statusFilter === "active" && user.blocked) return false;
  return true;
}

function updateUsersStats(allUsers, visibleUsers) {
  if (!adminUsersStats) return;
  const total = allUsers.length;
  const shown = visibleUsers.length;
  const paypal = allUsers.filter((u) => u.billing?.kind === "paypal_subscription").length;
  const balanceTotal = allUsers.reduce((sum, u) => sum + (Number(u.balance) || 0), 0);
  adminUsersStats.textContent = `表示 ${shown} / ${total} 件 · PayPalサブスク ${paypal} · 残高合計 ${formatBalanceJpy(balanceTotal)}`;
}

function renderUsers(users) {
  if (!adminUsersBody) return;
  const allUsers = users || [];
  const filtered = allUsers.filter(userMatchesFilters);
  adminUsersBody.innerHTML = "";
  filtered.forEach((user) => {
    const tr = document.createElement("tr");
    tr.dataset.username = user.username;
    const status = user.blocked
      ? '<span class="admin-status admin-status--blocked">利用停止</span>'
      : '<span class="admin-status">有効</span>';
    const roleBadge =
      user.role === "admin" ? ' <span class="admin-badge">管理者</span>' : "";
    const poolExpires = user.usage_pool_expires_at || user.plan_expires_at || "";

    tr.innerHTML = `
      <td>
        <button type="button" class="admin-user-link" data-action="open">${escapeHtml(user.username)}</button>${roleBadge}
      </td>
      <td>${escapeHtml(user.display_name || user.full_name || "—")}</td>
      <td class="admin-users-email">${escapeHtml(user.email || "—")}</td>
      <td>${escapeHtml(user.plan_name || user.plan)}</td>
      <td>${billingKindBadge(user)}</td>
      <td>${escapeHtml(formatBalanceJpy(user.balance))}</td>
      <td class="admin-usage-cell">${escapeHtml(formatUsage(user))}</td>
      <td>${escapeHtml(formatDate(poolExpires))}</td>
      <td>${escapeHtml(formatDate(user.created_at))}</td>
      <td>${status}</td>
    `;
    adminUsersBody.appendChild(tr);
  });
  updateUsersStats(allUsers, filtered);
  adminUsersTableWrap?.classList.toggle("hidden", filtered.length === 0);
  adminUsersEmpty?.classList.toggle("hidden", filtered.length > 0);
}

function fillUsersFilterPlans(plans) {
  if (!adminUsersFilterPlan) return;
  const current = adminUsersFilterPlan.value;
  adminUsersFilterPlan.innerHTML =
    '<option value="">すべて</option>' +
    (plans || [])
      .map(
        (p) =>
          `<option value="${escapeAttr(p.id)}">${escapeHtml(p.name || p.id)}</option>`
      )
      .join("");
  if (current) adminUsersFilterPlan.value = current;
}

function fillPlanSelect(selectEl, selected) {
  if (!selectEl) return;
  selectEl.innerHTML = PLAN_IDS.map(
    (id) => `<option value="${id}"${selected === id ? " selected" : ""}>${id}</option>`
  ).join("");
}

function renderPaymentRows(records) {
  if (!detailPaymentsBody) return;
  detailPaymentsBody.innerHTML = "";
  (records || []).forEach((rec) => {
    detailPaymentsBody.appendChild(createPaymentRow(rec));
  });
}

function createPaymentRow(rec = {}) {
  const tr = document.createElement("tr");
  tr.dataset.paymentId = rec.id || newUuid();
  const statusOptions = PAYMENT_STATUSES.map(
    (s) =>
      `<option value="${s.value}"${rec.status === s.value ? " selected" : ""}>${s.label}</option>`
  ).join("");
  const methodValue = rec.method || "その他";
  const knownMethod = PAYMENT_METHODS.some((m) => m.value === methodValue);
  const methodOptions = PAYMENT_METHODS.map((m) => {
    const selected = methodValue === m.value || (!knownMethod && m.value === "その他");
    return `<option value="${escapeAttr(m.value)}"${selected ? " selected" : ""}>${escapeHtml(m.label)}</option>`;
  }).join("");

  tr.innerHTML = `
    <td><input type="date" class="admin-inline-input" data-pay-field="date" value="${escapeAttr(rec.date || "")}"></td>
    <td><input type="number" step="1" class="admin-inline-input admin-inline-input--narrow" data-pay-field="amount" value="${escapeAttr(String(Math.round(Number(rec.amount) || 0)))}"></td>
    <td><select class="admin-inline-select" data-pay-field="method">${methodOptions}</select></td>
    <td><select class="admin-inline-select" data-pay-field="status">${statusOptions}</select></td>
    <td><input type="text" class="admin-inline-input" data-pay-field="note" value="${escapeAttr(rec.note || "")}"></td>
    <td><button type="button" class="admin-row-btn admin-row-btn--danger" data-action="remove-payment">削除</button></td>
  `;
  return tr;
}

function collectPaymentRecords() {
  const rows = [];
  detailPaymentsBody?.querySelectorAll("tr").forEach((tr) => {
    rows.push({
      id: tr.dataset.paymentId,
      date: tr.querySelector('[data-pay-field="date"]')?.value || "",
      amount: Number(tr.querySelector('[data-pay-field="amount"]')?.value || 0),
      method: tr.querySelector('[data-pay-field="method"]')?.value.trim() || "",
      status: tr.querySelector('[data-pay-field="status"]')?.value || "paid",
      note: tr.querySelector('[data-pay-field="note"]')?.value.trim() || "",
    });
  });
  return rows;
}

function renderBillingSummaryCard(user) {
  const el = document.getElementById("detailBillingSummary");
  if (!el) return;
  const billing = user.billing || {};
  const kind = billing.kind || "free";
  const items = [
    { label: "課金区分", value: billing.label || BILLING_KIND_LABELS[kind] || kind },
    { label: "有効プラン", value: user.plan_name || user.plan || "—" },
    { label: "残高", value: formatBalanceJpy(user.balance) },
    {
      label: "利用量",
      value: formatUsage(user),
    },
    {
      label: "枠の期限",
      value: formatDate(user.usage_pool_expires_at || user.plan_expires_at),
    },
    {
      label: "API",
      value: billing.api_access_allowed ? "利用可" : "不可",
    },
  ];
  el.innerHTML = `
    <div class="admin-billing-summary-header">
      ${billingKindBadge(user)}
      <span class="admin-billing-summary-plan">${escapeHtml(user.plan_name || user.plan || "")}</span>
    </div>
    <dl class="admin-billing-summary-grid">
      ${items
        .map(
          (item) =>
            `<div><dt>${escapeHtml(item.label)}</dt><dd>${escapeHtml(item.value)}</dd></div>`
        )
        .join("")}
    </dl>`;
}

function renderPaypalMeta(user) {
  const meta = document.getElementById("detailPaypalMeta");
  if (!meta) return;
  const billing = user.billing || {};
  const rows = [
    ["ステータス", billing.paypal_subscription_status || "—"],
    ["サブスクリプション ID", billing.paypal_subscription_id || "—"],
    ["Billing Plan ID", billing.paypal_billing_plan_id || "—"],
    ["最終更新", formatDate(billing.paypal_subscription_updated_at)],
  ];
  meta.innerHTML = rows
    .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
    .join("");
}

function renderBillingEventsRows(events) {
  if (!detailBillingEventsBody) return;
  const list = Array.isArray(events) ? events : [];
  if (!list.length) {
    detailBillingEventsBody.innerHTML =
      '<tr><td colspan="7" class="admin-table-empty">ログがありません</td></tr>';
    return;
  }
  detailBillingEventsBody.innerHTML = list
    .map((ev) => {
      const created = escapeHtml(formatDate(ev.created_at));
      const reqId = escapeHtml(ev.request_id || ev.id || "—");
      const model = escapeHtml(ev.model_id || "—");
      const payType = escapeHtml(ev.payment_type_label || ev.payment_type || "—");
      const billingPlan = escapeHtml(ev.billing_plan_label || ev.billing_plan || "—");
      const cost = `$${Number(ev.cost_usd || 0).toFixed(4)}`;
      const status = escapeHtml(ev.status_label || ev.status || "—");
      return `<tr>
        <td>${created}</td>
        <td class="admin-mono">${reqId}</td>
        <td>${model}</td>
        <td>${payType}</td>
        <td>${billingPlan}</td>
        <td>${escapeHtml(cost)}</td>
        <td>${status}</td>
      </tr>`;
    })
    .join("");
}

async function loadUserBillingEvents(username) {
  if (!username) return;
  const res = await fetch(
    `/api/admin/users/${encodeURIComponent(username)}/billing-events?limit=50`
  );
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "ログの読み込みに失敗しました");
  renderBillingEventsRows(data.events);
  if (detailBillingEventsCount) {
    detailBillingEventsCount.textContent = `全 ${Number(data.total || 0).toLocaleString()} 件`;
  }
}

function fillUserDetail(user) {
  currentDetailUser = user;
  renderBillingSummaryCard(user);
  document.getElementById("detailUsername").textContent = user.username;
  document.getElementById("detailDisplayName").value = user.display_name || "";
  document.getElementById("detailLastName").value = user.last_name || "";
  document.getElementById("detailFirstName").value = user.first_name || "";
  document.getElementById("detailEmail").value = user.email || "";
  document.getElementById("detailPhone").value = user.phone || "";
  fillPlanSelect(document.getElementById("detailPlan"), user.plan);
  const storedHint = document.getElementById("detailStoredPlanHint");
  if (storedHint) {
    const stored = user.billing?.stored_plan;
    storedHint.textContent =
      stored && stored !== user.plan
        ? `保存プラン: ${stored}（有効プランは枠・サブスクから算出）`
        : "有効プランはプラン枠・PayPalサブスク・設定から算出されます";
  }
  document.getElementById("detailBalance").value = Math.round(Number(user.balance) || 0);
  document.getElementById("detailPlanExpires").value = toDatetimeLocalValue(user.plan_expires_at);
  document.getElementById("detailCreatedAt").textContent = formatDate(user.created_at);
  renderPaypalMeta(user);
  if (detailBillingEventsBody) {
    detailBillingEventsBody.innerHTML =
      '<tr><td colspan="6" class="admin-table-empty">「ログを読み込む」で API 利用履歴を表示</td></tr>';
  }
  if (detailBillingEventsCount) detailBillingEventsCount.textContent = "";
  document.getElementById("detailUsage").textContent = formatUsage(user);
  const poolHint = document.getElementById("detailUsagePoolHint");
  if (poolHint) {
    const exp = user.usage_pool_expires_at || "";
    poolHint.textContent = exp
      ? `枠の有効期限: ${formatDate(exp)}`
      : "プラン枠の合計が利用上限です（上書き設定時はその値が優先されます）";
  }
  const quotaEl = document.getElementById("detailUsageQuotaOverride");
  if (quotaEl) {
    quotaEl.value =
      user.usage_quota_override_usd != null && user.usage_quota_override_usd !== ""
        ? String(user.usage_quota_override_usd)
        : "";
  }
  const costEdit = document.getElementById("detailUsageCostEdit");
  if (costEdit) {
    costEdit.value = String(Number(user.usage?.usage_cost_usd ?? 0));
  }
  fillPlanSelect(document.getElementById("detailAddEntitlementPlan"), user.plan);
  renderEntitlementRows(user.all_entitlements || user.entitlements || []);

  const blockedInput = document.getElementById("detailBlocked");
  blockedInput.checked = Boolean(user.blocked);
  blockedInput.disabled = user.role === "admin";

  renderPaymentRows(user.payment_records || []);

  const apiEnabled = document.getElementById("detailApiEnabled");
  const apiHint = document.getElementById("detailApiAccessHint");
  if (apiEnabled) {
    apiEnabled.checked = Boolean(user.billing?.api_enabled);
    apiEnabled.disabled = user.role === "admin";
  }
  if (apiHint) {
    apiHint.textContent = user.billing?.api_access_allowed
      ? "現在 API 利用可能（プランまたは個別許可）"
      : "プラン未対応の場合は個別許可で API を有効化できます";
  }

  if (detailDeleteUser) {
    const canDelete = user.role !== "admin";
    detailDeleteUser.classList.toggle("hidden", !canDelete);
    detailDeleteUser.disabled = Boolean(user.blocked);
    detailDeleteUser.title = user.blocked
      ? "利用停止中は削除できません"
      : "";
  }
}

async function openUserDetail(username, options = {}) {
  const { syncUrl = true } = options;
  if (!username) return;

  closePlanDetail({ syncUrl: false });
  adminUsersListView?.classList.add("hidden");
  adminUserDetailView?.classList.remove("hidden");
  adminUserDetailForm?.classList.add("hidden");
  adminUserDetailError?.classList.add("hidden");
  adminUserDetailLoading?.classList.remove("hidden");

  showAdminPanel("users", { syncUrl, adminUser: username });

  try {
    const user = await fetchUserDetail(username);
    fillUserDetail(user);
    adminUserDetailLoading?.classList.add("hidden");
    adminUserDetailForm?.classList.remove("hidden");
  } catch (err) {
    adminUserDetailLoading?.classList.add("hidden");
    if (adminUserDetailError) {
      adminUserDetailError.textContent = err.message;
      adminUserDetailError.classList.remove("hidden");
    }
  }
}

function closeUserDetail(options = {}) {
  const { syncUrl = true } = options;
  currentDetailUser = null;
  adminUsersListView?.classList.remove("hidden");
  adminUserDetailView?.classList.add("hidden");
  if (syncUrl && (location.pathname === "/admin" || location.pathname === "/admin/")) {
    const path = "/admin#overview";
    if (location.pathname + location.hash !== path) {
      history.replaceState(history.state, "", path);
    }
  }
}

function syncAdminRouteFromHash() {
  if (location.pathname !== "/admin" && location.pathname !== "/admin/") return;
  const { panel, username, planId } = parseAdminHash(location.hash);
  showAdminPanel(panel, { syncUrl: false });
  if (username) {
    closePlanDetail({ syncUrl: false });
    openUserDetail(username, { syncUrl: false });
  } else {
    closeUserDetail({ syncUrl: false });
  }
  if (planId) {
    closeUserDetail({ syncUrl: false });
    openPlanDetail(planId, { syncUrl: false });
  } else {
    closePlanDetail({ syncUrl: false });
  }
}

async function saveUserDetail() {
  if (!currentDetailUser) return;
  const username = currentDetailUser.username;
  const quotaRaw = document.getElementById("detailUsageQuotaOverride")?.value;
  const payload = {
    display_name: document.getElementById("detailDisplayName")?.value.trim(),
    last_name: document.getElementById("detailLastName")?.value.trim(),
    first_name: document.getElementById("detailFirstName")?.value.trim(),
    email: document.getElementById("detailEmail")?.value.trim(),
    phone: document.getElementById("detailPhone")?.value.trim(),
    plan: document.getElementById("detailPlan")?.value,
    balance: Number(document.getElementById("detailBalance")?.value || 0),
    plan_expires_at: document.getElementById("detailPlanExpires")?.value || "",
    payment_records: collectPaymentRecords(),
    usage_cost_usd: Number(document.getElementById("detailUsageCostEdit")?.value || 0),
    usage_quota_override_usd:
      quotaRaw === "" || quotaRaw == null ? null : Number(quotaRaw),
  };
  if (currentDetailUser.role !== "admin") {
    payload.blocked = document.getElementById("detailBlocked")?.checked ?? false;
    payload.api_enabled = document.getElementById("detailApiEnabled")?.checked ?? false;
  }

  const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");

  const updated = data.user;
  currentDetailUser = updated;
  fillUserDetail(updated);
  if (adminState?.users) {
    const idx = adminState.users.findIndex((u) => u.username === username);
    const summary = { ...updated };
    delete summary.payment_records;
    delete summary.billing_address;
    delete summary.all_entitlements;
    if (idx >= 0) adminState.users[idx] = summary;
    else adminState.users.push(summary);
    renderUsers(adminState.users);
  }
  return updated;
}

async function deleteUser(username) {
  const ok = await window.NexNotify?.confirm(
    `ユーザー「${username}」を削除しますか？この操作は取り消せません。`,
    { danger: true, confirmLabel: "削除" }
  );
  if (!ok) return;
  const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "削除に失敗しました");
}

function adminUserListSummary(user) {
  const summary = { ...user };
  delete summary.payment_records;
  delete summary.billing_address;
  delete summary.all_entitlements;
  return summary;
}

async function createAdminUser() {
  const payload = {
    username: document.getElementById("createUsername")?.value.trim(),
    password: document.getElementById("createPassword")?.value || "",
    display_name: document.getElementById("createDisplayName")?.value.trim(),
    email: document.getElementById("createEmail")?.value.trim(),
    plan: document.getElementById("createPlan")?.value,
    role: document.getElementById("createRole")?.value,
  };

  const res = await fetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "追加に失敗しました");

  const created = data.user;
  if (adminState?.users) {
    adminState.users.push(adminUserListSummary(created));
    adminState.users.sort((a, b) => a.username.localeCompare(b.username));
    renderUsers(adminState.users);
  }

  adminUserCreateForm?.reset();
  fillPlanSelect(createPlanSelect, "free");
  document.getElementById("createRole").value = "user";
  return created;
}

function truncatePlanDescription(text, maxLen = 48) {
  const oneLine = String(text ?? "").replace(/\s+/g, " ").trim();
  if (!oneLine) return "";
  return oneLine.length > maxLen ? `${oneLine.slice(0, maxLen)}…` : oneLine;
}

function renderPlansList(plans) {
  if (!adminPlansBody) return;
  adminPlansBody.innerHTML = "";
  (plans || []).forEach((plan) => {
    const feat = plan.features || {};
    const tr = document.createElement("tr");
    tr.dataset.planId = plan.id;
    const priceUsd =
      plan.price_usd == null ? "—" : escapeHtml(String(plan.price_usd));
    const descSnippet = truncatePlanDescription(plan.description);
    const descHtml = descSnippet
      ? `<span class="admin-plan-desc">${escapeHtml(descSnippet)}</span>`
      : "";
    tr.innerHTML = `
      <td>
        <button type="button" class="admin-user-link" data-action="open-plan">${escapeHtml(plan.name)}</button>
        <span class="admin-plan-id"> (${escapeHtml(plan.id)})</span>
        ${descHtml}
      </td>
      <td>${escapeHtml(plan.price_label || "")}</td>
      <td>${priceUsd}</td>
      <td>${escapeHtml(formatPlanBudget(feat.monthly_ai_budget_usd ?? plan.monthly_ai_budget_usd))}</td>
    `;
    adminPlansBody.appendChild(tr);
  });
}

function fillPlanDetail(plan) {
  currentDetailPlan = plan;
  document.getElementById("planDetailId").textContent = plan.id;
  document.getElementById("planDetailName").textContent = plan.name;
  const priceUsdEl = document.getElementById("planDetailPriceUsd");
  if (priceUsdEl) {
    priceUsdEl.value = plan.price_usd == null ? "" : plan.price_usd;
  }
  document.getElementById("planDetailPriceLabel").value = plan.price_label || "";
  const descEl = document.getElementById("planDetailDescription");
  if (descEl) descEl.value = plan.description || "";
  const feat = plan.features || {};
  const budgetEl = document.getElementById("planDetailMonthlyAiBudget");
  const budget = feat.monthly_ai_budget_usd ?? plan.monthly_ai_budget_usd;
  if (budgetEl) budgetEl.value = budget == null ? "" : budget;
}

function closePlanDetail(options = {}) {
  const { syncUrl = true } = options;
  currentDetailPlan = null;
  adminPlansListView?.classList.remove("hidden");
  adminPlanDetailView?.classList.add("hidden");
  if (syncUrl && (location.pathname === "/admin" || location.pathname === "/admin/")) {
    const path = "/admin#plans";
    if (location.pathname + location.hash !== path) {
      history.replaceState(history.state, "", path);
    }
  }
}

async function openPlanDetail(planId, options = {}) {
  const { syncUrl = true } = options;
  if (!planId || !PLAN_IDS.includes(planId)) return;

  closeUserDetail({ syncUrl: false });
  adminPlansListView?.classList.add("hidden");
  adminPlanDetailView?.classList.remove("hidden");
  adminPlanDetailForm?.classList.add("hidden");
  adminPlanDetailError?.classList.add("hidden");
  adminPlanDetailLoading?.classList.remove("hidden");

  showAdminPanel("plans", { syncUrl, adminPlan: planId });

  try {
    let plan = adminState?.plans?.find((p) => p.id === planId);
    if (!plan) {
      const res = await fetch(`/api/admin/plans/${encodeURIComponent(planId)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
      plan = data.plan;
    }
    fillPlanDetail(plan);
    adminPlanDetailLoading?.classList.add("hidden");
    adminPlanDetailForm?.classList.remove("hidden");
  } catch (err) {
    adminPlanDetailLoading?.classList.add("hidden");
    if (adminPlanDetailError) {
      adminPlanDetailError.textContent = err.message;
      adminPlanDetailError.classList.remove("hidden");
    }
  }
}

async function savePlanDetail() {
  if (!currentDetailPlan) return;
  const planId = currentDetailPlan.id;
  const usdRaw = document.getElementById("planDetailPriceUsd")?.value.trim();
  const budgetRaw = document.getElementById("planDetailMonthlyAiBudget")?.value.trim();
  const payload = {
    price_label: document.getElementById("planDetailPriceLabel")?.value.trim() ?? "",
    price_usd: usdRaw === "" ? null : Number(usdRaw),
    description: document.getElementById("planDetailDescription")?.value ?? "",
    features: {
      monthly_ai_budget_usd: budgetRaw === "" ? null : Number(budgetRaw),
    },
  };
  const res = await fetch(`/api/admin/plans/${encodeURIComponent(planId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  if (adminState?.plans) {
    const idx = adminState.plans.findIndex((p) => p.id === planId);
    if (idx >= 0) adminState.plans[idx] = data.plan;
    else adminState.plans.push(data.plan);
    renderPlansList(adminState.plans);
  }
  fillPlanDetail(data.plan);
  return data.plan;
}

function renderPlanFeatureGroupTable(group, plans) {
  const features = group.features || [];
  if (!features.length) return "";

  const planHeaders = plans
    .map(
      (plan) =>
        `<th scope="col">${escapeHtml(plan.name)}<span class="admin-plan-id">${escapeHtml(plan.id)}</span></th>`
    )
    .join("");

  const rows = features
    .map((feature) => {
      const cells = plans
        .map((plan) => {
          const flags = plan.flags || {};
          const checked = flags[feature.key] !== false;
          return `<td class="admin-plan-feature-cell">
            <input type="checkbox" class="admin-plan-feature-toggle" data-plan-id="${escapeAttr(plan.id)}" data-flag="${escapeAttr(feature.key)}"${checked ? " checked" : ""} aria-label="${escapeAttr(plan.name)} ${escapeAttr(feature.label)}">
          </td>`;
        })
        .join("");
      return `<tr data-feature-key="${escapeAttr(feature.key)}"><th scope="row">${escapeHtml(feature.label)}</th>${cells}</tr>`;
    })
    .join("");

  return `
    <div class="admin-table-wrap admin-table-wrap--wide">
      <table class="admin-table admin-plan-features-matrix admin-plan-features-matrix--by-feature">
        <thead>
          <tr>
            <th scope="col">機能</th>
            ${planHeaders}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function renderPlanFeaturesPanel(data) {
  if (!adminPlanFeaturesGroups || !data) return;
  const groups = data.feature_groups?.length
    ? data.feature_groups
    : [{ id: "all", label: "すべて", features: data.feature_keys || [] }];
  const plans = data.plans || [];

  adminPlanFeaturesGroups.innerHTML = groups
    .map((group) => {
      const tableHtml = renderPlanFeatureGroupTable(group, plans);
      if (!tableHtml) return "";
      const count = (group.features || []).length;
      return `
        <section class="admin-plan-features-group" data-group-id="${escapeAttr(group.id)}">
          <header class="admin-plan-features-group-header">
            <h3 class="admin-plan-features-group-title">${escapeHtml(group.label)}</h3>
            <span class="admin-plan-features-group-count">${count} 項目</span>
          </header>
          ${tableHtml}
        </section>`;
    })
    .join("");
}

function collectPlanFeaturesPayload() {
  const plans = {};
  adminPlanFeaturesGroups?.querySelectorAll(".admin-plan-feature-toggle").forEach((input) => {
    const planId = input.dataset.planId;
    const flag = input.dataset.flag;
    if (!planId || !flag) return;
    if (!plans[planId]) plans[planId] = { flags: {} };
    plans[planId].flags[flag] = input.checked;
  });
  return { plans };
}

async function loadPlanFeatures() {
  if (!adminPlanFeaturesForm) return;
  adminPlanFeaturesLoading?.classList.remove("hidden");
  adminPlanFeaturesError?.classList.add("hidden");
  adminPlanFeaturesForm.classList.add("hidden");
  adminPlanFeaturesMsg?.classList.add("hidden");
  try {
    const res = await fetch("/api/admin/plan-features");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    planFeaturesState = data;
    renderPlanFeaturesPanel(data);
    adminPlanFeaturesLoading?.classList.add("hidden");
    adminPlanFeaturesForm.classList.remove("hidden");
  } catch (err) {
    adminPlanFeaturesLoading?.classList.add("hidden");
    if (adminPlanFeaturesError) {
      adminPlanFeaturesError.textContent = err.message;
      adminPlanFeaturesError.classList.remove("hidden");
    }
  }
}

async function savePlanFeatures() {
  const res = await fetch("/api/admin/plan-features", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPlanFeaturesPayload()),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  planFeaturesState = data;
  renderPlanFeaturesPanel(data);
  if (adminState?.plans) {
    const resState = await fetchAdminState();
    adminState.plans = resState.plans;
    renderPlansList(adminState.plans);
  }
  return data;
}

function applyFeatures(features) {
  if (!adminFeaturesForm) return;
  adminFeaturesForm.querySelectorAll("[data-feature]").forEach((input) => {
    input.checked = Boolean(features?.[input.dataset.feature]);
  });
}

function formatTokenCount(n) {
  return Number(n || 0).toLocaleString();
}

const USD_TO_JPY = 160;

function formatCostWithJpy(usd) {
  const n = Number(usd || 0);
  const usdText = `$${n.toLocaleString(undefined, {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  })}`;
  const jpyText = (n * USD_TO_JPY).toLocaleString(undefined, {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });
  return `${usdText}<span class="admin-cost-jpy">(約 ${jpyText}円)</span>`;
}

function fillProviderSelect(selectEl, providerOptions, selected) {
  if (!selectEl || !providerOptions) return;
  selectEl.innerHTML = Object.entries(providerOptions)
    .map(
      ([id, label]) =>
        `<option value="${escapeAttr(id)}"${id === selected ? " selected" : ""}>${escapeHtml(label)}</option>`
    )
    .join("");
}

function renderProviders(providers, providerOptions) {
  if (!adminProvidersFields) return;
  adminProvidersFields.innerHTML = "";
  (providers || []).forEach((p) => {
    const card = document.createElement("div");
    card.className = "admin-provider-card";
    card.dataset.providerId = p.id;
    const keyHint = p.has_api_key ? "設定済み" : "未設定";
    card.innerHTML = `
      <h4 class="admin-provider-title">${escapeHtml(p.label)} <span class="admin-provider-status">${escapeHtml(keyHint)}</span></h4>
      <div class="settings-field">
        <label>APIキー <span class="settings-hint">(${escapeHtml(p.api_key_env || "")})</span></label>
        <input type="password" class="admin-inline-input" data-provider-field="api_key" placeholder="変更時のみ入力" autocomplete="new-password">
      </div>
      <div class="settings-field">
        <label>Base URL</label>
        <input type="text" class="admin-inline-input" data-provider-field="base_url" value="${escapeAttr(p.base_url || "")}">
        ${p.base_url_hint ? `<p class="settings-hint">${escapeHtml(p.base_url_hint)}</p>` : ""}
      </div>
    `;
    adminProvidersFields.appendChild(card);
  });
  if (addModelProvider && providerOptions) {
    fillProviderSelect(addModelProvider, providerOptions, "deepseek");
  }
}

function collectProvidersPayload() {
  const providers = {};
  adminProvidersFields?.querySelectorAll(".admin-provider-card").forEach((card) => {
    const id = card.dataset.providerId;
    if (!id) return;
    const apiKey = card.querySelector('[data-provider-field="api_key"]')?.value;
    const baseUrl = card.querySelector('[data-provider-field="base_url"]')?.value.trim();
    providers[id] = {};
    if (apiKey) providers[id].api_key = apiKey;
    if (baseUrl) providers[id].base_url = baseUrl;
  });
  return providers;
}

function collectModelsPayload() {
  const models = {};
  adminModelsList?.querySelectorAll(".admin-model-card[data-model-id]").forEach((card) => {
    const id = card.dataset.modelId;
    if (!id) return;
    models[id] = {
      api_id: card.querySelector('[data-model-field="api_id"]')?.value.trim() || id,
      display_name:
        card.querySelector('[data-model-field="display_name"]')?.value.trim() || id,
      tier: card.querySelector('[data-model-field="tier"]')?.value.trim() || "",
      provider: card.querySelector('[data-model-field="provider"]')?.value || "deepseek",
      api_model:
        card.querySelector('[data-model-field="api_model"]')?.value.trim() || id,
      agent_profile:
        card.querySelector('[data-model-field="agent_profile"]')?.value || "deepseek",
      enabled: card.querySelector('[data-model-field="enabled"]')?.checked !== false,
      cost_input_usd_per_1m: Number(
        card.querySelector('[data-model-field="cost_input_usd_per_1m"]')?.value
      ),
      cost_output_usd_per_1m: Number(
        card.querySelector('[data-model-field="cost_output_usd_per_1m"]')?.value
      ),
      price_input_usd_per_1m: Number(
        card.querySelector('[data-model-field="price_input_usd_per_1m"]')?.value
      ),
      price_output_usd_per_1m: Number(
        card.querySelector('[data-model-field="price_output_usd_per_1m"]')?.value
      ),
      cost_input_cache_hit_usd_per_1m: Number(
        card.querySelector('[data-model-field="cost_input_cache_hit_usd_per_1m"]')?.value
      ),
      price_input_cache_hit_usd_per_1m: Number(
        card.querySelector('[data-model-field="price_input_cache_hit_usd_per_1m"]')?.value
      ),
    };
  });
  return models;
}

async function testModelApi(modelId, btn) {
  if (!modelId) return;
  const label = btn?.textContent || "テスト";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "…";
  }
  try {
    const res = await fetch(`/api/admin/models/${encodeURIComponent(modelId)}/test`, {
      method: "POST",
    });
    const data = await res.json().catch(() => ({}));
    const msg = data.message || data.error || "APIキーのテストに失敗しました";
    if (res.ok && data.ok) {
      window.NexNotify?.showSuccess(msg, { durationMs: 5000 });
      showAdminMsg(adminModelsMsg, msg, false);
    } else {
      window.NexNotify?.showError(msg);
      showAdminMsg(adminModelsMsg, msg, true);
    }
  } catch (err) {
    const msg = err.message || "APIキーのテストに失敗しました";
    window.NexNotify?.showError(msg);
    showAdminMsg(adminModelsMsg, msg, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = label;
    }
  }
}

async function deleteModel(modelId) {
  if (!modelId) return;
  const ok = await window.NexNotify?.confirm(`モデル「${modelId}」を削除しますか？`, {
    danger: true,
    confirmLabel: "削除",
  });
  if (!ok) return;
  const res = await fetch(`/api/admin/models/${encodeURIComponent(modelId)}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "削除に失敗しました");
  if (adminState) adminState.models = data.models;
  renderModels(data.models);
}

function renderModels(modelsPayload) {
  if (!adminModelsList || !modelsPayload) return;
  renderProviders(modelsPayload.providers, modelsPayload.provider_options);
  if (adminModelsPeriod) {
    adminModelsPeriod.textContent = modelsPayload.period_label || modelsPayload.period || "—";
  }
  if (adminModelsActive) {
    adminModelsActive.textContent = modelsPayload.active_model || "—";
  }
  if (adminDefaultModel) {
    const opts = (modelsPayload.models || [])
      .map(
        (m) =>
          `<option value="${escapeAttr(m.id)}"${m.id === modelsPayload.default_model ? " selected" : ""}>${escapeHtml(m.display_name || m.id)}</option>`
      )
      .join("");
    adminDefaultModel.innerHTML = opts;
  }
  const totals = modelsPayload.totals || {};
  if (adminModelsTotals) {
    adminModelsTotals.innerHTML = `
      <div class="admin-models-total-card">
        <span class="admin-models-total-label">Input</span>
        <span class="admin-models-total-value">${formatTokenCount(totals.prompt_tokens)}</span>
      </div>
      <div class="admin-models-total-card">
        <span class="admin-models-total-label">Output</span>
        <span class="admin-models-total-value">${formatTokenCount(totals.completion_tokens)}</span>
      </div>
      <div class="admin-models-total-card">
        <span class="admin-models-total-label">推論</span>
        <span class="admin-models-total-value">${formatTokenCount(totals.reasoning_tokens)}</span>
      </div>
      <div class="admin-models-total-card">
        <span class="admin-models-total-label">合計</span>
        <span class="admin-models-total-value">${formatTokenCount(totals.total_tokens)}</span>
      </div>
      <div class="admin-models-total-card admin-models-total-card--cost">
        <span class="admin-models-total-label">原価計</span>
        <span class="admin-models-total-value">${escapeHtml(totals.cost_usd_label || "$0.0000")}</span>
      </div>
      <div class="admin-models-total-card admin-models-total-card--cost">
        <span class="admin-models-total-label">提供計</span>
        <span class="admin-models-total-value">${escapeHtml(totals.price_usd_label || "$0.0000")}</span>
      </div>
    `;
  }

  const providerOptions = modelsPayload.provider_options || {};
  const profileOptions = modelsPayload.agent_profile_options || ["deepseek", "standard"];

  adminModelsList.innerHTML = "";
  (modelsPayload.models || []).forEach((model) => {
    const card = document.createElement("article");
    card.className = "admin-model-card";
    card.dataset.modelId = model.id;
    const providerOpts = Object.entries(providerOptions)
      .map(
        ([id, label]) =>
          `<option value="${escapeAttr(id)}"${id === model.provider ? " selected" : ""}>${escapeHtml(label)}</option>`
      )
      .join("");
    const profileOpts = profileOptions
      .map(
        (id) =>
          `<option value="${escapeAttr(id)}"${id === (model.agent_profile || "deepseek") ? " selected" : ""}>${escapeHtml(id)}</option>`
      )
      .join("");
    card.innerHTML = `
      <header class="admin-model-card__header">
        <div class="admin-model-card__title-wrap">
          <h4 class="admin-model-card__title">${escapeHtml(model.display_name || model.id)}</h4>
          <span class="admin-model-card__catalog"><code>${escapeHtml(model.id)}</code></span>
        </div>
        <label class="admin-model-card__enabled">
          <input type="checkbox" data-model-field="enabled"${model.enabled !== false ? " checked" : ""}>
          <span>有効</span>
        </label>
      </header>
      <div class="admin-model-card__sections">
        <section class="admin-model-card__section">
          <h5 class="admin-model-card__section-title">公開設定</h5>
          <div class="admin-model-card__grid">
            <div class="settings-field">
              <label>APIモデルID</label>
              <input type="text" class="admin-inline-input" data-model-field="api_id" value="${escapeAttr(model.api_id || model.id)}" pattern="[a-zA-Z0-9][a-zA-Z0-9._\\-]{1,63}" required>
            </div>
            <div class="settings-field">
              <label>表示名</label>
              <input type="text" class="admin-inline-input" data-model-field="display_name" value="${escapeAttr(model.display_name)}">
            </div>
            <div class="settings-field">
              <label>チャット表示ラベル</label>
              <input type="text" class="admin-inline-input" data-model-field="tier" value="${escapeAttr(model.tier || "")}" placeholder="frontier model">
            </div>
          </div>
        </section>
        <section class="admin-model-card__section">
          <h5 class="admin-model-card__section-title">プロバイダー</h5>
          <div class="admin-model-card__grid">
            <div class="settings-field">
              <label>Provider</label>
              <select class="admin-inline-input" data-model-field="provider">${providerOpts}</select>
            </div>
            <div class="settings-field">
              <label>上流APIモデル名</label>
              <input type="text" class="admin-inline-input" data-model-field="api_model" value="${escapeAttr(model.api_model || model.id)}">
            </div>
            <div class="settings-field">
              <label>エージェント</label>
              <select class="admin-inline-input" data-model-field="agent_profile">${profileOpts}</select>
            </div>
          </div>
        </section>
        <section class="admin-model-card__section">
          <h5 class="admin-model-card__section-title">単価（$/1M tokens）</h5>
          <div class="admin-model-card__grid admin-model-card__grid--pricing">
            <div class="settings-field">
              <label>原価 Input</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="cost_input_usd_per_1m" value="${escapeAttr(String(model.cost_input_usd_per_1m))}">
            </div>
            <div class="settings-field">
              <label>原価 Output</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="cost_output_usd_per_1m" value="${escapeAttr(String(model.cost_output_usd_per_1m))}">
            </div>
            <div class="settings-field">
              <label>提供 Input</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="price_input_usd_per_1m" value="${escapeAttr(String(model.price_input_usd_per_1m))}">
            </div>
            <div class="settings-field">
              <label>提供 Output</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="price_output_usd_per_1m" value="${escapeAttr(String(model.price_output_usd_per_1m))}">
            </div>
            <div class="settings-field">
              <label>原価 Input Cache Hit</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="cost_input_cache_hit_usd_per_1m" value="${escapeAttr(String(model.cost_input_cache_hit_usd_per_1m))}">
            </div>
            <div class="settings-field">
              <label>提供 Input Cache Hit</label>
              <input type="number" step="0.0001" min="0" class="admin-inline-input admin-inline-input--num" data-model-field="price_input_cache_hit_usd_per_1m" value="${escapeAttr(String(model.price_input_cache_hit_usd_per_1m))}">
            </div>
          </div>
        </section>
        <section class="admin-model-card__section admin-model-card__section--stats">
          <h5 class="admin-model-card__section-title">当月利用</h5>
          <div class="admin-model-card__stats">
            <div class="admin-model-stat"><span>Input</span><strong>${formatTokenCount(model.prompt_tokens)}</strong></div>
            <div class="admin-model-stat"><span>Output</span><strong>${formatTokenCount(model.completion_tokens)}</strong></div>
            <div class="admin-model-stat"><span>推論</span><strong>${formatTokenCount(model.reasoning_tokens)}</strong></div>
            <div class="admin-model-stat admin-model-stat--cost"><span>原価計</span><strong>${escapeHtml(model.cost_usd_label)}</strong></div>
            <div class="admin-model-stat"><span>提供計</span><strong>${escapeHtml(model.price_usd_label || "")}</strong></div>
          </div>
        </section>
      </div>
      <footer class="admin-model-card__footer">
        <button type="button" class="admin-row-btn" data-action="test-model">APIキーテスト</button>
        <button type="button" class="admin-row-btn admin-row-btn--danger" data-action="delete-model">削除</button>
      </footer>
    `;
    adminModelsList.appendChild(card);
  });

  adminModelsList.querySelectorAll('[data-action="test-model"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".admin-model-card");
      const id = card?.dataset.modelId;
      void testModelApi(id, btn);
    });
  });

  adminModelsList.querySelectorAll('[data-action="delete-model"]').forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest(".admin-model-card");
      const id = card?.dataset.modelId;
      try {
        await deleteModel(id);
        showAdminMsg(adminModelsMsg, "モデルを削除しました", false);
      } catch (err) {
        showAdminMsg(adminModelsMsg, err.message, true);
      }
    });
  });

  populateChartModelSelect(modelsPayload.models);
  if (modelsPayload.chart) {
    updateModelChart(modelsPayload.chart);
  }
}

function getChartThemeColors() {
  const style = getComputedStyle(document.documentElement);
  const pick = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: pick("--text-secondary", "#94a3b8"),
    grid: pick("--border", "rgba(148, 163, 184, 0.2)"),
    tokens: "rgb(96, 165, 250)",
    cost: "rgb(167, 139, 250)",
    price: "rgb(52, 211, 153)",
  };
}

function populateChartModelSelect(models) {
  if (!adminModelsChartModel) return;
  const prev = adminModelsChartModel.value || "all";
  const options = ['<option value="all">すべて</option>'];
  (models || []).forEach((m) => {
    options.push(
      `<option value="${escapeAttr(m.id)}">${escapeHtml(m.display_name || m.id)}</option>`
    );
  });
  adminModelsChartModel.innerHTML = options.join("");
  if ([...adminModelsChartModel.options].some((o) => o.value === prev)) {
    adminModelsChartModel.value = prev;
  }
}

function renderChartRangeTotals(chart) {
  if (!adminModelsChartTotals || !chart?.totals) return;
  const t = chart.totals;
  adminModelsChartTotals.innerHTML = `
    <div class="admin-models-chart-total">
      <span>期間内トークン</span>
      <strong>${formatTokenCount(t.total_tokens)}</strong>
    </div>
    <div class="admin-models-chart-total">
      <span>期間内原価</span>
      <strong>${formatCostWithJpy(t.cost_usd)}</strong>
    </div>
    <div class="admin-models-chart-total">
      <span>期間内提供</span>
      <strong>${formatCostWithJpy(t.price_usd)}</strong>
    </div>
    <div class="admin-models-chart-total">
      <span>リクエスト</span>
      <strong>${formatTokenCount(t.requests)}</strong>
    </div>
  `;
}

function updateModelChart(chart) {
  if (!adminModelsChartCanvas || !chart) return;
  if (typeof Chart === "undefined") {
    // Chart.js がまだ読み込まれていない場合は少し待って再試行
    setTimeout(() => updateModelChart(chart), 200);
    return;
  }
  const colors = getChartThemeColors();
  const labels = chart.labels || [];
  const ds = chart.datasets || {};

  if (adminModelsChartMeta) {
    const modelOpt =
      chart.model_filter !== "all"
        ? adminModelsChartModel?.querySelector(`option[value="${CSS.escape(chart.model_filter)}"]`)
        : null;
    const modelLabel =
      chart.model_filter === "all" ? "全モデル" : modelOpt?.textContent || chart.model_filter;
    adminModelsChartMeta.textContent = `${chart.range_label || ""} · ${chart.granularity_label || ""}単位 · ${modelLabel} · 更新 ${chart.updated_at || ""}`;
  }
  renderChartRangeTotals(chart);

  const data = {
    labels,
    datasets: [
      {
        label: "トークン",
        data: ds.total_tokens || [],
        borderColor: colors.tokens,
        backgroundColor: "rgba(96, 165, 250, 0.12)",
        yAxisID: "y",
        tension: 0.25,
        fill: true,
        pointRadius: labels.length > 48 ? 0 : 2,
      },
      {
        label: "原価 (USD)",
        data: ds.cost_usd || [],
        borderColor: colors.cost,
        backgroundColor: "transparent",
        yAxisID: "y1",
        tension: 0.25,
        borderDash: [4, 4],
        pointRadius: labels.length > 48 ? 0 : 2,
      },
      {
        label: "提供 (USD)",
        data: ds.price_usd || [],
        borderColor: colors.price,
        backgroundColor: "transparent",
        yAxisID: "y1",
        tension: 0.25,
        pointRadius: labels.length > 48 ? 0 : 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: colors.text } },
      tooltip: {
        callbacks: {
          label(ctx) {
            const v = ctx.parsed.y;
            if (ctx.dataset.yAxisID === "y1") return ` ${ctx.dataset.label}: $${Number(v).toFixed(4)}`;
            return ` ${ctx.dataset.label}: ${Number(v).toLocaleString()}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: colors.text, maxRotation: 45, autoSkip: true, maxTicksLimit: 14 },
        grid: { color: colors.grid },
      },
      y: {
        type: "linear",
        position: "left",
        ticks: { color: colors.text },
        grid: { color: colors.grid },
        title: { display: true, text: "トークン", color: colors.text },
      },
      y1: {
        type: "linear",
        position: "right",
        ticks: {
          color: colors.text,
          callback: (v) => `$${Number(v).toFixed(2)}`,
        },
        grid: { drawOnChartArea: false },
        title: { display: true, text: "USD", color: colors.text },
      },
    },
  };

  if (modelUsageChart) {
    modelUsageChart.data = data;
    modelUsageChart.options = options;
    modelUsageChart.update("none");
    return;
  }

  modelUsageChart = new Chart(adminModelsChartCanvas, {
    type: "line",
    data,
    options,
  });
}

function getModelChartQuery() {
  return {
    range: adminModelsChartRange?.value || "7d",
    model: adminModelsChartModel?.value || "all",
  };
}

async function fetchModelChart() {
  const { range, model } = getModelChartQuery();
  const res = await fetch(
    `/api/admin/models/chart?range=${encodeURIComponent(range)}&model=${encodeURIComponent(model)}`
  );
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "グラフの取得に失敗しました");
  if (data.chart) updateModelChart(data.chart);
  return data.chart;
}

function stopModelChartRefresh() {
  if (modelChartRefreshTimer) {
    clearInterval(modelChartRefreshTimer);
    modelChartRefreshTimer = null;
  }
}

// --- APIダッシュボード: リアルタイムリクエスト表示（ポーリング） ---
function formatApiSessionTime(t) {
  if (!t) return "—";
  const d = new Date(t);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function apiElapsedLabel(startedAt) {
  if (!startedAt) return "—";
  const d = new Date(startedAt);
  if (isNaN(d.getTime())) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}秒`;
  const m = Math.floor(sec / 60);
  const r = sec % 60;
  return `${m}分${r}秒`;
}

function renderApiActiveSessions(active) {
  if (!adminApiActiveBody) return;
  if (!active || !active.length) {
    adminApiActiveBody.innerHTML =
      '<p class="settings-hint">進行中のリクエストはありません</p>';
    return;
  }
  adminApiActiveBody.innerHTML = active
    .map((s) => {
      const model = escapeHtml(s.model_id || s.api_model || "—");
      const user = escapeHtml(s.username || "—");
      const elapsed = apiElapsedLabel(s.started_at || s.created_at);
      return `<div class="admin-api-live-item admin-api-live-item--active">
        <div class="admin-api-live-item-main">
          <span class="admin-api-live-item-user">${user}</span>
          <span class="admin-api-live-item-model">${model}</span>
        </div>
        <div class="admin-api-live-item-sub">
          <span class="admin-api-live-item-time">${escapeHtml(formatApiSessionTime(s.started_at || s.created_at))} 開始</span>
          <span class="admin-api-live-item-elapsed">${elapsed}</span>
          <span class="admin-api-badge admin-api-badge--running">実行中</span>
        </div>
      </div>`;
    })
    .join("");
}

function renderApiRecentLogs(sessions) {
  if (!adminApiLogBody) return;
  if (!sessions || !sessions.length) {
    adminApiLogBody.innerHTML =
      '<p class="settings-hint">リクエスト履歴がありません</p>';
    return;
  }
  const labels = {
    running: "実行中",
    completed: "完了",
    cancelled: "中断",
    failed: "失敗",
  };
  adminApiLogBody.innerHTML = sessions
    .map((s) => {
      const model = escapeHtml(s.model_id || s.api_model || "—");
      const user = escapeHtml(s.username || "—");
      const status = (s.status || "").toLowerCase();
      const label = labels[status] || status || "—";
      const badgeCls =
        status === "failed"
          ? "admin-api-badge--failed"
          : status === "completed"
            ? "admin-api-badge--done"
            : "admin-api-badge--running";
      const tokens = s.total_tokens
        ? Number(s.total_tokens).toLocaleString()
        : "—";
      const cost = formatAdminSessionCost(s.cost_usd, s.cost_jpy);
      return `<div class="admin-api-live-item">
        <div class="admin-api-live-item-main">
          <span class="admin-api-live-item-user">${user}</span>
          <span class="admin-api-live-item-model">${model}</span>
        </div>
        <div class="admin-api-live-item-sub">
          <span class="admin-api-live-item-time">${escapeHtml(formatApiSessionTime(s.started_at || s.ended_at))}</span>
          <span class="admin-api-live-item-tokens">${tokens} tok</span>
          <span class="admin-api-live-item-cost">${cost}</span>
          <span class="admin-api-badge ${badgeCls}">${escapeHtml(label)}</span>
        </div>
      </div>`;
    })
    .join("");
}

async function loadApiDashboard() {
  try {
    const [activeRes, logsRes] = await Promise.all([
      fetch("/api/admin/sessions/active"),
      fetch("/api/admin/sessions/logs?limit=15"),
    ]);
    if (!activeRes.ok || !logsRes.ok) throw new Error("fetch failed");
    const activeData = await activeRes.json();
    const logsData = await logsRes.json();
    renderApiActiveSessions(activeData.active || []);
    renderApiRecentLogs(Array.isArray(logsData.sessions) ? logsData.sessions : []);
    if (adminApiLiveStatus) {
      adminApiLiveStatus.textContent = `更新 ${new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
      adminApiLiveStatus.classList.remove("is-error");
    }
  } catch {
    if (adminApiLiveStatus) {
      adminApiLiveStatus.textContent = "取得失敗";
      adminApiLiveStatus.classList.add("is-error");
    }
  }
}

function startApiDashboard() {
  stopApiDashboard();
  loadApiDashboard();
  apiDashboardTimer = setInterval(loadApiDashboard, 3000);
}

function stopApiDashboard() {
  if (apiDashboardTimer) {
    clearInterval(apiDashboardTimer);
    apiDashboardTimer = null;
  }
}

function startModelChartRefresh() {
  stopModelChartRefresh();
  const seconds = Number(adminModelsChartRefresh?.value || 0);
  if (!seconds || document.documentElement.getAttribute("data-admin-panel") !== "models") {
    return;
  }
  modelChartRefreshTimer = setInterval(() => {
    fetchModelChart().catch(() => {});
  }, seconds * 1000);
}

async function onModelChartControlsChange() {
  try {
    await fetchModelChart();
  } catch {
    return;
  }
  startModelChartRefresh();
}

if (adminModelsChartRange) {
  adminModelsChartRange.addEventListener("change", onModelChartControlsChange);
}
if (adminModelsChartModel) {
  adminModelsChartModel.addEventListener("change", onModelChartControlsChange);
}
if (adminModelsChartRefresh) {
  adminModelsChartRefresh.addEventListener("change", onModelChartControlsChange);
}

async function loadAdmin() {
  if (adminUsersLoading) adminUsersLoading.classList.remove("hidden");
  if (adminUsersError) adminUsersError.classList.add("hidden");
  if (adminUsersTableWrap) adminUsersTableWrap.classList.add("hidden");

  try {
    const data = await fetchAdminState();
    fillPlanSelect(createPlanSelect, "free");
    fillUsersFilterPlans(data.plans);
    renderUsers(data.users);
    renderPlansList(data.plans);
    renderModels(data.models);
    applyFeatures(data.features);
    const currentPanel = document.documentElement.getAttribute("data-admin-panel");
    if (currentPanel === "extended-models") renderExtendedModels(data.extended_models);
    if (currentPanel === "image-generation") renderImageGeneration(data.image_generation);
    if (adminUsersLoading) adminUsersLoading.classList.add("hidden");
    if (adminUsersTableWrap) adminUsersTableWrap.classList.remove("hidden");
  } catch (err) {
    if (adminUsersLoading) adminUsersLoading.classList.add("hidden");
    if (adminUsersError) {
      adminUsersError.textContent = err.message;
      adminUsersError.classList.remove("hidden");
    }
  }
}

if (adminUserCreateForm) {
  adminUserCreateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminUserCreateMsg) adminUserCreateMsg.classList.add("hidden");
    try {
      const created = await createAdminUser();
      showAdminMsg(
        adminUserCreateMsg,
        `ユーザー「${created.username}」を追加しました`,
        false
      );
    } catch (err) {
      showAdminMsg(adminUserCreateMsg, err.message, true);
    }
  });
}

if (adminUsersBody) {
  adminUsersBody.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="open"]');
    if (!btn) return;
    const tr = btn.closest("tr");
    if (!tr?.dataset.username) return;
    openUserDetail(tr.dataset.username);
  });
}

function onUsersFilterChange() {
  renderUsers(adminState?.users || []);
}

adminUsersSearch?.addEventListener("input", (e) => {
  usersFilterQuery = e.target.value || "";
  onUsersFilterChange();
});
adminUsersFilterPlan?.addEventListener("change", onUsersFilterChange);
adminUsersFilterBilling?.addEventListener("change", onUsersFilterChange);
adminUsersFilterStatus?.addEventListener("change", onUsersFilterChange);

document.getElementById("detailBalanceAdjustBtn")?.addEventListener("click", async () => {
  if (!currentDetailUser) return;
  const amount = Number(document.getElementById("detailBalanceAdjustAmount")?.value || 0);
  const note = document.getElementById("detailBalanceAdjustNote")?.value.trim() || "";
  if (!amount) {
    showAdminMsg(adminUserDetailMsg, "調整金額を入力してください", true);
    return;
  }
  try {
    const res = await fetch(
      `/api/admin/users/${encodeURIComponent(currentDetailUser.username)}/balance-adjustment`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount_jpy: amount, note }),
      }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "残高調整に失敗しました");
    fillUserDetail(data.user);
    if (adminState?.users) {
      const idx = adminState.users.findIndex((u) => u.username === data.user.username);
      const summary = adminUserListSummary(data.user);
      if (idx >= 0) adminState.users[idx] = summary;
      renderUsers(adminState.users);
    }
    document.getElementById("detailBalanceAdjustAmount").value = "";
    document.getElementById("detailBalanceAdjustNote").value = "";
    showAdminMsg(adminUserDetailMsg, "残高を調整しました", false);
  } catch (err) {
    showAdminMsg(adminUserDetailMsg, err.message, true);
  }
});

detailBillingEventsLoad?.addEventListener("click", async () => {
  if (!currentDetailUser) return;
  try {
    await loadUserBillingEvents(currentDetailUser.username);
  } catch (err) {
    showAdminMsg(adminUserDetailMsg, err.message, true);
  }
});

if (adminUserDetailBack) {
  adminUserDetailBack.addEventListener("click", () => closeUserDetail());
}

if (detailPaymentAdd) {
  detailPaymentAdd.addEventListener("click", () => {
    const row = createPaymentRow({
      id: newUuid(),
      date: new Date().toISOString().slice(0, 10),
      amount: 0,
      method: "管理者",
      status: "paid",
    });
    detailPaymentsBody?.appendChild(row);
  });
}

if (detailPaymentsBody) {
  detailPaymentsBody.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="remove-payment"]');
    if (!btn) return;
    btn.closest("tr")?.remove();
  });
}

if (adminUserDetailForm) {
  adminUserDetailForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminUserDetailMsg) adminUserDetailMsg.classList.add("hidden");
    try {
      await saveUserDetail();
      showAdminMsg(adminUserDetailMsg, "保存しました", false);
    } catch (err) {
      showAdminMsg(adminUserDetailMsg, err.message, true);
    }
  });
}

document.getElementById("detailUsageResetBtn")?.addEventListener("click", async () => {
  if (!currentDetailUser) return;
  if (adminUserDetailMsg) adminUserDetailMsg.classList.add("hidden");
  try {
    const ok = await window.NexNotify?.confirm(
      "現在の利用枠の利用量を 0 にリセットしますか？",
      { confirmLabel: "リセット" }
    );
    if (!ok) return;
    const res = await fetch(
      `/api/admin/users/${encodeURIComponent(currentDetailUser.username)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usage_reset: true }),
      }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "リセットに失敗しました");
    fillUserDetail(data.user);
    showAdminMsg(adminUserDetailMsg, "利用量をリセットしました", false);
  } catch (err) {
    showAdminMsg(adminUserDetailMsg, err.message, true);
  }
});

document.getElementById("detailAddEntitlementBtn")?.addEventListener("click", async () => {
  if (!currentDetailUser) return;
  if (adminUserDetailMsg) adminUserDetailMsg.classList.add("hidden");
  try {
    const planId = document.getElementById("detailAddEntitlementPlan")?.value;
    const quantity = Number(document.getElementById("detailAddEntitlementQty")?.value || 1);
    const months = Number(document.getElementById("detailAddEntitlementMonths")?.value || 1);
    const res = await fetch(
      `/api/admin/users/${encodeURIComponent(currentDetailUser.username)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          add_entitlement: {
            plan_id: planId,
            quantity: Math.max(1, quantity),
            months: Math.max(1, months),
          },
        }),
      }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "枠の追加に失敗しました");
    fillUserDetail(data.user);
    showAdminMsg(adminUserDetailMsg, "プラン枠を追加しました", false);
  } catch (err) {
    showAdminMsg(adminUserDetailMsg, err.message, true);
  }
});

document.getElementById("detailBlocked")?.addEventListener("change", (e) => {
  if (!detailDeleteUser || currentDetailUser?.role === "admin") return;
  detailDeleteUser.disabled = e.target.checked;
  detailDeleteUser.title = e.target.checked ? "利用停止中は削除できません" : "";
});

if (detailDeleteUser) {
  detailDeleteUser.addEventListener("click", async () => {
    if (!currentDetailUser || currentDetailUser.blocked) return;
    try {
      await deleteUser(currentDetailUser.username);
      if (adminState) {
        adminState.users = adminState.users.filter(
          (u) => u.username !== currentDetailUser.username
        );
      }
      closeUserDetail();
      renderUsers(adminState?.users || []);
    } catch (err) {
      showAdminMsg(adminUserDetailMsg, err.message, true);
    }
  });
}

const adminOcrEnabled = document.getElementById("adminOcrEnabled");
const adminOcrEngine = document.getElementById("adminOcrEngine");
const adminOcrEngineHint = document.getElementById("adminOcrEngineHint");
const adminOcrAiModelField = document.getElementById("adminOcrAiModelField");
const adminOcrStructureModelField = document.getElementById("adminOcrStructureModelField");
const adminOcrStructureModel = document.getElementById("adminOcrStructureModel");
const adminOcrAnthropicCard = document.getElementById("adminOcrAnthropicCard");
const adminOcrAiSettingsCard = document.getElementById("adminOcrAiSettingsCard");
const adminOcrAiModelsListCard = document.getElementById("adminOcrAiModelsListCard");
const adminOcrDefaultModel = document.getElementById("adminOcrDefaultModel");
const adminAnthropicApiKey = document.getElementById("adminAnthropicApiKey");
const adminAnthropicKeyHint = document.getElementById("adminAnthropicKeyHint");
const adminOcrModelsBody = document.getElementById("adminOcrModelsBody");
const adminExtendedModelsForm = document.getElementById("adminExtendedModelsForm");
const adminExtendedModelsMsg = document.getElementById("adminExtendedModelsMsg");
const adminOcrGeneralForm = document.getElementById("adminOcrGeneralForm");
const adminOcrGeneralMsg = document.getElementById("adminOcrGeneralMsg");
const adminOcrModelAddForm = document.getElementById("adminOcrModelAddForm");
const adminOcrModelAddMsg = document.getElementById("adminOcrModelAddMsg");
const addOcrPlanChecks = document.getElementById("addOcrPlanChecks");

function renderOcrPlanChecks(container, selectedIds, namePrefix) {
  if (!container) return;
  const selected = new Set(selectedIds || PLAN_IDS);
  container.innerHTML = PLAN_IDS.map((pid) => {
    const id = `${namePrefix || "ocr-plan"}-${pid}`;
    const checked = selected.has(pid) ? " checked" : "";
    return `<label class="admin-ocr-plan-check"><input type="checkbox" name="${escapeAttr(namePrefix || "ocr-plan")}" value="${escapeAttr(pid)}" id="${escapeAttr(id)}"${checked}> ${escapeHtml(pid)}</label>`;
  }).join("");
}

function collectOcrPlanIdsFromRow(tr) {
  const ids = [];
  tr?.querySelectorAll(".admin-ocr-plan-toggle:checked").forEach((el) => {
    if (el.value) ids.push(el.value);
  });
  return ids;
}

function collectOcrPlanIdsFromAddForm() {
  const ids = [];
  addOcrPlanChecks?.querySelectorAll('input[type="checkbox"]:checked').forEach((el) => {
    if (el.value) ids.push(el.value);
  });
  return ids.length ? ids : [...PLAN_IDS];
}

function syncAdminOcrEngineUi(engine) {
  const isAi = engine !== "local";
  adminOcrAnthropicCard?.classList.toggle("hidden", !isAi);
  adminOcrAiModelField?.classList.toggle("hidden", !isAi);
  adminOcrAiSettingsCard?.classList.toggle("hidden", !isAi);
  adminOcrAiModelsListCard?.classList.toggle("hidden", !isAi);
  adminOcrStructureModelField?.classList.toggle("hidden", isAi);
  if (adminOcrEngineHint) {
    adminOcrEngineHint.textContent = isAi
      ? "AI OCR は Anthropic Vision を使用します（ユーザーは選択できません）。"
      : "ローカル OCR（scanner）で文字抽出し、構造化専用モデルが設問・意図を復元します。チャット AI とは分離されています。";
  }
}

function renderExtendedModels(payload) {
  if (!payload) return;
  const engine = payload.engine === "local" ? "local" : "ai";
  if (adminOcrEngine) {
    const options = payload.engine_options?.length
      ? payload.engine_options
      : [
          { id: "ai", label: "AI OCR（Anthropic Vision）" },
          { id: "local", label: "OCR（ローカル・非AI）" },
        ];
    adminOcrEngine.innerHTML = options
      .map(
        (opt) =>
          `<option value="${escapeAttr(opt.id)}"${opt.id === engine ? " selected" : ""}>${escapeHtml(opt.label || opt.id)}</option>`
      )
      .join("");
  }
  syncAdminOcrEngineUi(engine);
  if (adminOcrEnabled) adminOcrEnabled.checked = payload.enabled !== false;
  if (adminAnthropicKeyHint) {
    adminAnthropicKeyHint.textContent = payload.anthropic?.has_api_key
      ? "APIキーが設定済みです（未入力で保存すると維持）"
      : "APIキー未設定（ANTHROPIC_API_KEY または下記）";
  }
  const models = payload.models || [];
  if (adminOcrDefaultModel) {
    adminOcrDefaultModel.innerHTML = models
      .map(
        (m) =>
          `<option value="${escapeAttr(m.id)}"${m.id === payload.default_model_id ? " selected" : ""}>${escapeHtml(m.display_name || m.id)}</option>`
      )
      .join("");
  }
  const structureModels = payload.structure_model_options || [];
  if (adminOcrStructureModel) {
    const selectedStructure = payload.structure_model_id || "";
    adminOcrStructureModel.innerHTML =
      `<option value="">既定のチャットモデル</option>` +
      structureModels
        .map(
          (m) =>
            `<option value="${escapeAttr(m.id)}"${m.id === selectedStructure ? " selected" : ""}>${escapeHtml(m.label || m.id)}</option>`
        )
        .join("");
  }
  renderOcrPlanChecks(addOcrPlanChecks, PLAN_IDS, "add-ocr-plan");
  if (!adminOcrModelsBody) return;
  adminOcrModelsBody.innerHTML = "";
  models.forEach((m) => {
    const tr = document.createElement("tr");
    tr.dataset.modelId = m.id;
    const planChecks = PLAN_IDS.map((pid) => {
      const checked = (m.plan_ids || []).includes(pid) ? " checked" : "";
      return `<label class="admin-ocr-plan-check"><input type="checkbox" class="admin-ocr-plan-toggle" value="${escapeAttr(pid)}"${checked}> ${escapeHtml(pid)}</label>`;
    }).join("");
    tr.innerHTML = `
      <td><code>${escapeHtml(m.id)}</code></td>
      <td><input type="text" class="admin-inline-input" data-field="display_name" value="${escapeAttr(m.display_name || "")}"></td>
      <td><input type="text" class="admin-inline-input" data-field="api_model" value="${escapeAttr(m.api_model || "")}"></td>
      <td><input type="checkbox" data-field="enabled"${m.enabled !== false ? " checked" : ""}></td>
      <td class="admin-ocr-plans-cell">${planChecks}</td>
      <td><button type="button" class="admin-row-btn admin-row-btn--danger" data-action="delete-ocr-model">削除</button></td>
    `;
    adminOcrModelsBody.appendChild(tr);
  });
}

function collectExtendedModelsPayload() {
  const models = [];
  adminOcrModelsBody?.querySelectorAll("tr[data-model-id]").forEach((tr) => {
    const id = tr.dataset.modelId;
    if (!id) return;
    models.push({
      id,
      display_name: tr.querySelector('[data-field="display_name"]')?.value.trim() || id,
      api_model: tr.querySelector('[data-field="api_model"]')?.value.trim() || id,
      enabled: Boolean(tr.querySelector('[data-field="enabled"]')?.checked),
      plan_ids: collectOcrPlanIdsFromRow(tr),
      provider: "anthropic",
    });
  });
  const providers = {};
  const key = adminAnthropicApiKey?.value.trim();
  if (key) providers.anthropic = { api_key: key };
  return {
    ocr: {
      enabled: Boolean(adminOcrEnabled?.checked),
      engine: adminOcrEngine?.value === "local" ? "local" : "ai",
      structure_model_id: adminOcrStructureModel?.value || "",
      default_model_id: adminOcrDefaultModel?.value || "",
      models,
    },
    providers,
  };
}

if (adminOcrEngine) {
  adminOcrEngine.addEventListener("change", () => {
    syncAdminOcrEngineUi(adminOcrEngine.value === "local" ? "local" : "ai");
  });
}

async function loadExtendedModels() {
  const res = await fetch("/api/admin/extended-models");
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
  if (adminState) adminState.extended_models = data.extended_models;
  renderExtendedModels(data.extended_models);
}

if (adminOcrModelsBody) {
  adminOcrModelsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest('[data-action="delete-ocr-model"]');
    if (!btn) return;
    const tr = btn.closest("tr");
    const modelId = tr?.dataset.modelId;
    if (!modelId) return;
    const ocrOk = await window.NexNotify?.confirm(
      `OCRモデル「${modelId}」を削除しますか？`,
      { danger: true, confirmLabel: "削除" }
    );
    if (!ocrOk) return;
    try {
      const res = await fetch(
        `/api/admin/extended-models/ocr/${encodeURIComponent(modelId)}`,
        { method: "DELETE" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "削除に失敗しました");
      if (adminState) adminState.extended_models = data.extended_models;
      renderExtendedModels(data.extended_models);
    } catch (err) {
      showAdminMsg(adminExtendedModelsMsg, err.message, true);
    }
  });
}

async function saveExtendedModelsSettings(successMsgEl) {
  if (successMsgEl) successMsgEl.classList.add("hidden");
  const res = await fetch("/api/admin/extended-models", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectExtendedModelsPayload()),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  if (adminState) adminState.extended_models = data.extended_models;
  renderExtendedModels(data.extended_models);
  if (adminAnthropicApiKey) adminAnthropicApiKey.value = "";
  showAdminMsg(successMsgEl, "拡張モデル設定を保存しました", false);
}

if (adminOcrGeneralForm) {
  adminOcrGeneralForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await saveExtendedModelsSettings(adminOcrGeneralMsg);
    } catch (err) {
      showAdminMsg(adminOcrGeneralMsg, err.message, true);
    }
  });
}

if (adminExtendedModelsForm) {
  adminExtendedModelsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await saveExtendedModelsSettings(adminExtendedModelsMsg);
    } catch (err) {
      showAdminMsg(adminExtendedModelsMsg, err.message, true);
    }
  });
}

if (adminOcrModelAddForm) {
  adminOcrModelAddForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminOcrModelAddMsg) adminOcrModelAddMsg.classList.add("hidden");
    const payload = {
      id: document.getElementById("addOcrModelId")?.value.trim(),
      display_name: document.getElementById("addOcrDisplayName")?.value.trim(),
      api_model: document.getElementById("addOcrApiModel")?.value.trim(),
      provider: "anthropic",
      enabled: true,
      plan_ids: collectOcrPlanIdsFromAddForm(),
    };
    try {
      const res = await fetch("/api/admin/extended-models/ocr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "追加に失敗しました");
      if (adminState) adminState.extended_models = data.extended_models;
      renderExtendedModels(data.extended_models);
      adminOcrModelAddForm.reset();
      renderOcrPlanChecks(addOcrPlanChecks, PLAN_IDS, "add-ocr-plan");
      showAdminMsg(adminOcrModelAddMsg, "OCRモデルを追加しました", false);
    } catch (err) {
      showAdminMsg(adminOcrModelAddMsg, err.message, true);
    }
  });
}

const adminImageGenEnabled = document.getElementById("adminImageGenEnabled");
const adminImageGenDefaultModel = document.getElementById("adminImageGenDefaultModel");
const adminFluxApiKey = document.getElementById("adminFluxApiKey");
const adminFluxKeyHint = document.getElementById("adminFluxKeyHint");
const adminFluxBaseUrl = document.getElementById("adminFluxBaseUrl");
const adminImageModelsBody = document.getElementById("adminImageModelsBody");
const adminImageGenerationForm = document.getElementById("adminImageGenerationForm");
const adminImageGenerationMsg = document.getElementById("adminImageGenerationMsg");
const adminImageModelAddForm = document.getElementById("adminImageModelAddForm");
const adminImageModelAddMsg = document.getElementById("adminImageModelAddMsg");
const addImagePlanChecks = document.getElementById("addImagePlanChecks");
const addImageApiModelHints = document.getElementById("addImageApiModelHints");

function renderImagePlanChecks(container, selectedIds, namePrefix) {
  if (!container) return;
  const selected = new Set(selectedIds || PLAN_IDS);
  container.innerHTML = PLAN_IDS.map((pid) => {
    const id = `${namePrefix || "image-plan"}-${pid}`;
    const checked = selected.has(pid) ? " checked" : "";
    return `<label class="admin-ocr-plan-check"><input type="checkbox" name="${escapeAttr(namePrefix || "image-plan")}" value="${escapeAttr(pid)}" id="${escapeAttr(id)}"${checked}> ${escapeHtml(pid)}</label>`;
  }).join("");
}

function collectImagePlanIdsFromRow(tr) {
  const ids = [];
  tr?.querySelectorAll(".admin-image-plan-toggle:checked").forEach((el) => {
    if (el.value) ids.push(el.value);
  });
  return ids;
}

function collectImagePlanIdsFromAddForm() {
  const ids = [];
  addImagePlanChecks?.querySelectorAll('input[type="checkbox"]:checked').forEach((el) => {
    if (el.value) ids.push(el.value);
  });
  return ids;
}

const IMAGE_ADD_DEFAULT_PLANS = ["plus", "pro", "pro_plus", "max", "enterprise"];

function renderImageGeneration(payload) {
  if (!payload) return;
  if (adminImageGenEnabled) adminImageGenEnabled.checked = payload.enabled !== false;
  const flux = payload.provider || {};
  if (adminFluxKeyHint) {
    adminFluxKeyHint.textContent = flux.has_api_key
      ? "APIトークンが設定済みです（未入力で保存すると維持）"
      : `APIトークン未設定（${flux.api_key_env || "BFL_API_KEY"} または下記）`;
  }
  if (adminFluxBaseUrl) {
    adminFluxBaseUrl.value = flux.base_url || "https://api.bfl.ai";
  }
  if (addImageApiModelHints && payload.api_model_hints?.length) {
    addImageApiModelHints.innerHTML = payload.api_model_hints
      .map((h) => `<option value="${escapeAttr(h)}"></option>`)
      .join("");
  }
  const models = payload.models || [];
  if (adminImageGenDefaultModel) {
    adminImageGenDefaultModel.innerHTML = models
      .map(
        (m) =>
          `<option value="${escapeAttr(m.id)}"${m.id === payload.default_model_id ? " selected" : ""}>${escapeHtml(m.display_name || m.id)}</option>`
      )
      .join("");
  }
  renderImagePlanChecks(addImagePlanChecks, IMAGE_ADD_DEFAULT_PLANS, "add-image-plan");
  if (!adminImageModelsBody) return;
  adminImageModelsBody.innerHTML = "";
  models.forEach((m) => {
    const tr = document.createElement("tr");
    tr.dataset.modelId = m.id;
    const planChecks = PLAN_IDS.map((pid) => {
      const checked = (m.plan_ids || []).includes(pid) ? " checked" : "";
      return `<label class="admin-ocr-plan-check"><input type="checkbox" class="admin-image-plan-toggle" value="${escapeAttr(pid)}"${checked}> ${escapeHtml(pid)}</label>`;
    }).join("");
    tr.innerHTML = `
      <td><code>${escapeHtml(m.id)}</code></td>
      <td><input type="text" class="admin-inline-input" data-field="display_name" value="${escapeAttr(m.display_name || "")}"></td>
      <td><input type="text" class="admin-inline-input" data-field="api_model" value="${escapeAttr(m.api_model || "")}" list="addImageApiModelHints"></td>
      <td><input type="number" class="admin-inline-input admin-inline-input--num" data-field="cost_usd_per_image" step="0.0001" min="0" value="${escapeAttr(String(m.cost_usd_per_image ?? 0))}"></td>
      <td><input type="number" class="admin-inline-input admin-inline-input--num" data-field="price_usd_per_image" step="0.0001" min="0" value="${escapeAttr(String(m.price_usd_per_image ?? 0))}"></td>
      <td><input type="checkbox" data-field="enabled"${m.enabled !== false ? " checked" : ""}></td>
      <td class="admin-ocr-plans-cell">${planChecks}</td>
      <td><button type="button" class="admin-row-btn admin-row-btn--danger" data-action="delete-image-model">削除</button></td>
    `;
    adminImageModelsBody.appendChild(tr);
  });
}

function collectImageGenerationPayload() {
  const models = [];
  adminImageModelsBody?.querySelectorAll("tr[data-model-id]").forEach((tr) => {
    const id = tr.dataset.modelId;
    if (!id) return;
    models.push({
      id,
      display_name: tr.querySelector('[data-field="display_name"]')?.value.trim() || id,
      api_model: tr.querySelector('[data-field="api_model"]')?.value.trim() || id,
      provider: "flux_bfl",
      cost_usd_per_image: Number(tr.querySelector('[data-field="cost_usd_per_image"]')?.value),
      price_usd_per_image: Number(tr.querySelector('[data-field="price_usd_per_image"]')?.value),
      enabled: Boolean(tr.querySelector('[data-field="enabled"]')?.checked),
      plan_ids: collectImagePlanIdsFromRow(tr),
    });
  });
  const providers = { flux_bfl: {} };
  const key = adminFluxApiKey?.value.trim();
  if (key) providers.flux_bfl.api_key = key;
  const baseUrl = adminFluxBaseUrl?.value.trim();
  if (baseUrl) providers.flux_bfl.base_url = baseUrl;
  return {
    enabled: Boolean(adminImageGenEnabled?.checked),
    default_model_id: adminImageGenDefaultModel?.value || "",
    models,
    providers,
  };
}

async function loadImageGeneration() {
  const res = await fetch("/api/admin/image-generation");
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
  if (adminState) adminState.image_generation = data.image_generation;
  renderImageGeneration(data.image_generation);
}

if (adminImageModelsBody) {
  adminImageModelsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest('[data-action="delete-image-model"]');
    if (!btn) return;
    const tr = btn.closest("tr");
    const modelId = tr?.dataset.modelId;
    if (!modelId) return;
    const ok = await window.NexNotify?.confirm(
      `画像生成モデル「${modelId}」を削除しますか？`,
      { danger: true, confirmLabel: "削除" }
    );
    if (!ok) return;
    try {
      const res = await fetch(
        `/api/admin/image-generation/models/${encodeURIComponent(modelId)}`,
        { method: "DELETE" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "削除に失敗しました");
      if (adminState) adminState.image_generation = data.image_generation;
      renderImageGeneration(data.image_generation);
    } catch (err) {
      showAdminMsg(adminImageGenerationMsg, err.message, true);
    }
  });
}

if (adminImageGenerationForm) {
  adminImageGenerationForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminImageGenerationMsg) adminImageGenerationMsg.classList.add("hidden");
    try {
      const res = await fetch("/api/admin/image-generation", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectImageGenerationPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      if (adminState) adminState.image_generation = data.image_generation;
      renderImageGeneration(data.image_generation);
      if (adminFluxApiKey) adminFluxApiKey.value = "";
      showAdminMsg(adminImageGenerationMsg, "画像生成設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminImageGenerationMsg, err.message, true);
    }
  });
}

if (adminImageModelAddForm) {
  adminImageModelAddForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminImageModelAddMsg) adminImageModelAddMsg.classList.add("hidden");
    const planIds = collectImagePlanIdsFromAddForm();
    if (!planIds.length) {
      showAdminMsg(adminImageModelAddMsg, "提供プランを1つ以上選択してください", true);
      return;
    }
    const payload = {
      id: document.getElementById("addImageModelId")?.value.trim(),
      display_name: document.getElementById("addImageDisplayName")?.value.trim(),
      api_model: document.getElementById("addImageApiModel")?.value.trim(),
      provider: "flux_bfl",
      cost_usd_per_image: Number(document.getElementById("addImageCostUsd")?.value),
      price_usd_per_image: Number(document.getElementById("addImagePriceUsd")?.value),
      enabled: true,
      plan_ids: planIds,
    };
    try {
      const res = await fetch("/api/admin/image-generation/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "追加に失敗しました");
      if (adminState) adminState.image_generation = data.image_generation;
      renderImageGeneration(data.image_generation);
      adminImageModelAddForm.reset();
      const costEl = document.getElementById("addImageCostUsd");
      const priceEl = document.getElementById("addImagePriceUsd");
      if (costEl) costEl.value = "0.04";
      if (priceEl) priceEl.value = "0.08";
      renderImagePlanChecks(addImagePlanChecks, IMAGE_ADD_DEFAULT_PLANS, "add-image-plan");
      showAdminMsg(adminImageModelAddMsg, "画像生成モデルを追加しました", false);
    } catch (err) {
      showAdminMsg(adminImageModelAddMsg, err.message, true);
    }
  });
}

if (adminModelAddForm) {
  adminModelAddForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminModelAddMsg) adminModelAddMsg.classList.add("hidden");
    const payload = {
      id: document.getElementById("addModelId")?.value.trim(),
      api_id: document.getElementById("addModelApiId")?.value.trim() || undefined,
      display_name: document.getElementById("addModelDisplayName")?.value.trim(),
      tier: document.getElementById("addModelTier")?.value.trim() || undefined,
      provider: addModelProvider?.value || "deepseek",
      api_model: document.getElementById("addModelApiModel")?.value.trim() || undefined,
      agent_profile: document.getElementById("addModelAgentProfile")?.value || "standard",
      cost_input_usd_per_1m: Number(document.getElementById("addModelCostIn")?.value),
      cost_output_usd_per_1m: Number(document.getElementById("addModelCostOut")?.value),
      price_input_usd_per_1m: Number(document.getElementById("addModelPriceIn")?.value),
      price_output_usd_per_1m: Number(document.getElementById("addModelPriceOut")?.value),
      cost_input_cache_hit_usd_per_1m: Number(
        document.getElementById("addModelCostCacheIn")?.value
      ),
      price_input_cache_hit_usd_per_1m: Number(
        document.getElementById("addModelPriceCacheIn")?.value
      ),
      enabled: true,
    };
    try {
      const res = await fetch("/api/admin/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "追加に失敗しました");
      if (adminState) adminState.models = data.models;
      renderModels(data.models);
      adminModelAddForm.reset();
      if (addModelProvider && data.models?.provider_options) {
        fillProviderSelect(addModelProvider, data.models.provider_options, "cerebras");
      }
      showAdminMsg(adminModelAddMsg, "モデルを追加しました", false);
    } catch (err) {
      showAdminMsg(adminModelAddMsg, err.message, true);
    }
  });
}

if (adminModelsForm) {
  adminModelsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminModelsMsg) adminModelsMsg.classList.add("hidden");
    const body = {
      models: collectModelsPayload(),
      providers: collectProvidersPayload(),
      default_model: adminDefaultModel?.value || "",
    };
    try {
      const res = await fetch("/api/admin/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      if (adminState) adminState.models = data.models;
      renderModels(data.models);
      showAdminMsg(adminModelsMsg, "設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminModelsMsg, err.message, true);
    }
  });
}

if (adminPlansBody) {
  adminPlansBody.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-action="open-plan"]');
    if (!btn) return;
    const tr = btn.closest("tr");
    if (!tr?.dataset.planId) return;
    openPlanDetail(tr.dataset.planId);
  });
}

if (adminPlanDetailBack) {
  adminPlanDetailBack.addEventListener("click", () => closePlanDetail());
}

if (adminPlanDetailForm) {
  adminPlanDetailForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminPlanDetailMsg) adminPlanDetailMsg.classList.add("hidden");
    try {
      await savePlanDetail();
      showAdminMsg(adminPlanDetailMsg, "プラン詳細を保存しました", false);
    } catch (err) {
      showAdminMsg(adminPlanDetailMsg, err.message, true);
    }
  });
}

if (adminPlanFeaturesForm) {
  adminPlanFeaturesForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminPlanFeaturesMsg) adminPlanFeaturesMsg.classList.add("hidden");
    try {
      await savePlanFeatures();
      showAdminMsg(adminPlanFeaturesMsg, "プラン機能を保存しました", false);
    } catch (err) {
      showAdminMsg(adminPlanFeaturesMsg, err.message, true);
    }
  });
}

if (adminFeaturesForm) {
  adminFeaturesForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminFeaturesMsg) adminFeaturesMsg.classList.add("hidden");
    const features = {};
    adminFeaturesForm.querySelectorAll("[data-feature]").forEach((input) => {
      features[input.dataset.feature] = input.checked;
    });
    try {
      const res = await fetch("/api/admin/features", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      if (adminState) adminState.features = data.features;
      window.applySystemFeatures?.(data.features);
      showAdminMsg(adminFeaturesMsg, "機能設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminFeaturesMsg, err.message, true);
    }
  });
}

const adminCouponsLoading = document.getElementById("adminCouponsLoading");
const adminCouponsError = document.getElementById("adminCouponsError");
const adminCouponsTableWrap = document.getElementById("adminCouponsTableWrap");
const adminCouponsBody = document.getElementById("adminCouponsBody");
const adminCouponCreateForm = document.getElementById("adminCouponCreateForm");
const adminCouponCreateMsg = document.getElementById("adminCouponCreateMsg");
const couponTypeSelect = document.getElementById("couponType");
const couponBalanceField = document.getElementById("couponBalanceField");
const couponPlanField = document.getElementById("couponPlanField");
const couponPlanHoursField = document.getElementById("couponPlanHoursField");
const couponPurchaseField = document.getElementById("couponPurchaseField");
const couponPurchasePlanField = document.getElementById("couponPurchasePlanField");

function updateCouponTypeFields() {
  const type = couponTypeSelect?.value || "balance";
  const isPlan = type === "plan";
  const isPurchase = type === "purchase";
  couponBalanceField?.classList.toggle("hidden", isPlan || isPurchase);
  couponPlanField?.classList.toggle("hidden", !isPlan);
  couponPlanHoursField?.classList.toggle("hidden", !isPlan);
  couponPurchaseField?.classList.toggle("hidden", !isPurchase);
  couponPurchasePlanField?.classList.toggle("hidden", !isPurchase);
}

couponTypeSelect?.addEventListener("change", updateCouponTypeFields);
updateCouponTypeFields();

function formatCouponExpires(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP");
}

function couponStatusLabel(status) {
  const map = {
    active: "有効",
    disabled: "無効",
    expired: "期限切れ",
    exhausted: "上限到達",
  };
  return map[status] || status;
}

function renderCoupons(coupons) {
  if (!adminCouponsBody) return;
  adminCouponsBody.innerHTML = "";
  coupons.forEach((c) => {
    const tr = document.createElement("tr");
    tr.dataset.couponId = c.id;
    const maxLabel = c.max_uses == null ? "∞" : c.max_uses;
    const canDisable = c.enabled && c.status !== "expired";
    const canEnable = !c.enabled;
    tr.innerHTML = `
      <td><code>${escapeHtml(c.code)}</code></td>
      <td>${escapeHtml(c.benefit_label)}</td>
      <td>${c.used_count} / ${maxLabel}</td>
      <td>${escapeHtml(formatCouponExpires(c.expires_at))}</td>
      <td><span class="admin-coupon-status admin-coupon-status--${escapeHtml(c.status)}">${escapeHtml(couponStatusLabel(c.status))}</span></td>
      <td class="admin-actions-cell">
        ${canDisable ? '<button type="button" class="admin-row-btn" data-action="disable-coupon">無効化</button>' : ""}
        ${canEnable ? '<button type="button" class="admin-row-btn" data-action="enable-coupon">有効化</button>' : ""}
        <button type="button" class="admin-row-btn admin-row-btn--danger" data-action="delete-coupon">削除</button>
      </td>
    `;
    adminCouponsBody.appendChild(tr);
  });
}

async function loadCoupons() {
  if (!adminCouponsLoading) return;
  adminCouponsLoading.classList.remove("hidden");
  adminCouponsError?.classList.add("hidden");
  adminCouponsTableWrap?.classList.add("hidden");

  try {
    const res = await fetch("/api/admin/coupons");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    renderCoupons(data.coupons || []);
    adminCouponsLoading.classList.add("hidden");
    adminCouponsTableWrap?.classList.remove("hidden");
  } catch (err) {
    adminCouponsLoading.classList.add("hidden");
    if (adminCouponsError) {
      adminCouponsError.textContent = err.message;
      adminCouponsError.classList.remove("hidden");
    }
  }
}

async function setCouponEnabled(couponId, enabled) {
  const res = await fetch(`/api/admin/coupons/${encodeURIComponent(couponId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "更新に失敗しました");
}

async function deleteCoupon(couponId, code) {
  const label = code ? `「${code}」` : "このクーポン";
  const ok = await window.NexNotify?.confirm(
    `${label}を削除しますか？利用履歴も消えます。`,
    { danger: true, confirmLabel: "削除" }
  );
  if (!ok) return false;
  const res = await fetch(`/api/admin/coupons/${encodeURIComponent(couponId)}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "削除に失敗しました");
  return true;
}

if (adminCouponsBody) {
  adminCouponsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const tr = btn.closest("tr");
    const couponId = tr?.dataset.couponId;
    if (!couponId) return;
    const code = tr.querySelector("code")?.textContent?.trim() || "";
    btn.disabled = true;
    try {
      let changed = false;
      if (btn.dataset.action === "disable-coupon") {
        await setCouponEnabled(couponId, false);
        changed = true;
      } else if (btn.dataset.action === "enable-coupon") {
        await setCouponEnabled(couponId, true);
        changed = true;
      } else if (btn.dataset.action === "delete-coupon") {
        changed = await deleteCoupon(couponId, code);
      }
      if (changed) await loadCoupons();
    } catch (err) {
      showAdminMsg(adminCouponsError, err.message, true);
    } finally {
      btn.disabled = false;
    }
  });
}

if (adminCouponCreateForm) {
  adminCouponCreateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminCouponCreateMsg) adminCouponCreateMsg.classList.add("hidden");

    const type = couponTypeSelect?.value || "balance";
    const payload = {
      code: document.getElementById("couponCode")?.value,
      type,
      expires_at: document.getElementById("couponExpiresAt")?.value,
      max_uses: document.getElementById("couponMaxUses")?.value,
      enabled: true,
    };
    if (type === "balance") {
      payload.balance_amount = document.getElementById("couponBalanceAmount")?.value;
    } else if (type === "plan") {
      payload.plan_id = document.getElementById("couponPlanId")?.value;
      payload.plan_hours = document.getElementById("couponPlanHours")?.value;
    } else {
      payload.discount_jpy = document.getElementById("couponPurchaseDiscount")?.value;
      payload.purchase_plan_id = document.getElementById("couponPurchasePlanId")?.value;
    }

    try {
      const res = await fetch("/api/admin/coupons", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "作成に失敗しました");
      adminCouponCreateForm.reset();
      updateCouponTypeFields();
      showAdminMsg(adminCouponCreateMsg, "クーポンを追加しました", false);
      await loadCoupons();
    } catch (err) {
      showAdminMsg(adminCouponCreateMsg, err.message, true);
    }
  });
}

const adminPaypalForm = document.getElementById("adminPaypalForm");
const adminPaypalMsg = document.getElementById("adminPaypalMsg");
const adminPaypalStatus = document.getElementById("adminPaypalStatus");
const adminPaypalSecretHint = document.getElementById("adminPaypalSecretHint");

function fillPaypalForm(paypal) {
  const clientIdEl = document.getElementById("adminPaypalClientId");
  const modeEl = document.getElementById("adminPaypalMode");
  const secretEl = document.getElementById("adminPaypalSecret");
  const webhookEl = document.getElementById("adminPaypalWebhookId");
  if (clientIdEl) clientIdEl.value = paypal?.client_id || "";
  if (modeEl) modeEl.value = paypal?.mode === "live" ? "live" : "sandbox";
  if (secretEl) secretEl.value = "";
  if (webhookEl) webhookEl.value = paypal?.webhook_id || "";

  if (adminPaypalStatus) {
    let status = "";
    if (paypal?.configured) {
      status = "状態: 設定済み（決済可能）";
      if (paypal.env_fallback) status += " ※ .env から読み込み中";
      if (paypal.webhook_id_set) status += " · Webhook 設定済み";
      else status += " · Webhook 未設定（サブスク自動反映なし）";
    } else {
      status = "状態: 未設定（Client ID と Secret が必要です）";
    }
    adminPaypalStatus.textContent = status;
    adminPaypalStatus.classList.remove("hidden");
    adminPaypalStatus.classList.toggle("error", !paypal?.configured);
    adminPaypalStatus.classList.toggle("success", Boolean(paypal?.configured));
  }
  if (adminPaypalSecretHint) {
    adminPaypalSecretHint.textContent = paypal?.secret_set
      ? "Secret は保存済みです。変更する場合のみ入力してください。"
      : "Secret を入力して保存してください。";
  }
}

const adminSubscriptionLoading = document.getElementById("adminSubscriptionLoading");
const adminSubscriptionError = document.getElementById("adminSubscriptionError");
const adminSubscriptionOverviewWrap = document.getElementById("adminSubscriptionOverviewWrap");
const adminSubscriptionOverviewBody = document.getElementById("adminSubscriptionOverviewBody");
const adminSubscriptionForm = document.getElementById("adminSubscriptionForm");
const adminSubscriptionMsg = document.getElementById("adminSubscriptionMsg");
const adminSubscriptionMode = document.getElementById("adminSubscriptionMode");
const SUBSCRIPTION_PLAN_IDS = ["plus", "pro", "pro_plus", "max"];
const SUBSCRIPTION_URL_INPUTS = {
  plus: document.getElementById("adminPlanUrlPlus"),
  pro: document.getElementById("adminPlanUrlPro"),
  pro_plus: document.getElementById("adminPlanUrlProPlus"),
  max: document.getElementById("adminPlanUrlMax"),
};

function fillSubscriptionForm(data) {
  const urls = data?.plan_urls || {};
  SUBSCRIPTION_PLAN_IDS.forEach((id) => {
    const input = SUBSCRIPTION_URL_INPUTS[id];
    if (input) input.value = urls[id] || "";
  });
  if (adminSubscriptionMode) {
    const mode = data?.mode_label || data?.mode || "—";
    const api = data?.paypal_configured
      ? "残高チャージ API: 設定済み"
      : "残高チャージ API: 未設定（PayPal設定タブで Client ID / Secret を設定）";
    adminSubscriptionMode.textContent = `PayPal モード: ${mode} · ${api}`;
    adminSubscriptionMode.classList.toggle("success", Boolean(data?.paypal_configured));
    adminSubscriptionMode.classList.toggle("error", !data?.paypal_configured);
  }
  renderSubscriptionOverview(data?.plans || []);
}

function renderSubscriptionOverview(plans) {
  if (!adminSubscriptionOverviewBody) return;
  adminSubscriptionOverviewBody.innerHTML = "";
  plans.forEach((plan) => {
    const tr = document.createElement("tr");
    const usd =
      plan.price_usd == null ? "—" : `$${Number(plan.price_usd).toLocaleString("en-US")}/月`;
    const status = plan.url_configured
      ? '<span class="admin-status">設定済み</span>'
      : '<span class="admin-status admin-status--blocked">未設定</span>';
    tr.innerHTML = `
      <td>${escapeHtml(plan.name)} <span class="settings-hint">(${escapeHtml(plan.id)})</span></td>
      <td>${escapeHtml(usd)}</td>
      <td>${status}</td>
    `;
    adminSubscriptionOverviewBody.appendChild(tr);
  });
  adminSubscriptionLoading?.classList.add("hidden");
  adminSubscriptionError?.classList.add("hidden");
  adminSubscriptionOverviewWrap?.classList.toggle("hidden", plans.length === 0);
}

async function loadSubscriptionSettings() {
  adminSubscriptionLoading?.classList.remove("hidden");
  adminSubscriptionOverviewWrap?.classList.add("hidden");
  adminSubscriptionError?.classList.add("hidden");
  if (adminSubscriptionMsg) adminSubscriptionMsg.classList.add("hidden");
  try {
    const res = await fetch("/api/admin/subscriptions");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillSubscriptionForm(data);
  } catch (err) {
    adminSubscriptionLoading?.classList.add("hidden");
    if (adminSubscriptionError) {
      adminSubscriptionError.textContent = err.message;
      adminSubscriptionError.classList.remove("hidden");
    }
  }
}

async function createPaypalPlanViaApi({ planId, all = false }) {
  if (adminSubscriptionMsg) adminSubscriptionMsg.classList.add("hidden");
  const payload = all ? { all: true } : { plan_id: planId };
  const res = await fetch("/api/admin/subscriptions/create-paypal-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail =
      data.errors?.map((e) => `${e.plan_id}: ${e.error}`).join(" · ") || data.error;
    throw new Error(detail || "PayPal プランの作成に失敗しました");
  }
  fillSubscriptionForm(data);
  const created = (data.created || [])
    .map((row) => `${row.plan_id} (${row.billing_plan_id})`)
    .join(", ");
  const partial =
    data.errors?.length > 0
      ? ` · 一部失敗: ${data.errors.map((e) => `${e.plan_id}: ${e.error}`).join(" · ")}`
      : "";
  showAdminMsg(
    adminSubscriptionMsg,
    created ? `PayPal プランを作成しました: ${created}${partial}` : "PayPal プランを作成しました",
    Boolean(data.errors?.length)
  );
}

const SUBSCRIPTION_PLAN_LABELS = {
  plus: "PASS+（plus）",
  pro: "PASS Pro（pro）",
  pro_plus: "PASS Pro+（pro_plus）",
  max: "PASS MAX（max）",
};

async function confirmDeletePaypalPlan({ planId, all = false }) {
  const message = all
    ? "全プランの PayPal 請求プランを無効化し、保存済み URL / API ID をクリアします。よろしいですか？"
    : `「${SUBSCRIPTION_PLAN_LABELS[planId] || planId}」の PayPal 請求プランを無効化し、保存済み URL / API ID をクリアします。よろしいですか？`;
  return Boolean(
    await window.NexNotify?.confirm(message, {
      title: "PayPal プラン削除",
      confirmLabel: "削除",
      danger: true,
    })
  );
}

async function deletePaypalPlanViaApi({ planId, all = false }) {
  if (adminSubscriptionMsg) adminSubscriptionMsg.classList.add("hidden");
  const payload = all ? { all: true } : { plan_id: planId };
  const res = await fetch("/api/admin/subscriptions/delete-paypal-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail =
      data.errors?.map((e) => `${e.plan_id}: ${e.error}`).join(" · ") || data.error;
    throw new Error(detail || "PayPal プランの削除に失敗しました");
  }
  fillSubscriptionForm(data);
  const removed = (data.deleted || [])
    .map((row) => {
      const label = SUBSCRIPTION_PLAN_LABELS[row.plan_id] || row.plan_id;
      if (row.paypal_deactivated && row.billing_plan_id) {
        return `${label}（${row.billing_plan_id} を無効化）`;
      }
      return `${label}（ローカル URL のみクリア）`;
    })
    .join(", ");
  const partial =
    data.errors?.length > 0
      ? ` · 一部失敗: ${data.errors.map((e) => `${e.plan_id}: ${e.error}`).join(" · ")}`
      : "";
  showAdminMsg(
    adminSubscriptionMsg,
    removed ? `PayPal プランを削除しました: ${removed}${partial}` : "PayPal プランを削除しました",
    Boolean(data.errors?.length)
  );
}

document.querySelectorAll(".admin-paypal-sync-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const planId = btn.dataset.planId;
    btn.disabled = true;
    try {
      await createPaypalPlanViaApi({ planId });
    } catch (err) {
      showAdminMsg(adminSubscriptionMsg, err.message, true);
    } finally {
      btn.disabled = false;
    }
  });
});

const adminPaypalSyncAllBtn = document.getElementById("adminPaypalSyncAllBtn");
if (adminPaypalSyncAllBtn) {
  adminPaypalSyncAllBtn.addEventListener("click", async () => {
    adminPaypalSyncAllBtn.disabled = true;
    try {
      await createPaypalPlanViaApi({ all: true });
    } catch (err) {
      showAdminMsg(adminSubscriptionMsg, err.message, true);
    } finally {
      adminPaypalSyncAllBtn.disabled = false;
    }
  });
}

document.querySelectorAll(".admin-paypal-delete-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const planId = btn.dataset.planId;
    const ok = await confirmDeletePaypalPlan({ planId });
    if (!ok) return;
    btn.disabled = true;
    try {
      await deletePaypalPlanViaApi({ planId });
    } catch (err) {
      showAdminMsg(adminSubscriptionMsg, err.message, true);
    } finally {
      btn.disabled = false;
    }
  });
});

const adminPaypalDeleteAllBtn = document.getElementById("adminPaypalDeleteAllBtn");
if (adminPaypalDeleteAllBtn) {
  adminPaypalDeleteAllBtn.addEventListener("click", async () => {
    const ok = await confirmDeletePaypalPlan({ all: true });
    if (!ok) return;
    adminPaypalDeleteAllBtn.disabled = true;
    try {
      await deletePaypalPlanViaApi({ all: true });
    } catch (err) {
      showAdminMsg(adminSubscriptionMsg, err.message, true);
    } finally {
      adminPaypalDeleteAllBtn.disabled = false;
    }
  });
}

if (adminSubscriptionForm) {
  adminSubscriptionForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminSubscriptionMsg) adminSubscriptionMsg.classList.add("hidden");
    const plan_urls = {};
    SUBSCRIPTION_PLAN_IDS.forEach((id) => {
      plan_urls[id] = SUBSCRIPTION_URL_INPUTS[id]?.value.trim() || "";
    });
    try {
      const res = await fetch("/api/admin/subscriptions", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_urls }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillSubscriptionForm(data);
      showAdminMsg(adminSubscriptionMsg, "サブスクリプション URL を保存しました", false);
    } catch (err) {
      showAdminMsg(adminSubscriptionMsg, err.message, true);
    }
  });
}

const adminSystemPromptsList = document.getElementById("adminSystemPromptsList");
const adminSystemPromptsCategory = document.getElementById("adminSystemPromptsCategory");
const adminSystemPromptsSearch = document.getElementById("adminSystemPromptsSearch");
const adminSystemPromptsMeta = document.getElementById("adminSystemPromptsMeta");
const adminSystemPromptsLoading = document.getElementById("adminSystemPromptsLoading");
const adminSystemPromptsError = document.getElementById("adminSystemPromptsError");
const adminSystemPromptsEmpty = document.getElementById("adminSystemPromptsEmpty");
let systemPromptsState = null;

function formatPromptCount(value) {
  const n = Number(value) || 0;
  return n.toLocaleString();
}

function renderSystemPromptsList() {
  if (!adminSystemPromptsList) return;
  const all = systemPromptsState?.prompts || [];
  const category = (adminSystemPromptsCategory?.value || "").trim();
  const query = (adminSystemPromptsSearch?.value || "").trim().toLowerCase();
  const rows = all.filter((item) => {
    if (category && item.category !== category) return false;
    if (!query) return true;
    const haystack = [
      item.name,
      item.category,
      item.source,
      item.symbol,
      item.condition,
      item.id,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  adminSystemPromptsEmpty?.classList.toggle("hidden", rows.length > 0);
  if (adminSystemPromptsMeta) {
    adminSystemPromptsMeta.textContent = `${rows.length} / ${all.length} 件`;
  }

  adminSystemPromptsList.innerHTML = rows
    .map((item) => {
      const badges = [
        `<span class="admin-system-prompts-badge">${escapeHtml(item.category)}</span>`,
        item.dynamic
          ? '<span class="admin-system-prompts-badge admin-system-prompts-badge--dynamic">動的</span>'
          : "",
      ]
        .filter(Boolean)
        .join("");
      const condition = item.condition
        ? `<p class="admin-system-prompts-condition"><strong>適用条件:</strong> ${escapeHtml(item.condition)}</p>`
        : "";
      return `<details class="admin-system-prompts-item">
        <summary class="admin-system-prompts-summary">
          <span class="admin-system-prompts-title">${escapeHtml(item.name)}</span>
          <span class="admin-system-prompts-badges">${badges}</span>
          <span class="admin-system-prompts-stats">${escapeHtml(formatPromptCount(item.char_count))} 文字 · ${escapeHtml(item.source)}</span>
        </summary>
        <div class="admin-system-prompts-body">
          <p class="admin-system-prompts-source"><code>${escapeHtml(item.symbol)}</code> · ${escapeHtml(item.source)} · ID: ${escapeHtml(item.id)}</p>
          ${condition}
          <pre class="admin-system-prompts-pre">${escapeHtml(item.content || "")}</pre>
        </div>
      </details>`;
    })
    .join("");
}

function fillSystemPromptsFilters(data) {
  if (!adminSystemPromptsCategory) return;
  const current = adminSystemPromptsCategory.value;
  const categories = data?.categories || [];
  adminSystemPromptsCategory.innerHTML =
    '<option value="">すべて</option>' +
    categories
      .map(
        (cat) =>
          `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`
      )
      .join("");
  if (categories.includes(current)) {
    adminSystemPromptsCategory.value = current;
  }
}

async function loadSystemPrompts() {
  if (!adminSystemPromptsList) return;
  adminSystemPromptsLoading?.classList.remove("hidden");
  adminSystemPromptsError?.classList.add("hidden");
  adminSystemPromptsEmpty?.classList.add("hidden");
  try {
    const res = await fetch("/api/admin/system-prompts");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    systemPromptsState = data;
    fillSystemPromptsFilters(data);
    renderSystemPromptsList();
  } catch (err) {
    if (adminSystemPromptsError) {
      adminSystemPromptsError.textContent = err.message || "読み込みに失敗しました";
      adminSystemPromptsError.classList.remove("hidden");
    }
    adminSystemPromptsList.innerHTML = "";
  } finally {
    adminSystemPromptsLoading?.classList.add("hidden");
  }
}

adminSystemPromptsCategory?.addEventListener("change", () => renderSystemPromptsList());
adminSystemPromptsSearch?.addEventListener("input", () => renderSystemPromptsList());

const adminSearchEnginesForm = document.getElementById("adminSearchEnginesForm");
const adminSearchEnginesMsg = document.getElementById("adminSearchEnginesMsg");
const adminSearchEnginesStatus = document.getElementById("adminSearchEnginesStatus");
const adminSearchPlanHead = document.getElementById("adminSearchPlanHead");
const adminSearchPlanBody = document.getElementById("adminSearchPlanBody");
const adminSearchPlanLoading = document.getElementById("adminSearchPlanLoading");
const adminSearchPlanError = document.getElementById("adminSearchPlanError");
const adminSearchPlanTableWrap = document.getElementById("adminSearchPlanTableWrap");
let searchEnginesState = null;

function renderSearchPlanMatrix(data) {
  if (!adminSearchPlanHead || !adminSearchPlanBody) return;
  const keys = data?.feature_keys || [];
  const plans = data?.plans || [];
  adminSearchPlanHead.innerHTML = "";
  adminSearchPlanBody.innerHTML = "";
  const headRow = document.createElement("tr");
  headRow.innerHTML = "<th scope=\"col\">プラン</th>";
  keys.forEach((fk) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = fk.label || fk.key;
    headRow.appendChild(th);
  });
  adminSearchPlanHead.appendChild(headRow);
  plans.forEach((plan) => {
    const tr = document.createElement("tr");
    tr.dataset.planId = plan.id;
    const nameTd = document.createElement("td");
    nameTd.textContent = plan.name || plan.id;
    tr.appendChild(nameTd);
    keys.forEach((fk) => {
      const td = document.createElement("td");
      const label = document.createElement("label");
      label.className = "admin-plan-feature-cell";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.className = "admin-plan-feature-toggle admin-search-plan-toggle";
      input.dataset.flag = fk.key;
      input.checked = Boolean(plan.flags?.[fk.key]);
      label.appendChild(input);
      td.appendChild(label);
      tr.appendChild(td);
    });
    adminSearchPlanBody.appendChild(tr);
  });
}

function fillSearchEnginesForm(data) {
  const se = data?.search_engines || {};
  const tavilyEl = document.getElementById("adminTavilyApiKey");
  const serperEl = document.getElementById("adminSerperApiKey");
  const tavilyHint = document.getElementById("adminTavilyKeyHint");
  const serperHint = document.getElementById("adminSerperKeyHint");
  if (tavilyEl) tavilyEl.value = "";
  if (serperEl) serperEl.value = "";
  const tavilyOn = document.getElementById("adminSearchTavilyEnabled");
  const serperOn = document.getElementById("adminSearchSerperEnabled");
  const ddgOn = document.getElementById("adminSearchDdgEnabled");
  if (tavilyOn) tavilyOn.checked = se.tavily_enabled !== false;
  if (serperOn) serperOn.checked = se.serper_enabled !== false;
  if (ddgOn) ddgOn.checked = se.ddg_enabled !== false;

  if (tavilyHint) {
    let hint = se.tavily_key_set
      ? `保存済み (${se.tavily_key_hint || "設定あり"})`
      : "未保存";
    if (se.env_fallback_tavily) hint += " · .env を使用中";
    tavilyHint.textContent = hint;
  }
  if (serperHint) {
    let hint = se.serper_key_set
      ? `保存済み (${se.serper_key_hint || "設定あり"})`
      : "未保存";
    if (se.env_fallback_serper) hint += " · .env を使用中";
    serperHint.textContent = hint;
  }

  if (adminSearchEnginesStatus) {
    const parts = [];
    if (se.tavily_configured) parts.push("Tavily: 利用可");
    else parts.push("Tavily: キー未設定");
    if (se.serper_configured) parts.push("Serper: 利用可");
    else parts.push("Serper: キー未設定");
    if (se.ddg_enabled !== false) parts.push("DDG: フォールバック可");
    adminSearchEnginesStatus.textContent = parts.join(" · ");
    adminSearchEnginesStatus.classList.remove("hidden");
    adminSearchEnginesStatus.classList.toggle(
      "success",
      Boolean(se.tavily_configured || se.serper_configured)
    );
    adminSearchEnginesStatus.classList.toggle(
      "error",
      !se.tavily_configured && !se.serper_configured
    );
  }
  renderSearchPlanMatrix(data);
}

function collectSearchEnginesPayload() {
  const search_engines = {
    tavily_enabled: Boolean(document.getElementById("adminSearchTavilyEnabled")?.checked),
    serper_enabled: Boolean(document.getElementById("adminSearchSerperEnabled")?.checked),
    ddg_enabled: Boolean(document.getElementById("adminSearchDdgEnabled")?.checked),
  };
  const tavilyKey = document.getElementById("adminTavilyApiKey")?.value.trim();
  const serperKey = document.getElementById("adminSerperApiKey")?.value.trim();
  if (tavilyKey) search_engines.tavily_api_key = tavilyKey;
  if (serperKey) search_engines.serper_api_key = serperKey;

  const plans = {};
  adminSearchPlanBody?.querySelectorAll("tr[data-plan-id]").forEach((tr) => {
    const planId = tr.dataset.planId;
    if (!planId) return;
    const flags = {};
    tr.querySelectorAll(".admin-search-plan-toggle").forEach((input) => {
      flags[input.dataset.flag] = input.checked;
    });
    plans[planId] = { flags };
  });
  return { search_engines, plans };
}

// --- NEXGATE APIキー管理（system-keys panel） ---
const adminSystemApiKeyForm = document.getElementById("adminSystemApiKeyForm");
const adminSystemApiKeyBody = document.getElementById("adminSystemApiKeyBody");
const adminUpstreamKeysStatus = document.getElementById("adminUpstreamKeysStatus");
const adminSystemApiKeySecret = document.getElementById("adminSystemApiKeySecret");
const adminSystemApiKeyMsg = document.getElementById("adminSystemApiKeyMsg");

function renderUpstreamKeysStatus(upstream) {
  if (!adminUpstreamKeysStatus) return;
  if (!upstream) {
    adminUpstreamKeysStatus.innerHTML =
      '<p class="settings-hint">上流キー情報を取得できませんでした。</p>';
    return;
  }
  const parts = [];
  parts.push("<div><strong>モデルプロバイダー</strong></div>");
  (upstream.providers || []).forEach((p) => {
    const on = !!p.has_api_key;
    parts.push(
      `<div class="admin-upstream-key-row"><span>${escapeHtml(p.label)}</span>` +
        `<span class="admin-provider-status${on ? "" : " admin-provider-status--off"}">${on ? "設定済み" : "未設定"}</span>` +
        `<code class="settings-hint">${escapeHtml(p.api_key_env || "")}</code></div>`
    );
  });
  const search = upstream.search || {};
  parts.push("<div><strong>検索エンジン</strong></div>");
  const searchRow = (label, set) =>
    `<div class="admin-upstream-key-row"><span>${escapeHtml(label)}</span>` +
    `<span class="admin-provider-status${set ? "" : " admin-provider-status--off"}">${set ? "設定済み" : "未設定"}</span></div>`;
  parts.push(searchRow("Tavily", !!search.tavily_set));
  parts.push(searchRow("Serper (Google)", !!search.serper_set));
  parts.push("<div><strong>内部通信用</strong></div>");
  parts.push(
    `<div class="admin-upstream-key-row"><span>NEXGATE 内部キー</span>` +
      `<span class="admin-provider-status${upstream.internal_key_set ? "" : " admin-provider-status--off"}">${upstream.internal_key_set ? "設定済み" : "未設定"}</span></div>`
  );
  adminUpstreamKeysStatus.innerHTML = parts.join("");
}

function renderSystemApiKeys(keys) {
  if (!adminSystemApiKeyBody) return;
  if (!keys || !keys.length) {
    adminSystemApiKeyBody.innerHTML =
      '<tr><td colspan="7" class="settings-hint">システムAPIキーはまだありません。</td></tr>';
    return;
  }
  adminSystemApiKeyBody.innerHTML = keys
    .map((k) => {
      const scopes = (k.scopes || []).map((s) => `<code>${escapeHtml(s)}</code>`).join(" ");
      return `<tr>
        <td>${escapeHtml(k.name || "—")}</td>
        <td>${escapeHtml(k.owner_username || "—")}</td>
        <td>${scopes || "—"}</td>
        <td><code>${escapeHtml(k.prefix || "")}…</code></td>
        <td>${escapeHtml(String(k.created_at || "—"))}</td>
        <td>${k.last_used_at ? escapeHtml(String(k.last_used_at)) : "—"}</td>
        <td><button type="button" class="admin-row-btn admin-row-btn--danger admin-system-key-revoke" data-key-id="${escapeAttr(k.id)}">失効</button></td>
      </tr>`;
    })
    .join("");
}

async function loadSystemKeysSettings() {
  try {
    const res = await fetch("/api/admin/system-keys");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderUpstreamKeysStatus(data.upstream);
    renderSystemApiKeys(data.downstream?.system_keys);
  } catch (err) {
    if (adminUpstreamKeysStatus) {
      adminUpstreamKeysStatus.innerHTML = `<p class="settings-hint">読み込みに失敗しました: ${escapeHtml(err.message)}</p>`;
    }
  }
}

if (adminSystemApiKeyForm) {
  adminSystemApiKeyForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    adminSystemApiKeyMsg?.classList.add("hidden");
    adminSystemApiKeySecret?.classList.add("hidden");
    const name =
      document.getElementById("adminSystemApiKeyName")?.value.trim() || "";
    const owner =
      document.getElementById("adminSystemApiKeyOwner")?.value.trim() || "";
    const scopes = [];
    if (document.getElementById("adminSystemApiKeyScopeModels")?.checked) {
      scopes.push("models");
    }
    if (document.getElementById("adminSystemApiKeyScopeChat")?.checked) {
      scopes.push("chat_completions");
    }
    try {
      const res = await fetch("/api/admin/system-api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, owner_username: owner, scopes }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "発行に失敗しました");
      if (adminSystemApiKeySecret) {
        adminSystemApiKeySecret.classList.remove("hidden");
        adminSystemApiKeySecret.textContent =
          `システムAPIキーを発行しました。シークレットはこの1回だけ表示します（再表示不可）。\n\n` +
          `Secret: ${data.secret}\n\n` +
          `Authorization: Bearer ${data.secret}`;
      }
      adminSystemApiKeyForm.reset();
      const scModels = document.getElementById("adminSystemApiKeyScopeModels");
      const scChat = document.getElementById("adminSystemApiKeyScopeChat");
      if (scModels) scModels.checked = true;
      if (scChat) scChat.checked = true;
      await loadSystemKeysSettings();
    } catch (err) {
      showAdminMsg(adminSystemApiKeyMsg, err.message, true);
    }
  });
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".admin-system-key-revoke");
  if (!btn) return;
  const keyId = btn.dataset.keyId;
  if (!keyId) return;
  if (
    !window.confirm(
      "このシステムAPIキーを失効しますか？この操作は取り消せません。"
    )
  ) {
    return;
  }
  try {
    const res = await fetch(
      `/api/admin/system-api-keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE" }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "失効に失敗しました");
    await loadSystemKeysSettings();
  } catch (err) {
    window.alert(err.message);
  }
});

async function loadSearchEnginesSettings() {
  if (!adminSearchEnginesForm) return;
  adminSearchPlanLoading?.classList.remove("hidden");
  adminSearchPlanError?.classList.add("hidden");
  adminSearchPlanTableWrap?.classList.add("hidden");
  try {
    const res = await fetch("/api/admin/search-engines");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    searchEnginesState = data;
    fillSearchEnginesForm(data);
    adminSearchPlanLoading?.classList.add("hidden");
    adminSearchPlanTableWrap?.classList.remove("hidden");
  } catch (err) {
    adminSearchPlanLoading?.classList.add("hidden");
    if (adminSearchPlanError) {
      adminSearchPlanError.textContent = err.message;
      adminSearchPlanError.classList.remove("hidden");
    }
    showAdminMsg(adminSearchEnginesMsg, err.message, true);
  }
}

if (adminSearchEnginesForm) {
  adminSearchEnginesForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminSearchEnginesMsg) adminSearchEnginesMsg.classList.add("hidden");
    try {
      const res = await fetch("/api/admin/search-engines", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectSearchEnginesPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      searchEnginesState = data;
      fillSearchEnginesForm(data);
      showAdminMsg(adminSearchEnginesMsg, "検索エンジン設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminSearchEnginesMsg, err.message, true);
    }
  });
}

async function loadPaypalSettings() {
  try {
    const res = await fetch("/api/admin/paypal");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillPaypalForm(data.paypal);
  } catch (err) {
    showAdminMsg(adminPaypalMsg, err.message, true);
  }
}

if (adminPaypalForm) {
  adminPaypalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminPaypalMsg) adminPaypalMsg.classList.add("hidden");

    const payload = {
      client_id: document.getElementById("adminPaypalClientId")?.value.trim(),
      mode: document.getElementById("adminPaypalMode")?.value,
      webhook_id: document.getElementById("adminPaypalWebhookId")?.value.trim(),
    };
    const secret = document.getElementById("adminPaypalSecret")?.value;
    if (secret) payload.client_secret = secret;

    try {
      const res = await fetch("/api/admin/paypal", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillPaypalForm(data.paypal);
      showAdminMsg(adminPaypalMsg, "PayPal設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminPaypalMsg, err.message, true);
    }
  });
}

const adminDeploymentMode = document.getElementById("adminDeploymentMode");
const adminDeploymentRuntime = document.getElementById("adminDeploymentRuntime");
const adminDeploymentHint = document.getElementById("adminDeploymentHint");
const adminDeploymentMeta = document.getElementById("adminDeploymentMeta");
const DEPLOYMENT_STATUS_LABELS = {
  operating: "operating",
  warning: "warning",
  error: "error",
  critical: "critical",
};
const DEPLOYMENT_STATUS_COLORS = {
  operating: "rgb(52, 211, 153)",
  warning: "rgb(250, 204, 21)",
  error: "rgb(251, 146, 60)",
  critical: "rgb(248, 113, 113)",
};
const deploymentCharts = {};
let deploymentHealthTimer = null;

function stopDeploymentHealthRefresh() {
  if (deploymentHealthTimer) {
    clearInterval(deploymentHealthTimer);
    deploymentHealthTimer = null;
  }
}

function startDeploymentHealthRefresh() {
  stopDeploymentHealthRefresh();
  deploymentHealthTimer = setInterval(() => {
    if (document.documentElement.getAttribute("data-admin-panel") !== "overview") {
      stopDeploymentHealthRefresh();
      return;
    }
    loadDeploymentOverview({ silent: true });
  }, 10000);
}

function renderDeploymentServiceCard(service, chart) {
  const id = service.id;
  const statusEl = document.getElementById(`adminServiceStatus-${id}`);
  const urlEl = document.getElementById(`adminServiceUrl-${id}`);
  const uptimeEl = document.getElementById(`adminServiceUptime-${id}`);
  const issuesEl = document.getElementById(`adminServiceIssues-${id}`);
  const canvas = document.getElementById(`adminServiceChart-${id}`);

  if (statusEl) {
    const status = service.status || "critical";
    statusEl.textContent = DEPLOYMENT_STATUS_LABELS[status] || status;
    statusEl.className = `admin-service-status-tag admin-service-status-tag--${status}`;
  }
  if (urlEl) urlEl.textContent = service.url || "URL未設定";
  if (uptimeEl) uptimeEl.textContent = service.uptime_label || "—";

  if (issuesEl) {
    const issues = Array.isArray(service.issues) ? service.issues : [];
    issuesEl.innerHTML = issues.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    issuesEl.classList.toggle("hidden", issues.length === 0);
  }

  if (!canvas || typeof Chart === "undefined" || !chart) return;
  const labels = chart.labels || [];
  const values = chart.datasets?.[id] || [];
  const colors = getChartThemeColors();
  const data = {
    labels,
    datasets: [
      {
        label: "稼働レベル",
        data: values,
        borderColor: DEPLOYMENT_STATUS_COLORS.operating,
        backgroundColor: "rgba(52, 211, 153, 0.12)",
        stepped: true,
        fill: true,
        pointRadius: labels.length > 36 ? 0 : 2,
      },
    ],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label(ctx) {
            const level = Number(ctx.parsed.y);
            const names = ["operating", "warning", "error", "critical"];
            return ` ${names[level] ?? level}`;
          },
        },
      },
    },
    layout: {
      padding: { left: 4, right: 8, bottom: 2 },
    },
    scales: {
      x: {
        ticks: {
          color: colors.text,
          maxTicksLimit: 6,
          maxRotation: 0,
          autoSkip: true,
          font: { size: 10 },
        },
        grid: { color: colors.grid },
      },
      y: {
        min: 0,
        max: 3,
        ticks: {
          color: colors.text,
          stepSize: 1,
          callback: (v) => ["operating", "warning", "error", "critical"][v] ?? v,
        },
        grid: { color: colors.grid },
      },
    },
  };

  if (deploymentCharts[id]) {
    deploymentCharts[id].data = data;
    deploymentCharts[id].options = options;
    deploymentCharts[id].update("none");
    return;
  }
  deploymentCharts[id] = new Chart(canvas, { type: "line", data, options });
}

function fillDeploymentOverview(payload) {
  const dep = payload?.deployment || {};
  if (adminDeploymentMode) {
    adminDeploymentMode.value = dep.operation_mode || "run-servers";
  }
  if (adminDeploymentRuntime) {
    adminDeploymentRuntime.textContent = `現在の実行モード: ${dep.runtime_mode_label || dep.runtime_mode || "—"}`;
  }
  if (adminDeploymentHint) {
    const hint = dep.restart_hint || "";
    adminDeploymentHint.textContent = hint;
    adminDeploymentHint.classList.toggle("hidden", !hint);
    adminDeploymentHint.classList.toggle("error", Boolean(dep.mode_mismatch));
  }
  if (adminDeploymentMeta) {
    adminDeploymentMeta.textContent = `全体: ${payload?.overall_status_label || "—"} · 更新 ${payload?.updated_at || "—"}（直近24時間・時間単位）`;
  }
  const chart = payload?.chart || {};
  (payload?.services || []).forEach((service) => {
    renderDeploymentServiceCard(service, chart);
  });
}

async function loadDeploymentOverview(options = {}) {
  const { silent = false } = options;
  try {
    const res = await fetch("/api/admin/deployment");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "稼働状況の読み込みに失敗しました");
    fillDeploymentOverview(data);
  } catch (err) {
    if (!silent) {
      showAdminMsg(adminServiceUrlsMsg, err.message, true);
    }
  }
}

const deploymentRestartPollers = {};

function setServiceRestartBusy(serviceId, busy, label = "システムの再起動") {
  const btn = document.querySelector(`.admin-service-restart-btn[data-service="${serviceId}"]`);
  if (!btn) return;
  btn.disabled = Boolean(busy);
  btn.textContent = busy ? "再起動中…" : label;
}

async function waitForServiceRestart(requestId, serviceId) {
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    try {
      const res = await fetch(`/api/admin/deployment/restart/${encodeURIComponent(requestId)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "再起動状態の確認に失敗しました");
      const status = data.request?.status;
      if (status === "done") {
        await loadDeploymentOverview({ silent: true });
        return;
      }
      if (status === "failed") {
        throw new Error(data.request?.error || "再起動に失敗しました");
      }
    } catch (err) {
      if (Date.now() >= deadline) throw err;
    }
  }
  throw new Error("再起動の完了を確認できませんでした");
}

async function restartDeploymentService(serviceId) {
  if (deploymentRestartPollers[serviceId]) return;
  deploymentRestartPollers[serviceId] = true;
  setServiceRestartBusy(serviceId, true);
  if (adminServiceUrlsMsg) adminServiceUrlsMsg.classList.add("hidden");

  try {
    const res = await fetch(`/api/admin/deployment/services/${encodeURIComponent(serviceId)}/restart`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "再起動の開始に失敗しました");
    showAdminMsg(adminServiceUrlsMsg, `${data.service_label || serviceId} を再起動しています…`, false);
    await waitForServiceRestart(data.request_id, serviceId);
    showAdminMsg(adminServiceUrlsMsg, `${data.service_label || serviceId} の再起動が完了しました`, false);
  } catch (err) {
    showAdminMsg(adminServiceUrlsMsg, err.message, true);
    loadDeploymentOverview({ silent: true });
  } finally {
    deploymentRestartPollers[serviceId] = false;
    setServiceRestartBusy(serviceId, false);
  }
}

document.querySelectorAll(".admin-service-restart-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const serviceId = btn.getAttribute("data-service");
    if (!serviceId) return;
    if (!window.confirm("このシステムを再起動しますか？復旧まで数十秒かかる場合があります。")) return;
    restartDeploymentService(serviceId);
  });
});

if (adminDeploymentMode) {
  adminDeploymentMode.addEventListener("change", async () => {
    const operation_mode = adminDeploymentMode.value;
    try {
      const res = await fetch("/api/admin/deployment", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operation_mode }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillDeploymentOverview(data);
      showAdminMsg(adminServiceUrlsMsg, "稼働タイプを保存しました", false);
    } catch (err) {
      showAdminMsg(adminServiceUrlsMsg, err.message, true);
      loadDeploymentOverview({ silent: true });
    }
  });
}

const adminServiceUrlsForm = document.getElementById("adminServiceUrlsForm");
const adminServiceUrlsMsg = document.getElementById("adminServiceUrlsMsg");
const adminServiceUrlsStatus = document.getElementById("adminServiceUrlsStatus");

function fillServiceUrlsEffectiveHint(inputId, effectiveId, stored, effective, envFallback) {
  const effectiveEl = document.getElementById(effectiveId);
  if (!effectiveEl) return;
  if (!effective) {
    effectiveEl.classList.add("hidden");
    effectiveEl.textContent = "";
    return;
  }
  const parts = [`現在有効: ${effective}`];
  if (!stored && envFallback) parts.push(".env から読み込み中");
  else if (stored && stored !== effective) parts.push(`保存値: ${stored}`);
  effectiveEl.textContent = parts.join(" · ");
  effectiveEl.classList.remove("hidden");
}

function fillServiceUrlsForm(serviceUrls) {
  const frontendEl = document.getElementById("adminFrontendBaseUrl");
  const portalEl = document.getElementById("adminApiPortalBaseUrl");
  const apiEl = document.getElementById("adminApiBaseUrl");
  const effective = serviceUrls?.effective || {};
  const envFallback = serviceUrls?.env_fallback || {};

  if (frontendEl) frontendEl.value = serviceUrls?.frontend_base_url || "";
  if (portalEl) portalEl.value = serviceUrls?.api_portal_base_url || "";
  if (apiEl) apiEl.value = serviceUrls?.api_base_url || "";

  fillServiceUrlsEffectiveHint(
    "adminFrontendBaseUrl",
    "adminFrontendBaseUrlEffective",
    serviceUrls?.frontend_base_url,
    effective.frontend_base_url,
    envFallback.frontend_base_url
  );
  fillServiceUrlsEffectiveHint(
    "adminApiPortalBaseUrl",
    "adminApiPortalBaseUrlEffective",
    serviceUrls?.api_portal_base_url,
    effective.api_portal_base_url,
    envFallback.api_portal_base_url
  );
  fillServiceUrlsEffectiveHint(
    "adminApiBaseUrl",
    "adminApiBaseUrlEffective",
    serviceUrls?.api_base_url,
    effective.api_base_url,
    envFallback.api_base_url
  );

  if (adminServiceUrlsStatus) {
    const configured = Boolean(
      serviceUrls?.frontend_base_url ||
        serviceUrls?.api_portal_base_url ||
        serviceUrls?.api_base_url
    );
    adminServiceUrlsStatus.textContent = configured
      ? "状態: system_config.json に URL が保存されています"
      : "状態: 未保存（.env またはデフォルト値を使用中）";
    adminServiceUrlsStatus.classList.remove("hidden");
    adminServiceUrlsStatus.classList.toggle("success", configured);
    adminServiceUrlsStatus.classList.toggle("error", !configured);
  }
}

async function loadServiceUrlsSettings() {
  try {
    const res = await fetch("/api/admin/service-urls");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillServiceUrlsForm(data.service_urls);
  } catch (err) {
    showAdminMsg(adminServiceUrlsMsg, err.message, true);
  }
}

if (adminServiceUrlsForm) {
  adminServiceUrlsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminServiceUrlsMsg) adminServiceUrlsMsg.classList.add("hidden");

    const payload = {
      frontend_base_url: document.getElementById("adminFrontendBaseUrl")?.value.trim(),
      api_portal_base_url: document.getElementById("adminApiPortalBaseUrl")?.value.trim(),
      api_base_url: document.getElementById("adminApiBaseUrl")?.value.trim(),
    };

    try {
      const res = await fetch("/api/admin/service-urls", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillServiceUrlsForm(data.service_urls);
      loadDeploymentOverview({ silent: true });
      showAdminMsg(adminServiceUrlsMsg, "URL設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminServiceUrlsMsg, err.message, true);
    }
  });
}

const adminGoogleOauthForm = document.getElementById("adminGoogleOauthForm");
const adminGoogleOauthMsg = document.getElementById("adminGoogleOauthMsg");
const adminGoogleOauthStatus = document.getElementById("adminGoogleOauthStatus");
const adminGoogleSecretHint = document.getElementById("adminGoogleSecretHint");
const adminGoogleRedirectCopyBtn = document.getElementById("adminGoogleRedirectCopyBtn");

function fillGoogleOauthForm(googleOauth) {
  const clientIdEl = document.getElementById("adminGoogleClientId");
  const secretEl = document.getElementById("adminGoogleSecret");
  const redirectEl = document.getElementById("adminGoogleRedirectUri");
  const redirectDisplay = document.getElementById("adminGoogleRedirectUriDisplay");
  const originsEl = document.getElementById("adminGoogleOriginsHint");
  const calEl = document.getElementById("adminGoogleCalendarScopes");
  const gmailEl = document.getElementById("adminGoogleGmailScopes");

  if (clientIdEl) clientIdEl.value = googleOauth?.client_id || "";
  if (secretEl) secretEl.value = "";
  if (redirectEl) redirectEl.value = googleOauth?.redirect_uri || "";
  if (redirectDisplay) redirectDisplay.value = googleOauth?.redirect_uri || "";
  if (originsEl) originsEl.value = googleOauth?.javascript_origins_hint || "";
  if (calEl) calEl.checked = googleOauth?.calendar_scopes_enabled !== false;
  if (gmailEl) gmailEl.checked = googleOauth?.gmail_scopes_enabled !== false;

  if (adminGoogleOauthStatus) {
    let status = "";
    if (googleOauth?.configured) {
      status = "状態: 設定済み（ユーザーが Google 連携可能）";
      if (googleOauth.env_fallback) status += " ※ .env から読み込み中";
      const scopes = googleOauth.scopes || [];
      if (scopes.length) status += ` · スコープ: ${scopes.length} 件`;
    } else {
      status = "状態: 未設定（Client ID と Client Secret が必要です）";
    }
    adminGoogleOauthStatus.textContent = status;
    adminGoogleOauthStatus.classList.remove("hidden");
    adminGoogleOauthStatus.classList.toggle("error", !googleOauth?.configured);
    adminGoogleOauthStatus.classList.toggle("success", Boolean(googleOauth?.configured));
  }
  if (adminGoogleSecretHint) {
    adminGoogleSecretHint.textContent = googleOauth?.secret_set
      ? "Secret は保存済みです。変更する場合のみ入力してください。"
      : "Secret を入力して保存してください。";
  }
}

async function loadGoogleOauthSettings() {
  try {
    const res = await fetch("/api/admin/google-oauth");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillGoogleOauthForm(data.google_oauth);
  } catch (err) {
    showAdminMsg(adminGoogleOauthMsg, err.message, true);
  }
}

if (adminGoogleRedirectCopyBtn) {
  adminGoogleRedirectCopyBtn.addEventListener("click", async () => {
    const value = document.getElementById("adminGoogleRedirectUriDisplay")?.value || "";
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showAdminMsg(adminGoogleOauthMsg, "Redirect URI をコピーしました", false);
    } catch {
      showAdminMsg(adminGoogleOauthMsg, "コピーに失敗しました", true);
    }
  });
}

if (adminGoogleOauthForm) {
  adminGoogleOauthForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminGoogleOauthMsg) adminGoogleOauthMsg.classList.add("hidden");

    const payload = {
      client_id: document.getElementById("adminGoogleClientId")?.value.trim(),
      redirect_uri: document.getElementById("adminGoogleRedirectUri")?.value.trim(),
      calendar_scopes_enabled: Boolean(
        document.getElementById("adminGoogleCalendarScopes")?.checked
      ),
      gmail_scopes_enabled: Boolean(
        document.getElementById("adminGoogleGmailScopes")?.checked
      ),
    };
    const secret = document.getElementById("adminGoogleSecret")?.value;
    if (secret) payload.client_secret = secret;

    try {
      const res = await fetch("/api/admin/google-oauth", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillGoogleOauthForm(data.google_oauth);
      showAdminMsg(adminGoogleOauthMsg, "Google OAuth設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminGoogleOauthMsg, err.message, true);
    }
  });
}

const adminDiscordOauthForm = document.getElementById("adminDiscordOauthForm");
const adminDiscordOauthMsg = document.getElementById("adminDiscordOauthMsg");
const adminDiscordOauthStatus = document.getElementById("adminDiscordOauthStatus");
const adminDiscordSecretHint = document.getElementById("adminDiscordSecretHint");
const adminDiscordRedirectCopyBtn = document.getElementById("adminDiscordRedirectCopyBtn");

function fillDiscordOauthForm(discordOauth) {
  const clientIdEl = document.getElementById("adminDiscordClientId");
  const secretEl = document.getElementById("adminDiscordSecret");
  const redirectEl = document.getElementById("adminDiscordRedirectUri");
  const redirectDisplay = document.getElementById("adminDiscordRedirectUriDisplay");
  const loginDisabledEl = document.getElementById("adminDiscordLoginDisabled");

  if (clientIdEl) clientIdEl.value = discordOauth?.client_id || "";
  if (secretEl) secretEl.value = "";
  if (redirectEl) redirectEl.value = discordOauth?.redirect_uri || "";
  if (redirectDisplay) redirectDisplay.value = discordOauth?.redirect_uri || "";
  if (loginDisabledEl) loginDisabledEl.checked = Boolean(discordOauth?.discord_login_disabled);

  if (adminDiscordOauthStatus) {
    let status = "";
    if (discordOauth?.configured) {
      status = "状態: 設定済み（OAuth クライアント利用可能）";
      if (discordOauth.env_fallback) status += " ※ .env から読み込み中";
      if (discordOauth.discord_login_disabled) {
        status += " · Discord ログインは禁止中";
      } else if (discordOauth.discord_login_available !== false) {
        status += " · ログイン画面に Discord ボタン表示";
      }
    } else {
      status = "状態: 未設定（Client ID と Client Secret が必要です）";
    }
    adminDiscordOauthStatus.textContent = status;
    adminDiscordOauthStatus.classList.remove("hidden");
    adminDiscordOauthStatus.classList.toggle("error", !discordOauth?.configured);
    adminDiscordOauthStatus.classList.toggle("success", Boolean(discordOauth?.configured));
  }
  if (adminDiscordSecretHint) {
    adminDiscordSecretHint.textContent = discordOauth?.secret_set
      ? "Secret は保存済みです。変更する場合のみ入力してください。"
      : "Secret を入力して保存してください。";
  }
}

async function loadDiscordOauthSettings() {
  try {
    const res = await fetch("/api/admin/discord-oauth");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillDiscordOauthForm(data.discord_oauth);
  } catch (err) {
    showAdminMsg(adminDiscordOauthMsg, err.message, true);
  }
}

const adminDiscordRedirectUriInput = document.getElementById("adminDiscordRedirectUri");
if (adminDiscordRedirectUriInput) {
  adminDiscordRedirectUriInput.addEventListener("input", () => {
    const display = document.getElementById("adminDiscordRedirectUriDisplay");
    if (display) display.value = adminDiscordRedirectUriInput.value.trim();
  });
}

if (adminDiscordRedirectCopyBtn) {
  adminDiscordRedirectCopyBtn.addEventListener("click", async () => {
    const value = document.getElementById("adminDiscordRedirectUriDisplay")?.value || "";
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showAdminMsg(adminDiscordOauthMsg, "Redirect URI をコピーしました", false);
    } catch {
      showAdminMsg(adminDiscordOauthMsg, "コピーに失敗しました", true);
    }
  });
}

if (adminDiscordOauthForm) {
  adminDiscordOauthForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (adminDiscordOauthMsg) adminDiscordOauthMsg.classList.add("hidden");

    const payload = {
      client_id: document.getElementById("adminDiscordClientId")?.value.trim(),
      redirect_uri: document.getElementById("adminDiscordRedirectUri")?.value.trim(),
      discord_login_disabled: Boolean(
        document.getElementById("adminDiscordLoginDisabled")?.checked
      ),
    };
    const secret = document.getElementById("adminDiscordSecret")?.value;
    if (secret) payload.client_secret = secret;

    try {
      const res = await fetch("/api/admin/discord-oauth", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillDiscordOauthForm(data.discord_oauth);
      if (data.features) {
        if (adminState) adminState.features = data.features;
        applyFeatures(data.features);
        window.applySystemFeatures?.(data.features);
      }
      showAdminMsg(adminDiscordOauthMsg, "Discord OAuth設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminDiscordOauthMsg, err.message, true);
    }
  });
}

const adminMailServerForm = document.getElementById("adminMailServerForm");
const adminMailServerMsg = document.getElementById("adminMailServerMsg");
const adminMailServerStatus = document.getElementById("adminMailServerStatus");
const adminMailPasswordHint = document.getElementById("adminMailPasswordHint");
const adminMailServerTestForm = document.getElementById("adminMailServerTestForm");
const adminMailServerTestMsg = document.getElementById("adminMailServerTestMsg");

function fillMailServerForm(mailServer) {
  const enabledEl = document.getElementById("adminMailServerEnabled");
  const verificationEl = document.getElementById("adminMailVerificationRequired");
  const hostEl = document.getElementById("adminMailHost");
  const portEl = document.getElementById("adminMailPort");
  const tlsEl = document.getElementById("adminMailUseTls");
  const sslEl = document.getElementById("adminMailUseSsl");
  const usernameEl = document.getElementById("adminMailUsername");
  const passwordEl = document.getElementById("adminMailPassword");
  const fromEmailEl = document.getElementById("adminMailFromEmail");
  const fromNameEl = document.getElementById("adminMailFromName");

  if (enabledEl) enabledEl.checked = Boolean(mailServer?.enabled);
  if (verificationEl) {
    verificationEl.checked = mailServer?.verification_required !== false;
  }
  if (hostEl) hostEl.value = mailServer?.host || "";
  if (portEl) portEl.value = String(mailServer?.port ?? 587);
  if (tlsEl) tlsEl.checked = mailServer?.use_ssl ? false : mailServer?.use_tls !== false;
  if (sslEl) sslEl.checked = Boolean(mailServer?.use_ssl);
  if (usernameEl) usernameEl.value = mailServer?.username || "";
  if (passwordEl) passwordEl.value = "";
  if (fromEmailEl) fromEmailEl.value = mailServer?.from_email || "";
  if (fromNameEl) fromNameEl.value = mailServer?.from_name || "NEXGATE AI";

  if (adminMailServerStatus) {
    const parts = [];
    if (mailServer?.configured) parts.push("SMTP設定済み");
    else parts.push("SMTP未設定");
    if (mailServer?.verification_active) parts.push("登録時メール認証: 有効");
    else if (mailServer?.enabled) parts.push("登録時メール認証: 無効");
    if (mailServer?.env_fallback) parts.push(".env フォールバック");
    adminMailServerStatus.textContent = parts.join(" · ");
    adminMailServerStatus.classList.remove("hidden");
    adminMailServerStatus.classList.toggle("error", !mailServer?.configured);
    adminMailServerStatus.classList.toggle("success", Boolean(mailServer?.configured));
  }
  if (adminMailPasswordHint) {
    adminMailPasswordHint.textContent = mailServer?.password_set
      ? "パスワードは保存済みです。変更する場合のみ入力してください。"
      : "パスワードを入力して保存してください。";
  }
}

async function loadMailServerSettings() {
  try {
    const res = await fetch("/api/admin/mail-server");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    fillMailServerForm(data.mail_server);
  } catch (err) {
    showAdminMsg(adminMailServerMsg, err.message, true);
  }
}

if (adminMailServerForm) {
  adminMailServerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    adminMailServerMsg?.classList.add("hidden");

    const payload = {
      enabled: Boolean(document.getElementById("adminMailServerEnabled")?.checked),
      verification_required: Boolean(
        document.getElementById("adminMailVerificationRequired")?.checked
      ),
      host: document.getElementById("adminMailHost")?.value.trim(),
      port: Number(document.getElementById("adminMailPort")?.value || 587),
      use_tls: Boolean(document.getElementById("adminMailUseTls")?.checked),
      use_ssl: Boolean(document.getElementById("adminMailUseSsl")?.checked),
      username: document.getElementById("adminMailUsername")?.value.trim(),
      from_email: document.getElementById("adminMailFromEmail")?.value.trim(),
      from_name: document.getElementById("adminMailFromName")?.value.trim(),
    };
    const password = document.getElementById("adminMailPassword")?.value;
    if (password) payload.password = password;

    try {
      const res = await fetch("/api/admin/mail-server", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存に失敗しました");
      fillMailServerForm(data.mail_server);
      showAdminMsg(adminMailServerMsg, "メールサーバー設定を保存しました", false);
    } catch (err) {
      showAdminMsg(adminMailServerMsg, err.message, true);
    }
  });
}

if (adminMailServerTestForm) {
  adminMailServerTestForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    adminMailServerTestMsg?.classList.add("hidden");
    const to_email = document.getElementById("adminMailTestTo")?.value.trim();
    try {
      const res = await fetch("/api/admin/mail-server/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "テスト送信に失敗しました");
      showAdminMsg(adminMailServerTestMsg, data.message || "テストメールを送信しました", false);
    } catch (err) {
      showAdminMsg(adminMailServerTestMsg, err.message, true);
    }
  });
}

const adminActiveSessionsBody = document.getElementById("adminActiveSessionsBody");
const adminSessionLogsBody = document.getElementById("adminSessionLogsBody");
const adminSessionsWsStatus = document.getElementById("adminSessionsWsStatus");
const adminSessionLogsMeta = document.getElementById("adminSessionLogsMeta");
const adminSessionLogsRefreshBtn = document.getElementById("adminSessionLogsRefreshBtn");

const adminSessionsMonitor = {
  ws: null,
  reconnectTimer: null,
  active: new Map(),
  logs: [],
  logsTotal: 0,
};

const ADMIN_SESSION_USD_JPY = 160;

const ADMIN_SESSION_STATUS_LABELS = {
  running: "進行中",
  completed: "完了",
  cancelled: "中断",
  failed: "失敗",
};

function formatAdminSessionCost(usd, jpyHint) {
  const n = Number(usd);
  const usdVal = Number.isFinite(n) && n > 0 ? n : 0;
  const usdText =
    usdVal <= 0
      ? "$0.00"
      : usdVal < 0.01
        ? `$${usdVal.toFixed(4)}`
        : `$${usdVal.toFixed(2)}`;
  const jpy =
    jpyHint != null && Number.isFinite(Number(jpyHint))
      ? Math.round(Number(jpyHint))
      : Math.round(usdVal * ADMIN_SESSION_USD_JPY);
  return `${usdText} (${jpy.toLocaleString()}円)`;
}

function formatAdminSessionTps(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return `${n.toFixed(1)} tps`;
}

function formatAdminSessionDuration(session) {
  if (session?.duration_label) return session.duration_label;
  const sec = Number(session?.duration_seconds);
  if (!Number.isFinite(sec) || sec <= 0) return "—";
  if (sec < 60) return `${sec.toFixed(1)} 秒`;
  const m = Math.floor(sec / 60);
  const r = Math.round(sec % 60);
  return `${m} 分 ${r} 秒`;
}

function formatAdminSessionTokens(n) {
  const v = Number(n) || 0;
  return v.toLocaleString();
}

function shortRequestId(id) {
  const s = String(id || "");
  if (s.length <= 14) return s;
  return `${s.slice(0, 8)}…${s.slice(-4)}`;
}

function adminSessionsWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/admin/sessions`;
}

function setAdminSessionsWsStatus(text, isError = false) {
  if (!adminSessionsWsStatus) return;
  adminSessionsWsStatus.textContent = text;
  adminSessionsWsStatus.classList.toggle("is-error", isError);
}

function upsertAdminActiveSession(session) {
  const id = session?.request_id;
  if (!id) return;
  const status = (session.status || "").toLowerCase();
  if (status === "running") {
    adminSessionsMonitor.active.set(id, session);
  } else {
    adminSessionsMonitor.active.delete(id);
  }
}

function renderAdminActiveSessions() {
  if (!adminActiveSessionsBody) return;
  const rows = Array.from(adminSessionsMonitor.active.values()).sort((a, b) =>
    (b.started_at || "").localeCompare(a.started_at || "")
  );
  if (!rows.length) {
    adminActiveSessionsBody.innerHTML =
      '<tr><td colspan="11" class="admin-sessions-empty">進行中のセッションはありません</td></tr>';
    return;
  }
  adminActiveSessionsBody.innerHTML = rows
    .map((s) => {
      const who = escapeHtml(s.display_name || s.username || "—");
      const userSub = s.display_name && s.username ? `<span class="admin-sessions-user-sub">${escapeHtml(s.username)}</span>` : "";
      const settling = Boolean(s.settling);
      const settlingNote = settling
        ? '<span class="admin-sessions-settling">終了処理中</span>'
        : "";
      const stopBtn = settling
        ? ""
        : `<button type="button" class="settings-btn settings-btn--secondary admin-session-stop-btn" data-stop-request-id="${escapeAttr(s.request_id)}">停止</button>`;
      const detailBtn = `<button type="button" class="settings-btn settings-btn--secondary admin-session-detail-btn" data-open-request-id="${escapeAttr(s.request_id)}">詳細</button>`;
      return `<tr data-request-id="${escapeAttr(s.request_id)}">
        <td><span class="admin-sessions-user">${who}</span>${userSub}${settlingNote}</td>
        <td><code>${escapeHtml(s.model_id || "—")}</code></td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.prompt_tokens)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.completion_tokens)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTps(s.tps)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.total_tokens)}</td>
        <td class="admin-sessions-num">${formatAdminSessionCost(s.cost_usd, s.cost_jpy)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.tool_call_count)}</td>
        <td>${escapeHtml(s.started_at || "—")}</td>
        <td class="admin-sessions-num">${escapeHtml(formatAdminSessionDuration(s))}</td>
        <td class="admin-sessions-actions">${detailBtn}${stopBtn}</td>
      </tr>`;
    })
    .join("");
}

function renderAdminSessionLogs() {
  if (!adminSessionLogsBody) return;
  const rows = adminSessionsMonitor.logs;
  if (!rows.length) {
    adminSessionLogsBody.innerHTML =
      '<tr><td colspan="11" class="admin-sessions-empty">セッションログはまだありません</td></tr>';
    if (adminSessionLogsMeta) {
      adminSessionLogsMeta.textContent = "";
      adminSessionLogsMeta.classList.add("hidden");
    }
    return;
  }
  adminSessionLogsBody.innerHTML = rows
    .map((s) => {
      const rawId = s.request_id || "";
      const statusKey = (s.status || "").toLowerCase();
      const statusLabel = ADMIN_SESSION_STATUS_LABELS[statusKey] || escapeHtml(s.status || "—");
      const who = escapeHtml(s.display_name || s.username || "—");
      return `<tr>
        <td>
          <button type="button" class="billing-request-id-copy admin-session-request-id-open" data-open-request-id="${escapeAttr(rawId)}" title="リクエスト詳細を表示">
            <code>${escapeHtml(shortRequestId(rawId))}</code>
          </button>
        </td>
        <td>${who}</td>
        <td><code>${escapeHtml(s.model_id || "—")}</code></td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.prompt_tokens)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTokens(s.completion_tokens)}</td>
        <td class="admin-sessions-num">${formatAdminSessionTps(s.tps)}</td>
        <td class="admin-sessions-num">${formatAdminSessionCost(s.cost_usd, s.cost_jpy)}</td>
        <td><span class="admin-session-status admin-session-status--${escapeAttr(statusKey || "unknown")}">${statusLabel}</span></td>
        <td>${escapeHtml(s.started_at || "—")}</td>
        <td>${escapeHtml(s.ended_at || "—")}</td>
        <td class="admin-sessions-num">${escapeHtml(formatAdminSessionDuration(s))}</td>
      </tr>`;
    })
    .join("");
  if (adminSessionLogsMeta) {
    adminSessionLogsMeta.textContent = `全 ${adminSessionsMonitor.logsTotal.toLocaleString()} 件（最新 ${rows.length} 件を表示）`;
    adminSessionLogsMeta.classList.remove("hidden");
  }
}

function prependAdminSessionLog(session) {
  if (!session?.request_id) return;
  const exists = adminSessionsMonitor.logs.some((r) => r.request_id === session.request_id);
  adminSessionsMonitor.logs = [
    session,
    ...adminSessionsMonitor.logs.filter((r) => r.request_id !== session.request_id),
  ].slice(0, 120);
  if (!exists) adminSessionsMonitor.logsTotal += 1;
  renderAdminSessionLogs();
}

function handleAdminSessionsWsMessage(event) {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch {
    return;
  }
  const type = data?.type;
  if (type === "snapshot" && Array.isArray(data.active)) {
    adminSessionsMonitor.active.clear();
    data.active.forEach((s) => upsertAdminActiveSession(s));
    renderAdminActiveSessions();
    return;
  }
  if (type === "session.updated" && data.session) {
    upsertAdminActiveSession(data.session);
    renderAdminActiveSessions();
    return;
  }
  if (type === "session.ended" && data.session) {
    adminSessionsMonitor.active.delete(data.session.request_id);
    renderAdminActiveSessions();
    prependAdminSessionLog(data.session);
  }
}

function scheduleAdminSessionsReconnect() {
  if (adminSessionsMonitor.reconnectTimer) return;
  adminSessionsMonitor.reconnectTimer = window.setTimeout(() => {
    adminSessionsMonitor.reconnectTimer = null;
    if (document.documentElement.getAttribute("data-admin-panel") === "sessions") {
      connectAdminSessionsWs();
    }
  }, 3000);
}

function connectAdminSessionsWs() {
  if (!adminActiveSessionsBody) return;
  if (adminSessionsMonitor.ws) {
    try {
      adminSessionsMonitor.ws.close();
    } catch {
      /* ignore */
    }
  }
  setAdminSessionsWsStatus("接続中…");
  const ws = new WebSocket(adminSessionsWsUrl());
  adminSessionsMonitor.ws = ws;
  ws.addEventListener("open", () => setAdminSessionsWsStatus("リアルタイム接続中"));
  ws.addEventListener("message", handleAdminSessionsWsMessage);
  ws.addEventListener("close", () => {
    setAdminSessionsWsStatus("接続が切れました。再接続します…", true);
    adminSessionsMonitor.ws = null;
    scheduleAdminSessionsReconnect();
  });
  ws.addEventListener("error", () => {
    setAdminSessionsWsStatus("WebSocket エラー", true);
  });
}

function stopAdminSessionsMonitor() {
  if (adminSessionsMonitor.reconnectTimer) {
    clearTimeout(adminSessionsMonitor.reconnectTimer);
    adminSessionsMonitor.reconnectTimer = null;
  }
  if (adminSessionsMonitor.ws) {
    try {
      adminSessionsMonitor.ws.close();
    } catch {
      /* ignore */
    }
    adminSessionsMonitor.ws = null;
  }
}

async function loadAdminSessionLogs() {
  if (!adminSessionLogsBody) return;
  adminSessionLogsBody.innerHTML =
    '<tr><td colspan="11" class="admin-sessions-empty">読み込み中…</td></tr>';
  try {
    const res = await fetch("/api/admin/sessions/logs?limit=120");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    adminSessionsMonitor.logs = Array.isArray(data.sessions) ? data.sessions : [];
    adminSessionsMonitor.logsTotal = Number(data.total) || adminSessionsMonitor.logs.length;
    renderAdminSessionLogs();
  } catch (err) {
    adminSessionLogsBody.innerHTML = `<tr><td colspan="11" class="admin-sessions-empty">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function stopAdminSession(requestId) {
  const id = (requestId || "").trim();
  if (!id) return;
  try {
    const res = await fetch(`/api/admin/sessions/${encodeURIComponent(id)}/stop`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "停止に失敗しました");
  } catch (err) {
    setAdminSessionsWsStatus(err.message, true);
  }
}

function startAdminSessionsMonitor() {
  loadAdminSessionLogs();
  connectAdminSessionsWs();
}

const adminSessionDetailDialog = document.getElementById("adminSessionDetailDialog");
const adminSessionDetailBody = document.getElementById("adminSessionDetailBody");
const adminSessionDetailMeta = document.getElementById("adminSessionDetailMeta");
const adminSessionDetailTitle = document.getElementById("adminSessionDetailTitle");
const adminSessionDetailCloseBtn = document.getElementById("adminSessionDetailCloseBtn");
const adminSessionDetailCopyIdBtn = document.getElementById("adminSessionDetailCopyIdBtn");
const adminSessionDetailCopyBriefBtn = document.getElementById("adminSessionDetailCopyBriefBtn");
const adminSessionDetailBrief = document.getElementById("adminSessionDetailBrief");

let adminSessionDetailCurrentId = "";
let adminSessionDetailBriefText = "";

function copyAdminRequestId(id) {
  const text = (id || "").trim();
  if (!text || !navigator.clipboard?.writeText) return;
  navigator.clipboard.writeText(text).catch(() => {});
}

function copyAdminSessionBrief() {
  const text = (adminSessionDetailBriefText || "").trim();
  if (!text || !navigator.clipboard?.writeText) return;
  navigator.clipboard.writeText(text).catch(() => {});
}

function briefLine(label, value, labelWidth = 16) {
  const key = String(label || "").padEnd(labelWidth, " ");
  const val = String(value ?? "—").replace(/\r\n/g, "\n");
  return `${key} │ ${val}`;
}

function briefSection(title) {
  return `\n── ${title} ${"─".repeat(Math.max(0, 44 - title.length))}`;
}

function formatBriefToolTrace(events) {
  if (!events?.length) return "  (no tool invocations)";
  return events
    .map((ev, idx) => {
      const tool = (ev.tool || "unknown").toUpperCase();
      const at = ev.at || "—";
      const payload = JSON.stringify(ev.payload ?? ev, null, 2);
      return `  [${idx + 1}] ${tool} @ ${at}\n${payload
        .split("\n")
        .map((line) => `      ${line}`)
        .join("\n")}`;
    })
    .join("\n\n");
}

function buildAdminSessionBrief(detail) {
  const tokens = detail.token_usage || {};
  const prompt = Number(tokens.prompt_tokens ?? detail.prompt_tokens) || 0;
  const completion = Number(tokens.completion_tokens ?? detail.completion_tokens) || 0;
  const total = Number(tokens.total_tokens ?? detail.total_tokens) || 0;
  const operator = detail.display_name
    ? `${detail.display_name} <${detail.username || "—"}>`
    : detail.username || "—";
  const cost = formatAdminSessionCost(detail.cost_usd, detail.cost_jpy);
  const duration = detail.duration_label || formatAdminSessionDuration(detail);
  const status = String(detail.status || "unknown").toUpperCase();

  const messagesSent =
    Array.isArray(detail.messages_sent) && detail.messages_sent.length
      ? detail.messages_sent
          .map((m) => `  [${(m.role || "?").toUpperCase()}]\n${(m.content || "")
            .split("\n")
            .map((line) => `    ${line}`)
            .join("\n")}`)
          .join("\n\n")
      : "  (none)";

  const rule = "════════════════════════════════════════════════════";
  const lines = [
    rule,
    "  NEXGATE · REQUEST SESSION BRIEF",
    rule,
    "",
    briefLine("REQUEST ID", detail.request_id || "—"),
    briefLine("SESSION ID", detail.session_id || "—"),
    briefLine("STATUS", status),
    briefLine("MODEL", detail.model_id || "—"),
    briefLine("OPERATOR", operator),
    briefSection("TIMELINE"),
    briefLine("STARTED AT", detail.started_at || "—"),
    briefLine("ENDED AT", detail.ended_at || "—"),
    briefLine("DURATION", duration),
    briefSection("METRICS"),
    briefLine("TOKENS IN", prompt.toLocaleString()),
    briefLine("  └ CACHE HIT", (Number(tokens.input_cache_hit_tokens) || 0).toLocaleString()),
    briefLine("  └ CACHE MISS", (Number(tokens.input_cache_miss_tokens) || 0).toLocaleString()),
    briefLine("TOKENS OUT", completion.toLocaleString()),
    briefLine("TOKENS TTL", total.toLocaleString()),
    briefLine("TOOL CALLS", Number(detail.tool_call_count) || 0),
    briefLine("COST", cost),
    briefSection("CLIENT"),
    briefLine("IP ADDRESS", detail.client_ip || "—"),
    briefLine("USER AGENT", detail.user_agent || "—"),
    briefSection("USER PAYLOAD"),
    (detail.user_message || "  (empty)")
      .split("\n")
      .map((line) => `  ${line}`)
      .join("\n"),
    briefSection("MESSAGE LOG"),
    messagesSent,
    briefSection("ASSISTANT OUTPUT"),
    (detail.assistant_response || "  (empty)")
      .split("\n")
      .map((line) => `  ${line}`)
      .join("\n"),
  ];

  if ((detail.reasoning_text || "").trim()) {
    lines.push(
      briefSection("REASONING TRACE"),
      detail.reasoning_text
        .split("\n")
        .map((line) => `  ${line}`)
        .join("\n")
    );
  }

  lines.push(briefSection("TOOL TRACE"), formatBriefToolTrace(detail.tool_events));

  if ((detail.error_message || "").trim()) {
    lines.push(
      briefSection("ERROR"),
      detail.error_message
        .split("\n")
        .map((line) => `  ${line}`)
        .join("\n")
    );
  }

  lines.push("", rule, "  END OF BRIEF", rule);
  return lines.join("\n");
}

function renderAdminSessionBrief(detail) {
  adminSessionDetailBriefText = buildAdminSessionBrief(detail);
  if (adminSessionDetailBrief) {
    adminSessionDetailBrief.textContent = adminSessionDetailBriefText;
  }
}

function renderAdminSessionDetailBlock(title, content, emptyText = "（なし）") {
  const text = (content || "").trim() || emptyText;
  return `<section class="admin-session-detail-block">
    <h4 class="admin-session-detail-block-title">${escapeHtml(title)}</h4>
    <pre class="admin-session-detail-pre">${escapeHtml(text)}</pre>
  </section>`;
}

function renderAdminSessionToolEvents(events) {
  if (!events?.length) {
    return renderAdminSessionDetailBlock("ツール呼び出し", "", "（ツール実行なし）");
  }
  const parts = events.map((ev, idx) => {
    const tool = escapeHtml(ev.tool || "tool");
    const at = escapeHtml(ev.at || "");
    const payload = JSON.stringify(ev.payload ?? ev, null, 2);
    return `--- #${idx + 1} ${tool} (${at}) ---\n${payload}`;
  });
  return renderAdminSessionDetailBlock("ツール呼び出し", parts.join("\n\n"));
}

function renderAdminSessionDetail(detail) {
  if (!adminSessionDetailBody) return;
  const who = detail.display_name
    ? `${detail.display_name} (${detail.username})`
    : detail.username || "—";
  const tokens = detail.token_usage || {};
  const summary = [
    `利用者: ${who}`,
    `モデル: ${detail.model_id || "—"}`,
    `状態: ${detail.status || "—"}`,
    `開始: ${detail.started_at || "—"}`,
    `終了: ${detail.ended_at || "—"}`,
    `所要時間: ${detail.duration_label || formatAdminSessionDuration(detail)}`,
    `IP: ${detail.client_ip || "—"}`,
    `User-Agent: ${detail.user_agent || "—"}`,
    `トークン: 入力 ${Number(tokens.prompt_tokens || detail.prompt_tokens) || 0}（キャッシュHIT ${Number(tokens.input_cache_hit_tokens) || 0} / MISS ${Number(tokens.input_cache_miss_tokens) || 0}）/ 出力 ${Number(tokens.completion_tokens || detail.completion_tokens) || 0} / 合計 ${Number(tokens.total_tokens || detail.total_tokens) || 0}`,
    `コスト: ${formatAdminSessionCost(detail.cost_usd, detail.cost_jpy)}`,
    `ツール回数: ${Number(detail.tool_call_count) || 0}`,
  ].join("\n");

  if (adminSessionDetailMeta) {
    adminSessionDetailMeta.textContent = summary;
  }
  if (adminSessionDetailTitle) {
    adminSessionDetailTitle.textContent = `リクエスト詳細 — ${shortRequestId(detail.request_id)}`;
  }

  renderAdminSessionBrief(detail);

  const messagesSent =
    Array.isArray(detail.messages_sent) && detail.messages_sent.length
      ? detail.messages_sent
          .map((m) => `[${m.role || "?"}]\n${m.content || ""}`)
          .join("\n\n— — —\n\n")
      : "";

  adminSessionDetailBody.innerHTML = [
    renderAdminSessionDetailBlock("送信内容（直近ユーザー発話）", detail.user_message),
    messagesSent
      ? renderAdminSessionDetailBlock("送信メッセージ一覧", messagesSent)
      : "",
    renderAdminSessionDetailBlock("回答内容", detail.assistant_response),
    detail.reasoning_text
      ? renderAdminSessionDetailBlock("推論（reasoning）", detail.reasoning_text)
      : "",
    renderAdminSessionToolEvents(detail.tool_events),
    detail.error_message
      ? renderAdminSessionDetailBlock("エラー", detail.error_message)
      : "",
  ].join("");
}

async function openAdminSessionDetail(requestId) {
  const id = (requestId || "").trim();
  if (!id || !adminSessionDetailDialog) return;
  adminSessionDetailCurrentId = id;
  adminSessionDetailBody.innerHTML = '<p class="admin-sessions-empty">読み込み中…</p>';
  if (adminSessionDetailMeta) adminSessionDetailMeta.textContent = "";
  if (adminSessionDetailBrief) adminSessionDetailBrief.textContent = "Loading session brief…";
  adminSessionDetailBriefText = "";
  adminSessionDetailDialog.showModal();
  try {
    const res = await fetch(`/api/admin/sessions/${encodeURIComponent(id)}/detail`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "詳細の取得に失敗しました");
    renderAdminSessionDetail(data.detail || {});
  } catch (err) {
    adminSessionDetailBody.innerHTML = `<p class="admin-sessions-empty">${escapeHtml(err.message)}</p>`;
  }
}

function closeAdminSessionDetail() {
  adminSessionDetailDialog?.close();
  adminSessionDetailCurrentId = "";
}

if (adminActiveSessionsBody) {
  adminActiveSessionsBody.addEventListener("click", (e) => {
    const openBtn = e.target.closest("[data-open-request-id]");
    if (openBtn) {
      openAdminSessionDetail(openBtn.getAttribute("data-open-request-id"));
      return;
    }
    const stopBtn = e.target.closest("[data-stop-request-id]");
    if (!stopBtn) return;
    stopAdminSession(stopBtn.getAttribute("data-stop-request-id"));
  });
}

if (adminSessionLogsBody) {
  adminSessionLogsBody.addEventListener("click", (e) => {
    const openBtn = e.target.closest("[data-open-request-id]");
    if (!openBtn) return;
    openAdminSessionDetail(openBtn.getAttribute("data-open-request-id"));
  });
}

adminSessionDetailCloseBtn?.addEventListener("click", closeAdminSessionDetail);
adminSessionDetailDialog?.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeAdminSessionDetail();
});
adminSessionDetailDialog?.addEventListener("click", (e) => {
  if (e.target === adminSessionDetailDialog) closeAdminSessionDetail();
});
adminSessionDetailCopyBriefBtn?.addEventListener("click", () => {
  if (!adminSessionDetailBriefText) return;
  copyAdminSessionBrief();
  adminSessionDetailCopyBriefBtn.textContent = "Copied";
  adminSessionDetailCopyBriefBtn.classList.add("is-copied");
  window.setTimeout(() => {
    adminSessionDetailCopyBriefBtn.textContent = "Copy Session Brief";
    adminSessionDetailCopyBriefBtn.classList.remove("is-copied");
  }, 1400);
});

adminSessionDetailBrief?.addEventListener("dblclick", () => {
  if (!adminSessionDetailBriefText) return;
  copyAdminSessionBrief();
  adminSessionDetailCopyBriefBtn?.classList.add("is-copied");
  window.setTimeout(() => adminSessionDetailCopyBriefBtn?.classList.remove("is-copied"), 1400);
});

adminSessionDetailCopyIdBtn?.addEventListener("click", () => {
  if (!adminSessionDetailCurrentId) return;
  copyAdminRequestId(adminSessionDetailCurrentId);
  adminSessionDetailCopyIdBtn.textContent = "Copied";
  window.setTimeout(() => {
    adminSessionDetailCopyIdBtn.textContent = "Copy Request ID";
  }, 1200);
});

adminSessionLogsRefreshBtn?.addEventListener("click", () => loadAdminSessionLogs());

window.adminApp = {
  showPanel: showAdminPanel,
  loadAdmin,
  loadPlanFeatures,
  loadCoupons,
  loadSearchEnginesSettings,
  loadSystemPrompts,
  loadPaypalSettings,
  loadGoogleOauthSettings,
  loadDiscordOauthSettings,
  loadSubscriptionSettings,
  openUser: openUserDetail,
  closeUser: closeUserDetail,
  openPlan: openPlanDetail,
  closePlan: closePlanDetail,
  syncRouteFromHash: syncAdminRouteFromHash,
};

if (document.getElementById("adminMain")) {
  const { panel, username, planId } = parseAdminHash(location.hash);
  showAdminPanel(panel, { syncUrl: false });
  loadAdmin().then(() => {
    if (username) openUserDetail(username, { syncUrl: false });
    if (planId) openPlanDetail(planId, { syncUrl: false });
  });
}

// ============================================================
// Server Resources Monitor
// ============================================================

function stopResourceMonitor() {
  if (resourceTimer) {
    clearInterval(resourceTimer);
    resourceTimer = null;
  }
}

function startResourceMonitor() {
  stopResourceMonitor();
  fetchResourceStats().catch(() => {});
  resourceTimer = setInterval(() => {
    const panel = document.documentElement.getAttribute("data-admin-panel");
    if (panel !== "resources") {
      stopResourceMonitor();
      return;
    }
    fetchResourceStats().catch(() => {});
  }, RESOURCE_POLL_MS);
}

function resourceProgressClass(pct) {
  if (pct >= 90) return "is-danger";
  if (pct >= 75) return "is-warning";
  return "";
}

function formatMb(mb) {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(0)} MB`;
}

function formatUptime(seconds) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}日 ${h}時間 ${m}分`;
  if (h > 0) return `${h}時間 ${m}分`;
  return `${m}分`;
}

async function fetchResourceStats() {
  const res = await fetch("/api/admin/system-stats");
  const data = await res.json();
  if (!res.ok) return;

  updateResourceCard(data);
  updateResourceHistory(data);
  updateResourceCharts();
}

function updateResourceCard(data) {
  const cpu = data.cpu || {};
  const mem = data.memory || {};
  const disk = data.disk || {};
  const net = data.network || {};

  // CPU
  const cpuPct = cpu.percent || 0;
  const cpuEl = document.getElementById("adminResourceCpuPercent");
  const cpuBar = document.getElementById("adminResourceCpuBar");
  const cpuMeta = document.getElementById("adminResourceCpuMeta");
  if (cpuEl) cpuEl.textContent = `${cpuPct}%`;
  if (cpuBar) {
    cpuBar.style.width = `${cpuPct}%`;
    cpuBar.className = `admin-resource-progress-bar ${resourceProgressClass(cpuPct)}`;
  }
  if (cpuMeta) {
    const freq = cpu.freq_current ? ` · ${(cpu.freq_current / 1000).toFixed(1)} GHz` : "";
    cpuMeta.textContent = `${cpu.count} コア${freq}`;
  }

  // Memory
  const memPct = mem.percent || 0;
  const memEl = document.getElementById("adminResourceMemPercent");
  const memBar = document.getElementById("adminResourceMemBar");
  const memMeta = document.getElementById("adminResourceMemMeta");
  if (memEl) memEl.textContent = `${memPct}%`;
  if (memBar) {
    memBar.style.width = `${memPct}%`;
    memBar.className = `admin-resource-progress-bar ${resourceProgressClass(memPct)}`;
  }
  if (memMeta) {
    memMeta.textContent = `${formatMb(mem.used_mb || 0)} / ${formatMb(mem.total_mb || 0)} 使用中`;
  }

  // Disk
  const diskPct = disk.percent || 0;
  const diskEl = document.getElementById("adminResourceDiskPercent");
  const diskBar = document.getElementById("adminResourceDiskBar");
  const diskMeta = document.getElementById("adminResourceDiskMeta");
  if (diskEl) diskEl.textContent = `${diskPct}%`;
  if (diskBar) {
    diskBar.style.width = `${diskPct}%`;
    diskBar.className = `admin-resource-progress-bar ${resourceProgressClass(diskPct)}`;
  }
  if (diskMeta) {
    diskMeta.textContent = `${disk.used_gb || 0} GB / ${disk.total_gb || 0} GB 使用中`;
  }

  // Network
  const netRateEl = document.getElementById("adminResourceNetRate");
  const netMeta = document.getElementById("adminResourceNetMeta");
  if (netRateEl) netRateEl.textContent = `${formatMb(net.recv_mb || 0)} ↓`;
  if (netMeta) {
    netMeta.textContent = `送信 ${formatMb(net.sent_mb || 0)} · 受信 ${formatMb(net.recv_mb || 0)} (累計)`;
  }

  // Uptime
  const upEl = document.getElementById("adminResourceUptime");
  if (upEl) upEl.textContent = formatUptime(data.uptime_seconds || 0);

  // NEXGATE processes
  const ng = data.nexgate || {};
  const ngCpuEl = document.getElementById("adminResourceNexgateCpu");
  const ngCpuBar = document.getElementById("adminResourceNexgateCpuBar");
  const ngCpuMeta = document.getElementById("adminResourceNexgateCpuMeta");
  if (ngCpuEl) ngCpuEl.textContent = `${ng.cpu_percent || 0}%`;
  if (ngCpuBar) {
    ngCpuBar.style.width = `${ng.cpu_percent || 0}%`;
    ngCpuBar.className = `admin-resource-progress-bar ${resourceProgressClass(ng.cpu_percent || 0)}`;
  }
  if (ngCpuMeta) {
    ngCpuMeta.textContent = `${ng.process_count || 0} プロセス · サーバー全体CPU ${data.cpu?.percent || 0}%`;
  }

  const ngMemEl = document.getElementById("adminResourceNexgateMem");
  const ngMemBar = document.getElementById("adminResourceNexgateMemBar");
  const ngMemMeta = document.getElementById("adminResourceNexgateMemMeta");
  if (ngMemEl) ngMemEl.textContent = formatMb(ng.memory_mb || 0);
  if (ngMemBar) {
    const totalMb = data.memory?.total_mb || 1;
    const pct = Math.min(100, ((ng.memory_mb || 0) / totalMb) * 100);
    ngMemBar.style.width = `${pct}%`;
    ngMemBar.className = `admin-resource-progress-bar ${resourceProgressClass(pct)}`;
  }
  if (ngMemMeta) {
    ngMemMeta.textContent = `サーバー全体 ${formatMb(data.memory?.used_mb || 0)} / ${formatMb(data.memory?.total_mb || 0)}`;
  }
}

function updateResourceHistory(data) {
  const now = new Date();
  const label = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;

  resourceHistory.cpu.push(data.cpu?.percent || 0);
  resourceHistory.mem.push(data.memory?.percent || 0);
  resourceHistory.netRecv.push((data.network?.recv_mb || 0) / 1024);
  resourceHistory.netSent.push((data.network?.sent_mb || 0) / 1024);
  resourceHistory.labels.push(label);

  if (resourceHistory.cpu.length > RESOURCE_HISTORY_MAX) {
    resourceHistory.cpu.shift();
    resourceHistory.mem.shift();
    resourceHistory.netRecv.shift();
    resourceHistory.netSent.shift();
    resourceHistory.labels.shift();
  }
}

function createResourceChart(canvasId, datasets, yLabel) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === "undefined") return null;

  const colors = {
    text: getComputedStyle(document.documentElement).getPropertyValue("--text-secondary").trim() || "#94a3b8",
    grid: getComputedStyle(document.documentElement).getPropertyValue("--border").trim() || "rgba(148,163,184,0.2)",
    accent: getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#9decff",
  };

  const data = {
    labels: resourceHistory.labels,
    datasets: datasets.map((ds) => ({
      ...ds,
      borderColor: ds.borderColor || colors.accent,
      backgroundColor: ds.backgroundColor || "rgba(157,236,255,0.08)",
      tension: 0.3,
      fill: true,
      pointRadius: 0,
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: { legend: { display: datasets.length > 1, labels: { color: colors.text, boxWidth: 12, padding: 8 } } },
    scales: {
      x: { ticks: { color: colors.text, maxTicksLimit: 6, maxRotation: 0, font: { size: 9 } }, grid: { color: colors.grid } },
      y: { ticks: { color: colors.text, font: { size: 9 }, callback: (v) => `${v}%` }, grid: { color: colors.grid }, title: { display: true, text: yLabel, color: colors.text } },
    },
  };

  return new Chart(canvas, { type: "line", data, options });
}

function updateResourceCharts() {
  if (resourceCharts.cpu) {
    resourceCharts.cpu.data.labels = resourceHistory.labels;
    resourceCharts.cpu.data.datasets[0].data = resourceHistory.cpu;
    resourceCharts.cpu.update("none");
  } else {
    resourceCharts.cpu = createResourceChart("adminChartCpu", [
      { label: "CPU %", data: resourceHistory.cpu },
    ], "CPU %");
  }

  if (resourceCharts.mem) {
    resourceCharts.mem.data.labels = resourceHistory.labels;
    resourceCharts.mem.data.datasets[0].data = resourceHistory.mem;
    resourceCharts.mem.update("none");
  } else {
    resourceCharts.mem = createResourceChart("adminChartMem", [
      { label: "メモリ %", data: resourceHistory.mem },
    ], "メモリ %");
  }

  if (resourceCharts.net) {
    resourceCharts.net.data.labels = resourceHistory.labels;
    resourceCharts.net.data.datasets[0].data = resourceHistory.netRecv;
    resourceCharts.net.data.datasets[1].data = resourceHistory.netSent;
    resourceCharts.net.update("none");
  } else {
    resourceCharts.net = createResourceChart("adminChartNet", [
      { label: "受信 GB", data: resourceHistory.netRecv, borderColor: "rgb(96,165,250)", backgroundColor: "rgba(96,165,250,0.08)" },
      { label: "送信 GB", data: resourceHistory.netSent, borderColor: "rgb(167,139,250)", backgroundColor: "rgba(167,139,250,0.08)" },
    ], "GB");
  }
}

// ============================================================
// Admin Reports
// ============================================================

const REPORT_STATUS_MAP = {
  unconfirmed: { label: "未確認", cls: "is-unconfirmed" },
  confirmed:   { label: "確認済み", cls: "is-confirmed" },
  unresolved:  { label: "未解決", cls: "is-unresolved" },
  cancelled:   { label: "中止", cls: "is-cancelled" },
  resolved:    { label: "解決済み", cls: "is-resolved" },
};

const REPORT_STATUS_ORDER = ["unconfirmed", "confirmed", "unresolved", "cancelled", "resolved"];

async function loadAdminReports() {
  const container = document.getElementById("admin-reports-list");
  if (!container) return;

  container.innerHTML = '<p class="admin-loading">読み込み中…</p>';
  try {
    const res = await fetch("/api/admin/reports");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "読み込みに失敗しました");
    renderAdminReports(container, data.reports || []);
  } catch (e) {
    container.innerHTML = `<p class="admin-error">${escapeHtml(e.message)}</p>`;
  }
}

function renderAdminReports(container, reports) {
  if (!reports.length) {
    container.innerHTML = '<p class="admin-empty">報告はまだありません</p>';
    return;
  }

  const rows = reports.map((r) => {
    const created = r.created_at ? new Date(r.created_at).toLocaleString("ja-JP") : "—";
    const username = escapeHtml(r.username || "unknown");
    const desc = escapeHtml((r.description || "").slice(0, 200));
    const sessionId = escapeHtml((r.session_id || "").slice(0, 8));
    const ip = escapeHtml(r.client_ip || "—");
    const id = escapeAttr(r.id || "");
    const status = r.status || "unconfirmed";
    const info = REPORT_STATUS_MAP[status] || REPORT_STATUS_MAP.unconfirmed;

    const statusOptions = REPORT_STATUS_ORDER.map((s) => {
      const opt = REPORT_STATUS_MAP[s];
      const sel = s === status ? " selected" : "";
      return `<option value="${escapeAttr(s)}"${sel}>${escapeHtml(opt.label)}</option>`;
    }).join("");

    return `
      <article class="admin-report-card" data-report-id="${id}">
        <div class="admin-report-head">
          <span class="admin-report-user">${username}</span>
          <div class="admin-report-head-right">
            <select class="admin-report-status-select ${info.cls}" data-report-id="${id}" aria-label="ステータス">
              ${statusOptions}
            </select>
            <button type="button" class="admin-report-delete-btn" data-report-id="${id}" aria-label="削除" title="削除">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            </button>
          </div>
        </div>
        <div class="admin-report-head-sub">
          <span class="admin-report-time">${created}</span>
        </div>
        <p class="admin-report-desc">${desc}</p>
        <div class="admin-report-meta">
          <span>Session: <code>${sessionId}…</code></span>
          <span>IP: <code>${ip}</code></span>
        </div>
        <details class="admin-report-detail">
          <summary>チャット内容を表示</summary>
          <pre class="admin-report-chat">${escapeHtml(JSON.stringify(r.messages || [], null, 2))}</pre>
        </details>
      </article>
    `;
  });

  container.innerHTML = rows.join("");

  // Bind status change
  container.querySelectorAll(".admin-report-status-select").forEach((sel) => {
    sel.addEventListener("change", () => {
      updateReportStatus(sel.dataset.reportId, sel.value, sel);
    });
  });

  // Bind delete
  container.querySelectorAll(".admin-report-delete-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      deleteReport(btn.dataset.reportId, btn.closest(".admin-report-card"));
    });
  });
}

async function updateReportStatus(reportId, newStatus, selectEl) {
  try {
    const res = await fetch(`/api/admin/reports/${encodeURIComponent(reportId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "更新に失敗しました");

    // Update select class
    const info = REPORT_STATUS_MAP[newStatus] || REPORT_STATUS_MAP.unconfirmed;
    selectEl.className = `admin-report-status-select ${info.cls}`;
    window.NexNotify?.showSuccess("ステータスを更新しました");
  } catch (e) {
    window.NexNotify?.showError(e.message || "更新に失敗しました");
    // Revert select
    const report = await fetchReportById(reportId);
    if (report) {
      selectEl.value = report.status || "unconfirmed";
    }
  }
}

async function deleteReport(reportId, cardEl) {
  if (!cardEl) return;
  const confirmed = await new Promise((resolve) => {
    if (window.NexNotify?.confirm) {
      window.NexNotify.confirm("この報告を削除してもよろしいですか？", "削除の確認").then(resolve);
    } else {
      resolve(confirm("この報告を削除してもよろしいですか？"));
    }
  });
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/admin/reports/${encodeURIComponent(reportId)}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "削除に失敗しました");

    cardEl.style.transition = "opacity 0.2s, transform 0.2s";
    cardEl.style.opacity = "0";
    cardEl.style.transform = "scale(0.95)";
    setTimeout(() => cardEl.remove(), 250);
    window.NexNotify?.showSuccess("報告を削除しました");
  } catch (e) {
    window.NexNotify?.showError(e.message || "削除に失敗しました");
  }
}

async function fetchReportById(reportId) {
  try {
    const res = await fetch("/api/admin/reports");
    const data = await res.json();
    return (data.reports || []).find((r) => r.id === reportId) || null;
  } catch (_) {
    return null;
  }
}
