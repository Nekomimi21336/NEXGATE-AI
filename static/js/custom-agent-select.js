(function () {
  const STORAGE_KEY = "nexgate_selected_custom_agent_v1";
  const customAgentSelectBtn = document.getElementById("customAgentSelectBtn");
  const customAgentSelectMenu = document.getElementById("customAgentSelectMenu");
  const customAgentSelectTrigger = document.getElementById("customAgentSelectTrigger");

  let agents = [];
  let selectedAgentId = null;

  function loadStoredId() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw === "none" || raw === "") return null;
      return raw || null;
    } catch {
      return null;
    }
  }

  function saveStoredId(id) {
    try {
      if (!id) localStorage.setItem(STORAGE_KEY, "none");
      else localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* ignore */
    }
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

  function selectedAgent() {
    if (!selectedAgentId) return null;
    return agents.find((a) => a.id === selectedAgentId) || null;
  }

  function updateTrigger() {
    if (!customAgentSelectTrigger) return;
    const agent = selectedAgent();
    if (!agent) {
      customAgentSelectTrigger.textContent = window.t("customAgentSelectDefault");
    } else {
      customAgentSelectTrigger.textContent = agent.name || window.t("customAgentsUntitled");
    }
    if (customAgentSelectBtn) {
      customAgentSelectBtn.classList.toggle("is-active", Boolean(agent));
      customAgentSelectBtn.setAttribute(
        "aria-label",
        agent
          ? `${window.t("customAgentSelectDefault")}: ${agent.name}`
          : window.t("customAgentSelectDefault")
      );
    }
    window.__SELECTED_CUSTOM_AGENT_ID__ = selectedAgentId || null;
  }

  function closeMenu() {
    customAgentSelectMenu?.classList.add("hidden");
    customAgentSelectBtn?.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    if (!customAgentSelectMenu || !customAgentSelectBtn) return;
    window.closeModelMenu?.();
    renderMenu();
    customAgentSelectMenu.classList.remove("hidden");
    customAgentSelectBtn.setAttribute("aria-expanded", "true");
  }

  function toggleMenu() {
    if (!customAgentSelectMenu) return;
    if (customAgentSelectMenu.classList.contains("hidden")) openMenu();
    else closeMenu();
  }

  function selectAgent(agentId) {
    selectedAgentId = agentId || null;
    saveStoredId(selectedAgentId);
    updateTrigger();
    closeMenu();
    renderMenu();
    window.dispatchEvent(new CustomEvent("nexgate:session-settings-changed"));
  }

  function renderMenu() {
    if (!customAgentSelectMenu) return;
    customAgentSelectMenu.innerHTML = "";
    const noneSelected = !selectedAgentId;
    const noneBtn = document.createElement("button");
    noneBtn.type = "button";
    noneBtn.className = "model-select-option" + (noneSelected ? " is-selected" : "");
    noneBtn.dataset.agentId = "";
    noneBtn.setAttribute("role", "option");
    noneBtn.setAttribute("aria-selected", noneSelected ? "true" : "false");
    noneBtn.innerHTML = `<span class="model-select-option-name">${escapeHtml(window.t("customAgentSelectNone"))}</span>`;
    noneBtn.addEventListener("click", () => selectAgent(null));
    customAgentSelectMenu.appendChild(noneBtn);

    if (!agents.length) {
      const empty = document.createElement("p");
      empty.className = "model-select-empty";
      empty.textContent = window.t("customAgentSelectEmpty");
      customAgentSelectMenu.appendChild(empty);
      return;
    }

    for (const agent of agents) {
      const isSelected = agent.id === selectedAgentId;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "model-select-option" + (isSelected ? " is-selected" : "");
      btn.dataset.agentId = agent.id;
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", isSelected ? "true" : "false");
      const desc = (agent.description || "").trim();
      btn.innerHTML = `
        <span class="model-select-option-name">${escapeHtml(agent.name || "")}</span>
        ${desc ? `<span class="model-select-option-tier">${escapeHtml(desc)}</span>` : ""}
      `;
      btn.addEventListener("click", () => selectAgent(agent.id));
      customAgentSelectMenu.appendChild(btn);
    }
  }

  async function fetchAgents() {
    try {
      const res = await fetch("/api/custom-agents");
      const data = await res.json();
      if (!res.ok) return [];
      return Array.isArray(data.agents) ? data.agents : [];
    } catch {
      return [];
    }
  }

  function isEnabled() {
    return window.__USER__?.custom_agents_enabled === true;
  }

  async function refresh() {
    if (!isEnabled()) {
      agents = [];
      selectedAgentId = null;
      saveStoredId(null);
      updateTrigger();
      return;
    }
    agents = await fetchAgents();
    selectedAgentId = loadStoredId();
    if (selectedAgentId && !agents.some((a) => a.id === selectedAgentId)) {
      selectedAgentId = null;
      saveStoredId(null);
    }
    updateTrigger();
    if (customAgentSelectMenu && !customAgentSelectMenu.classList.contains("hidden")) {
      renderMenu();
    }
  }

  function getSelectedAgentId() {
    return selectedAgentId || null;
  }

  function getSelectedAgent() {
    return selectedAgent();
  }

  if (customAgentSelectBtn && customAgentSelectMenu) {
    customAgentSelectBtn.addEventListener("click", (e) => {
      if (!isEnabled()) return;
      e.stopPropagation();
      toggleMenu();
    });
    customAgentSelectMenu.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => closeMenu());
    refresh();
  }

  window.customAgentSelect = {
    refresh,
    getSelectedAgentId,
    getSelectedAgent,
    selectAgent,
    closeMenu,
  };
})();
