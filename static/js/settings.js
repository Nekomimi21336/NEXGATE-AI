const generalForm = document.getElementById("generalForm");
const passwordForm = document.getElementById("passwordForm");
const generalMsg = document.getElementById("generalMsg");
const passwordMsg = document.getElementById("passwordMsg");
const navItems = document.querySelectorAll(".settings-nav-item");
const panels = document.querySelectorAll(".settings-panel");
const billingInfoForm = document.getElementById("billingInfoForm");
const billingInfoMsg = document.getElementById("billingInfoMsg");
const billingInfoEmail = document.getElementById("billingInfoEmail");
const billingInfoEmailDisplay = document.getElementById("billingInfoEmailDisplay");
const billingInfoEmailToggle = document.getElementById("billingInfoEmailToggle");
let billingInfoEmailRevealed = false;
const settingsLanguage = document.getElementById("settingsLanguage");
const embedMsg = document.getElementById("embedMsg");
const embedWebSearchEnabled = document.getElementById("embedWebSearchEnabled");
const embedGeolocationEnabled = document.getElementById("embedGeolocationEnabled");
const embedImageGenerationEnabled = document.getElementById("embedImageGenerationEnabled");
const embedUserQuestionsEnabled = document.getElementById("embedUserQuestionsEnabled");
let embedSaving = false;

const themeMsg = document.getElementById("themeMsg");
const settingsTheme = document.getElementById("settingsTheme");
const settingsChatBackground = document.getElementById("settingsChatBackground");
let themeSaving = false;

const displayMsg = document.getElementById("displayMsg");
const displayReasoningCardsEnabled = document.getElementById("displayReasoningCardsEnabled");
const displayToolTraceEnabled = document.getElementById("displayToolTraceEnabled");
const displayExpressionExtensionEnabled = document.getElementById("displayExpressionExtensionEnabled");
const displayFullInfoEnabled = document.getElementById("displayFullInfoEnabled");
let displaySaving = false;

const performanceMsg = document.getElementById("performanceMsg");
const performanceReasoningDisabled = document.getElementById("performanceReasoningDisabled");
const performanceReasoningInEnglish = document.getElementById("performanceReasoningInEnglish");
const performanceReasoningInEnglishRow = document.getElementById("performanceReasoningInEnglishRow");
const performanceReasoningInEnglishHint = document.getElementById("performanceReasoningInEnglishHint");
const performanceCostPerformanceMaximized = document.getElementById(
  "performanceCostPerformanceMaximized"
);
let performanceSaving = false;

const extensionsMsg = document.getElementById("extensionsMsg");
const extensionsTasksEnabled = document.getElementById("extensionsTasksEnabled");
const extensionsMemoryEnabled = document.getElementById("extensionsMemoryEnabled");
const extensionsProjectsEnabled = document.getElementById("extensionsProjectsEnabled");
const extensionsInfoExpertEnabled = document.getElementById("extensionsInfoExpertEnabled");
const extensionsDeepResearchEnabled = document.getElementById("extensionsDeepResearchEnabled");
const extensionsIntelligentSearchOverrideEnabled = document.getElementById(
  "extensionsIntelligentSearchOverrideEnabled"
);
const extensionsDeepResearchPrefsWrap = document.getElementById("extensionsDeepResearchPrefsWrap");
const extensionsDeepResearchMaxRounds = document.getElementById("extensionsDeepResearchMaxRounds");
const extensionsDeepResearchPrefsSave = document.getElementById("extensionsDeepResearchPrefsSave");
let extensionsSaving = false;
let extensionsDeepResearchPrefsSaving = false;

const PANEL_IDS = ["general", "billing-info", "security", "embed", "theme", "display", "performance", "extensions", "memory-settings", "integrations", "agent"];
const settingsApiAccessEnabled = document.getElementById("settingsApiAccessEnabled");
const settingsOnDemandBillingEnabled = document.getElementById("settingsOnDemandBillingEnabled");
const settingsApiPortalActions = document.getElementById("settingsApiPortalActions");
const settingsApiPlanBlockedHint = document.getElementById("settingsApiPlanBlockedHint");
const apiAccessMsg = document.getElementById("apiAccessMsg");
let apiAccessSaving = false;
const settingsMemoryNav = document.getElementById("settingsMemoryNav");
const settingsAgentNav = document.getElementById("settingsAgentNav");
const INTEGRATIONS_TAB_IDS = ["overview", "google", "discord", "computelab"];
let currentIntegrationsTab = "overview";

function parseIntegrationsTabFromHash() {
  const raw = (location.hash || "").slice(1).split("?")[0];
  if (raw === "integrations/google") return "google";
  if (raw === "integrations/discord") return "discord";
  if (raw === "integrations/computelab") return "computelab";
  if (raw === "integrations" || raw.startsWith("integrations/")) return "overview";
  return null;
}

function parseAgentRouteFromHash() {
  const raw = (location.hash || "").slice(1).split("?")[0];
  const editMatch = raw.match(/^agent\/edit\/([^/]+)$/);
  if (editMatch) {
    return { screen: "editor", agentId: decodeURIComponent(editMatch[1]) };
  }
  return { screen: "list", agentId: null };
}

function settingsHashForPanel(panelId, integrationsTab, agentRoute) {
  if (panelId === "general") return "general";
  if (panelId === "integrations" && integrationsTab === "google") return "integrations/google";
  if (panelId === "integrations" && integrationsTab === "discord") return "integrations/discord";
  if (panelId === "integrations" && integrationsTab === "computelab") return "integrations/computelab";
  if (panelId === "agent" && agentRoute?.screen === "editor" && agentRoute.agentId) {
    return `agent/edit/${encodeURIComponent(agentRoute.agentId)}`;
  }
  return panelId;
}

function showIntegrationsTab(tabId, options = {}) {
  const { syncUrl = true } = options;
  if (!INTEGRATIONS_TAB_IDS.includes(tabId)) tabId = "overview";
  currentIntegrationsTab = tabId;
  document.documentElement.setAttribute("data-settings-integrations-tab", tabId);

  document.querySelectorAll("[data-integrations-tab]").forEach((btn) => {
    const active = btn.dataset.integrationsTab === tabId;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });

  document.querySelectorAll("[data-integrations-panel]").forEach((panel) => {
    const active = panel.dataset.integrationsPanel === tabId;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });

  if (!syncUrl) return;

  const hashPart = settingsHashForPanel("integrations", tabId);
  const path = hashPart ? `/settings#${hashPart}` : "/settings";
  if (location.pathname === "/settings" || location.pathname === "/settings/") {
    if (location.pathname + location.hash !== path) {
      history.replaceState(history.state, "", path);
    }
  }
}

function syncExtensionsDeepResearchPrefsFromUser() {
  const prefs = window.__USER__?.deep_research_prefs || {};
  const rounds = String(prefs.max_search_rounds ?? 5);
  if (extensionsDeepResearchMaxRounds) {
    extensionsDeepResearchMaxRounds.value = rounds;
  }
  const showPrefs =
    window.__USER__?.plan_deep_research_enabled === true &&
    window.__USER__?.deep_research_enabled === true;
  extensionsDeepResearchPrefsWrap?.classList.toggle("hidden", !showPrefs);
}

function showPanel(panelId, options = {}) {
  const { syncUrl = true, integrationsTab, agentRoute: agentRouteOption, forceAgentList } = options;
  if (panelId === "profile" || panelId === "account") panelId = "general";
  if (panelId === "agent" && !isCustomAgentsEnabled()) panelId = "general";
  if (!PANEL_IDS.includes(panelId)) panelId = "general";

  document.documentElement.setAttribute("data-settings-panel", panelId);
  if (panelId !== "agent") {
    document.documentElement.removeAttribute("data-custom-agents-screen");
  }

  navItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.panel === panelId);
  });

  panels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${panelId}`);
  });

  if (panelId === "integrations") {
    const tab =
      integrationsTab ??
      parseIntegrationsTabFromHash() ??
      currentIntegrationsTab;
    showIntegrationsTab(tab, { syncUrl: false });
  }

  let agentRoute = null;
  if (panelId === "agent") {
    agentRoute =
      agentRouteOption ??
      (forceAgentList ? { screen: "list", agentId: null } : parseAgentRouteFromHash());
    window.customAgentsSettingsApp?.applyAgentRoute?.(agentRoute, { syncUrl: false });
  } else {
    window.customAgentsSettingsApp?.closeEditor?.({ syncUrl: false });
  }

  if (panelId === "memory-settings") {
    window.memorySettingsApp?.load?.();
  }

  if (!syncUrl) return;

  const hashPart = settingsHashForPanel(panelId, currentIntegrationsTab, agentRoute);
  const path = hashPart ? `/settings#${hashPart}` : "/settings";
  if (location.pathname === "/settings" || location.pathname === "/settings/") {
    if (location.pathname + location.hash !== path) {
      history.replaceState(history.state, "", path);
    }
  }
}

navItems.forEach((item) => {
  item.addEventListener("click", () => {
    if (item.dataset.panel === "integrations") {
      showPanel("integrations", { integrationsTab: "overview" });
      return;
    }
    if (item.dataset.panel === "agent") {
      showPanel("agent", { forceAgentList: true, syncUrl: true });
      return;
    }
    showPanel(item.dataset.panel);
  });
});

document.querySelectorAll("[data-integrations-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    showPanel("integrations", { integrationsTab: btn.dataset.integrationsTab });
  });
});

function isMemoryEnabled() {
  return window.__USER__?.memory_enabled === true;
}

function updateMemoryNavVisibility() {
  if (!settingsMemoryNav) return;
  const enabled = isMemoryEnabled();
  settingsMemoryNav.classList.toggle("hidden", !enabled);
  settingsMemoryNav.setAttribute("aria-hidden", String(!enabled));
  if (!enabled && document.documentElement.getAttribute("data-settings-panel") === "memory-settings") {
    showPanel("extensions", { syncUrl: true });
  }
}

function isCustomAgentsEnabled() {
  return window.__USER__?.custom_agents_enabled === true;
}

function updateAgentNavVisibility() {
  if (!settingsAgentNav) return;
  const enabled = isCustomAgentsEnabled();
  settingsAgentNav.classList.toggle("hidden", !enabled);
  settingsAgentNav.setAttribute("aria-hidden", String(!enabled));
  if (!enabled && document.documentElement.getAttribute("data-settings-panel") === "agent") {
    showPanel("general", { syncUrl: true });
  }
}

window.updateMemoryNavVisibility = updateMemoryNavVisibility;
window.updateAgentNavVisibility = updateAgentNavVisibility;
window.settingsApp = { showPanel, showIntegrationsTab };

if (window.__USER__) {
  updateMemoryNavVisibility();
  updateAgentNavVisibility();
  syncExtensionsDeepResearchPrefsFromUser();
}

function showMsg(el, text, isError) {
  el.textContent = text;
  el.classList.remove("hidden", "success", "error");
  el.classList.add(isError ? "error" : "success");
}

function formatAccountBalance(amount) {
  const value = Math.round(Number(amount) || 0);
  return `¥${value.toLocaleString("ja-JP")}`;
}

function syncLanguageSelect(lang) {
  if (!settingsLanguage) return;
  const value = lang || settingsLanguage.value || "ja";
  if (["ja", "en", "ko"].includes(value)) {
    settingsLanguage.value = value;
  }
}

function updateAccountProfileCard(user) {
  const u = user || window.__USER__ || {};
  const displayName = (u.display_name || u.username || "").trim();
  const initial = (displayName || "?").slice(0, 1).toUpperCase();
  const avatar = document.getElementById("accountProfileAvatar");
  const nameEl = document.getElementById("accountProfileDisplayName");
  const usernameEl = document.getElementById("accountProfileUsername");
  const planEl = document.getElementById("accountProfilePlan");
  const balanceEl = document.getElementById("accountProfileBalance");
  if (avatar) avatar.textContent = initial;
  if (nameEl) nameEl.textContent = displayName || "—";
  if (usernameEl) usernameEl.textContent = u.username || "";
  if (planEl) planEl.textContent = u.plan_name || u.plan || "—";
  if (balanceEl) balanceEl.textContent = formatAccountBalance(u.balance);
}

function maskEmailAddress(email) {
  const value = String(email || "").trim();
  if (!value || !value.includes("@")) return "—";
  const [local, domain] = value.split("@");
  if (!local) return `•••@${domain}`;
  const visible = local.slice(0, 1);
  return `${visible}${"•".repeat(Math.max(2, Math.min(4, local.length - 1)))}@${domain}`;
}

function syncBillingInfoEmailDisplay() {
  const email = billingInfoEmail?.value.trim() || window.__USER__?.email || "";
  if (!billingInfoEmailDisplay) return;
  if (billingInfoEmailRevealed) {
    billingInfoEmailDisplay.textContent = email || "—";
    billingInfoEmailDisplay.classList.add("hidden");
    billingInfoEmail?.classList.remove("hidden");
  } else {
    billingInfoEmailDisplay.textContent = maskEmailAddress(email);
    billingInfoEmailDisplay.classList.remove("hidden");
    billingInfoEmail?.classList.add("hidden");
  }
  if (billingInfoEmailToggle) {
    billingInfoEmailToggle.setAttribute(
      "aria-label",
      billingInfoEmailRevealed ? "メールアドレスを隠す" : "メールアドレスを表示"
    );
  }
}

function collectBillingInfoPayload() {
  return {
    email: billingInfoEmail?.value.trim() ?? "",
    phone: document.getElementById("billingInfoPhone")?.value.trim() ?? "",
    last_name: document.getElementById("billingInfoLastName")?.value.trim() ?? "",
    first_name: document.getElementById("billingInfoFirstName")?.value.trim() ?? "",
    billing_currency: document.getElementById("billingInfoCurrency")?.value || "JPY",
    billing: {
      name: document.getElementById("billingInfoBillingName")?.value.trim() ?? "",
      postal_code: document.getElementById("billingInfoPostal")?.value.trim() ?? "",
      address: document.getElementById("billingInfoAddress")?.value.trim() ?? "",
      country: document.getElementById("billingInfoCountry")?.value.trim() ?? "",
    },
  };
}

function syncBillingInfoFormFromUser(user = window.__USER__) {
  const u = user || {};
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? "";
  };
  set("billingInfoLastName", u.last_name);
  set("billingInfoFirstName", u.first_name);
  set("billingInfoPhone", u.phone);
  set("billingInfoBillingName", u.billing?.name);
  set("billingInfoPostal", u.billing?.postal_code);
  set("billingInfoAddress", u.billing?.address);
  set("billingInfoCountry", u.billing?.country);
  if (billingInfoEmail) billingInfoEmail.value = u.email || "";
  const currencyEl = document.getElementById("billingInfoCurrency");
  if (currencyEl && u.billing_currency) currencyEl.value = u.billing_currency;
  syncBillingInfoEmailDisplay();
}

async function saveBillingInfoSettings(msgEl) {
  msgEl?.classList.add("hidden");
  try {
    const res = await fetch("/api/settings/billing-info", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectBillingInfoPayload()),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(msgEl, data.error || window.t("saveFailed"), true);
      return;
    }
    window.__USER__ = data.user;
    window.updateAccountDisplay?.(data.user);
    updateAccountProfileCard(data.user);
    syncBillingInfoFormFromUser(data.user);
    showMsg(msgEl, window.t("saved"), false);
  } catch {
    showMsg(msgEl, window.t("networkError"), true);
  }
}

function syncApiAccessFormFromUser() {
  const u = window.__USER__ || {};
  const planAllowed = u.plan_api_access_enabled === true;
  const active = u.api_access_active === true;
  if (settingsApiAccessEnabled) {
    settingsApiAccessEnabled.checked = u.api_enabled === true;
    settingsApiAccessEnabled.disabled = !planAllowed || apiAccessSaving;
  }
  if (settingsOnDemandBillingEnabled) {
    settingsOnDemandBillingEnabled.checked = u.on_demand_billing_enabled === true;
    settingsOnDemandBillingEnabled.disabled = apiAccessSaving;
  }
  settingsApiPlanBlockedHint?.classList.toggle("hidden", planAllowed);
  if (settingsApiPlanBlockedHint && !planAllowed) {
    settingsApiPlanBlockedHint.textContent = window.t("apiAccessBlocked");
  }
  settingsApiPortalActions?.classList.toggle("hidden", !active);
}

async function saveApiAccessSettings(payload) {
  if (apiAccessSaving) return;
  apiAccessSaving = true;
  if (settingsApiAccessEnabled) settingsApiAccessEnabled.disabled = true;
  if (settingsOnDemandBillingEnabled) settingsOnDemandBillingEnabled.disabled = true;
  apiAccessMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/api-access", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403
          ? window.t("apiAccessBlocked")
          : data.error || window.t("saveFailed");
      showMsg(apiAccessMsg, msg, true);
      syncApiAccessFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    window.updateAccountDisplay?.(data.user);
    updateAccountProfileCard(data.user);
    syncApiAccessFormFromUser();
    showMsg(apiAccessMsg, window.t("saved"), false);
  } catch {
    showMsg(apiAccessMsg, window.t("networkError"), true);
    syncApiAccessFormFromUser();
  } finally {
    apiAccessSaving = false;
    syncApiAccessFormFromUser();
  }
}

if (settingsApiAccessEnabled) {
  settingsApiAccessEnabled.addEventListener("change", () => {
    saveApiAccessSettings({ api_enabled: settingsApiAccessEnabled.checked });
  });
}

if (settingsOnDemandBillingEnabled) {
  settingsOnDemandBillingEnabled.addEventListener("change", () => {
    saveApiAccessSettings({
      on_demand_billing_enabled: settingsOnDemandBillingEnabled.checked,
    });
  });
}

syncLanguageSelect(window.__USER__?.language);
updateAccountProfileCard(window.__USER__);
syncApiAccessFormFromUser();
window.updateAccountProfileCard = updateAccountProfileCard;

if (generalForm) generalForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  generalMsg.classList.add("hidden");

  const display_name = document.getElementById("settingsDisplayName").value.trim();
  const language = document.getElementById("settingsLanguage").value;
  const theme = window.__USER__?.theme || "dark";
  const chat_background_pattern = getSelectedChatBackgroundPattern();

  try {
    const res = await fetch("/api/settings/general", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name, theme, language, chat_background_pattern }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(generalMsg, data.error || window.t("saveFailed"), true);
      return;
    }

    window.__USER__ = data.user;
    window.updateAccountDisplay?.(data.user);
    updateAccountProfileCard(data.user);
    syncLanguageSelect(data.user.language);
    applyLanguage(data.user.language);

    showMsg(generalMsg, window.t("saved"), false);
  } catch {
    showMsg(generalMsg, window.t("networkError"), true);
  }
});

if (passwordForm) passwordForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  passwordMsg.classList.add("hidden");

  const current_password = document.getElementById("currentPassword").value;
  const new_password = document.getElementById("newPassword").value;
  const confirm = document.getElementById("confirmPassword").value;

  if (new_password !== confirm) {
    showMsg(passwordMsg, "新しいパスワードが一致しません", true);
    return;
  }

  try {
    const res = await fetch("/api/settings/password", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(passwordMsg, data.error || "変更に失敗しました", true);
      return;
    }

    passwordForm.reset();
    showMsg(passwordMsg, "パスワードを変更しました", false);
  } catch {
    showMsg(passwordMsg, "通信エラーが発生しました", true);
  }
});

function syncEmbedFormFromUser() {
  const searchBlocked = Boolean(window.getSystemFeatures?.().search_disabled);
  if (embedWebSearchEnabled) {
    embedWebSearchEnabled.checked = window.__USER__?.web_search_enabled !== false;
    embedWebSearchEnabled.disabled = embedSaving || searchBlocked;
  }
  if (embedGeolocationEnabled) {
    embedGeolocationEnabled.checked = window.__USER__?.geolocation_enabled === true;
    embedGeolocationEnabled.disabled = embedSaving;
  }
  if (embedImageGenerationEnabled) {
    embedImageGenerationEnabled.checked =
      window.__USER__?.image_generation_enabled === true;
    embedImageGenerationEnabled.disabled = embedSaving;
  }
  if (embedUserQuestionsEnabled) {
    embedUserQuestionsEnabled.checked =
      window.__USER__?.user_questions_enabled === true;
    embedUserQuestionsEnabled.disabled = embedSaving;
  }
}

syncEmbedFormFromUser();
window.syncEmbedFormFromUser = syncEmbedFormFromUser;

async function saveEmbedWebSearch(enabled) {
  if (!embedWebSearchEnabled || embedSaving) return;
  embedSaving = true;
  syncEmbedFormFromUser();
  embedMsg?.classList.add("hidden");

  if (window.getSystemFeatures?.().search_disabled) {
    showMsg(embedMsg, window.t("embedSearchBlocked"), true);
    syncEmbedFormFromUser();
    embedSaving = false;
    syncEmbedFormFromUser();
    return;
  }

  try {
    const res = await fetch("/api/settings/embed", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ web_search_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(embedMsg, data.error || window.t("saveFailed"), true);
      syncEmbedFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    window.chatInput?.setWebSearchEnabled?.(data.user.web_search_enabled, { persist: false });
    syncEmbedFormFromUser();
    window.updateChatInputIndicators?.();
    showMsg(embedMsg, window.t("saved"), false);
  } catch {
    showMsg(embedMsg, window.t("networkError"), true);
    syncEmbedFormFromUser();
  } finally {
    embedSaving = false;
    syncEmbedFormFromUser();
  }
}

async function saveEmbedGeolocation(enabled) {
  if (!embedGeolocationEnabled || embedSaving) return;
  embedSaving = true;
  syncEmbedFormFromUser();
  embedMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/embed", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geolocation_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(embedMsg, data.error || window.t("saveFailed"), true);
      syncEmbedFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncEmbedFormFromUser();
    showMsg(embedMsg, window.t("saved"), false);
  } catch {
    showMsg(embedMsg, window.t("networkError"), true);
    syncEmbedFormFromUser();
  } finally {
    embedSaving = false;
    syncEmbedFormFromUser();
  }
}

if (embedWebSearchEnabled) {
  embedWebSearchEnabled.addEventListener("change", () => {
    const enabled = embedWebSearchEnabled.checked;
    window.chatInput?.setWebSearchEnabled?.(enabled, { persist: false });
    saveEmbedWebSearch(enabled);
  });
}

if (embedGeolocationEnabled) {
  embedGeolocationEnabled.addEventListener("change", () => {
    saveEmbedGeolocation(embedGeolocationEnabled.checked);
  });
}

async function saveEmbedImageGeneration(enabled) {
  if (!embedImageGenerationEnabled || embedSaving) return;
  embedSaving = true;
  syncEmbedFormFromUser();
  embedMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/embed", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_generation_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403
          ? window.t("embedImageGenerationBlocked")
          : data.error || window.t("saveFailed");
      showMsg(embedMsg, msg, true);
      syncEmbedFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncEmbedFormFromUser();
    window.invalidateImageGenOptions?.();
    window.updateChatInputIndicators?.();
    showMsg(embedMsg, window.t("saved"), false);
  } catch {
    showMsg(embedMsg, window.t("networkError"), true);
    syncEmbedFormFromUser();
  } finally {
    embedSaving = false;
    syncEmbedFormFromUser();
  }
}

if (embedImageGenerationEnabled) {
  embedImageGenerationEnabled.addEventListener("change", () => {
    saveEmbedImageGeneration(embedImageGenerationEnabled.checked);
  });
}

async function saveEmbedUserQuestions(enabled) {
  if (!embedUserQuestionsEnabled || embedSaving) return;
  embedSaving = true;
  syncEmbedFormFromUser();
  embedMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/embed", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_questions_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(embedMsg, data.error || window.t("saveFailed"), true);
      syncEmbedFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncEmbedFormFromUser();
    showMsg(embedMsg, window.t("saved"), false);
  } catch {
    showMsg(embedMsg, window.t("networkError"), true);
    syncEmbedFormFromUser();
  } finally {
    embedSaving = false;
    syncEmbedFormFromUser();
  }
}

if (embedUserQuestionsEnabled) {
  embedUserQuestionsEnabled.addEventListener("change", () => {
    saveEmbedUserQuestions(embedUserQuestionsEnabled.checked);
  });
}

function getGeneralSettingsPayload(overrides = {}) {
  const display_name = (
    window.__USER__?.display_name ??
    document.getElementById("settingsDisplayName")?.value ??
    ""
  ).trim();
  const theme =
    overrides.theme ??
    settingsTheme?.value ??
    window.__USER__?.theme ??
    "dark";
  const language =
    overrides.language ??
    document.getElementById("settingsLanguage")?.value ??
    window.__USER__?.language ??
    "ja";
  const chat_background_pattern =
    overrides.chat_background_pattern ??
    getSelectedChatBackgroundPattern();
  return { display_name, theme, language, chat_background_pattern };
}

function getSelectedChatBackgroundPattern() {
  const active = settingsChatBackground?.querySelector(".settings-bg-pattern-btn.is-active");
  const pattern = active?.dataset.pattern || window.__USER__?.chat_background_pattern || "simple";
  return pattern === "grid" ? "grid" : "simple";
}

function syncChatBackgroundFormFromUser() {
  if (!settingsChatBackground) return;
  const pattern = window.__USER__?.chat_background_pattern === "grid" ? "grid" : "simple";
  settingsChatBackground.querySelectorAll(".settings-bg-pattern-btn").forEach((btn) => {
    const active = btn.dataset.pattern === pattern;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-checked", active ? "true" : "false");
    btn.disabled = themeSaving;
  });
}

function syncThemeFormFromUser() {
  if (!settingsTheme) return;
  const allowed = ["dark", "light", "system", "midnight"];
  const t = window.__USER__?.theme || "dark";
  settingsTheme.value = allowed.includes(t) ? t : "dark";
}

syncThemeFormFromUser();
syncChatBackgroundFormFromUser();

async function saveThemeSettings(overrides = {}) {
  if (themeSaving) return;
  themeSaving = true;
  if (settingsTheme) settingsTheme.disabled = true;
  syncChatBackgroundFormFromUser();
  themeMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/general", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getGeneralSettingsPayload(overrides)),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(themeMsg, data.error || window.t("saveFailed"), true);
      syncThemeFormFromUser();
      syncChatBackgroundFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncThemeFormFromUser();
    syncChatBackgroundFormFromUser();
    applyTheme(data.user.theme, { animate: false });
    window.applyChatBackground?.(data.user.chat_background_pattern || "simple");
    showMsg(themeMsg, window.t("saved"), false);
  } catch {
    showMsg(themeMsg, window.t("networkError"), true);
    syncThemeFormFromUser();
    syncChatBackgroundFormFromUser();
  } finally {
    themeSaving = false;
    if (settingsTheme) settingsTheme.disabled = false;
    syncChatBackgroundFormFromUser();
  }
}

async function saveTheme(theme) {
  await saveThemeSettings({ theme });
}

if (settingsTheme) {
  settingsTheme.addEventListener("change", () => {
    applyTheme(settingsTheme.value, { animate: true });
    saveThemeSettings({ theme: settingsTheme.value });
  });
}

if (settingsChatBackground) {
  settingsChatBackground.addEventListener("click", (event) => {
    const btn = event.target.closest(".settings-bg-pattern-btn");
    if (!btn || btn.disabled || btn.classList.contains("is-active")) return;
    const pattern = btn.dataset.pattern === "grid" ? "grid" : "simple";
    settingsChatBackground.querySelectorAll(".settings-bg-pattern-btn").forEach((item) => {
      const active = item === btn;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-checked", active ? "true" : "false");
    });
    window.applyChatBackground?.(pattern);
    saveThemeSettings({ chat_background_pattern: pattern });
  });
}

function syncDisplayFormFromUser() {
  if (displayReasoningCardsEnabled) {
    displayReasoningCardsEnabled.checked =
      window.__USER__?.reasoning_cards_enabled === true;
    displayReasoningCardsEnabled.disabled = displaySaving;
  }
  if (displayToolTraceEnabled) {
    displayToolTraceEnabled.checked = window.__USER__?.tool_trace_enabled === true;
    displayToolTraceEnabled.disabled = displaySaving;
  }
  if (displayExpressionExtensionEnabled) {
    displayExpressionExtensionEnabled.checked =
      window.__USER__?.expression_extension_enabled === true;
    displayExpressionExtensionEnabled.disabled = displaySaving;
  }
  const planFullInfoAllowed = window.__USER__?.plan_full_info_display_enabled === true;
  const fullInfoRow = displayFullInfoEnabled?.closest(".settings-toggle-row");
  fullInfoRow?.classList.toggle("hidden", !planFullInfoAllowed);
  if (displayFullInfoEnabled) {
    displayFullInfoEnabled.checked = window.__USER__?.full_info_display_enabled === true;
    displayFullInfoEnabled.disabled = !planFullInfoAllowed || displaySaving;
  }
}

syncDisplayFormFromUser();

async function saveDisplaySettings(payload) {
  if (displaySaving) return;
  displaySaving = true;
  syncDisplayFormFromUser();
  displayMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/display", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(displayMsg, data.error || window.t("saveFailed"), true);
      syncDisplayFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncDisplayFormFromUser();
    window.NexFullInfoPanel?.refresh?.();
    showMsg(displayMsg, window.t("saved"), false);
  } catch {
    showMsg(displayMsg, window.t("networkError"), true);
    syncDisplayFormFromUser();
  } finally {
    displaySaving = false;
    syncDisplayFormFromUser();
  }
}

if (displayReasoningCardsEnabled) {
  displayReasoningCardsEnabled.addEventListener("change", () => {
    saveDisplaySettings({
      reasoning_cards_enabled: Boolean(displayReasoningCardsEnabled.checked),
    });
  });
}

if (displayToolTraceEnabled) {
  displayToolTraceEnabled.addEventListener("change", () => {
    saveDisplaySettings({
      tool_trace_enabled: Boolean(displayToolTraceEnabled.checked),
    });
  });
}

if (displayExpressionExtensionEnabled) {
  displayExpressionExtensionEnabled.addEventListener("change", () => {
    saveDisplaySettings({
      expression_extension_enabled: Boolean(displayExpressionExtensionEnabled.checked),
    });
  });
}

if (displayFullInfoEnabled) {
  displayFullInfoEnabled.addEventListener("change", () => {
    saveDisplaySettings({
      full_info_display_enabled: Boolean(displayFullInfoEnabled.checked),
    });
  });
}

function selectedModelSupportsThinking() {
  return window.getSelectedModel?.()?.supports_thinking === true;
}

function reasoningInEnglishAllowed() {
  return !window.__USER__?.reasoning_disabled && selectedModelSupportsThinking();
}

async function savePerformanceSettings(payload, options = {}) {
  const { silent = false } = options;
  if (performanceSaving) return false;
  performanceSaving = true;
  syncPerformanceFormFromUser();
  performanceMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/performance", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      if (!silent) {
        showMsg(performanceMsg, data.error || window.t("saveFailed"), true);
      }
      syncPerformanceFormFromUser();
      return false;
    }

    window.__USER__ = data.user;
    syncPerformanceFormFromUser();
    if (!silent) {
      showMsg(performanceMsg, window.t("saved"), false);
    }
    return true;
  } catch {
    if (!silent) {
      showMsg(performanceMsg, window.t("networkError"), true);
    }
    syncPerformanceFormFromUser();
    return false;
  } finally {
    performanceSaving = false;
    syncPerformanceFormFromUser();
  }
}

function syncPerformanceFormFromUser() {
  if (performanceReasoningDisabled) {
    performanceReasoningDisabled.checked =
      window.__USER__?.reasoning_disabled === true;
    performanceReasoningDisabled.disabled = performanceSaving;
  }
  if (performanceCostPerformanceMaximized) {
    performanceCostPerformanceMaximized.checked =
      window.__USER__?.cost_performance_maximized === true;
    performanceCostPerformanceMaximized.disabled = performanceSaving;
  }
  if (!performanceReasoningInEnglish) return;

  const allowed = reasoningInEnglishAllowed();
  const storedEnabled = window.__USER__?.reasoning_in_english === true;
  performanceReasoningInEnglish.checked = allowed && storedEnabled;
  performanceReasoningInEnglish.disabled = !allowed || performanceSaving;
  performanceReasoningInEnglishRow?.classList.toggle("is-unavailable", !allowed);

  if (performanceReasoningInEnglishHint) {
    performanceReasoningInEnglishHint.classList.toggle("hidden", allowed);
    if (!allowed) {
      const parts = [];
      if (window.__USER__?.reasoning_disabled) {
        parts.push(window.t("performanceReasoningInEnglishBlockedDisabled"));
      } else if (!selectedModelSupportsThinking()) {
        parts.push(window.t("performanceReasoningInEnglishBlockedModel"));
      }
      performanceReasoningInEnglishHint.textContent = parts.join(" ");
    }
  }

  if (!allowed && storedEnabled && !performanceSaving) {
    savePerformanceSettings({ reasoning_in_english: false }, { silent: true });
  }
}

window.updatePerformanceReasoningInEnglishState = syncPerformanceFormFromUser;

syncPerformanceFormFromUser();

async function savePerformanceReasoningDisabled(disabled) {
  if (!performanceReasoningDisabled) return;
  const payload = { reasoning_disabled: Boolean(disabled) };
  if (disabled) {
    payload.reasoning_in_english = false;
  }
  await savePerformanceSettings(payload);
}

if (performanceReasoningDisabled) {
  performanceReasoningDisabled.addEventListener("change", () => {
    savePerformanceReasoningDisabled(performanceReasoningDisabled.checked);
  });
}

async function savePerformanceReasoningInEnglish(enabled) {
  if (!performanceReasoningInEnglish || !reasoningInEnglishAllowed()) return;
  await savePerformanceSettings({ reasoning_in_english: Boolean(enabled) });
}

if (performanceReasoningInEnglish) {
  performanceReasoningInEnglish.addEventListener("change", () => {
    if (!reasoningInEnglishAllowed()) {
      syncPerformanceFormFromUser();
      return;
    }
    savePerformanceReasoningInEnglish(performanceReasoningInEnglish.checked);
  });
}

if (performanceCostPerformanceMaximized) {
  performanceCostPerformanceMaximized.addEventListener("change", () => {
    savePerformanceSettings({
      cost_performance_maximized: Boolean(performanceCostPerformanceMaximized.checked),
    });
  });
}

function syncExtensionsFormFromUser() {
  if (extensionsTasksEnabled) {
    extensionsTasksEnabled.checked = window.__USER__?.tasks_enabled === true;
    extensionsTasksEnabled.disabled = extensionsSaving;
  }
  if (extensionsMemoryEnabled) {
    extensionsMemoryEnabled.checked = window.__USER__?.memory_enabled === true;
    extensionsMemoryEnabled.disabled = extensionsSaving;
  }
  if (extensionsProjectsEnabled) {
    extensionsProjectsEnabled.checked = window.__USER__?.projects_enabled === true;
    extensionsProjectsEnabled.disabled = extensionsSaving;
  }
  if (extensionsInfoExpertEnabled) {
    extensionsInfoExpertEnabled.checked = window.__USER__?.info_expert_enabled === true;
    extensionsInfoExpertEnabled.disabled = extensionsSaving;
  }
  if (extensionsDeepResearchEnabled) {
    extensionsDeepResearchEnabled.checked = window.__USER__?.deep_research_enabled === true;
    extensionsDeepResearchEnabled.disabled = extensionsSaving;
  }
  if (extensionsIntelligentSearchOverrideEnabled) {
    extensionsIntelligentSearchOverrideEnabled.checked =
      window.__USER__?.intelligent_search_override_enabled === true;
    extensionsIntelligentSearchOverrideEnabled.disabled = extensionsSaving;
  }
}

syncExtensionsFormFromUser();

async function saveExtensionsTasks(enabled) {
  if (!extensionsTasksEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tasks_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403 ? window.t("extensionsTasksBlocked") : data.error || window.t("saveFailed");
      showMsg(extensionsMsg, msg, true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    window.updateTasksNavVisibility?.();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsTasksEnabled) {
  extensionsTasksEnabled.addEventListener("change", () => {
    saveExtensionsTasks(extensionsTasksEnabled.checked);
  });
}

async function saveExtensionsMemory(enabled) {
  if (!extensionsMemoryEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memory_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403 ? window.t("extensionsMemoryBlocked") : data.error || window.t("saveFailed");
      showMsg(extensionsMsg, msg, true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    window.updateMemoryNavVisibility?.();
    if (data.user?.memory_enabled) {
      window.memorySettingsApp?.load?.();
    }
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsMemoryEnabled) {
  extensionsMemoryEnabled.addEventListener("change", () => {
    saveExtensionsMemory(extensionsMemoryEnabled.checked);
  });
}

async function saveExtensionsProjects(enabled) {
  if (!extensionsProjectsEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projects_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403 ? window.t("extensionsProjectsBlocked") : data.error || window.t("saveFailed");
      showMsg(extensionsMsg, msg, true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    window.updateProjectsNavVisibility?.();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsProjectsEnabled) {
  extensionsProjectsEnabled.addEventListener("change", () => {
    saveExtensionsProjects(extensionsProjectsEnabled.checked);
  });
}

async function saveExtensionsInfoExpert(enabled) {
  if (!extensionsInfoExpertEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ info_expert_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMsg(extensionsMsg, data.error || window.t("saveFailed"), true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    window.updateTasksNavVisibility?.();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsInfoExpertEnabled) {
  extensionsInfoExpertEnabled.addEventListener("change", () => {
    saveExtensionsInfoExpert(extensionsInfoExpertEnabled.checked);
  });
}

async function saveExtensionsDeepResearch(enabled) {
  if (!extensionsDeepResearchEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deep_research_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403
          ? window.t("extensionsDeepResearchBlocked")
          : data.error || window.t("saveFailed");
      showMsg(extensionsMsg, msg, true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    syncExtensionsDeepResearchPrefsFromUser();
    window.updateChatInputIndicators?.();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsDeepResearchEnabled) {
  extensionsDeepResearchEnabled.addEventListener("change", () => {
    saveExtensionsDeepResearch(extensionsDeepResearchEnabled.checked);
  });
}

async function saveExtensionsIntelligentSearchOverride(enabled) {
  if (!extensionsIntelligentSearchOverrideEnabled || extensionsSaving) return;
  extensionsSaving = true;
  syncExtensionsFormFromUser();
  extensionsMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/extensions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intelligent_search_override_enabled: Boolean(enabled) }),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg =
        res.status === 403
          ? window.t("extensionsIntelligentSearchOverrideBlocked")
          : data.error || window.t("saveFailed");
      showMsg(extensionsMsg, msg, true);
      syncExtensionsFormFromUser();
      return;
    }

    window.__USER__ = data.user;
    syncExtensionsFormFromUser();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
    syncExtensionsFormFromUser();
  } finally {
    extensionsSaving = false;
    syncExtensionsFormFromUser();
  }
}

if (extensionsIntelligentSearchOverrideEnabled) {
  extensionsIntelligentSearchOverrideEnabled.addEventListener("change", () => {
    saveExtensionsIntelligentSearchOverride(extensionsIntelligentSearchOverrideEnabled.checked);
  });
}

async function saveExtensionsDeepResearchPrefs() {
  if (!extensionsDeepResearchMaxRounds || extensionsDeepResearchPrefsSaving) return;
  extensionsDeepResearchPrefsSaving = true;
  extensionsDeepResearchPrefsSave && (extensionsDeepResearchPrefsSave.disabled = true);
  extensionsMsg?.classList.add("hidden");
  try {
    const max_search_rounds = parseInt(extensionsDeepResearchMaxRounds.value, 10);
    const res = await fetch("/api/settings/deep-research", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deep_research_prefs: { max_search_rounds } }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(
        extensionsMsg,
        res.status === 403 ? window.t("extensionsDeepResearchPrefsBlocked") : data.error || window.t("saveFailed"),
        true
      );
      syncExtensionsDeepResearchPrefsFromUser();
      return;
    }
    window.__USER__ = data.user;
    syncExtensionsDeepResearchPrefsFromUser();
    showMsg(extensionsMsg, window.t("saved"), false);
  } catch {
    showMsg(extensionsMsg, window.t("networkError"), true);
  } finally {
    extensionsDeepResearchPrefsSaving = false;
    if (extensionsDeepResearchPrefsSave) extensionsDeepResearchPrefsSave.disabled = false;
  }
}

if (extensionsDeepResearchPrefsSave) {
  extensionsDeepResearchPrefsSave.addEventListener("click", saveExtensionsDeepResearchPrefs);
}

const googleConnectBtn = document.getElementById("googleConnectBtn");
const googleDisconnectBtn = document.getElementById("googleDisconnectBtn");
const googleConnectionStatus = document.getElementById("googleConnectionStatus");
const integrationsGoogleOverviewStatus = document.getElementById("integrationsGoogleOverviewStatus");
const googleOAuthHint = document.getElementById("googleOAuthHint");
const googleSettingsSections = document.getElementById("googleSettingsSections");
const googleToolsSection = document.getElementById("googleToolsSection");
const googleFeaturesSection = document.getElementById("googleFeaturesSection");
const googleCalendarEnabled = document.getElementById("googleCalendarEnabled");
const googleGmailEnabled = document.getElementById("googleGmailEnabled");
const googleLoginEnabled = document.getElementById("googleLoginEnabled");
const googleLoginLinkBtn = document.getElementById("googleLoginLinkBtn");
const googleLoginEmailHint = document.getElementById("googleLoginEmailHint");
const googleMsg = document.getElementById("googleMsg");
const googlePlanBlockedHint = document.getElementById("googlePlanBlockedHint");
let googleSaving = false;
let googleStatusCache = null;

const GOOGLE_INTEGRATION_TOOL_COUNT = 2;

function googleToolsEnabledCount(status) {
  const cal = Boolean(
    status?.user_calendar_toggle ??
      status?.google_calendar_enabled ??
      window.__USER__?.google_calendar_enabled
  );
  const mail = Boolean(
    status?.user_gmail_toggle ??
      status?.google_gmail_enabled ??
      window.__USER__?.google_gmail_enabled
  );
  return (cal ? 1 : 0) + (mail ? 1 : 0);
}

function googleStatusText(connected) {
  return connected
    ? window.t("integrationsGoogleStatusConnected")
    : window.t("integrationsGoogleStatusDisconnected");
}

function googleOverviewStatusText(connected, status) {
  if (!connected) return window.t("integrationsGoogleStatusDisconnected");
  const enabled = googleToolsEnabledCount(status);
  return window
    .t("integrationsGoogleOverviewConnected")
    .replace("{total}", String(GOOGLE_INTEGRATION_TOOL_COUNT))
    .replace("{enabled}", String(enabled));
}

function applyGoogleUi(status) {
  googleStatusCache = status;
  const configured = status?.configured ?? window.__USER__?.google_oauth_configured;
  const connected = status?.connected ?? window.__USER__?.google_connected;
  const planCal = status?.plan_google_calendar ?? window.__USER__?.plan_google_calendar;
  const planMail = status?.plan_google_gmail ?? window.__USER__?.plan_google_gmail;

  if (googleConnectionStatus) {
    googleConnectionStatus.textContent = googleStatusText(connected);
    googleConnectionStatus.removeAttribute("data-i18n");
  }
  if (integrationsGoogleOverviewStatus) {
    integrationsGoogleOverviewStatus.textContent = googleOverviewStatusText(
      connected,
      status
    );
    integrationsGoogleOverviewStatus.removeAttribute("data-i18n");
  }

  if (googleOAuthHint) {
    googleOAuthHint.classList.toggle("hidden", Boolean(configured));
  }
  if (googleConnectBtn) {
    googleConnectBtn.disabled = !configured || connected;
    googleConnectBtn.classList.toggle("hidden", connected);
  }
  if (googleDisconnectBtn) {
    googleDisconnectBtn.classList.toggle("hidden", !connected);
  }
  if (googleSettingsSections) {
    googleSettingsSections.classList.toggle("hidden", !configured);
  }
  if (googleToolsSection) {
    googleToolsSection.classList.toggle("hidden", !connected);
  }

  const loginEnabled = Boolean(
    status?.google_login_enabled ?? window.__USER__?.google_login_enabled
  );
  const loginLinked = Boolean(
    status?.google_login_linked ?? window.__USER__?.google_login_linked
  );
  const loginEmail = (status?.google_email ?? window.__USER__?.google_email ?? "").trim();
  const systemLoginAllowed = Boolean(
    status?.system_google_login_allowed ?? window.__USER__?.system_google_login_allowed
  );

  if (googleLoginEnabled) {
    googleLoginEnabled.checked = loginEnabled;
    googleLoginEnabled.disabled =
      googleSaving || !configured || !systemLoginAllowed;
  }
  if (googleLoginLinkBtn) {
    const showLink = configured && loginEnabled && !loginLinked && systemLoginAllowed;
    googleLoginLinkBtn.classList.toggle("hidden", !showLink);
  }
  if (googleLoginEmailHint) {
    if (loginLinked && loginEmail) {
      googleLoginEmailHint.textContent = window
        .t("integrationsGoogleLoginLinkedEmail")
        .replace("{email}", loginEmail);
      googleLoginEmailHint.classList.remove("hidden");
    } else {
      googleLoginEmailHint.classList.add("hidden");
    }
  }

  if (googleCalendarEnabled) {
    googleCalendarEnabled.checked = Boolean(
      status?.google_calendar_enabled ?? window.__USER__?.google_calendar_enabled
    );
    googleCalendarEnabled.disabled = googleSaving || !connected || !planCal;
  }
  if (googleGmailEnabled) {
    googleGmailEnabled.checked = Boolean(
      status?.google_gmail_enabled ?? window.__USER__?.google_gmail_enabled
    );
    googleGmailEnabled.disabled = googleSaving || !connected || !planMail;
  }

  if (googlePlanBlockedHint) {
    const blocked =
      connected && (!planCal || !planMail);
    googlePlanBlockedHint.classList.toggle("hidden", !blocked);
    if (blocked) {
      const parts = [];
      if (!planCal) parts.push(window.t("integrationsGooglePlanBlockedCalendar"));
      if (!planMail) parts.push(window.t("integrationsGooglePlanBlockedGmail"));
      googlePlanBlockedHint.textContent = parts.join(" ");
    }
  }
}

async function refreshGoogleStatus() {
  try {
    const res = await fetch("/api/settings/google");
    const data = await res.json();
    if (res.ok) applyGoogleUi(data);
  } catch {
    applyGoogleUi({});
  }
}

function handleGoogleOAuthRedirectQuery() {
  const params = new URLSearchParams(location.search);
  if (params.get("google_connected") === "1") {
    showMsg(googleMsg, window.t("integrationsGoogleConnectSuccess"), false);
    history.replaceState(history.state, "", location.pathname + location.hash);
  }
  if (params.get("google_login_linked") === "1") {
    showMsg(googleMsg, window.t("integrationsGoogleLoginLinkSuccess"), false);
    history.replaceState(history.state, "", location.pathname + location.hash);
  }
  const err = params.get("google_error");
  if (err) {
    showMsg(googleMsg, `${window.t("integrationsGoogleConnectFailed")}: ${err}`, true);
    history.replaceState(history.state, "", location.pathname + location.hash);
  }
}

async function saveGoogleToggle(field, enabled) {
  if (googleSaving) return;
  googleSaving = true;
  if (googleCalendarEnabled) googleCalendarEnabled.disabled = true;
  if (googleGmailEnabled) googleGmailEnabled.disabled = true;
  if (googleLoginEnabled) googleLoginEnabled.disabled = true;
  googleMsg?.classList.add("hidden");

  try {
    const res = await fetch("/api/settings/google", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: Boolean(enabled) }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(googleMsg, data.error || window.t("saveFailed"), true);
      applyGoogleUi(googleStatusCache || {});
      return;
    }
    window.__USER__ = data.user;
    applyGoogleUi(data.google);
    showMsg(googleMsg, window.t("saved"), false);
  } catch {
    showMsg(googleMsg, window.t("networkError"), true);
    applyGoogleUi(googleStatusCache || {});
  } finally {
    googleSaving = false;
    applyGoogleUi(googleStatusCache || {});
  }
}

applyGoogleUi({});
refreshGoogleStatus();
handleGoogleOAuthRedirectQuery();

(function () {
  const prevApplyLanguage = window.applyLanguage;
  if (typeof prevApplyLanguage === "function") {
    window.applyLanguage = function (lang) {
      prevApplyLanguage(lang);
      applyGoogleUi(googleStatusCache || {});
    };
  }
})();

if (googleConnectBtn) {
  googleConnectBtn.addEventListener("click", () => {
    window.location.href = "/api/auth/google";
  });
}

if (googleDisconnectBtn) {
  googleDisconnectBtn.addEventListener("click", async () => {
    googleDisconnectBtn.disabled = true;
    try {
      const res = await fetch("/api/settings/google/disconnect", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        showMsg(googleMsg, data.error || window.t("saveFailed"), true);
        return;
      }
      window.__USER__ = data.user;
      applyGoogleUi(data.google);
      showMsg(googleMsg, window.t("saved"), false);
    } catch {
      showMsg(googleMsg, window.t("networkError"), true);
    } finally {
      googleDisconnectBtn.disabled = false;
    }
  });
}

if (googleCalendarEnabled) {
  googleCalendarEnabled.addEventListener("change", () => {
    if (!googleStatusCache?.plan_google_calendar) {
      showMsg(googleMsg, window.t("integrationsGooglePlanBlockedCalendar"), true);
      googleCalendarEnabled.checked = false;
      return;
    }
    saveGoogleToggle("google_calendar_enabled", googleCalendarEnabled.checked);
  });
}

if (googleGmailEnabled) {
  googleGmailEnabled.addEventListener("change", () => {
    if (!googleStatusCache?.plan_google_gmail) {
      showMsg(googleMsg, window.t("integrationsGooglePlanBlockedGmail"), true);
      googleGmailEnabled.checked = false;
      return;
    }
    saveGoogleToggle("google_gmail_enabled", googleGmailEnabled.checked);
  });
}

if (googleLoginEnabled) {
  googleLoginEnabled.addEventListener("change", () => {
    saveGoogleToggle("google_login_enabled", googleLoginEnabled.checked);
  });
}

if (googleLoginLinkBtn) {
  googleLoginLinkBtn.addEventListener("click", () => {
    window.location.href = "/api/auth/google/link";
  });
}

const integrationsDiscordOverviewStatus = document.getElementById(
  "integrationsDiscordOverviewStatus"
);
const discordConnectionStatus = document.getElementById("discordConnectionStatus");
const discordOAuthHint = document.getElementById("discordOAuthHint");
const discordSettingsSections = document.getElementById("discordSettingsSections");
const discordLoginEnabled = document.getElementById("discordLoginEnabled");
const discordLoginLinkBtn = document.getElementById("discordLoginLinkBtn");
const discordLoginUsernameHint = document.getElementById("discordLoginUsernameHint");
const discordMsg = document.getElementById("discordMsg");
let discordSaving = false;
let discordStatusCache = null;

function discordStatusText(connected) {
  return connected
    ? window.t("integrationsDiscordStatusConnected")
    : window.t("integrationsDiscordStatusDisconnected");
}

function applyDiscordUi(status) {
  discordStatusCache = status;
  const configured = status?.configured ?? window.__USER__?.discord_oauth_configured;
  const connected = status?.connected ?? status?.discord_login_linked ?? window.__USER__?.discord_login_linked;
  const loginEnabled = Boolean(
    status?.discord_login_enabled ?? window.__USER__?.discord_login_enabled
  );
  const loginLinked = Boolean(
    status?.discord_login_linked ?? window.__USER__?.discord_login_linked
  );
  const discordUsername = (status?.discord_username ?? window.__USER__?.discord_username ?? "").trim();
  const systemLoginAllowed = Boolean(
    status?.system_discord_login_allowed ?? window.__USER__?.system_discord_login_allowed
  );

  if (discordConnectionStatus) {
    discordConnectionStatus.textContent = discordStatusText(connected);
    discordConnectionStatus.removeAttribute("data-i18n");
  }
  if (integrationsDiscordOverviewStatus) {
    integrationsDiscordOverviewStatus.textContent = discordStatusText(connected);
    integrationsDiscordOverviewStatus.removeAttribute("data-i18n");
  }
  if (discordOAuthHint) {
    discordOAuthHint.classList.toggle("hidden", Boolean(configured));
  }
  if (discordSettingsSections) {
    discordSettingsSections.classList.toggle("hidden", !configured);
  }
  if (discordLoginEnabled) {
    discordLoginEnabled.checked = loginEnabled;
    discordLoginEnabled.disabled =
      discordSaving || !configured || !systemLoginAllowed;
  }
  if (discordLoginLinkBtn) {
    const showLink = configured && loginEnabled && !loginLinked && systemLoginAllowed;
    discordLoginLinkBtn.classList.toggle("hidden", !showLink);
  }
  if (discordLoginUsernameHint) {
    if (loginLinked && discordUsername) {
      discordLoginUsernameHint.textContent = window
        .t("integrationsDiscordLoginLinkedUsername")
        .replace("{username}", discordUsername);
      discordLoginUsernameHint.classList.remove("hidden");
    } else {
      discordLoginUsernameHint.classList.add("hidden");
    }
  }
}

async function loadDiscordSettings() {
  try {
    const res = await fetch("/api/settings/discord");
    const data = await res.json();
    if (!res.ok) return;
    applyDiscordUi(data);
  } catch {
    /* ignore */
  }
}

function handleDiscordOAuthRedirectQuery() {
  const hash = location.hash || "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : location.search.slice(1);
  const params = new URLSearchParams(query);
  const hashPath = hash.split("?")[0] || hash;
  if (params.get("discord_login_linked") === "1") {
    showMsg(discordMsg, window.t("integrationsDiscordLoginLinkSuccess"), false);
    history.replaceState(history.state, "", location.pathname + hashPath);
  }
  const err = params.get("discord_error");
  if (err) {
    showMsg(discordMsg, `${window.t("integrationsDiscordConnectFailed")}: ${err}`, true);
    history.replaceState(history.state, "", location.pathname + hashPath);
  }
}

async function saveDiscordToggle(field, value) {
  if (discordSaving) return;
  discordSaving = true;
  if (discordLoginEnabled) discordLoginEnabled.disabled = true;
  discordMsg?.classList.add("hidden");
  try {
    const body = { [field]: value };
    const res = await fetch("/api/settings/discord", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(discordMsg, data.error || window.t("saveFailed"), true);
      applyDiscordUi(discordStatusCache || {});
      return;
    }
    window.__USER__ = data.user;
    applyDiscordUi(data.discord);
    showMsg(discordMsg, window.t("saved"), false);
  } catch {
    showMsg(discordMsg, window.t("networkError"), true);
    applyDiscordUi(discordStatusCache || {});
  } finally {
    discordSaving = false;
    applyDiscordUi(discordStatusCache || {});
  }
}

loadDiscordSettings();
handleDiscordOAuthRedirectQuery();

if (discordLoginEnabled) {
  discordLoginEnabled.addEventListener("change", () => {
    saveDiscordToggle("discord_login_enabled", discordLoginEnabled.checked);
  });
}

if (discordLoginLinkBtn) {
  discordLoginLinkBtn.addEventListener("click", () => {
    window.location.href = "/api/auth/discord/link";
  });
}

const integrationsComputelabOverviewStatus = document.getElementById(
  "integrationsComputelabOverviewStatus"
);
const computelabConnectionStatus = document.getElementById("computelabConnectionStatus");
const computelabSettingsSections = document.getElementById("computelabSettingsSections");
const computelabToolsSection = document.getElementById("computelabToolsSection");
const computelabApiKey = document.getElementById("computelabApiKey");
const computelabKeyPrefixHint = document.getElementById("computelabKeyPrefixHint");
const computelabSaveKeyBtn = document.getElementById("computelabSaveKeyBtn");
const computelabDisconnectBtn = document.getElementById("computelabDisconnectBtn");
const computelabToolsEnabled = document.getElementById("computelabToolsEnabled");
const computelabMsg = document.getElementById("computelabMsg");
let computelabSaving = false;
let computelabStatusCache = null;

function computelabStatusText(connected) {
  return connected
    ? window.t("integrationsComputelabStatusConnected")
    : window.t("integrationsComputelabStatusDisconnected");
}

function computelabOverviewStatusText(connected, status) {
  if (!connected) return window.t("integrationsComputelabStatusDisconnected");
  const toolsOn = Boolean(
    status?.user_tools_toggle ??
      status?.computelab_tools_enabled ??
      window.__USER__?.computelab_tools_enabled
  );
  return toolsOn
    ? window.t("integrationsComputelabOverviewToolsOn")
    : window.t("integrationsComputelabOverviewConnected");
}

function applyComputelabUi(status) {
  computelabStatusCache = status;
  const connected = status?.connected ?? window.__USER__?.computelab_connected;
  const keyPrefix = (status?.key_prefix ?? window.__USER__?.computelab_key_prefix ?? "").trim();

  if (computelabConnectionStatus) {
    computelabConnectionStatus.textContent = computelabStatusText(connected);
    computelabConnectionStatus.removeAttribute("data-i18n");
  }
  if (integrationsComputelabOverviewStatus) {
    integrationsComputelabOverviewStatus.textContent = computelabOverviewStatusText(
      connected,
      status
    );
    integrationsComputelabOverviewStatus.removeAttribute("data-i18n");
  }
  if (computelabSettingsSections) {
    computelabSettingsSections.classList.toggle("hidden", !connected);
  }
  if (computelabToolsSection) {
    computelabToolsSection.classList.toggle("hidden", !connected);
  }
  if (computelabDisconnectBtn) {
    computelabDisconnectBtn.classList.toggle("hidden", !connected);
  }
  if (computelabSaveKeyBtn) {
    computelabSaveKeyBtn.disabled = computelabSaving;
  }
  if (computelabKeyPrefixHint) {
    if (connected && keyPrefix) {
      computelabKeyPrefixHint.textContent = window
        .t("integrationsComputelabKeyPrefix")
        .replace("{prefix}", keyPrefix);
      computelabKeyPrefixHint.classList.remove("hidden");
    } else {
      computelabKeyPrefixHint.classList.add("hidden");
    }
  }
  if (computelabApiKey && connected) {
    computelabApiKey.value = "";
    computelabApiKey.placeholder = window.t("integrationsComputelabApiKeyReplace");
  }
  if (computelabToolsEnabled) {
    computelabToolsEnabled.checked = Boolean(
      status?.computelab_tools_enabled ?? window.__USER__?.computelab_tools_enabled
    );
    computelabToolsEnabled.disabled = computelabSaving || !connected;
  }
}

async function refreshComputelabStatus() {
  try {
    const res = await fetch("/api/settings/computelab");
    const data = await res.json();
    if (res.ok) applyComputelabUi(data);
  } catch {
    applyComputelabUi({});
  }
}

async function saveComputelabApiKey() {
  if (computelabSaving || !computelabApiKey) return;
  const apiKey = computelabApiKey.value.trim();
  if (!apiKey) {
    showMsg(computelabMsg, window.t("integrationsComputelabApiKeyRequired"), true);
    return;
  }
  computelabSaving = true;
  if (computelabSaveKeyBtn) computelabSaveKeyBtn.disabled = true;
  computelabMsg?.classList.add("hidden");
  try {
    const res = await fetch("/api/settings/computelab", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(computelabMsg, data.error || window.t("saveFailed"), true);
      return;
    }
    window.__USER__ = data.user;
    computelabApiKey.value = "";
    applyComputelabUi(data.computelab);
    showMsg(computelabMsg, window.t("integrationsComputelabConnectSuccess"), false);
  } catch {
    showMsg(computelabMsg, window.t("networkError"), true);
  } finally {
    computelabSaving = false;
    applyComputelabUi(computelabStatusCache || {});
  }
}

async function saveComputelabToolsToggle(enabled) {
  if (computelabSaving) return;
  computelabSaving = true;
  if (computelabToolsEnabled) computelabToolsEnabled.disabled = true;
  computelabMsg?.classList.add("hidden");
  try {
    const res = await fetch("/api/settings/computelab", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ computelab_tools_enabled: Boolean(enabled) }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMsg(computelabMsg, data.error || window.t("saveFailed"), true);
      applyComputelabUi(computelabStatusCache || {});
      return;
    }
    window.__USER__ = data.user;
    applyComputelabUi(data.computelab);
    showMsg(computelabMsg, window.t("saved"), false);
  } catch {
    showMsg(computelabMsg, window.t("networkError"), true);
    applyComputelabUi(computelabStatusCache || {});
  } finally {
    computelabSaving = false;
    applyComputelabUi(computelabStatusCache || {});
  }
}

applyComputelabUi({});
refreshComputelabStatus();

(function () {
  const prevApplyLanguage = window.applyLanguage;
  if (typeof prevApplyLanguage === "function") {
    window.applyLanguage = function (lang) {
      prevApplyLanguage(lang);
      applyComputelabUi(computelabStatusCache || {});
    };
  }
})();

if (computelabSaveKeyBtn) {
  computelabSaveKeyBtn.addEventListener("click", () => saveComputelabApiKey());
}

if (computelabDisconnectBtn) {
  computelabDisconnectBtn.addEventListener("click", async () => {
    computelabDisconnectBtn.disabled = true;
    try {
      const res = await fetch("/api/settings/computelab/disconnect", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        showMsg(computelabMsg, data.error || window.t("saveFailed"), true);
        return;
      }
      window.__USER__ = data.user;
      if (computelabApiKey) computelabApiKey.value = "";
      applyComputelabUi(data.computelab);
      showMsg(computelabMsg, window.t("saved"), false);
    } catch {
      showMsg(computelabMsg, window.t("networkError"), true);
    } finally {
      computelabDisconnectBtn.disabled = false;
    }
  });
}

if (computelabToolsEnabled) {
  computelabToolsEnabled.addEventListener("change", () => {
    saveComputelabToolsToggle(computelabToolsEnabled.checked);
  });
}

if (billingInfoForm) {
  billingInfoForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    await saveBillingInfoSettings(billingInfoMsg);
  });
}

const settingsApiPortalLink = document.getElementById("settingsApiPortalLink");
if (settingsApiPortalLink) {
  settingsApiPortalLink.href = "/api/auth/go-portal";
}
