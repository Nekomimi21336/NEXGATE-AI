(function () {
  if (window.__USER__?.projects_enabled !== true) return;

  const projectsMain = document.getElementById("projectsMain");
  const projectsSelectBtn = document.getElementById("projectsSelectBtn");
  const projectsSelectMenu = document.getElementById("projectsSelectMenu");
  const projectsSelectTrigger = document.getElementById("projectsSelectTrigger");
  const projectsSelectDesc = document.getElementById("projectsSelectDesc");
  const projectsNewBtn = document.getElementById("projectsNewBtn");
  const projectsListView = document.getElementById("projectsListView");
  const projectsWorkspace = document.getElementById("projectsWorkspace");
  const projectsList = document.getElementById("projectsList");
  const projectsListEmpty = document.getElementById("projectsListEmpty");
  const projectsListNewBtn = document.getElementById("projectsListNewBtn");
  const projectsBackBtn = document.getElementById("projectsBackBtn");
  const projectsStatsDeleteBtn = document.getElementById("projectsStatsDeleteBtn");
  const projectsWelcome = document.getElementById("projectsWelcome");
  const projectsMessages = document.getElementById("projectsMessages");
  const projectsMessageInput = document.getElementById("projectsMessageInput");
  const projectsSendBtn = document.getElementById("projectsSendBtn");
  const projectsDialog = document.getElementById("projectsDialog");
  const projectsForm = document.getElementById("projectsForm");
  const projectsDialogTitle = document.getElementById("projectsDialogTitle");
  const projectsName = document.getElementById("projectsName");
  const projectsDescription = document.getElementById("projectsDescription");
  const projectsCancel = document.getElementById("projectsCancel");
  const projectSidebarNav = document.getElementById("projectSidebarNav");
  const projectsChatArea = document.getElementById("projectsChatArea");
  const projectsStatsArea = document.getElementById("projectsStatsArea");
  const projectsWorkerArea = document.getElementById("projectsWorkerArea");
  const projectsArchiveArea = document.getElementById("projectsArchiveArea");
  const projectsStatsPanel = document.getElementById("projectsStatsPanel");
  const projectsStatsNav = document.getElementById("projectsStatsNav");
  const projectsStatsEmpty = document.getElementById("projectsStatsEmpty");
  const projectsInvitesBanner = document.getElementById("projectsInvitesBanner");
  const projectsInvitesBannerTitle = document.getElementById("projectsInvitesBannerTitle");
  const projectsInvitesList = document.getElementById("projectsInvitesList");
  const projectsStatsSaveBtn = document.getElementById("projectsStatsSaveBtn");
  const projectsWorkerBody = document.getElementById("projectsWorkerBody");
  const projectsWorkerEmpty = document.getElementById("projectsWorkerEmpty");
  const projectsWorkerTitle = document.getElementById("projectsWorkerTitle");
  const projectsArchiveBody = document.getElementById("projectsArchiveBody");
  const projectsArchiveEmpty = document.getElementById("projectsArchiveEmpty");
  const projectsArchiveTitle = document.getElementById("projectsArchiveTitle");
  const projectsInputArea = document.getElementById("projectsInputArea");
  const projectsModeBtn = document.getElementById("projectsModeBtn");
  const projectsModeMenu = document.getElementById("projectsModeMenu");
  const projectsModeIcon = document.getElementById("projectsModeIcon");
  const projectsModeLabel = document.getElementById("projectsModeLabel");

  if (!projectsMain || !projectsSelectBtn || !projectsMessageInput || !projectsSendBtn) return;

  const ACTIVE_PROJECT_KEY = "nexgate_active_project_id";
  const ACTIVE_PANE_PREFIX = "nexgate_project_pane_";
  const PROJECT_MODE_PREFIX = "nexgate_project_mode_";
  const PROJECT_MODES = [
    { id: "agent", label: "Agent" },
    { id: "multitask", label: "MultiTask" },
    { id: "chat", label: "Chat" },
    { id: "plan", label: "Plan" },
    { id: "ask", label: "Ask" },
  ];
  const PROJECT_SUGGESTIONS = {
    ja: [
      "このプロジェクトの目的と進め方を整理して",
      "次にやるべきタスクを3つ提案して",
      "要件を箇条書きにまとめて",
    ],
    en: [
      "Help me clarify this project's goals and next steps",
      "Suggest three tasks I should tackle next",
      "Summarize the requirements as bullet points",
    ],
    ko: [
      "이 프로젝트의 목표와 진행 방법을 정리해 줘",
      "다음에 할 작업 3가지를 제안해 줘",
      "요구사항을 bullet point로 정리해 줘",
    ],
  };

  const PROJECT_ROLE_OPTIONS = [
    { id: "editor", labelKey: "projectsRoleEditor" },
    { id: "viewer", labelKey: "projectsRoleViewer" },
  ];
  const STATS_SECTIONS = [
    { id: "overview", labelKey: "projectsStatsNavOverview" },
    { id: "members", labelKey: "projectsStatsNavMembers" },
    { id: "chat", labelKey: "projectsStatsNavChat" },
    { id: "workspace", labelKey: "projectsStatsNavWorkspace" },
    { id: "tools", labelKey: "projectsStatsNavTools" },
  ];
  const PERMISSION_LABELS = {
    view: "projectsPermissionView",
    chat: "projectsPermissionChat",
    edit_settings: "projectsPermissionEditSettings",
    manage_members: "projectsPermissionManageMembers",
    delete_project: "projectsPermissionDeleteProject",
  };

  let state = { projects: [], pendingInvites: [] };
  let viewMode = "list";
  let activeProjectId = null;
  let activePane = "chat";
  let activeSubId = null;
  let activeChatMode = "chat";
  let saving = false;
  let isLoading = false;
  let abortController = null;
  let streamingEl = null;
  let pendingProjectId = null;
  let activeStatsSection = "overview";
  let membersCache = null;
  let projectSocket = null;
  let socketReady = false;
  let socketJoinedProjectId = null;
  let socketReconnectTimer = null;
  let socketPingTimer = null;
  let suppressRealtimeUntil = 0;
  let pendingWsRequests = new Map();
  let activeChatRequestId = null;
  let streamingTextByRequest = {};
  let streamingElementsByRequest = {};
  let streamingSendersByRequest = {};

  function roleLabel(role) {
    if (role === "owner") return t("projectsRoleOwner");
    if (role === "editor") return t("projectsRoleEditor");
    return t("projectsRoleViewer");
  }

  function isOwnedProject(project) {
    if (!project) return false;
    if (project.my_role === "owner") return true;
    const owner = (project.owner || "").trim().toLowerCase();
    const me = (window.__USER__?.username || "").trim().toLowerCase();
    return !project._shared && (!owner || owner === me);
  }

  function projectHasPermission(project, permission) {
    if (!project) return false;
    if (Array.isArray(project.my_permissions)) {
      return project.my_permissions.includes(permission);
    }
    return isOwnedProject(project);
  }

  function applyProjectsBundle(data) {
    const owned = (data?.projects || []).map((project) => ({ ...project, _shared: false }));
    const shared = (data?.shared_projects || []).map((project) => ({ ...project, _shared: true }));
    state.projects = [...owned, ...shared];
    state.pendingInvites = Array.isArray(data?.pending_invites) ? data.pending_invites : [];
  }

  function syncProjectInState(project) {
    if (!project?.id) return;
    const index = (state.projects || []).findIndex((item) => item.id === project.id);
    if (index === -1) {
      state.projects = [...(state.projects || []), project];
      return;
    }
    const next = [...state.projects];
    next[index] = project;
    state.projects = next;
  }

  function stripProjectForSave(project) {
    const copy = { ...project };
    delete copy._shared;
    delete copy.my_role;
    delete copy.my_permissions;
    return copy;
  }

  function shouldSuppressRealtime() {
    return Date.now() < suppressRealtimeUntil || saving || isLoading;
  }

  function markLocalMutation() {
    suppressRealtimeUntil = Date.now() + 1500;
  }

  function getProjectSocketUrl() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${location.host}/ws/projects`;
  }

  function sendProjectSocket(payload) {
    if (!projectSocket || projectSocket.readyState !== WebSocket.OPEN) return false;
    projectSocket.send(JSON.stringify(payload));
    return true;
  }

  function ensureProjectSocketReady(timeoutMs = 8000) {
    if (socketReady) return Promise.resolve();
    connectProjectSocket();
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = window.setInterval(() => {
        if (socketReady) {
          window.clearInterval(timer);
          resolve();
          return;
        }
        if (Date.now() - started > timeoutMs) {
          window.clearInterval(timer);
          reject(new Error(t("networkError")));
        }
      }, 40);
    });
  }

  async function wsRequest(action, payload = {}, { timeout = 30000 } = {}) {
    await ensureProjectSocketReady();
    return new Promise((resolve, reject) => {
      const requestId = crypto.randomUUID?.() || String(Date.now());
      const timer = window.setTimeout(() => {
        pendingWsRequests.delete(requestId);
        reject(new Error(t("networkError")));
      }, timeout);
      pendingWsRequests.set(requestId, { resolve, reject, timer, action });
      if (!sendProjectSocket({ action, request_id: requestId, ...payload })) {
        window.clearTimeout(timer);
        pendingWsRequests.delete(requestId);
        reject(new Error(t("networkError")));
      }
    });
  }

  function resolveWsResponse(data) {
    if (data.type !== "response" || !data.request_id) return false;
    const pending = pendingWsRequests.get(data.request_id);
    if (!pending) return false;
    window.clearTimeout(pending.timer);
    pendingWsRequests.delete(data.request_id);
    if (data.ok) pending.resolve(data.data ?? data);
    else pending.reject(new Error(data.error || t("saveFailed")));
    return true;
  }

  function scheduleSocketReconnect() {
    if (socketReconnectTimer) return;
    socketReconnectTimer = window.setTimeout(() => {
      socketReconnectTimer = null;
      connectProjectSocket();
    }, 2000);
  }

  function startSocketPing() {
    stopSocketPing();
    socketPingTimer = window.setInterval(() => {
      sendProjectSocket({ action: "ping" });
    }, 25000);
  }

  function stopSocketPing() {
    if (socketPingTimer) {
      window.clearInterval(socketPingTimer);
      socketPingTimer = null;
    }
  }

  function disconnectProjectSocket() {
    stopSocketPing();
    if (socketReconnectTimer) {
      window.clearTimeout(socketReconnectTimer);
      socketReconnectTimer = null;
    }
    socketReady = false;
    socketJoinedProjectId = null;
    if (!projectSocket) return;
    projectSocket.onclose = null;
    projectSocket.onerror = null;
    projectSocket.onmessage = null;
    projectSocket.onopen = null;
    projectSocket.close();
    projectSocket = null;
  }

  function joinProjectSocket(projectId) {
    if (!projectId) return;
    if (!projectSocket || projectSocket.readyState === WebSocket.CLOSED) {
      connectProjectSocket();
    }
    if (socketReady) {
      if (socketJoinedProjectId && socketJoinedProjectId !== projectId) {
        sendProjectSocket({ action: "leave", project_id: socketJoinedProjectId });
      }
      socketJoinedProjectId = projectId;
      sendProjectSocket({ action: "join", project_id: projectId });
    }
  }

  function leaveProjectSocket(projectId) {
    if (!projectId) return;
    sendProjectSocket({ action: "leave", project_id: projectId });
    if (socketJoinedProjectId === projectId) socketJoinedProjectId = null;
  }

  function connectProjectSocket() {
    if (window.__USER__?.projects_enabled !== true) return;
    if (
      projectSocket &&
      (projectSocket.readyState === WebSocket.OPEN || projectSocket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    projectSocket = new WebSocket(getProjectSocketUrl());
    projectSocket.onopen = () => {
      socketReady = true;
      startSocketPing();
      if (activeProjectId && viewMode === "project") {
        joinProjectSocket(activeProjectId);
      }
    };
    projectSocket.onmessage = (event) => handleProjectSocketMessage(event);
    projectSocket.onclose = () => {
      socketReady = false;
      stopSocketPing();
      projectSocket = null;
      if (window.NexRouter?.getActiveView?.() === "projects") {
        scheduleSocketReconnect();
      }
    };
    projectSocket.onerror = () => {};
  }

  function applyRemoteProjectPatch(patch, owner) {
    if (!patch?.id || shouldSuppressRealtime()) return;
    const index = (state.projects || []).findIndex((item) => item.id === patch.id);
    if (index === -1) {
      if (owner && owner !== window.__USER__?.username) {
        loadProjects();
      }
      return;
    }
    const current = state.projects[index];
    const merged = {
      ...current,
      ...patch,
      my_role: current.my_role,
      my_permissions: current.my_permissions,
      _shared: current._shared,
      owner: patch.owner || current.owner || owner,
    };
    syncProjectInState(merged);
    if (activeProjectId !== patch.id) {
      renderProjectList();
      renderProjectMenu();
      return;
    }
    updateProjectHeader();
    renderProjectList();
    renderProjectMenu();
    renderProjectSidebar();
    if (activePane === "chat") {
      updateWelcomeLayout();
      renderMessages();
    } else if (activePane === "stats") {
      membersCache = null;
      renderStatsPane();
    } else if (activePane === "worker") {
      renderWorkerPane();
    } else if (activePane === "archive") {
      renderArchivePane();
    }
    updateInputState();
  }

  function appendProjectMessage(project, message) {
    if (!project || !message?.content) return;
    project.messages = project.messages || [];
    const exists = project.messages.some(
      (item) =>
        item.role === message.role &&
        item.content === message.content &&
        item.created_at === message.created_at
    );
    if (!exists) {
      project.messages.push(message);
      project.updatedAt = Date.now();
    }
  }

  function clearStreamingDomState({ keepText = true } = {}) {
    for (const el of Object.values(streamingElementsByRequest)) {
      if (!el) continue;
      window.cancelStreamingMarkdown?.(el);
      const messageEl = el.classList?.contains("message-content") ? el.closest(".message") : el;
      if (messageEl && streamingEl === messageEl) streamingEl = null;
      messageEl?.remove();
    }
    removeStreamingMessage();
    streamingElementsByRequest = {};
    if (!keepText) {
      streamingTextByRequest = {};
      streamingSendersByRequest = {};
    }
    window.cancelStreamingMarkdown?.();
  }

  function restoreActiveStreamingElements() {
    for (const [requestId, text] of Object.entries(streamingTextByRequest)) {
      if (!text) continue;
      const contentEl = getStreamingElement(requestId, streamingSendersByRequest[requestId]);
      if (!contentEl) continue;
      contentEl.classList.remove("is-stream-waiting");
      window.scheduleStreamingMarkdown?.(contentEl, text);
      window.enhanceChatImagesInElement?.(contentEl);
    }
    if (Object.keys(streamingTextByRequest).length) scrollToBottom();
  }

  function getStreamingElement(requestId, sender) {
    const cached = streamingElementsByRequest[requestId];
    if (cached) {
      if (cached.isConnected) return cached;
      delete streamingElementsByRequest[requestId];
    }
    const isSelf = sender === window.__USER__?.username;
    if (isSelf && activeChatRequestId === requestId) {
      const el = showStreamingPending();
      if (el) streamingElementsByRequest[requestId] = el;
      return el;
    }
    removeStreamingMessage();
    const div = appendMessage("assistant", "", null, true);
    div.dataset.streamRequest = requestId;
    if (sender && sender !== window.__USER__?.username) {
      div.dataset.remoteSender = sender;
    }
    const contentEl = div.querySelector(".message-content");
    contentEl?.classList.add("is-stream-waiting");
    streamingElementsByRequest[requestId] = contentEl;
    return contentEl;
  }

  function handleChatUserEvent(data) {
    const project = (state.projects || []).find((item) => item.id === data.project_id);
    if (!project || !data.message) return;
    markLocalMutation();
    appendProjectMessage(project, data.message);
    if (activeProjectId === data.project_id) {
      renderMessages();
      renderProjectSidebar();
      updateWelcomeLayout();
    } else {
      renderProjectList();
      renderProjectMenu();
    }
  }

  function handleChatStreamEvent(data) {
    if (activeProjectId !== data.project_id) return;
    const requestId = data.request_id;
    if (!requestId || !data.content) return;
    streamingTextByRequest[requestId] = (streamingTextByRequest[requestId] || "") + data.content;
    if (data.sender) streamingSendersByRequest[requestId] = data.sender;
    const contentEl = getStreamingElement(requestId, data.sender);
    if (!contentEl) return;
    contentEl.classList.remove("is-stream-waiting");
    window.scheduleStreamingMarkdown?.(contentEl, streamingTextByRequest[requestId]);
    window.enhanceChatImagesInElement?.(contentEl);
    scrollToBottom();
    if (data.sender === window.__USER__?.username) {
      isLoading = true;
      updateInputState();
    }
  }

  function handleChatDoneEvent(data) {
    const project = (state.projects || []).find((item) => item.id === data.project_id);
    if (!project) return;
    const requestId = data.request_id;
    if (data.message) appendProjectMessage(project, data.message);
    window.flushStreamingMarkdown?.();
    delete streamingTextByRequest[requestId];
    delete streamingElementsByRequest[requestId];
    delete streamingSendersByRequest[requestId];
    if (data.sender === window.__USER__?.username && requestId === activeChatRequestId) {
      isLoading = false;
      activeChatRequestId = null;
      abortController = null;
      updateInputState();
    }
    removeStreamingMessage();
    if (activeProjectId === data.project_id) {
      renderMessages();
      renderProjectSidebar();
      updateWelcomeLayout();
    }
    renderProjectList();
    renderProjectMenu();
  }

  function handleChatErrorEvent(data) {
    if (data.sender === window.__USER__?.username && data.request_id === activeChatRequestId) {
      isLoading = false;
      activeChatRequestId = null;
      abortController = null;
      updateInputState();
    }
    window.flushStreamingMarkdown?.();
    delete streamingTextByRequest[data.request_id];
    delete streamingElementsByRequest[data.request_id];
    delete streamingSendersByRequest[data.request_id];
    removeStreamingMessage();
    if (activeProjectId === data.project_id) {
      appendMessage("assistant", data.error || t("networkError"));
    }
  }
  function handleProjectSocketMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (resolveWsResponse(data)) return;
    if (data.type === "pong" || data.type === "connected" || data.type === "joined" || data.type === "left") {
      return;
    }
    if (data.type === "chat.user") {
      handleChatUserEvent(data);
      return;
    }
    if (data.type === "chat.stream") {
      handleChatStreamEvent(data);
      return;
    }
    if (data.type === "chat.done") {
      handleChatDoneEvent(data);
      return;
    }
    if (data.type === "chat.error") {
      handleChatErrorEvent(data);
      return;
    }
    if (data.type === "user.sync") {
      loadProjects();
      return;
    }
    if (data.type === "project.deleted") {
      state.projects = (state.projects || []).filter((item) => item.id !== data.project_id);
      if (activeProjectId === data.project_id) exitToList({ syncUrl: true });
      renderProjectList();
      renderProjectMenu();
      return;
    }
    if (data.type === "members.updated") {
      membersCache = null;
      if (activeProjectId === data.project_id && activePane === "stats" && activeStatsSection === "members") {
        renderStatsPane();
      }
      return;
    }
    if (data.type === "project.updated" && data.patch) {
      applyRemoteProjectPatch(data.patch, data.owner);
    }
  }

  function syncProjectUrl(projectId, { replace = false } = {}) {
    const path = projectId ? `/projects/${projectId}` : "/projects";
    const current = location.pathname.replace(/\/$/, "") || "/";
    const target = path.replace(/\/$/, "") || "/";
    if (current === target) return;
    window.NexRouter?.navigate(path, { replace });
  }

  function t(key) {
    return window.t?.(key) || key;
  }

  function lang() {
    const l = (window.__USER__?.language || "ja").slice(0, 2);
    return PROJECT_SUGGESTIONS[l] ? l : "ja";
  }

  function getActiveProject() {
    return (state.projects || []).find((p) => p.id === activeProjectId) || null;
  }

  function persistActiveProjectId(id) {
    activeProjectId = id || null;
    try {
      if (id) localStorage.setItem(ACTIVE_PROJECT_KEY, id);
      else localStorage.removeItem(ACTIVE_PROJECT_KEY);
    } catch {
      /* ignore */
    }
  }

  function loadStoredProjectId() {
    try {
      return localStorage.getItem(ACTIVE_PROJECT_KEY) || null;
    } catch {
      return null;
    }
  }

  function loadStoredPane(projectId) {
    if (!projectId) return { pane: "chat", subId: null };
    try {
      const raw = localStorage.getItem(`${ACTIVE_PANE_PREFIX}${projectId}`);
      if (!raw) return { pane: "chat", subId: null };
      const parsed = JSON.parse(raw);
      const pane = ["chat", "stats", "worker", "archive"].includes(parsed?.pane) ? parsed.pane : "chat";
      const subId = typeof parsed?.subId === "string" && parsed.subId ? parsed.subId : null;
      return { pane, subId };
    } catch {
      return { pane: "chat", subId: null };
    }
  }

  function persistActivePane(projectId, pane, subId) {
    if (!projectId) return;
    try {
      localStorage.setItem(`${ACTIVE_PANE_PREFIX}${projectId}`, JSON.stringify({ pane, subId: subId || null }));
    } catch {
      /* ignore */
    }
  }

  function getModeLabel(modeId) {
    return PROJECT_MODES.find((mode) => mode.id === modeId)?.label || "Chat";
  }

  function modeIconSvg(modeId) {
    const icons = {
      agent:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM9 13c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm6 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zM8 17h8v-2H8v2z"/></svg>',
      multitask:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z"/></svg>',
      chat:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>',
      plan:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>',
      ask:
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/></svg>',
    };
    return icons[modeId] || icons.chat;
  }

  function loadStoredChatMode(projectId) {
    if (!projectId) return "chat";
    try {
      const stored = localStorage.getItem(`${PROJECT_MODE_PREFIX}${projectId}`);
      return PROJECT_MODES.some((mode) => mode.id === stored) ? stored : "chat";
    } catch {
      return "chat";
    }
  }

  function persistChatMode(projectId, modeId) {
    if (!projectId) return;
    try {
      localStorage.setItem(`${PROJECT_MODE_PREFIX}${projectId}`, modeId);
    } catch {
      /* ignore */
    }
  }

  function closeModeMenu() {
    projectsModeMenu?.classList.add("hidden");
    projectsModeBtn?.setAttribute("aria-expanded", "false");
  }

  function renderModeMenu() {
    if (!projectsModeMenu) return;
    projectsModeMenu.innerHTML = "";
    for (const mode of PROJECT_MODES) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `project-mode-select-option${mode.id === activeChatMode ? " is-selected" : ""}`;
      btn.setAttribute("role", "option");
      btn.dataset.mode = mode.id;
      btn.innerHTML = `
        <span class="project-mode-select-option-content">
          ${modeIconSvg(mode.id)}
          <span class="project-mode-select-option-label">${escapeHtml(mode.label)}</span>
        </span>
      `;
      btn.addEventListener("click", () => {
        setChatMode(mode.id);
        closeModeMenu();
      });
      projectsModeMenu.appendChild(btn);
    }
  }

  function syncModeSelectUi() {
    if (projectsModeIcon) projectsModeIcon.innerHTML = modeIconSvg(activeChatMode);
    if (projectsModeLabel) projectsModeLabel.textContent = getModeLabel(activeChatMode);
    renderModeMenu();
  }

  function setChatMode(modeId, persist = true) {
    const nextMode = PROJECT_MODES.some((mode) => mode.id === modeId) ? modeId : "chat";
    activeChatMode = nextMode;
    if (persist && activeProjectId) persistChatMode(activeProjectId, nextMode);
    syncModeSelectUi();
  }

  function loadProjectChatMode(projectId) {
    const project = (state.projects || []).find((item) => item.id === projectId);
    const settings = getProjectSettings(project);
    setChatMode(settings.default_mode, false);
  }

  function formatProjectDate(ts) {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return "—";
    }
  }

  function getDefaultProjectSettings() {
    return {
      default_mode: "chat",
      custom_instructions: "",
      status: "active",
      scope: "",
      tools: {
        web_search: false,
        geolocation: false,
        memory: false,
        tasks: false,
        google_calendar: false,
        google_gmail: false,
      },
    };
  }

  function getProjectSettings(project) {
    const defaults = getDefaultProjectSettings();
    const raw = project?.settings || {};
    return {
      ...defaults,
      ...raw,
      tools: { ...defaults.tools, ...(raw.tools || {}) },
    };
  }

  function statStatusLabel(enabled) {
    return enabled ? t("projectsStatsStatusEnabled") : t("projectsStatsStatusDisabled");
  }

  function accountToolHint(accountEnabled) {
    return `${t("projectsStatsAccountLabel")}: ${statStatusLabel(Boolean(accountEnabled))}`;
  }

  function buildOverviewStats(project) {
    return [
      {
        label: t("projectsStatMessages"),
        value: String((project.messages || []).length),
      },
      {
        label: t("projectsStatCreated"),
        value: formatProjectDate(project.createdAt),
      },
      {
        label: t("projectsStatUpdated"),
        value: formatProjectDate(project.updatedAt),
      },
    ];
  }

  function buildWorkspaceMeta(project, settings) {
    return [
      { label: t("projectsStatsWorkerCount"), value: String((project.workers || []).length) },
      { label: t("projectsStatsArchiveCount"), value: String((project.archive || []).length) },
      {
        label: t("projectsStatsChatMode"),
        value: getModeLabel(settings?.default_mode || activeChatMode),
      },
    ];
  }

  function renderStatsRows(items) {
    return items
      .map(
        (item) => `
        <div class="project-stat-item${item.placeholder ? " project-stat-item--placeholder" : ""}">
          <span class="project-stat-label">${escapeHtml(item.label || "")}</span>
          <span class="project-stat-value">${escapeHtml(item.value || "")}</span>
        </div>
      `
      )
      .join("");
  }

  function renderStatsCard(title, items, modifier = "") {
    return `
      <section class="project-stats-section${modifier ? ` ${modifier}` : ""}">
        <h3 class="project-stats-section-title">${escapeHtml(title)}</h3>
        <div class="project-stats-grid">${renderStatsRows(items)}</div>
      </section>
    `;
  }

  function renderStatusOptions(selected) {
    const statuses = [
      { id: "active", label: t("projectsStatsWorkspaceStatusActive") },
      { id: "paused", label: t("projectsStatsStatusPaused") },
      { id: "archived", label: t("projectsStatsStatusArchived") },
    ];
    return statuses
      .map(
        (status) =>
          `<option value="${status.id}"${status.id === selected ? " selected" : ""}>${escapeHtml(status.label)}</option>`
      )
      .join("");
  }

  function renderModeOptions(selected) {
    return PROJECT_MODES.map(
      (mode) =>
        `<option value="${mode.id}"${mode.id === selected ? " selected" : ""}>${escapeHtml(mode.label)}</option>`
    ).join("");
  }

  function renderToolToggle(name, label, checked, accountEnabled, disabledAttr = "") {
    const disabled = disabledAttr || (!accountEnabled ? " disabled" : "");
    return `
      <label class="project-stats-toggle-row">
        <span class="project-stats-toggle-copy">
          <span class="project-stats-toggle-label">${escapeHtml(label)}</span>
          <span class="project-stats-toggle-hint">${escapeHtml(accountToolHint(accountEnabled))}</span>
        </span>
        <input type="checkbox" name="${escapeHtml(name)}"${checked ? " checked" : ""}${disabled}>
      </label>
    `;
  }

  function collectProjectSettingsFromForm(form) {
    const settings = getDefaultProjectSettings();
    settings.default_mode = form.querySelector("#projectsStatsDefaultMode")?.value || "chat";
    settings.custom_instructions = form.querySelector("#projectsStatsCustomInstructions")?.value || "";
    settings.status = form.querySelector("#projectsStatsStatus")?.value || "active";
    settings.scope = form.querySelector("#projectsStatsScope")?.value || "";
    for (const key of Object.keys(settings.tools)) {
      settings.tools[key] = Boolean(form.querySelector(`[name="tool_${key}"]`)?.checked);
    }
    if (!PROJECT_MODES.some((mode) => mode.id === settings.default_mode)) {
      settings.default_mode = "chat";
    }
    return settings;
  }

  async function saveProjectSettings(form) {
    const project = getActiveProject();
    if (!project) return false;
    if (!projectHasPermission(project, "edit_settings")) {
      window.NexNotify?.showError?.(t("saveFailed"));
      return false;
    }
    const trimmedName = (form.querySelector("#projectsStatsName")?.value || "").trim();
    if (!trimmedName) {
      window.NexNotify?.showError?.(t("projectsStatsNameRequired"));
      return false;
    }
    project.name = trimmedName;
    project.description = (form.querySelector("#projectsStatsDescription")?.value || "").trim();
    project.settings = collectProjectSettingsFromForm(form);
    project.updatedAt = Date.now();
    const saved = await persistActiveProject();
    if (!saved) return false;
    setChatMode(project.settings.default_mode, true);
    updateProjectHeader();
    renderProjectList();
    renderProjectMenu();
    renderStatsPane();
    window.NexNotify?.showSuccess?.(t("projectsStatsSaved"));
    return true;
  }

  function isSidebarItemActive(pane, subId) {
    if (activePane !== pane) return false;
    if (pane === "worker" || pane === "archive") return activeSubId === subId;
    return true;
  }

  function createSidebarNavItem(title, pane, subId) {
    const item = document.createElement("div");
    item.className = `history-item${isSidebarItemActive(pane, subId) ? " active" : ""}`;
    item.dataset.pane = pane;
    if (subId) item.dataset.subId = subId;
    const titleEl = document.createElement("span");
    titleEl.className = "history-item-title";
    titleEl.textContent = title;
    item.appendChild(titleEl);
    item.addEventListener("click", () => selectProjectPane(pane, subId || null));
    return item;
  }

  function renderSectionEntries(entries, pane) {
    const list = document.createElement("ul");
    list.className = "project-sidebar-list";
    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "project-sidebar-empty";
      empty.textContent = pane === "worker" ? t("projectsWorkerEmpty") : t("projectsArchiveEmpty");
      list.appendChild(empty);
      return list;
    }
    for (const entry of entries) {
      const li = document.createElement("li");
      const label = (entry.title || "").trim() || t("projectsUntitled");
      li.appendChild(createSidebarNavItem(label, pane, entry.id));
      list.appendChild(li);
    }
    return list;
  }

  function renderProjectSidebar() {
    if (!projectSidebarNav) return;
    const project = getActiveProject();
    projectSidebarNav.innerHTML = "";
    if (!project) return;

    const sessionSection = document.createElement("div");
    sessionSection.className = "project-sidebar-section";
    const sessionList = document.createElement("ul");
    sessionList.className = "project-sidebar-list";

    const chatLi = document.createElement("li");
    chatLi.appendChild(createSidebarNavItem(t("projectsSidebarChat"), "chat"));
    sessionList.appendChild(chatLi);

    const statsLi = document.createElement("li");
    statsLi.appendChild(createSidebarNavItem(t("projectsSidebarStats"), "stats"));
    sessionList.appendChild(statsLi);

    sessionSection.appendChild(sessionList);
    projectSidebarNav.appendChild(sessionSection);

    const workerSection = document.createElement("div");
    workerSection.className = "project-sidebar-section";
    const workerCategory = document.createElement("div");
    workerCategory.className = "project-sidebar-category";
    workerCategory.textContent = t("projectsSidebarWorker");
    workerSection.appendChild(workerCategory);
    workerSection.appendChild(renderSectionEntries(project.workers || [], "worker"));
    projectSidebarNav.appendChild(workerSection);

    const archiveSection = document.createElement("div");
    archiveSection.className = "project-sidebar-section";
    const archiveCategory = document.createElement("div");
    archiveCategory.className = "project-sidebar-category";
    archiveCategory.textContent = t("projectsSidebarArchive");
    archiveSection.appendChild(archiveCategory);
    archiveSection.appendChild(renderSectionEntries(project.archive || [], "archive"));
    projectSidebarNav.appendChild(archiveSection);
  }

  function selectStatsSection(sectionId) {
    activeStatsSection = sectionId;
    renderStatsNav();
    renderStatsPane();
    updateStatsHeaderActions();
  }

  function renderStatsNav() {
    if (!projectsStatsNav) return;
    projectsStatsNav.innerHTML = "";
    for (const section of STATS_SECTIONS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `project-stats-nav-item${activeStatsSection === section.id ? " is-active" : ""}`;
      btn.textContent = t(section.labelKey);
      btn.addEventListener("click", () => selectStatsSection(section.id));
      projectsStatsNav.appendChild(btn);
    }
  }

  function renderRoleOptions(selected) {
    return PROJECT_ROLE_OPTIONS.map(
      (role) =>
        `<option value="${role.id}"${role.id === selected ? " selected" : ""}>${escapeHtml(t(role.labelKey))}</option>`
    ).join("");
  }

  function renderPermissionChips(permissions) {
    const all = Object.keys(PERMISSION_LABELS);
    return all
      .map(
        (perm) => `
        <div class="project-permission-chip${permissions.includes(perm) ? " is-on" : ""}">
          ${escapeHtml(t(PERMISSION_LABELS[perm]))}
        </div>
      `
      )
      .join("");
  }

  async function fetchProjectMembers(projectId) {
    return wsRequest("members.list", { project_id: projectId });
  }

  function renderMembersSection(project, membersData) {
    const canManage = projectHasPermission(project, "manage_members");
    const members = membersData?.members || [];
    const invites = membersData?.invites || [];
    const permissions = membersData?.permissions || project.my_permissions || [];
    return `
      <div class="project-stats-layout">
        <section class="project-stats-section project-stats-section--wide">
          <h3 class="project-stats-section-title">${escapeHtml(t("projectsMembersTitle"))}</h3>
          <p class="project-stats-section-desc">${escapeHtml(t("projectsMembersDesc"))}</p>
          ${
            canManage
              ? `
          <div class="project-members-invite-row">
            <div class="settings-field">
              <label for="projectsMemberInviteUsername">${escapeHtml(t("projectsMembersInviteUsername"))}</label>
              <input type="text" id="projectsMemberInviteUsername" autocomplete="off" placeholder="username">
            </div>
            <div class="settings-field">
              <label for="projectsMemberInviteRole">${escapeHtml(t("projectsMembersInviteRole"))}</label>
              <select id="projectsMemberInviteRole">${renderRoleOptions("editor")}</select>
            </div>
            <button type="button" class="projects-header-btn" id="projectsMemberInviteBtn">${escapeHtml(t("projectsMembersInvite"))}</button>
          </div>`
              : ""
          }
          <div class="project-members-list">
            ${members
              .map((member) => {
                const isOwner = member.role === "owner";
                const canEditMember = canManage && !isOwner;
                return `
                <div class="project-member-row" data-member="${escapeHtml(member.username)}">
                  <div class="project-member-copy">
                    <span class="project-member-name">${escapeHtml(member.display_name || member.username)}</span>
                    <span class="project-member-meta">@${escapeHtml(member.username)}</span>
                  </div>
                  ${
                    canEditMember
                      ? `<select class="project-member-role-select" data-member-role="${escapeHtml(member.username)}">${renderRoleOptions(member.role)}</select>`
                      : `<span class="project-member-meta">${escapeHtml(roleLabel(member.role))}</span>`
                  }
                  <div class="project-member-actions">
                    ${
                      canEditMember
                        ? `<button type="button" class="projects-header-btn projects-header-btn--danger project-member-remove" data-member-remove="${escapeHtml(member.username)}">${escapeHtml(t("projectsMembersRemove"))}</button>`
                        : ""
                    }
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        </section>
        ${
          invites.length
            ? `
        <section class="project-stats-section project-stats-section--wide">
          <h3 class="project-stats-section-title">${escapeHtml(t("projectsMembersPending"))}</h3>
          <div class="project-members-list">
            ${invites
              .map(
                (invite) => `
              <div class="project-invite-row" data-invite="${escapeHtml(invite.username)}">
                <div class="project-member-copy">
                  <span class="project-member-name">${escapeHtml(invite.display_name || invite.username)}</span>
                  <span class="project-member-meta">@${escapeHtml(invite.username)} · ${escapeHtml(roleLabel(invite.role))}</span>
                </div>
                <span class="project-member-meta">${escapeHtml(t("projectsMembersPending"))}</span>
                <div class="project-invite-actions">
                  ${
                    canManage
                      ? `<button type="button" class="projects-header-btn project-invite-cancel" data-invite-cancel="${escapeHtml(invite.username)}">${escapeHtml(t("projectsMembersCancelInvite"))}</button>`
                      : ""
                  }
                </div>
              </div>
            `
              )
              .join("")}
          </div>
        </section>`
            : ""
        }
        <section class="project-stats-section project-stats-section--wide">
          <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionOverview"))}</h3>
          <div class="project-permissions-grid">${renderPermissionChips(permissions)}</div>
        </section>
      </div>
    `;
  }

  function bindMembersSectionEvents(project) {
    document.getElementById("projectsMemberInviteBtn")?.addEventListener("click", async () => {
      const username = document.getElementById("projectsMemberInviteUsername")?.value.trim().toLowerCase();
      const role = document.getElementById("projectsMemberInviteRole")?.value || "editor";
      if (!username) return;
      try {
        const data = await wsRequest("members.invite", {
          project_id: project.id,
          username,
          role,
        });
        membersCache = data;
        markLocalMutation();
        window.NexNotify?.showSuccess?.(t("projectsMembersInvited"));
        renderStatsPane();
      } catch (err) {
        window.NexNotify?.showError?.(err.message || t("saveFailed"));
      }
    });

    projectsStatsPanel.querySelectorAll("[data-member-role]").forEach((select) => {
      select.addEventListener("change", async () => {
        const memberUsername = select.getAttribute("data-member-role");
        try {
          const data = await wsRequest("members.update", {
            project_id: project.id,
            member_username: memberUsername,
            role: select.value,
          });
          membersCache = { ...(membersCache || {}), members: data.members || [] };
          markLocalMutation();
          window.NexNotify?.showSuccess?.(t("projectsMembersUpdated"));
        } catch (err) {
          window.NexNotify?.showError?.(err.message || t("saveFailed"));
          renderStatsPane();
        }
      });
    });

    projectsStatsPanel.querySelectorAll("[data-member-remove]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const memberUsername = btn.getAttribute("data-member-remove");
        try {
          await wsRequest("members.remove", {
            project_id: project.id,
            member_username: memberUsername,
          });
          markLocalMutation();
          window.NexNotify?.showSuccess?.(t("projectsMembersRemoved"));
          membersCache = null;
          renderStatsPane();
        } catch (err) {
          window.NexNotify?.showError?.(err.message || t("saveFailed"));
        }
      });
    });

    projectsStatsPanel.querySelectorAll("[data-invite-cancel]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const inviteUsername = btn.getAttribute("data-invite-cancel");
        try {
          await wsRequest("members.remove", {
            project_id: project.id,
            member_username: inviteUsername,
          });
          markLocalMutation();
          window.NexNotify?.showSuccess?.(t("projectsMembersInviteCancelled"));
          membersCache = null;
          renderStatsPane();
        } catch (err) {
          window.NexNotify?.showError?.(err.message || t("saveFailed"));
        }
      });
    });
  }

  function renderOverviewSection(project, settings, canEdit) {
    const name = (project.name || "").trim();
    const description = (project.description || "").trim();
    const disabledAttr = canEdit ? "" : " disabled readonly";
    return `
      <form id="projectsStatsForm" class="project-stats-form-shell">
        <div class="project-stats-layout">
          <section class="project-stats-section project-stats-section--wide">
            <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionBasic"))}</h3>
            <div class="project-stats-fields project-stats-fields--pair">
              <div class="settings-field">
                <label for="projectsStatsName">${escapeHtml(t("projectsFieldName"))}</label>
                <input type="text" id="projectsStatsName" value="${escapeHtml(name)}" autocomplete="off" required${disabledAttr}>
              </div>
              <div class="settings-field">
                <label for="projectsStatsDescription">${escapeHtml(t("projectsFieldDescription"))}</label>
                <textarea id="projectsStatsDescription" rows="4"${disabledAttr}>${escapeHtml(description)}</textarea>
              </div>
            </div>
          </section>
          ${renderStatsCard(t("projectsStatsSectionOverview"), buildOverviewStats(project), "project-stats-section--metrics")}
        </div>
      </form>
    `;
  }

  function renderChatSection(project, settings, canEdit) {
    const customInstructions = (settings.custom_instructions || "").trim();
    const disabledAttr = canEdit ? "" : " disabled";
    return `
      <form id="projectsStatsForm" class="project-stats-form-shell">
        <div class="project-stats-layout">
          <section class="project-stats-section project-stats-section--wide">
            <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionChat"))}</h3>
            <div class="project-stats-fields project-stats-fields--stack">
              <div class="settings-field">
                <label for="projectsStatsDefaultMode">${escapeHtml(t("projectsStatsDefaultMode"))}</label>
                <select id="projectsStatsDefaultMode"${disabledAttr}>${renderModeOptions(settings.default_mode)}</select>
              </div>
              <div class="settings-field">
                <label for="projectsStatsCustomInstructions">${escapeHtml(t("projectsStatsCustomInstructions"))}</label>
                <textarea id="projectsStatsCustomInstructions" rows="4" placeholder="${escapeHtml(t("projectsStatsCustomInstructionsPlaceholder"))}"${canEdit ? "" : " readonly"}>${escapeHtml(customInstructions)}</textarea>
              </div>
            </div>
          </section>
        </div>
      </form>
    `;
  }

  function renderWorkspaceSection(project, settings, canEdit) {
    const scope = (settings.scope || "").trim();
    const disabledAttr = canEdit ? "" : " disabled";
    return `
      <form id="projectsStatsForm" class="project-stats-form-shell">
        <div class="project-stats-layout">
          <section class="project-stats-section project-stats-section--wide">
            <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionWorkspace"))}</h3>
            <div class="project-stats-fields project-stats-fields--stack">
              <div class="settings-field">
                <label for="projectsStatsStatus">${escapeHtml(t("projectsStatsWorkspaceStatus"))}</label>
                <select id="projectsStatsStatus"${disabledAttr}>${renderStatusOptions(settings.status)}</select>
              </div>
              <div class="settings-field">
                <label for="projectsStatsScope">${escapeHtml(t("projectsStatsWorkspaceScope"))}</label>
                <textarea id="projectsStatsScope" rows="3" placeholder="${escapeHtml(t("projectsStatsScopePlaceholder"))}"${canEdit ? "" : " readonly"}>${escapeHtml(scope)}</textarea>
              </div>
              <div class="settings-field">
                <label for="projectsStatsWorkspaceId">${escapeHtml(t("projectsStatsWorkspaceId"))}</label>
                <input type="text" id="projectsStatsWorkspaceId" value="${escapeHtml(project.id)}" readonly>
              </div>
            </div>
            <div class="project-stats-grid project-stats-grid--compact">${renderStatsRows(buildWorkspaceMeta(project, settings))}</div>
          </section>
        </div>
      </form>
    `;
  }

  function renderToolsSection(project, settings, user, canEdit) {
    const disabledAttr = canEdit ? "" : " disabled";
    return `
      <form id="projectsStatsForm" class="project-stats-form-shell">
        <div class="project-stats-layout">
          <section class="project-stats-section project-stats-section--wide">
            <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionExternalTools"))}</h3>
            <p class="project-stats-section-desc">${escapeHtml(t("projectsStatsProjectUseLabel"))}</p>
            <div class="project-stats-toggle-list">
              ${renderToolToggle("tool_web_search", t("projectsStatsExternalSearch"), settings.tools.web_search, user.web_search_enabled !== false, disabledAttr)}
              ${renderToolToggle("tool_geolocation", t("projectsStatsExternalGeo"), settings.tools.geolocation, user.geolocation_enabled, disabledAttr)}
              ${renderToolToggle("tool_memory", t("projectsStatsExternalMemory"), settings.tools.memory, user.memory_enabled, disabledAttr)}
              ${renderToolToggle("tool_tasks", t("projectsStatsExternalTasks"), settings.tools.tasks, user.tasks_enabled, disabledAttr)}
            </div>
          </section>
          <section class="project-stats-section project-stats-section--wide">
            <h3 class="project-stats-section-title">${escapeHtml(t("projectsStatsSectionIntegrations"))}</h3>
            <div class="project-stats-grid project-stats-grid--compact">
              ${renderStatsRows([
                {
                  label: t("projectsStatsIntegrationGoogle"),
                  value: user.google_connected ? t("projectsStatsStatusConnected") : t("projectsStatsStatusDisconnected"),
                },
                {
                  label: t("projectsStatsIntegrationDiscord"),
                  value: user.discord_login_linked ? t("projectsStatsStatusConnected") : t("projectsStatsStatusDisconnected"),
                },
              ])}
            </div>
            <div class="project-stats-toggle-list">
              ${renderToolToggle("tool_google_calendar", t("projectsStatsIntegrationCalendar"), settings.tools.google_calendar, user.google_calendar_enabled && user.google_connected, disabledAttr)}
              ${renderToolToggle("tool_google_gmail", t("projectsStatsIntegrationGmail"), settings.tools.google_gmail, user.google_gmail_enabled && user.google_connected, disabledAttr)}
            </div>
          </section>
        </div>
      </form>
    `;
  }

  function renderStatsPane() {
    if (!projectsStatsPanel) return;
    renderStatsNav();
    const project = getActiveProject();
    projectsStatsPanel.innerHTML = "";
    if (!project) {
      projectsStatsEmpty?.classList.remove("hidden");
      return;
    }
    projectsStatsEmpty?.classList.add("hidden");
    const settings = getProjectSettings(project);
    const user = window.__USER__ || {};
    const canEdit = projectHasPermission(project, "edit_settings");

    if (activeStatsSection === "members") {
      projectsStatsPanel.innerHTML = `<div class="project-pane-empty">${escapeHtml(t("projectsMembersLoadFailed"))}</div>`;
      fetchProjectMembers(project.id)
        .then((data) => {
          membersCache = data;
          project.my_role = data.my_role || project.my_role;
          project.my_permissions = data.permissions || project.my_permissions;
          projectsStatsPanel.innerHTML = renderMembersSection(project, data);
          bindMembersSectionEvents(project);
          updateStatsHeaderActions();
        })
        .catch((err) => {
          projectsStatsPanel.innerHTML = `<p class="project-pane-empty">${escapeHtml(err.message || t("projectsMembersLoadFailed"))}</p>`;
        });
      return;
    }

    if (activeStatsSection === "overview") {
      projectsStatsPanel.innerHTML = renderOverviewSection(project, settings, canEdit);
    } else if (activeStatsSection === "chat") {
      projectsStatsPanel.innerHTML = renderChatSection(project, settings, canEdit);
    } else if (activeStatsSection === "workspace") {
      projectsStatsPanel.innerHTML = renderWorkspaceSection(project, settings, canEdit);
    } else if (activeStatsSection === "tools") {
      projectsStatsPanel.innerHTML = renderToolsSection(project, settings, user, canEdit);
    }

    document.getElementById("projectsStatsForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await saveProjectSettings(e.currentTarget);
    });
    updateStatsHeaderActions();
  }

  function renderEntryPane(entries, subId, titleEl, bodyEl, emptyEl, fallbackTitleKey) {
    if (!bodyEl) return;
    bodyEl.innerHTML = "";
    const entry = (entries || []).find((item) => item.id === subId);
    if (!entry) {
      if (titleEl) titleEl.textContent = t(fallbackTitleKey);
      bodyEl.classList.add("hidden");
      emptyEl?.classList.remove("hidden");
      return;
    }
    if (titleEl) titleEl.textContent = (entry.title || "").trim() || t("projectsUntitled");
    bodyEl.classList.remove("hidden");
    emptyEl?.classList.add("hidden");
    const card = document.createElement("div");
    card.className = "project-entry-card";
    const summary = (entry.summary || "").trim();
    card.innerHTML = summary
      ? `<p class="project-entry-card-summary">${escapeHtml(summary)}</p>`
      : `<p class="project-entry-card-summary">—</p>`;
    bodyEl.appendChild(card);
  }

  function renderWorkerPane() {
    renderEntryPane(
      getActiveProject()?.workers,
      activeSubId,
      projectsWorkerTitle,
      projectsWorkerBody,
      projectsWorkerEmpty,
      "projectsSidebarWorker"
    );
  }

  function renderArchivePane() {
    renderEntryPane(
      getActiveProject()?.archive,
      activeSubId,
      projectsArchiveTitle,
      projectsArchiveBody,
      projectsArchiveEmpty,
      "projectsSidebarArchive"
    );
  }

  function updatePaneVisibility() {
    const project = getActiveProject();
    const panes = [
      { el: projectsChatArea, pane: "chat" },
      { el: projectsStatsArea, pane: "stats" },
      { el: projectsWorkerArea, pane: "worker" },
      { el: projectsArchiveArea, pane: "archive" },
    ];
    for (const { el, pane } of panes) {
      el?.classList.toggle("hidden", !project || activePane !== pane);
    }
    projectsInputArea?.classList.toggle("hidden", !project || activePane !== "chat");
    updateDeleteButtonVisibility();
    updateWelcomeLayout();
    if (activePane === "stats") renderStatsPane();
    else if (activePane === "worker") renderWorkerPane();
    else if (activePane === "archive") renderArchivePane();
  }

  function selectProjectPane(pane, subId = null) {
    const project = getActiveProject();
    if (!project) return;
    activePane = pane;
    activeSubId = subId;
    if ((pane === "worker" || pane === "archive") && !subId) {
      const entries = pane === "worker" ? project.workers : project.archive;
      activeSubId = entries?.[0]?.id || null;
    }
    persistActivePane(project.id, activePane, activeSubId);
    renderProjectSidebar();
    updatePaneVisibility();
    updateDeleteButtonVisibility();
  }

  function updateWelcomeLayout() {
    const project = getActiveProject();
    const hasMessages = Array.isArray(project?.messages) && project.messages.length > 0;
    const showWelcome = viewMode === "project" && project && activePane === "chat" && !hasMessages;
    projectsMain.classList.toggle("projects-main--welcome", showWelcome);
    projectsWelcome?.classList.toggle("hidden", !showWelcome);
    projectsMessages?.classList.toggle("hidden", !project || activePane !== "chat" || !hasMessages);
  }

  function showListView() {
    viewMode = "list";
    projectsListView?.classList.remove("hidden");
    projectsWorkspace?.classList.add("hidden");
    projectsMain.classList.remove("projects-main--welcome");
    syncProjectSidebarMode();
    renderProjectList();
  }

  function showProjectWorkspace() {
    viewMode = "project";
    projectsListView?.classList.add("hidden");
    projectsWorkspace?.classList.remove("hidden");
    syncProjectSidebarMode();
    updateProjectHeader();
    updatePaneVisibility();
    updateWelcomeLayout();
    updateInputState();
    renderProjectSidebar();
  }

  function exitToList({ syncUrl = true } = {}) {
    if (isLoading) abortController?.abort();
    if (activeProjectId) leaveProjectSocket(activeProjectId);
    persistActiveProjectId(null);
    activePane = "chat";
    activeSubId = null;
    closeProjectMenu();
    showListView();
    if (syncUrl) syncProjectUrl(null);
  }

  function enterProject(id, { syncUrl = true } = {}) {
    if (!id || !state.projects.some((p) => p.id === id)) return;
    if (activeProjectId === id && viewMode === "project") {
      joinProjectSocket(id);
      if (syncUrl) syncProjectUrl(id);
      return;
    }
    activePane = "chat";
    activeSubId = null;
    persistActiveProjectId(id);
    persistActivePane(id, "chat", null);
    loadProjectChatMode(id);
    updateProjectHeader();
    renderMessages();
    updateDeleteButtonVisibility();
    showProjectWorkspace();
    joinProjectSocket(id);
    if (syncUrl) syncProjectUrl(id);
  }

  function renderProjectList() {
    if (!projectsList) return;
    projectsList.innerHTML = "";
    const items = state.projects || [];
    projectsListEmpty?.classList.toggle("hidden", items.length > 0);
    for (const project of items) {
      const li = document.createElement("li");
      li.className = "projects-list-item";
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "projects-list-item-main";
      const name = (project.name || "").trim() || t("projectsUntitled");
      const desc = (project.description || "").trim();
      const messageCount = (project.messages || []).length;
      const roleBadge = project._shared
        ? `<span class="projects-list-item-badge">${escapeHtml(t("projectsSharedBadge"))} · ${escapeHtml(roleLabel(project.my_role || "viewer"))}</span>`
        : "";
      openBtn.innerHTML = `
        <span class="projects-list-item-name">${escapeHtml(name)}</span>
        <span class="projects-list-item-desc">${escapeHtml(desc || "—")}</span>
        <span class="projects-list-item-meta">${escapeHtml(t("projectsStatMessages"))}: ${messageCount}${roleBadge ? ` · ${roleBadge}` : ""}</span>
      `;
      openBtn.addEventListener("click", () => enterProject(project.id));
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "projects-list-item-delete";
      deleteBtn.textContent = t("projectsDelete");
      deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteProject(project.id);
      });
      li.appendChild(openBtn);
      li.appendChild(deleteBtn);
      projectsList.appendChild(li);
    }
  }

  function syncProjectSidebarMode() {
    const onProjectsView = window.NexRouter?.getActiveView?.() === "projects";
    window.setProjectSidebarMode?.(onProjectsView && viewMode === "project" && Boolean(getActiveProject()));
    if (viewMode === "project") renderProjectSidebar();
  }

  function updateInputState() {
    const project = getActiveProject();
    const hasContent = Boolean(projectsMessageInput.value.trim());
    const enabled =
      viewMode === "project" &&
      Boolean(project) &&
      activePane === "chat" &&
      projectHasPermission(project, "chat");
    projectsMessageInput.disabled = !enabled;
    projectsModeBtn.disabled = !enabled;

    projectsSendBtn.classList.toggle("is-generating", isLoading);
    if (isLoading) {
      projectsSendBtn.classList.add("active");
      projectsSendBtn.disabled = false;
      projectsSendBtn.setAttribute("aria-label", "停止");
      return;
    }

    projectsSendBtn.classList.toggle("active", enabled && hasContent);
    projectsSendBtn.disabled = !enabled || !hasContent;
    projectsSendBtn.setAttribute("aria-label", "送信");
  }

  function updateStatsHeaderActions() {
    const project = getActiveProject();
    const onStats = viewMode === "project" && activePane === "stats" && Boolean(project);
    const canSave =
      onStats &&
      activeStatsSection !== "members" &&
      projectHasPermission(project, "edit_settings");
    const canDelete = onStats && projectHasPermission(project, "delete_project");
    projectsStatsDeleteBtn?.classList.toggle("hidden", !canDelete);
    projectsStatsSaveBtn?.classList.toggle("hidden", !canSave);
  }

  function updateDeleteButtonVisibility() {
    updateStatsHeaderActions();
  }

  function updateProjectHeader() {
    const project = getActiveProject();
    if (!project) {
      if (projectsSelectTrigger) projectsSelectTrigger.textContent = t("projectsSelectPlaceholder");
      if (projectsSelectDesc) {
        projectsSelectDesc.textContent = "";
        projectsSelectDesc.classList.add("hidden");
      }
      updateDeleteButtonVisibility();
      return;
    }
    if (projectsSelectTrigger) {
      projectsSelectTrigger.textContent = (project.name || "").trim() || t("projectsUntitled");
    }
    const desc = (project.description || "").trim();
    if (projectsSelectDesc) {
      projectsSelectDesc.textContent = desc;
      projectsSelectDesc.classList.toggle("hidden", !desc);
    }
    updateDeleteButtonVisibility();
  }

  function renderProjectMenu() {
    if (!projectsSelectMenu) return;
    projectsSelectMenu.innerHTML = "";
    const items = state.projects || [];
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "model-select-empty";
      empty.textContent = t("projectsEmpty");
      projectsSelectMenu.appendChild(empty);
      return;
    }
    for (const project of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "model-select-option";
      btn.setAttribute("role", "option");
      btn.dataset.id = project.id;
      btn.innerHTML = `<span class="model-select-option-name">${escapeHtml((project.name || "").trim() || t("projectsUntitled"))}</span>`;
      if (project.id === activeProjectId) btn.classList.add("is-selected");
      btn.addEventListener("click", () => {
        selectProject(project.id);
        closeProjectMenu();
      });
      projectsSelectMenu.appendChild(btn);
    }
  }

  function renderSuggestions() {
    const prompts = PROJECT_SUGGESTIONS[lang()] || PROJECT_SUGGESTIONS.ja;
    ["projectsSuggestion1", "projectsSuggestion2", "projectsSuggestion3"].forEach((id, index) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      const prompt = prompts[index] || "";
      btn.textContent = prompt;
      btn.dataset.prompt = prompt;
      btn.classList.toggle("hidden", !prompt);
    });
  }

  function renderMessages() {
    if (!projectsMessages) return;
    const project = getActiveProject();
    clearStreamingDomState({ keepText: true });
    projectsMessages.innerHTML = "";
    if (!project?.messages?.length) {
      updateWelcomeLayout();
      restoreActiveStreamingElements();
      return;
    }
    updateWelcomeLayout();
    project.messages.forEach((msg, index) => {
      appendMessage(msg.role, msg.content, index, false);
    });
    restoreActiveStreamingElements();
    scrollToBottom(true);
  }

  function appendMessage(role, content, messageIndex = null, scroll = true) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    if (messageIndex !== null) div.dataset.messageIndex = String(messageIndex);
    if (role === "assistant") {
      div.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-body">
          <div class="message-content markdown-body"></div>
        </div>
      `;
      const assistantContent = div.querySelector(".message-content");
      if (typeof content === "string" && content.trim()) {
        window.applyMarkdownContent?.(assistantContent, content);
      }
      window.enhanceChatImagesInElement?.(assistantContent);
    } else {
      div.innerHTML = `
        <div class="message-avatar">You</div>
        <div class="message-body">
          <div class="message-content">${formatMessageHtml(role, content)}</div>
        </div>
      `;
    }
    projectsMessages.appendChild(div);
    if (scroll) scrollToBottom();
    return div;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function scrollToBottom(force = false) {
    const area = document.getElementById("projectsChatArea");
    if (!area) return;
    area.scrollTop = area.scrollHeight;
  }

  function autoResizeInput() {
    projectsMessageInput.style.height = "auto";
    projectsMessageInput.style.height = `${Math.min(projectsMessageInput.scrollHeight, 200)}px`;
  }

  function closeProjectMenu() {
    projectsSelectMenu?.classList.add("hidden");
    projectsSelectBtn?.setAttribute("aria-expanded", "false");
  }

  function openProjectMenu() {
    renderProjectMenu();
    projectsSelectMenu?.classList.remove("hidden");
    projectsSelectBtn?.setAttribute("aria-expanded", "true");
  }

  function selectProject(id, { syncUrl = true } = {}) {
    if (viewMode !== "project") {
      enterProject(id, { syncUrl });
      return;
    }
    persistActiveProjectId(id);
    const stored = loadStoredPane(id);
    activePane = stored.pane;
    activeSubId = stored.subId;
    const project = getActiveProject();
    if (project && (activePane === "worker" || activePane === "archive")) {
      const entries = activePane === "worker" ? project.workers : project.archive;
      if (!entries?.length) {
        activePane = "chat";
        activeSubId = null;
      } else if (activeSubId && !entries.some((entry) => entry.id === activeSubId)) {
        activeSubId = entries[0]?.id || null;
      } else if (!activeSubId) {
        activeSubId = entries[0]?.id || null;
      }
    }
    if (project) persistActivePane(project.id, activePane, activeSubId);
    loadProjectChatMode(id);
    updateProjectHeader();
    renderMessages();
    renderProjectSidebar();
    updatePaneVisibility();
    updateDeleteButtonVisibility();
    updateInputState();
    syncProjectSidebarMode();
    if (syncUrl) syncProjectUrl(id);
  }

  async function loadProjects() {
    try {
      await ensureProjectSocketReady();
      const data = await wsRequest("bundle.get");
      applyProjectsBundle(data);
      renderPendingInvites();
      renderProjectMenu();
      renderProjectList();

      const route = window.NexRouter?.parseRoute?.(location.pathname, location.hash);
      const urlProjectId = route?.view === "projects" ? route.projectId : null;
      const targetId = pendingProjectId || urlProjectId;
      pendingProjectId = null;

      if (targetId && state.projects.some((p) => p.id === targetId)) {
        enterProject(targetId, { syncUrl: false });
        return;
      }

      if (viewMode === "list") {
        showListView();
      } else if (activeProjectId && state.projects.some((p) => p.id === activeProjectId)) {
        showProjectWorkspace();
      } else {
        showListView();
      }
    } catch {
      /* ignore */
    }
  }

  async function persistProjects() {
    if (saving) return false;
    saving = true;
    markLocalMutation();
    try {
      const ownedProjects = (state.projects || []).filter(isOwnedProject).map(stripProjectForSave);
      const data = await wsRequest("bundle.save", { projects: ownedProjects });
      applyProjectsBundle(data);
      return true;
    } catch {
      return false;
    } finally {
      saving = false;
    }
  }

  async function persistActiveProject() {
    const project = getActiveProject();
    if (!project) return false;
    if (isOwnedProject(project)) {
      return persistProjects();
    }
    if (saving) return false;
    saving = true;
    markLocalMutation();
    try {
      const data = await wsRequest("project.save", {
        project_id: project.id,
        project: stripProjectForSave(project),
      });
      if (data.project) syncProjectInState({ ...data.project, _shared: true });
      return true;
    } catch {
      return false;
    } finally {
      saving = false;
    }
  }

  function renderPendingInvites() {
    const invites = state.pendingInvites || [];
    if (!projectsInvitesBanner || !projectsInvitesList) return;
    projectsInvitesBanner.classList.toggle("hidden", !invites.length);
    if (!invites.length) {
      projectsInvitesList.innerHTML = "";
      return;
    }
    if (projectsInvitesBannerTitle) {
      projectsInvitesBannerTitle.textContent = t("projectsInvitesBannerTitle");
    }
    projectsInvitesList.innerHTML = "";
    for (const invite of invites) {
      const li = document.createElement("li");
      li.className = "projects-invite-item";
      const title = (invite.project_name || "").trim() || t("projectsUntitled");
      li.innerHTML = `
        <div class="projects-invite-item-copy">
          <div class="projects-invite-item-title">${escapeHtml(title)}</div>
          <div class="projects-invite-item-meta">@${escapeHtml(invite.owner || "")} · ${escapeHtml(roleLabel(invite.role))}</div>
        </div>
        <div class="projects-invite-item-actions">
          <button type="button" class="projects-header-btn" data-invite-accept="${escapeHtml(invite.id)}">${escapeHtml(t("projectsInvitesAccept"))}</button>
          <button type="button" class="projects-header-btn" data-invite-decline="${escapeHtml(invite.id)}">${escapeHtml(t("projectsInvitesDecline"))}</button>
        </div>
      `;
      li.querySelector("[data-invite-accept]")?.addEventListener("click", () => respondToInvite(invite.id, "accept"));
      li.querySelector("[data-invite-decline]")?.addEventListener("click", () => respondToInvite(invite.id, "decline"));
      projectsInvitesList.appendChild(li);
    }
  }

  async function respondToInvite(inviteId, action) {
    try {
      if (action === "accept") {
        const data = await wsRequest("invites.accept", { invite_id: inviteId });
        if (data.project) {
          syncProjectInState({ ...data.project, _shared: true });
          window.NexNotify?.showSuccess?.(t("projectsInvitesAccepted"));
          enterProject(data.project.id);
        }
      } else {
        await wsRequest("invites.decline", { invite_id: inviteId });
        window.NexNotify?.showSuccess?.(t("projectsInvitesDeclined"));
      }
      await loadProjects();
    } catch (err) {
      window.NexNotify?.showError?.(err.message || t("saveFailed"));
    }
  }

  function openDialog() {
    if (projectsDialogTitle) projectsDialogTitle.textContent = t("projectsAdd");
    if (projectsName) projectsName.value = "";
    if (projectsDescription) projectsDescription.value = "";
    projectsDialog?.showModal();
  }

  async function deleteProject(id) {
    const targetId = id || activeProjectId;
    if (!targetId) return;
    const project = (state.projects || []).find((p) => p.id === targetId);
    if (!project) return;

    if (!projectHasPermission(project, "delete_project")) return;

    const ok = await window.NexNotify?.confirm(t("projectsDeleteConfirm"), {
      title: t("projectsDelete"),
      confirmLabel: t("projectsDelete"),
      danger: true,
    });
    if (!ok) return;

    if (isLoading && activeProjectId === targetId) {
      abortController?.abort();
    }

    state.projects = (state.projects || []).filter((p) => p.id !== targetId);
    const saved = await persistProjects();
    if (!saved) return;

    closeProjectMenu();

    if (activeProjectId === targetId) {
      persistActiveProjectId(null);
      activePane = "chat";
      activeSubId = null;
      if (viewMode === "project") {
        if (projectsMessages) projectsMessages.innerHTML = "";
        exitToList();
      } else {
        updateProjectHeader();
        updateInputState();
      }
    }

    renderProjectMenu();
    renderProjectList();
  }

  function closeDialog() {
    projectsDialog?.close();
  }

  function removeStreamingMessage() {
    streamingEl?.remove();
    streamingEl = null;
  }

  function showStreamingPending() {
    removeStreamingMessage();
    streamingEl = appendMessage("assistant", "", null, true);
    const contentEl = streamingEl.querySelector(".message-content");
    contentEl?.classList.add("is-stream-waiting");
    return contentEl;
  }

  async function sendMessage(text) {
    const project = getActiveProject();
    if (!project || isLoading) return;
    const trimmed = (text || "").trim();
    if (!trimmed) return;
    if (!projectHasPermission(project, "chat")) return;

    try {
      await ensureProjectSocketReady();
    } catch {
      window.NexNotify?.showError?.(t("networkError"));
      return;
    }

    const requestId = crypto.randomUUID?.() || String(Date.now());
    activeChatRequestId = requestId;
    isLoading = true;
    updateInputState();
    projectsMessageInput.value = "";
    autoResizeInput();

    sendProjectSocket({
      action: "chat.send",
      request_id: requestId,
      project_id: project.id,
      content: trimmed,
      mode: activeChatMode,
      model: window.__SELECTED_MODEL_ID__ || window.__MODELS__?.[0]?.id || null,
    });
  }

  projectsSelectBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (projectsSelectMenu?.classList.contains("hidden")) openProjectMenu();
    else closeProjectMenu();
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#projectsSelectBtn") && !e.target.closest("#projectsSelectMenu")) {
      closeProjectMenu();
    }
    if (!e.target.closest("#projectsModeWrap")) {
      closeModeMenu();
    }
  });

  projectsNewBtn?.addEventListener("click", openDialog);
  projectsListNewBtn?.addEventListener("click", openDialog);
  projectsBackBtn?.addEventListener("click", exitToList);
  projectsStatsDeleteBtn?.addEventListener("click", () => deleteProject(activeProjectId));
  projectsCancel?.addEventListener("click", closeDialog);

  projectsModeBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (projectsModeBtn.disabled) return;
    if (projectsModeMenu?.classList.contains("hidden")) {
      renderModeMenu();
      projectsModeMenu.classList.remove("hidden");
      projectsModeBtn.setAttribute("aria-expanded", "true");
    } else {
      closeModeMenu();
    }
  });

  projectsForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = projectsName?.value.trim() || "";
    if (!name) return;
    const now = Date.now();
    const project = {
      id: crypto.randomUUID?.() || String(now),
      name,
      description: projectsDescription?.value.trim() || "",
      messages: [],
      stats_items: [],
      workers: [],
      archive: [],
      settings: getDefaultProjectSettings(),
      createdAt: now,
      updatedAt: now,
    };
    state.projects = [...(state.projects || []), project];
    const saved = await persistProjects();
    if (!saved) return;
    closeDialog();
    enterProject(project.id);
    renderProjectMenu();
    renderProjectList();
  });

  document.getElementById("projectsSuggestions")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".suggestion[data-prompt]");
    if (!btn) return;
    const prompt = btn.dataset.prompt || "";
    if (!prompt || !getActiveProject()) return;
    sendMessage(prompt);
  });

  projectsMessageInput.addEventListener("input", () => {
    autoResizeInput();
    updateInputState();
  });
  projectsMessageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!projectsSendBtn.disabled) sendMessage(projectsMessageInput.value);
    }
  });

  projectsSendBtn.addEventListener("click", () => {
    if (isLoading) {
      if (activeChatRequestId) {
        sendProjectSocket({ action: "chat.stop", request_id: activeChatRequestId });
      }
      isLoading = false;
      activeChatRequestId = null;
      updateInputState();
      return;
    }
    sendMessage(projectsMessageInput.value);
  });

  renderSuggestions();
  syncModeSelectUi();
  window.addEventListener("nexgate:language-changed", () => {
    renderSuggestions();
    renderProjectList();
    renderProjectSidebar();
    if (activePane === "stats") renderStatsPane();
    else if (activePane === "worker") renderWorkerPane();
    else if (activePane === "archive") renderArchivePane();
  });

  window.projectsApp = {
    onShow: (projectIdFromRoute = null) => {
      connectProjectSocket();
      renderSuggestions();
      if (projectIdFromRoute) {
        if (state.projects.some((p) => p.id === projectIdFromRoute)) {
          enterProject(projectIdFromRoute, { syncUrl: false });
          return;
        }
        pendingProjectId = projectIdFromRoute;
        showListView();
        loadProjects();
        return;
      }
      pendingProjectId = null;
      showListView();
      loadProjects();
    },
    onHide: () => {
      disconnectProjectSocket();
    },
    renderSidebar: renderProjectSidebar,
  };
})();
