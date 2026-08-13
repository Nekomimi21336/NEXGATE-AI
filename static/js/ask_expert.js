(function () {
  const composeHintEl = document.getElementById("askExpertComposeHint");
  const messagesEl = document.getElementById("askExpertMessages");
  const inputAreaEl = document.getElementById("askExpertInputArea");
  const messageInput = document.getElementById("askExpertMessageInput");
  const sendBtn = document.getElementById("askExpertSendBtn");
  const msgEl = document.getElementById("askExpertMsg");
  const pageTitleEl = document.getElementById("askExpertPageTitle");
  const pageDescEl = document.getElementById("askExpertPageDesc");
  const headerActionsEl = document.getElementById("askExpertHeaderActions");
  const deleteBtn = document.getElementById("askExpertDeleteBtn");
  const sidebarCreateBtn = document.getElementById("askExpertCreateBtn");
  const sessionHistoryEl = document.getElementById("askExpertSessionHistory");

  let sessions = [];
  let activeSession = null;
  let activeExpert = null;
  let composeMode = false;
  let isLoading = false;
  let abortController = null;

  function t(key) {
    return window.t?.(key) || key;
  }

  function showMsg(text, isError) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
    msgEl.classList.toggle("hidden", !text);
    msgEl.classList.toggle("error", Boolean(isError));
  }

  function sessionPath(sessionId) {
    if (!sessionId) return "/ask-expert";
    return `/ask-expert/session/${encodeURIComponent(sessionId)}`;
  }

  function parseSessionIdFromPath() {
    const match = location.pathname.match(/^\/ask-expert\/session\/([0-9a-f-]{36})\/?$/i);
    return match ? decodeURIComponent(match[1]) : null;
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function scrollToBottom() {
    const conv = document.getElementById("askExpertConversation");
    if (!conv) return;
    conv.scrollTop = conv.scrollHeight;
  }

  function applyComposePlaceholder() {
    if (!messageInput) return;
    const ph = t("askExpertComposePlaceholder");
    messageInput.placeholder = ph;
    messageInput.dataset.i18nPlaceholder = "askExpertComposePlaceholder";
  }

  function applySessionPlaceholder() {
    if (!messageInput) return;
    const ph = t("messagePlaceholder");
    messageInput.placeholder = ph;
    messageInput.dataset.i18nPlaceholder = "messagePlaceholder";
  }

  function updateSendBtn() {
    if (!sendBtn) return;
    const stopIcon = sendBtn.querySelector(".send-btn-icon--stop");
    const sendIcon = sendBtn.querySelector(".send-btn-icon--send");
    if (isLoading) {
      stopIcon?.classList.remove("hidden");
      sendIcon?.classList.add("hidden");
      sendBtn.setAttribute("aria-label", "停止");
    } else {
      stopIcon?.classList.add("hidden");
      sendIcon?.classList.remove("hidden");
      sendBtn.setAttribute("aria-label", "送信");
    }
    if (messageInput) {
      const canType = Boolean(activeSession || composeMode);
      messageInput.disabled = isLoading || !canType;
    }
  }

  function autoResizeInput() {
    if (!messageInput) return;
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 200)}px`;
  }

  function showChatShell({ showHint = false } = {}) {
    composeHintEl?.classList.toggle("hidden", !showHint);
    messagesEl?.classList.remove("hidden");
    inputAreaEl?.classList.remove("hidden");
  }

  function enterComposeMode() {
    activeSession = null;
    activeExpert = null;
    composeMode = true;
    if (messagesEl) messagesEl.innerHTML = "";
    showChatShell({ showHint: true });
    applyComposePlaceholder();
    headerActionsEl?.classList.add("hidden");
    if (pageTitleEl) pageTitleEl.textContent = t("askExpertComposeTitle");
    pageDescEl?.classList.add("hidden");
    updateSendBtn();
    messageInput?.focus();
  }

  function exitComposeMode() {
    composeMode = false;
    composeHintEl?.classList.add("hidden");
    applySessionPlaceholder();
  }

  function formatMessageHtml(role, content) {
    const text = String(content || "");
    if (role === "assistant") {
      return window.renderMarkdown?.(text) || escapeHtml(text);
    }
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  async function renderAssistantMessageContent(contentEl, content) {
    if (!contentEl) return;
    if (typeof window.applyMarkdownContent === "function") {
      await window.applyMarkdownContent(contentEl, content);
      return;
    }
    contentEl.innerHTML = formatMessageHtml("assistant", content);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function appendMessage(role, content, scroll = true) {
    exitComposeMode();
    showChatShell({ showHint: false });
    if (!messagesEl) return null;
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const label = role === "user" ? "You" : "AI";
    div.innerHTML = `
      <div class="message-avatar">${label}</div>
      <div class="message-body">
        <div class="message-content markdown-body"></div>
      </div>
    `;
    messagesEl.appendChild(div);
    const contentEl = div.querySelector(".message-content");
    if (role === "assistant" && typeof content === "string" && content.trim()) {
      void renderAssistantMessageContent(contentEl, content);
    } else if (content) {
      contentEl.innerHTML = formatMessageHtml(role, content);
    }
    if (scroll) scrollToBottom();
    return div;
  }

  function showStreamingAssistant() {
    exitComposeMode();
    showChatShell({ showHint: false });
    const div = document.createElement("div");
    div.className = "message assistant";
    div.id = "askExpertStreamingMessage";
    div.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-body">
        <div class="message-content markdown-body is-stream-waiting">
          <div class="stream-waiting">
            <span class="typing" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="stream-waiting-text">${escapeHtml(t("generating") || "回答を生成しています")}</span>
          </div>
        </div>
      </div>
    `;
    messagesEl?.appendChild(div);
    scrollToBottom();
    return div.querySelector(".message-content");
  }

  function removeStreamingMessage() {
    document.getElementById("askExpertStreamingMessage")?.remove();
  }

  function isLikelyUrl(text) {
    return /^https?:\/\//i.test(String(text || "").trim());
  }

  function hostFromUrl(url) {
    try {
      return new URL(url).host;
    } catch {
      return "";
    }
  }

  function showContentWaiting(contentEl) {
    if (!contentEl) return;
    contentEl.classList.remove("is-content-empty");
    contentEl.classList.add("is-stream-waiting");
    contentEl.innerHTML = `
      <div class="stream-waiting">
        <span class="typing" aria-hidden="true"><span></span><span></span><span></span></span>
        <span class="stream-waiting-text">${escapeHtml(t("generating") || "回答を生成しています")}</span>
      </div>
    `;
  }

  function clearContentWaiting(contentEl) {
    if (!contentEl) return;
    contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
    contentEl.querySelector(".stream-waiting")?.remove();
  }

  function finalizeStreamingAssistant(contentEl, segmentText) {
    const streamingEl = document.getElementById("askExpertStreamingMessage");
    if (!streamingEl) return null;
    streamingEl.removeAttribute("id");
    clearContentWaiting(contentEl);
    window.cancelStreamingMarkdown?.(contentEl);
    const text = String(segmentText || "").trim();
    if (contentEl) {
      if (text) {
        contentEl.classList.remove("is-content-empty");
        void window.applyMarkdownContent?.(contentEl, text, { finalize: true });
      } else if (!contentEl.textContent?.trim()) {
        contentEl.innerHTML = "";
        contentEl.classList.add("is-content-empty");
      }
    }
    scrollToBottom();
    return streamingEl;
  }

  function renderAllMessages() {
    if (!activeSession) {
      enterComposeMode();
      return;
    }
    exitComposeMode();
    showChatShell({ showHint: false });
    if (!messagesEl) return;
    messagesEl.innerHTML = "";
    if (!activeSession.messages?.length) {
      updateSendBtn();
      return;
    }
    for (const m of activeSession.messages) {
      if (m.role === "user" || m.role === "assistant") {
        appendMessage(m.role, m.content, false);
      }
    }
    scrollToBottom();
  }

  function updateHeader() {
    if (!activeSession || !activeExpert) {
      if (!composeMode && pageTitleEl) pageTitleEl.textContent = t("askExpertTitle");
      if (!activeSession) {
        pageDescEl?.classList.add("hidden");
        headerActionsEl?.classList.add("hidden");
      }
      return;
    }
    headerActionsEl?.classList.remove("hidden");
    if (pageTitleEl) {
      pageTitleEl.textContent = activeExpert.name || activeSession.title || t("askExpertTitle");
    }
    if (pageDescEl) {
      const modeLabel =
        activeSession.creation_mode === "crawl"
          ? t("askExpertModeCrawl")
          : t("askExpertModeChat");
      pageDescEl.textContent = `${modeLabel} · ${activeExpert.description || ""}`.trim();
      pageDescEl.classList.remove("hidden");
    }
  }

  function isExpertSessionMenuOpen() {
    return Boolean(sessionHistoryEl?.querySelector(".history-item-menu:not(.hidden)"));
  }

  function closeExpertSessionMenus() {
    if (!sessionHistoryEl) return;
    sessionHistoryEl.classList.remove("history-has-open-menu");
    sessionHistoryEl.querySelectorAll(".history-item-menu").forEach((menu) => {
      menu.classList.add("hidden");
    });
    sessionHistoryEl.querySelectorAll(".history-item-menu-btn").forEach((btn) => {
      btn.setAttribute("aria-expanded", "false");
    });
    sessionHistoryEl.querySelectorAll(".history-item").forEach((item) => {
      item.classList.remove("history-item--menu-anchor", "history-item--menu-dimmed");
    });
  }

  function syncExpertSessionMenuOpenState() {
    if (!sessionHistoryEl) return;
    const open = isExpertSessionMenuOpen();
    sessionHistoryEl.classList.toggle("history-has-open-menu", open);
    const anchor = sessionHistoryEl
      .querySelector(".history-item-menu:not(.hidden)")
      ?.closest(".history-item");
    sessionHistoryEl.querySelectorAll(".history-item").forEach((item) => {
      item.classList.toggle("history-item--menu-anchor", item === anchor);
      item.classList.toggle("history-item--menu-dimmed", open && item !== anchor);
    });
  }

  function createExpertSessionHistoryItem(row) {
    const item = document.createElement("div");
    item.className = `history-item${activeSession?.id === row.id ? " active" : ""}`;
    item.dataset.sessionId = row.id;
    item.addEventListener("click", (e) => {
      if (e.target.closest(".history-item-menu-wrap")) return;
      if (isExpertSessionMenuOpen()) {
        closeExpertSessionMenus();
        return;
      }
      void loadSession(row.id);
      window.NexSidebar?.close?.();
    });

    const title = document.createElement("span");
    title.className = "history-item-title";
    title.textContent = row.title || t("askExpertUntitled");

    const menuWrap = document.createElement("div");
    menuWrap.className = "history-item-menu-wrap";

    const menuBtn = document.createElement("button");
    menuBtn.type = "button";
    menuBtn.className = "history-item-menu-btn";
    menuBtn.setAttribute("aria-label", t("askExpertSessionMenuLabel"));
    menuBtn.setAttribute("aria-haspopup", "menu");
    menuBtn.setAttribute("aria-expanded", "false");
    menuBtn.textContent = "⋯";

    const menu = document.createElement("div");
    menu.className = "history-item-menu hidden";
    menu.setAttribute("role", "menu");

    const deleteSessionBtn = document.createElement("button");
    deleteSessionBtn.type = "button";
    deleteSessionBtn.className = "history-item-menu-item history-item-menu-item--danger";
    deleteSessionBtn.setAttribute("role", "menuitem");
    deleteSessionBtn.textContent = t("askExpertSessionDelete");
    deleteSessionBtn.addEventListener("click", (e) => {
      void deleteExpertSession(row.id, e);
    });

    menu.append(deleteSessionBtn);
    menuWrap.append(menuBtn, menu);

    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const isOpen = !menu.classList.contains("hidden");
      closeExpertSessionMenus();
      if (!isOpen) {
        menu.classList.remove("hidden");
        menuBtn.setAttribute("aria-expanded", "true");
        syncExpertSessionMenuOpenState();
      }
    });

    menu.addEventListener("click", (e) => e.stopPropagation());
    menu.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      closeExpertSessionMenus();
      menuBtn.focus();
    });

    item.append(title, menuWrap);
    return item;
  }

  function renderSidebarSessions() {
    if (!sessionHistoryEl) return;
    closeExpertSessionMenus();
    sessionHistoryEl.innerHTML = "";
    if (!sessions.length) {
      const empty = document.createElement("p");
      empty.className = "ask-expert-history-empty";
      empty.textContent = t("askExpertSessionsEmpty");
      sessionHistoryEl.appendChild(empty);
      return;
    }
    for (const row of sessions) {
      sessionHistoryEl.appendChild(createExpertSessionHistoryItem(row));
    }
  }

  async function deleteExpertSession(sessionId, event) {
    event?.stopPropagation();
    event?.preventDefault();
    if (!window.confirm(t("askExpertSessionDeleteConfirm"))) return;
    closeExpertSessionMenus();
    try {
      const res = await fetch(`/api/expert-sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || t("saveFailed"));
    } catch (err) {
      showMsg(err.message || t("networkError"), true);
      return;
    }
    sessions = sessions.filter((s) => s.id !== sessionId);
    if (activeSession?.id === sessionId) {
      activeSession = null;
      activeExpert = null;
      enterComposeMode();
      window.NexRouter?.navigate?.("/ask-expert", { replace: true });
      return;
    }
    renderSidebarSessions();
  }

  function inferCreationMode(text) {
    const value = String(text || "").trim();
    if (/^https?:\/\//i.test(value)) return "crawl";
    if (/^www\.\S+/i.test(value)) return "crawl";
    if (/https?:\/\/\S+/i.test(value)) return "crawl";
    return "chat";
  }

  async function loadSessions() {
    const res = await fetch("/api/expert-sessions");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || t("saveFailed"));
    sessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSidebarSessions();
  }

  async function persistSession() {
    if (!activeSession?.id) return;
    const res = await fetch(`/api/expert-sessions/${encodeURIComponent(activeSession.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: activeSession.title,
        messages: activeSession.messages,
        updated_at: nowIso(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || t("saveFailed"));
    if (data.session) {
      activeSession.title = data.session.title || activeSession.title;
      const idx = sessions.findIndex((s) => s.id === activeSession.id);
      if (idx >= 0) {
        sessions[idx] = { ...sessions[idx], ...data.session };
      } else {
        sessions.unshift(data.session);
      }
      renderSidebarSessions();
    }
  }

  async function createSession(creationMode) {
    const res = await fetch("/api/expert-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ creation_mode: creationMode }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || t("saveFailed"));
    await loadSessions();
    activeExpert = data.expert;
    activeSession = {
      id: data.session.id,
      title: data.session.title,
      creation_mode: data.session.creation_mode || creationMode,
      expert_id: data.session.expert_id,
      messages: [],
    };
    composeMode = false;
    exitComposeMode();
    updateHeader();
    renderSidebarSessions();
    window.NexRouter?.navigate?.(sessionPath(data.session.id));
  }

  async function loadSession(sessionId, { syncUrl = true } = {}) {
    if (!sessionId) {
      enterComposeMode();
      updateHeader();
      renderSidebarSessions();
      if (syncUrl) window.NexRouter?.navigate?.("/ask-expert", { replace: true });
      return;
    }
    const res = await fetch(`/api/expert-sessions/${encodeURIComponent(sessionId)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || t("saveFailed"));
    composeMode = false;
    activeSession = {
      id: data.session.id,
      title: data.session.title,
      creation_mode: data.session.creation_mode,
      expert_id: data.session.expert_id,
      messages: Array.isArray(data.messages) ? data.messages : [],
    };
    activeExpert = data.expert || null;
    renderAllMessages();
    updateHeader();
    renderSidebarSessions();
    if (syncUrl) {
      const path = sessionPath(sessionId);
      if (location.pathname !== path) {
        window.NexRouter?.navigate?.(path, { replace: false });
      }
    }
    applySessionPlaceholder();
    messageInput?.focus();
  }

  async function readExpertStream(response, onChunk, signal, handlers = {}) {
    const onCrawl = handlers.onCrawl;
    const onMeta = handlers.onMeta;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        throw new DOMException("Aborted", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const data = window.parseSseDataFromPart?.(part);
        if (!data) continue;
        if (data.error) throw new Error(data.error);
        if (data.segment_end) onMeta?.({ segment_end: true });
        if (data.segment_start) {
          onMeta?.({
            segment_start: true,
            discard_previous: Boolean(data.discard_previous),
          });
        }
        if (data.content) onChunk(data.content);
        window.NexFullInfoPanel?.handleSseData?.(data);
        if (data.expert_crawl && onCrawl) onCrawl(data.expert_crawl);
        if (data.expert_knowledge_updated) {
          void refreshExpert();
        }
        if (data.done) return;
      }
    }
  }

  async function refreshExpert() {
    if (!activeSession?.expert_id) return;
    const res = await fetch(`/api/info-experts/${encodeURIComponent(activeSession.expert_id)}`);
    const data = await res.json();
    if (res.ok) {
      activeExpert = data;
      updateHeader();
    }
  }

  function buildApiMessages() {
    return (activeSession?.messages || [])
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));
  }

  async function sendMessage(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed || isLoading) return;
    if (!activeSession && !composeMode) return;

    isLoading = true;
    updateSendBtn();
    showMsg("", false);

    try {
      if (!activeSession) {
        await createSession(inferCreationMode(trimmed));
      }

      activeSession.messages.push({
        role: "user",
        content: trimmed,
        created_at: nowIso(),
      });
      appendMessage("user", trimmed);
      if (messageInput) messageInput.value = "";
      autoResizeInput();
      await persistSession();

      abortController = new AbortController();
      let segmentText = "";
      let crawlActive = false;
      const contentEl = showStreamingAssistant();
      const messageBody = contentEl?.closest(".message-body");
      let crawlCard = window.ExpertCrawlCard?.attach(messageBody);
      const maybeUrl = isLikelyUrl(trimmed) ? trimmed.trim() : "";
      if (
        crawlCard &&
        (maybeUrl || activeSession?.creation_mode === "crawl")
      ) {
        crawlActive = true;
        const previewUrl = maybeUrl || trimmed;
        crawlCard.handleEvent({
          type: "start",
          site: {
            host: hostFromUrl(previewUrl) || previewUrl,
            base_url: previewUrl,
          },
        });
        crawlCard.handleEvent({ type: "crawl_phase_start" });
        showContentWaiting(contentEl);
      }

      const res = await fetch("/api/expert-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeSession.id,
          messages: buildApiMessages(),
        }),
        signal: abortController.signal,
      });

      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) {
        let errMsg = t("networkError");
        try {
          const err = await res.json();
          if (err.error) errMsg = err.error;
        } catch (e) {}
        throw new Error(errMsg);
      }

      await readExpertStream(
        res,
        (chunk) => {
          segmentText += chunk;
          if (contentEl) {
            contentEl.classList.remove("is-stream-waiting", "is-content-empty");
            clearContentWaiting(contentEl);
            window.scheduleStreamingMarkdown?.(contentEl, segmentText);
            scrollToBottom();
          }
        },
        abortController.signal,
        {
          onCrawl: (evt) => {
            crawlActive = true;
            if (!crawlCard && messageBody) {
              crawlCard = window.ExpertCrawlCard?.attach(messageBody);
            }
            crawlCard?.handleEvent(evt);
            scrollToBottom();
          },
          onMeta: (meta) => {
            if (meta.segment_end) {
              segmentText = "";
              if (contentEl) {
                clearContentWaiting(contentEl);
                contentEl.innerHTML = "";
                if (crawlActive) {
                  contentEl.classList.add("is-content-empty");
                }
              }
            }
            if (meta.segment_start) {
              segmentText = "";
              if (!contentEl) return;
              if (meta.discard_previous) {
                clearContentWaiting(contentEl);
                contentEl.innerHTML = "";
                if (!crawlActive) showContentWaiting(contentEl);
                else contentEl.classList.add("is-content-empty");
              } else if (crawlActive) {
                clearContentWaiting(contentEl);
                contentEl.innerHTML = "";
                contentEl.classList.add("is-content-empty");
              } else {
                showContentWaiting(contentEl);
              }
            }
          },
        }
      );

      finalizeStreamingAssistant(contentEl, segmentText);
      if (segmentText.trim() || crawlActive) {
        activeSession.messages.push({
          role: "assistant",
          content: segmentText.trim(),
          created_at: nowIso(),
        });
      }
      await persistSession();
      await refreshExpert();
    } catch (err) {
      removeStreamingMessage();
      if (err.name !== "AbortError") {
        showMsg(err.message || t("networkError"), true);
        if (activeSession) {
          const errText = `エラー: ${err.message}`;
          activeSession.messages.push({
            role: "assistant",
            content: errText,
            created_at: nowIso(),
          });
          appendMessage("assistant", errText);
          await persistSession().catch(() => {});
        }
      }
    } finally {
      abortController = null;
      isLoading = false;
      updateSendBtn();
    }
  }

  async function deleteActiveExpert() {
    if (!activeExpert?.id || isLoading) return;
    if (!window.confirm(t("askExpertDeleteConfirm"))) return;
    isLoading = true;
    try {
      const res = await fetch(`/api/info-experts/${encodeURIComponent(activeExpert.id)}`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || t("saveFailed"));
      await loadSessions();
      enterComposeMode();
      window.NexRouter?.navigate?.("/ask-expert", { replace: true });
    } catch (err) {
      showMsg(err.message || t("networkError"), true);
    } finally {
      isLoading = false;
      updateSendBtn();
    }
  }

  function openCreateMenu() {
    window.NexRouter?.navigate?.("/ask-expert");
    window.NexSidebar?.close?.();
  }

  async function onShow(route = {}) {
    window.setAskExpertSidebarMode?.(true);
    const expertId = route?.expertId || null;
    let sessionId = route?.sessionId || parseSessionIdFromPath() || window.__SESSION_ID__ || null;
    try {
      await loadSessions();
    } catch {
      sessions = [];
      renderSidebarSessions();
    }
    if (sessionId) {
      try {
        await loadSession(sessionId, { syncUrl: false });
        return;
      } catch {
        sessionId = null;
      }
    }
    if (expertId) {
      const match = sessions.find((s) => s.expert_id === expertId);
      if (match) {
        await loadSession(match.id, { syncUrl: true });
        return;
      }
    }
    enterComposeMode();
    updateHeader();
  }

  function onHide() {
    if (abortController) abortController.abort();
    window.setAskExpertSidebarMode?.(false);
    activeSession = null;
    activeExpert = null;
    composeMode = false;
  }

  sidebarCreateBtn?.addEventListener("click", () => openCreateMenu());
  deleteBtn?.addEventListener("click", () => void deleteActiveExpert());

  sendBtn?.addEventListener("click", () => {
    if (isLoading && abortController) {
      abortController.abort();
      return;
    }
    void sendMessage(messageInput?.value || "");
  });

  messageInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading) void sendMessage(messageInput.value);
    }
  });

  messageInput?.addEventListener("input", autoResizeInput);

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#askExpertSessionHistory .history-item-menu-wrap")) {
      closeExpertSessionMenus();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeExpertSessionMenus();
  });

  applyComposePlaceholder();
  updateSendBtn();
  window.askExpertApp = { onShow, onHide, renderSidebar: renderSidebarSessions, enterComposeMode };
})();
