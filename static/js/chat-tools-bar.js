(function () {
  const STORAGE_KEY = "nexgate_chat_tool_state_v1";

  const TOOL_DEFS = [
    {
      id: "web_search",
      labelKey: "chatToolWebSearch",
      isAvailable(u) {
        if (window.getSystemFeatures?.().search_disabled) return false;
        return u?.web_search_enabled !== false;
      },
    },
    {
      id: "image_generation",
      labelKey: "chatToolImageGeneration",
      isAvailable(u) {
        return u?.image_generation_enabled === true;
      },
    },
    {
      id: "google_calendar",
      labelKey: "chatToolGoogleCalendar",
      isAvailable(u) {
        return (
          u?.google_connected === true &&
          u?.google_calendar_enabled === true &&
          u?.plan_google_calendar !== false
        );
      },
    },
    {
      id: "google_gmail",
      labelKey: "chatToolGoogleGmail",
      isAvailable(u) {
        return (
          u?.google_connected === true &&
          u?.google_gmail_enabled === true &&
          u?.plan_google_gmail !== false
        );
      },
    },
    {
      id: "tasks",
      labelKey: "chatToolTasks",
      isAvailable(u) {
        return u?.tasks_enabled === true;
      },
    },
    {
      id: "memory",
      labelKey: "chatToolMemory",
      isAvailable(u) {
        return u?.memory_enabled === true;
      },
    },
    {
      id: "deep_research",
      labelKey: "chatToolDeepResearch",
      attachMenuOnly: true,
      defaultEnabled: false,
      isAvailable(u) {
        if (window.getSystemFeatures?.().search_disabled) return false;
        return u?.deep_research_enabled === true;
      },
    },
    {
      id: "computelab",
      labelKey: "chatToolComputeLab",
      isAvailable(u) {
        return (
          u?.computelab_connected === true && u?.computelab_tools_enabled === true
        );
      },
    },
  ];

  const summaryBtn = document.getElementById("chatToolsSummaryBtn");
  const toolsBar = document.getElementById("chatToolsBar");
  const popover = document.getElementById("chatToolsPopover");
  const popoverList = document.getElementById("chatToolsPopoverList");
  const popoverEmpty = document.getElementById("chatToolsPopoverEmpty");

  let sessionState = loadSessionState();

  function loadSessionState() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function saveSessionState() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sessionState));
    } catch {
      /* ignore */
    }
  }

  function getAvailableTools(options = {}) {
    const user = window.__USER__ || {};
    const { attachMenuOnly } = options;
    return TOOL_DEFS.filter((def) => {
      if (!def.isAvailable(user)) return false;
      if (attachMenuOnly === true) return def.attachMenuOnly === true;
      if (attachMenuOnly === false) return !def.attachMenuOnly;
      return true;
    });
  }

  function isToolEnabled(id) {
    const user = window.__USER__ || {};
    const def = TOOL_DEFS.find((t) => t.id === id);
    if (!def || !def.isAvailable(user)) return false;
    if (Object.prototype.hasOwnProperty.call(sessionState, id)) {
      return Boolean(sessionState[id]);
    }
    return def.defaultEnabled !== false;
  }

  function setToolEnabled(id, enabled) {
    const user = window.__USER__ || {};
    const def = TOOL_DEFS.find((t) => t.id === id);
    if (!def || !def.isAvailable(user)) return false;
    sessionState[id] = Boolean(enabled);
    saveSessionState();
    renderSummary();
    renderPopoverList();
    window.updateChatInputIndicators?.();
    window.dispatchEvent(new CustomEvent("nexgate:session-settings-changed"));
    return true;
  }

  function getCounts() {
    const available = getAvailableTools({ attachMenuOnly: false });
    const enabled = available.filter((t) => isToolEnabled(t.id));
    return { available: available.length, enabled: enabled.length };
  }

  function renderSummary() {
    if (!summaryBtn) return;
    const { available, enabled } = getCounts();
    if (available === 0 || enabled === 0) {
      summaryBtn.innerHTML = '<i class="bi bi-plus-circle"></i> ' + window.t("chatToolsAllDisabled");
      summaryBtn.setAttribute("aria-label", window.t("chatToolsAllDisabled"));
      if (toolsBar) toolsBar.classList.add("is-empty");
    } else {
      const text = window.t("chatToolsSummary")
        .replace("{enabled}", String(enabled))
        .replace("{total}", String(available));
      summaryBtn.textContent = text;
      summaryBtn.setAttribute("aria-label", text);
      if (toolsBar) toolsBar.classList.remove("is-empty");
    }
  }

  function renderPopoverList() {
    if (!popoverList || !popoverEmpty) return;
    const available = getAvailableTools({ attachMenuOnly: false });
    if (!available.length) {
      popoverList.innerHTML = "";
      popoverEmpty.classList.remove("hidden");
      return;
    }
    popoverEmpty.classList.add("hidden");
    popoverList.innerHTML = available
      .map((def) => {
        const on = isToolEnabled(def.id);
        const label = window.t(def.labelKey);
        return `
          <label class="chat-tools-popover-row">
            <span class="chat-tools-popover-row-label">${escapeHtml(label)}</span>
            <span class="settings-switch chat-tools-switch">
              <input type="checkbox" class="settings-switch-input chat-tools-toggle" data-tool-id="${escapeAttr(def.id)}"${on ? " checked" : ""}>
              <span class="settings-switch-track" aria-hidden="true"></span>
            </span>
          </label>
        `;
      })
      .join("");

    popoverList.querySelectorAll(".chat-tools-toggle").forEach((input) => {
      input.addEventListener("change", () => {
        setToolEnabled(input.dataset.toolId, input.checked);
      });
    });
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

  function closePopover() {
    popover?.classList.add("hidden");
    summaryBtn?.setAttribute("aria-expanded", "false");
  }

  function togglePopover() {
    if (!popover || !summaryBtn) return;
    const open = popover.classList.contains("hidden");
    if (open) {
      renderPopoverList();
      popover.classList.remove("hidden");
      summaryBtn.setAttribute("aria-expanded", "true");
    } else {
      closePopover();
    }
  }

  function getChatToolsPayload() {
    const payload = {};
    for (const def of getAvailableTools()) {
      payload[def.id] = isToolEnabled(def.id);
    }
    if (isToolEnabled("deep_research")) {
      payload.web_search = true;
    }
    return payload;
  }

  function refresh() {
    const knownIds = new Set(TOOL_DEFS.map((t) => t.id));
    for (const key of Object.keys(sessionState)) {
      if (!knownIds.has(key)) delete sessionState[key];
    }
    saveSessionState();
    renderSummary();
    if (popover && !popover.classList.contains("hidden")) {
      renderPopoverList();
    }
  }

  if (summaryBtn) {
    summaryBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePopover();
    });
  }

  if (popover) {
    popover.addEventListener("click", (e) => e.stopPropagation());
  }

  document.addEventListener("click", () => {
    closePopover();
  });

  window.chatToolsBar = {
    refresh,
    getChatToolsPayload,
    isToolEnabled,
    setToolEnabled,
    getCounts,
  };

  window.addEventListener("languagechange", () => {
    renderSummary();
    renderPopoverList();
  });

  refresh();
  window.updateChatInputIndicators?.();
})();
