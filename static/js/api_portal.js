(function () {
  const tokenList = document.getElementById("apiPortalTokenList");
  const tokenEmpty = document.getElementById("apiPortalTokenEmpty");
  const createForm = document.getElementById("apiPortalCreateForm");
  const createMsg = document.getElementById("apiPortalCreateMsg");
  const secretBox = document.getElementById("apiPortalSecretBox");
  const secretValue = document.getElementById("apiPortalSecretValue");
  const copySecretBtn = document.getElementById("apiPortalCopySecret");
  const usageList = document.getElementById("apiPortalUsageList");
  const usageEmpty = document.getElementById("apiPortalUsageEmpty");
  const profileSummary = document.getElementById("apiPortalProfileSummary");
  const usageChartCanvas = document.getElementById("apiPortalUsageChart");
  const usageChartMeta = document.getElementById("apiPortalUsageChartMeta");
  const usageChartTotals = document.getElementById("apiPortalUsageChartTotals");
  let usageChartInstance = null;
  const docsEndpoint = document.getElementById("apiPortalDocsEndpoint");
  const docsCurl = document.getElementById("apiPortalDocsCurl");
  const dashPlan = document.getElementById("apiPortalDashPlan");
  const dashBudget = document.getElementById("apiPortalDashBudget");
  const dashTokens = document.getElementById("apiPortalDashTokens");
  const dashRequests = document.getElementById("apiPortalDashRequests");
  const dashEndpoint = document.getElementById("apiPortalDashEndpoint");

  const publicApiBase = (window.__PUBLIC_API_BASE__ || "").replace(/\/$/, "");
  const frontendBase = (window.__FRONTEND_BASE__ || "").replace(/\/$/, "");

  function redirectToApiSettings() {
    const target = frontendBase ? `${frontendBase}/settings#general` : "/settings#general";
    window.location.replace(target);
  }

  function t(key) {
    return window.t ? window.t(key) : key;
  }

  function showMsg(el, text, isError) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove("hidden", "success", "error");
    el.classList.add(isError ? "error" : "success");
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  async function fetchJson(url, options = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 403 && /API/.test(String(data.error || ""))) {
      redirectToApiSettings();
      throw new Error(data.error || "API access disabled");
    }
    if (!res.ok) {
      throw new Error(data.error || res.statusText || "Request failed");
    }
    return data;
  }

  function apiEndpointText() {
    return `POST ${publicApiBase}/v1/chat/completions`;
  }

  function renderDocs() {
    const endpoint = apiEndpointText();
    if (docsEndpoint) docsEndpoint.textContent = endpoint;
    if (dashEndpoint) dashEndpoint.textContent = endpoint;
    if (docsCurl) {
      docsCurl.textContent = `# 利用可能なモデル一覧
curl ${publicApiBase}/v1/models \\
  -H "Authorization: Bearer ngx_YOUR_TOKEN"

# チャット補完
curl ${publicApiBase}/v1/chat/completions \\
  -H "Authorization: Bearer ngx_YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"API_MODEL_ID","messages":[{"role":"user","content":"Hello"}]}'`;
    }
  }

  function renderTokens(tokens) {
    if (!tokenList) return tokens;
    const rows = Array.isArray(tokens) ? tokens : [];
    tokenEmpty?.classList.toggle("hidden", rows.length > 0);
    tokenList.innerHTML = rows
      .map((token) => {
        const revoked = !token.active;
        return `<li class="api-portal-token-item${revoked ? " is-revoked" : ""}">
          <div class="api-portal-token-main">
            <strong>${escapeHtml(token.name || "Token")}</strong>
            <code>${escapeHtml(token.prefix || "")}…</code>
          </div>
          <div class="api-portal-token-meta">
            <span>${escapeHtml((token.created_at || "").slice(0, 16))}</span>
            ${
              revoked
                ? `<span>${escapeHtml(t("apiPortalRevoked"))}</span>`
                : `<button type="button" class="settings-btn settings-btn--ghost api-portal-revoke" data-id="${escapeHtml(token.id)}">${escapeHtml(t("apiPortalRevoke"))}</button>`
            }
          </div>
        </li>`;
      })
      .join("");
    tokenList.querySelectorAll(".api-portal-revoke").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id || !confirm(t("apiPortalRevokeConfirm"))) return;
        try {
          await fetchJson(`/api/developer/tokens/${encodeURIComponent(id)}`, {
            method: "DELETE",
          });
          await loadTokens();
        } catch (err) {
          showMsg(createMsg, err.message, true);
        }
      });
    });
    return rows;
  }

  async function loadTokens() {
    const data = await fetchJson("/api/developer/tokens");
    return renderTokens(data.tokens || []);
  }

  function formatTokenCount(value) {
    const n = Number(value) || 0;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  }

  function getChartThemeColors() {
    const style = getComputedStyle(document.documentElement);
    const pick = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return {
      text: pick("--text-secondary", "#94a3b8"),
      grid: pick("--border", "rgba(148, 163, 184, 0.2)"),
      requests: "rgb(96, 165, 250)",
      tokens: "rgb(52, 211, 153)",
    };
  }

  function buildUsageChartSeries(events, days = 14) {
    const buckets = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i -= 1) {
      const date = new Date(now);
      date.setHours(0, 0, 0, 0);
      date.setDate(date.getDate() - i);
      const key = date.toISOString().slice(0, 10);
      buckets.push({
        key,
        label: `${date.getMonth() + 1}/${date.getDate()}`,
        requests: 0,
        tokens: 0,
      });
    }
    const index = new Map(buckets.map((bucket, idx) => [bucket.key, idx]));
    (events || []).forEach((event) => {
      const key = String(event.created_at || "").slice(0, 10);
      const slot = index.get(key);
      if (slot === undefined) return;
      buckets[slot].requests += 1;
      buckets[slot].tokens += Number(event.token_usage?.total_tokens || 0);
    });
    return buckets;
  }

  function renderUsageChart(events) {
    if (!usageChartCanvas || typeof Chart === "undefined") return;
    const series = buildUsageChartSeries(events);
    const colors = getChartThemeColors();
    const totalRequests = series.reduce((sum, row) => sum + row.requests, 0);
    const totalTokens = series.reduce((sum, row) => sum + row.tokens, 0);

    if (usageChartMeta) {
      usageChartMeta.textContent = t("apiPortalUsageChartMeta");
    }
    if (usageChartTotals) {
      usageChartTotals.innerHTML = `
        <div class="api-portal-usage-chart-total">
          <span>${escapeHtml(t("apiPortalUsageChartRequests"))}</span>
          <strong>${escapeHtml(String(totalRequests))}</strong>
        </div>
        <div class="api-portal-usage-chart-total">
          <span>${escapeHtml(t("apiPortalUsageChartTokens"))}</span>
          <strong>${escapeHtml(formatTokenCount(totalTokens))}</strong>
        </div>`;
    }

    const data = {
      labels: series.map((row) => row.label),
      datasets: [
        {
          label: t("apiPortalUsageChartRequests"),
          data: series.map((row) => row.requests),
          borderColor: colors.requests,
          backgroundColor: "rgba(96, 165, 250, 0.14)",
          tension: 0.28,
          fill: true,
          yAxisID: "y",
        },
        {
          label: t("apiPortalUsageChartTokens"),
          data: series.map((row) => row.tokens),
          borderColor: colors.tokens,
          backgroundColor: "rgba(52, 211, 153, 0.1)",
          tension: 0.28,
          fill: false,
          yAxisID: "y1",
        },
      ],
    };
    const options = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: { color: colors.text, boxWidth: 12, boxHeight: 12 },
        },
      },
      scales: {
        x: {
          ticks: { color: colors.text, maxTicksLimit: 7 },
          grid: { color: colors.grid },
        },
        y: {
          position: "left",
          beginAtZero: true,
          ticks: { color: colors.text, precision: 0 },
          grid: { color: colors.grid },
        },
        y1: {
          position: "right",
          beginAtZero: true,
          ticks: { color: colors.text },
          grid: { drawOnChartArea: false },
        },
      },
    };

    if (usageChartInstance) {
      usageChartInstance.data = data;
      usageChartInstance.options = options;
      usageChartInstance.update("none");
      return;
    }
    usageChartInstance = new Chart(usageChartCanvas, {
      type: "line",
      data,
      options,
    });
  }

  function renderProfileSummary(data) {
    if (!profileSummary) return;
    const usage = data?.usage || {};
    profileSummary.innerHTML = `
      <div class="api-portal-profile-grid">
        <div class="api-portal-profile-stat">
          <span>${escapeHtml(t("apiPortalPlan"))}</span>
          <strong>${escapeHtml(data?.plan || "—")}</strong>
        </div>
        <div class="api-portal-profile-stat">
          <span>${escapeHtml(t("apiPortalUsageBudget"))}</span>
          <strong>${escapeHtml(String(usage.usage_label || "—"))}</strong>
        </div>
        <div class="api-portal-profile-stat">
          <span>${escapeHtml(t("apiPortalDashApiRequests"))}</span>
          <strong>${escapeHtml(String(usage.api_token_events ?? data?.api_token_events ?? "—"))}</strong>
        </div>
      </div>`;
  }

  async function loadProfile() {
    const data = await fetchJson("/api/developer/profile");
    if (data.api_access_enabled !== true) {
      redirectToApiSettings();
      return data;
    }
    renderProfileSummary(data);
    return data;
  }

  function usageStatusClass(status) {
    const value = String(status || "completed").toLowerCase();
    if (value === "completed") return "api-portal-usage-status--completed";
    if (value === "running") return "api-portal-usage-status--running";
    return "api-portal-usage-status--failed";
  }

  async function loadUsage() {
    const profile = await loadProfile();
    const data = await fetchJson("/api/developer/usage?limit=120");
    const rows = data.recent_api_events || [];
    renderUsageChart(rows);
    usageEmpty?.classList.toggle("hidden", rows.length > 0);
    if (!usageList) return data;
    usageList.innerHTML = rows
      .map((event) => {
        const usage = event.token_usage || {};
        const status = String(event.status || "completed");
        return `<li class="api-portal-usage-item">
          <div>
            <strong>${escapeHtml(event.model_id || "—")}</strong>
            <div class="api-portal-usage-meta">
              <span>${escapeHtml((event.created_at || "").replace("T", " ").slice(0, 16))}</span>
              <span>${escapeHtml(formatTokenCount(usage.total_tokens || 0))} tokens</span>
              <span>${escapeHtml(event.billing_plan_label || event.billing_plan || "—")}</span>
            </div>
          </div>
          <span class="api-portal-usage-status ${usageStatusClass(status)}">${escapeHtml(status)}</span>
        </li>`;
      })
      .join("");
    if (profile && data.api_token_events != null) {
      renderProfileSummary({ ...profile, api_token_events: data.api_token_events });
    }
    return data;
  }

  async function loadDashboard() {
    renderDocs();
    try {
      const [profile, tokens, usage] = await Promise.all([
        loadProfile(),
        loadTokens().catch(() => []),
        fetchJson("/api/developer/usage?limit=1").catch(() => ({ api_token_events: 0 })),
      ]);
      const usageInfo = profile?.usage || {};
      if (dashPlan) dashPlan.textContent = profile?.plan || "—";
      if (dashBudget) dashBudget.textContent = usageInfo.usage_label || "—";
      if (dashTokens) {
        const activeCount = (tokens || []).filter((token) => token.active).length;
        dashTokens.textContent = String(activeCount);
      }
      if (dashRequests) {
        dashRequests.textContent = String(usage?.api_token_events ?? 0);
      }
    } catch {
      if (dashPlan) dashPlan.textContent = "—";
      if (dashBudget) dashBudget.textContent = "—";
      if (dashTokens) dashTokens.textContent = "—";
      if (dashRequests) dashRequests.textContent = "—";
    }
  }

  createForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("apiPortalTokenName")?.value?.trim() || "";
    try {
      const data = await fetchJson("/api/developer/tokens", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      showMsg(createMsg, t("apiPortalCreated"), false);
      if (secretBox && secretValue && data.secret) {
        secretValue.textContent = data.secret;
        secretBox.classList.remove("hidden");
      }
      createForm.reset();
      await loadTokens();
    } catch (err) {
      showMsg(createMsg, err.message, true);
      secretBox?.classList.add("hidden");
    }
  });

  copySecretBtn?.addEventListener("click", async () => {
    const value = secretValue?.textContent?.trim();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showMsg(createMsg, t("apiPortalCopied"), false);
    } catch {
      showMsg(createMsg, t("apiPortalCopyFailed"), true);
    }
  });

  document.addEventListener("api-portal-panel", (e) => {
    const panel = e.detail?.panel;
    if (panel === "dashboard") loadDashboard().catch(() => {});
    if (panel === "tokens") loadTokens().catch(() => {});
    if (panel === "usage") loadUsage().catch(() => {});
    if (panel === "docs") renderDocs();
  });

  document.addEventListener("DOMContentLoaded", () => {
    if (window.__USER__?.api_access_active === false) {
      redirectToApiSettings();
      return;
    }
    if (window.applyTranslations) window.applyTranslations();
    window.apiPortalRouter?.init();
    const panel = window.apiPortalRouter?.currentPanel?.() || "dashboard";
    if (panel === "dashboard") loadDashboard().catch(() => {});
    if (panel === "tokens") loadTokens().catch(() => {});
    if (panel === "usage") loadUsage().catch(() => {});
    if (panel === "docs") renderDocs();
  });
})();
