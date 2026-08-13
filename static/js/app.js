const currentUser = window.__USER__;
const LEGACY_STORAGE_KEY = `nexgate_chats_${currentUser.username}`;
const SESSIONS_KEY = `nexgate_sessions_${currentUser.username}`;
const messagesStorageKey = (id) => `nexgate_chat_${currentUser.username}_${id}`;
const HISTORY_PAGE_SIZE = 10;
const DEFAULT_SESSION_TITLE = "新しいチャット";
const PRIVATE_CHAT_PREF_KEY = "nexgate_private_chat_enabled";
const PRIVATE_CHAT_EXPIRY_MS = 35 * 60 * 1000;

let sessions = [];
let historyVisibleCount = HISTORY_PAGE_SIZE;
const loadedChats = new Map();
let currentChatId = window.__SESSION_ID__ || null;
let isLoading = false;
let chatAbortController = null;
let activeUserMessageEdit = null;
let privateChatEnabled = false;
let currentPrivateChat = null;
let privateChatExpiryTimer = null;
let privateChatFrameExitTimer = null;
let chatShareInFlight = false;
let chatShareFetchToken = 0;
let currentChatShareState = {
  visibility: "private",
  share_id: null,
  url: null,
  collab_mode: "private",
  collab_id: null,
  collab_url: null,
};
let sessionAccess = {
  owner: currentUser.username,
  role: "owner",
  permissions: ["view", "chat", "edit_settings", "manage_share"],
  collab_mode: "private",
};
let suppressRealtimeUntil = 0;
let suppressSessionIndexUntil = 0;
let sessionSyncTimer = null;
let passiveStreamRequestId = null;
let passiveStreamSessionId = null;
let passiveStreamOff = null;
let localGenerationRequestId = null;
let localGenerationSessionId = null;
const generatingSessionIds = new Set();
let sessionGeneration = {
  requestId: null,
  startedBy: null,
};
let isPassiveGenerating = false;
let passiveFinalizeTimer = null;
let historySearchQuery = "";
let historySearchTimer = null;
const chatShareCollab = document.getElementById("chatShareCollab");
const chatShareCollabLinkRow = document.getElementById("chatShareCollabLinkRow");
const chatShareCollabLinkInput = document.getElementById("chatShareCollabLinkInput");
const chatShareCollabCopyBtn = document.getElementById("chatShareCollabCopyBtn");
const PRIVATE_CHAT_FRAME_MS = 280;
const WELCOME_LAYOUT_MS = 420;

const chatArea = document.getElementById("chatArea");
const chatScrollToBottomBtn = document.getElementById("chatScrollToBottomBtn");
const chatMain = document.getElementById("chatMain");
const messageEditNotice = document.getElementById("messageEditNotice");
const messageEditNoticeText = document.getElementById("messageEditNoticeText");
const messageEditNoticeCancel = document.getElementById("messageEditNoticeCancel");
const chatConversation = document.getElementById("chatConversation");
const privateChatFrameNotice = document.getElementById("privateChatFrameNotice");
const privateChatToggle = document.getElementById("privateChatToggle");
const privateChatToggleWrap = document.getElementById("privateChatToggleWrap");
const chatShareBtn = document.getElementById("chatShareBtn");
const chatSharePanel = document.getElementById("chatSharePanel");
const chatShareVisibility = document.getElementById("chatShareVisibility");
const chatShareLinkRow = document.getElementById("chatShareLinkRow");
const chatShareLinkInput = document.getElementById("chatShareLinkInput");
const chatShareCopyBtn = document.getElementById("chatShareCopyBtn");
const secretModeLabel = document.getElementById("secretModeLabel");
const messagesEl = document.getElementById("messages");
const welcomeEl = document.getElementById("welcome");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const chatHistory = document.getElementById("chatHistory");
const newChatBtn = document.getElementById("newChatBtn");
const sidebarSessionSearchInput = document.getElementById("sidebarSessionSearchInput");
const sidebarSessionSearchClear = document.getElementById("sidebarSessionSearchClear");
const chatSessionTitleBar = document.getElementById("chatSessionTitleBar");
const chatSessionTitle = document.getElementById("chatSessionTitle");

const CHAT_SCROLL_STICK_THRESHOLD = 16;
const CHAT_SCROLL_STICK_THRESHOLD_GENERATING = 120;
let chatStickToBottom = true;
let chatScrollRaf = 0;
let chatLastScrollTop = 0;
let chatProgrammaticScrollDepth = 0;

// Markdown ストリーミングレンダリング完了後にスクロール位置を補正
window._onStreamingMarkdownApplied = () => {
  if (!chatArea || !chatStickToBottom) return;
  requestAnimationFrame(() => {
    if (!chatArea) return;
    chatArea.scrollTop = chatArea.scrollHeight;
    chatLastScrollTop = chatArea.scrollTop;
  });
};

function messageTimestampNow() {
  return new Date().toISOString();
}

function chatLocale() {
  const lang = window.__USER__?.language || "ja";
  if (lang === "en") return "en-US";
  if (lang === "ko") return "ko-KR";
  return "ja-JP";
}

function formatMessageTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(chatLocale(), {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getMessageRoleLabel(role) {
  if (role === "user") return window.t?.("messageRoleUser") || "ユーザー";
  return window.t?.("messageRoleAssistant") || "AI";
}

function getConversationStartedAt(chat) {
  if (!chat?.messages?.length) return null;
  for (const m of chat.messages) {
    if (m.created_at) return m.created_at;
  }
  return null;
}

function createConversationHeaderElement(startedAt) {
  const header = document.createElement("div");
  header.className = "conversation-header";
  header.setAttribute("role", "note");
  const label = window.t?.("conversationStarted") || "会話を開始";
  header.textContent = `${label} · ${formatMessageTimestamp(startedAt)}`;
  return header;
}

function createMessageMetaElement(role, createdAt) {
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = `${formatMessageTimestamp(createdAt)} · ${getMessageRoleLabel(role)}`;
  return meta;
}

function attachMessageMeta(messageEl, role, createdAt) {
  if (!createdAt || !messageEl) return;
  const body = messageEl.querySelector(".message-body");
  if (!body || body.querySelector(".message-meta")) return;
  const content = body.querySelector(".message-content");
  const meta = createMessageMetaElement(role, createdAt);
  if (content) {
    content.insertAdjacentElement("afterend", meta);
  } else {
    body.appendChild(meta);
  }
}

function ensureConversationHeaderInDom(chat) {
  const startedAt = getConversationStartedAt(chat);
  if (!startedAt || messagesEl.querySelector(".conversation-header")) return;
  messagesEl.insertBefore(
    createConversationHeaderElement(startedAt),
    messagesEl.firstChild
  );
}

function isChatNearBottom(threshold = CHAT_SCROLL_STICK_THRESHOLD) {
  if (!chatArea) return true;
  const distance =
    chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
  return distance <= threshold;
}

function isChatGenerationScrollActive() {
  return isSessionGenerating();
}

function beginChatProgrammaticScroll() {
  chatProgrammaticScrollDepth += 1;
}

function endChatProgrammaticScroll() {
  chatProgrammaticScrollDepth = Math.max(0, chatProgrammaticScrollDepth - 1);
}

function isChatProgrammaticScroll() {
  return chatProgrammaticScrollDepth > 0;
}

function updateChatScrollButton() {
  if (!chatScrollToBottomBtn) return;
  const show =
    !chatStickToBottom &&
    messagesEl &&
    !messagesEl.classList.contains("hidden");
  chatScrollToBottomBtn.classList.toggle("hidden", !show);
}

function onChatAreaScroll() {
  if (!chatArea || chatScrollRaf) return;
  chatScrollRaf = requestAnimationFrame(() => {
    chatScrollRaf = 0;
    if (isChatProgrammaticScroll()) return;

    const scrollTop = chatArea.scrollTop;
    const userScrolledUp = scrollTop < chatLastScrollTop - 8;

    if (isChatGenerationScrollActive()) {
      if (userScrolledUp) {
        chatStickToBottom = false;
      } else if (isChatNearBottom(CHAT_SCROLL_STICK_THRESHOLD_GENERATING)) {
        chatStickToBottom = true;
      }
    } else {
      chatStickToBottom = isChatNearBottom();
    }

    chatLastScrollTop = scrollTop;
    updateChatScrollButton();
  });
}

function scrollChatToBottom(force = false) {
  if (!chatArea) return;
  if (force) {
    chatStickToBottom = true;
  }
  if (!force && !chatStickToBottom) return;

  beginChatProgrammaticScroll();
  const apply = () => {
    if (!chatArea) return;
    chatArea.scrollTop = chatArea.scrollHeight;
    chatLastScrollTop = chatArea.scrollTop;
  };
  apply();
  requestAnimationFrame(() => {
    apply();
    requestAnimationFrame(() => {
      apply();
      endChatProgrammaticScroll();
      updateChatScrollButton();
    });
  });
  updateChatScrollButton();
}

function scrollChatToMessage(messageIndex) {
  if (!chatArea || !messagesEl) return;
  const el = messagesEl.querySelector(
    `.message.user[data-message-index="${messageIndex}"]`
  );
  if (!el) return;

  chatStickToBottom = false;
  beginChatProgrammaticScroll();
  const target =
    chatArea.scrollTop +
    el.getBoundingClientRect().top -
    chatArea.getBoundingClientRect().top -
    20;
  chatArea.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
  chatLastScrollTop = chatArea.scrollTop;

  el.classList.add("is-nav-highlight");
  window.setTimeout(() => el.classList.remove("is-nav-highlight"), 1400);
  window.setTimeout(() => {
    endChatProgrammaticScroll();
    updateChatScrollButton();
  }, 450);
  updateChatScrollButton();
}

window.chatMessageScroll = { scrollToMessage: scrollChatToMessage };

function reasoningCardsEnabled() {
  return window.__USER__?.reasoning_cards_enabled === true;
}

function toolTraceEnabled() {
  return window.__USER__?.tool_trace_enabled === true;
}

function isPrivateChat(chat) {
  return Boolean(chat?.private);
}

function isCurrentChatPrivate() {
  const chat = getCurrentChat();
  return isPrivateChat(chat);
}

function chatHasMessageExchange(chat) {
  return Boolean(
    chat?.messages?.some((m) => m.role === "user" || m.role === "assistant")
  );
}

function shouldShowPrivateChatToggle() {
  const chat = getCurrentChat();
  if (!chat) return true;
  return !chatHasMessageExchange(chat);
}

function isPrivateChatToggleVisible() {
  if (sessionAccess.role === "viewer") return false;
  if (window.__SHARED_CHAT__) return false;
  return shouldShowPrivateChatToggle();
}

function syncPrivateChatToggleVisibility() {
  const showToggle = isPrivateChatToggleVisible();
  privateChatToggleWrap?.classList.toggle("hidden", !showToggle);
  if (privateChatToggle) {
    privateChatToggle.disabled = !showToggle;
    privateChatToggle.setAttribute("aria-hidden", showToggle ? "false" : "true");
  }
}

function shouldShowChatShareButton() {
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat)) return false;
  return chatHasMessageExchange(chat);
}

function isChatSharedVisibility(visibility) {
  return visibility === "login_required" || visibility === "public";
}

function isCollabSharedMode(mode) {
  return mode === "view_only" || mode === "participate";
}

function getSessionOwner(sessionId = currentChatId) {
  if (
    window.__SHARED_CHAT__?.session_id === sessionId &&
    window.__SHARED_CHAT__?.owner
  ) {
    return window.__SHARED_CHAT__.owner;
  }
  if (sessionAccess?.owner && sessionAccess.owner !== currentUser.username) {
    return sessionAccess.owner;
  }
  return currentUser.username;
}

function sessionHasPermission(permission) {
  const perms = sessionAccess?.permissions;
  if (!Array.isArray(perms)) return true;
  return perms.includes(permission);
}

function canSendInSession() {
  return sessionHasPermission("chat");
}

function canEditSessionSettings() {
  return sessionHasPermission("edit_settings");
}

function shouldSuppressRealtime() {
  return Date.now() < suppressRealtimeUntil;
}

function isSessionIdGenerating(sessionId) {
  return Boolean(sessionId && generatingSessionIds.has(sessionId));
}

function markSessionGenerating(sessionId) {
  if (!sessionId) return;
  generatingSessionIds.add(sessionId);
  syncGeneratingSessionUI();
}

function unmarkSessionGenerating(sessionId) {
  if (!sessionId) return;
  if (!generatingSessionIds.delete(sessionId)) return;
  syncGeneratingSessionUI();
}

function resolveSessionDisplayTitle(sessionId) {
  if (!sessionId) return "";
  if (currentPrivateChat?.id === sessionId) {
    return (
      String(currentPrivateChat.title || "").trim() ||
      window.t?.("privateChatLabel") ||
      "プライベートチャット"
    );
  }
  const cached = loadedChats.get(sessionId);
  const indexed = sessions.find((s) => s.id === sessionId);
  const title = String(cached?.title || indexed?.title || "").trim();
  return title || DEFAULT_SESSION_TITLE;
}

function updateHistoryGeneratingIndicators() {
  if (!chatHistory) return;
  chatHistory.querySelectorAll(".history-item[data-session-id]").forEach((el) => {
    const sessionId = el.dataset.sessionId;
    const generating = isSessionIdGenerating(sessionId);
    el.classList.toggle("history-item--generating", generating);
    const spinner = el.querySelector(".history-item-spinner");
    if (!spinner) return;
    const wasHidden = spinner.classList.contains("hidden");
    spinner.classList.toggle("hidden", !generating);
    if (generating && wasHidden) {
      spinner.style.animation = "none";
      void spinner.offsetWidth;
      spinner.style.animation = "";
    }
  });
}

function updateChatSessionTitleBar() {
  if (!chatSessionTitleBar || !chatSessionTitle) return;
  const welcomeActive =
    welcomeEl &&
    !welcomeEl.classList.contains("hidden") &&
    !welcomeEl.classList.contains("welcome--exit");
  const title = resolveSessionDisplayTitle(currentChatId);
  const show = Boolean(currentChatId && title && !welcomeActive);
  chatSessionTitleBar.classList.toggle("hidden", !show);
  chatSessionTitle.textContent = show ? title : "";
  chatMain?.classList.toggle("chat-has-session-title", show);
}

function syncGeneratingSessionUI() {
  updateHistoryGeneratingIndicators();
  updateChatSessionTitleBar();
}

function isSessionGenerating() {
  return Boolean(sessionGeneration.requestId) || isLoading || isPassiveGenerating;
}

function syncSessionGenerationUI() {
  messageInput?.toggleAttribute("disabled", !canSendInSession());
  updateSendBtn();
  syncSessionCollaborationUI();
  syncGeneratingSessionUI();
}

function setSessionGeneration(requestId, startedBy = null) {
  sessionGeneration = {
    requestId: requestId || null,
    startedBy: startedBy || null,
  };
  syncSessionGenerationUI();
}

function clearSessionGeneration(requestId) {
  if (requestId && sessionGeneration.requestId && sessionGeneration.requestId !== requestId) {
    return;
  }
  setSessionGeneration(null, null);
}

function markLocalMutation(durationMs = 2500) {
  suppressRealtimeUntil = Date.now() + durationMs;
}

function applySessionAccess(access) {
  if (!access) return;
  sessionAccess = {
    owner: access.owner || getSessionOwner(),
    role: access.role || "owner",
    permissions: Array.isArray(access.permissions) ? access.permissions : [],
    collab_mode: access.collab_mode || "private",
  };
  syncSessionCollaborationUI();
}

function syncSessionCollaborationUI() {
  const viewer = sessionAccess.role === "viewer";
  const canSend = canSendInSession();
  const generating = isSessionGenerating();
  messageInput?.toggleAttribute("disabled", viewer || !canSend);
  sendBtn?.toggleAttribute("disabled", viewer || (!canSend && !generating));
  syncPrivateChatToggleVisibility();
  chatShareBtn?.classList.toggle("hidden", viewer || !shouldShowChatShareButton());
  document.getElementById("modelSelectBtn")?.toggleAttribute("disabled", !canEditSessionSettings());
  document.getElementById("customAgentSelectBtn")?.toggleAttribute("disabled", !canEditSessionSettings());
  document.getElementById("chatToolsSummaryBtn")?.toggleAttribute("disabled", !canEditSessionSettings());
  window.chatInput?.syncAttachButtonState?.();
}

function syncChatShareButtonUI() {
  const show = shouldShowChatShareButton();
  chatShareBtn?.classList.toggle("hidden", !show || sessionAccess.role === "viewer");
  const shared =
    isChatSharedVisibility(currentChatShareState.visibility) ||
    isCollabSharedMode(currentChatShareState.collab_mode);
  chatShareBtn?.classList.toggle("is-shared", shared);
  const labelEl = chatShareBtn?.querySelector(".chat-share-btn-label");
  if (labelEl && window.t) {
    labelEl.textContent = shared
      ? window.t("chatShareActiveLabel")
      : window.t("chatShareLabel");
  }
  if (chatShareBtn && window.t) {
    chatShareBtn.title = window.t("chatShareAria");
    chatShareBtn.setAttribute("aria-label", window.t("chatShareAria"));
  }
  syncChatSharePanelUI();
}

function syncChatSharePanelUI() {
  if (!chatShareVisibility) return;
  const visibility = currentChatShareState.visibility || "private";
  chatShareVisibility.querySelectorAll(".chat-share-visibility-btn").forEach((btn) => {
    const active = btn.dataset.visibility === visibility;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-checked", active ? "true" : "false");
  });
  const showLink = isChatSharedVisibility(visibility) && currentChatShareState.url;
  chatShareLinkRow?.classList.toggle("hidden", !showLink);
  if (showLink && chatShareLinkInput) {
    chatShareLinkInput.value = currentChatShareState.url;
  }
  if (chatShareCollab) {
    const collabMode = currentChatShareState.collab_mode || "private";
    chatShareCollab.querySelectorAll(".chat-share-collab-btn").forEach((btn) => {
      const active = btn.dataset.collabMode === collabMode;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
  }
  const showCollabLink =
    isCollabSharedMode(currentChatShareState.collab_mode) && currentChatShareState.collab_url;
  chatShareCollabLinkRow?.classList.toggle("hidden", !showCollabLink);
  if (showCollabLink && chatShareCollabLinkInput) {
    chatShareCollabLinkInput.value = currentChatShareState.collab_url;
  }
}

function loadPrivateChatPref() {
  try {
    return sessionStorage.getItem(PRIVATE_CHAT_PREF_KEY) === "1";
  } catch {
    return false;
  }
}

function savePrivateChatPref(enabled) {
  try {
    sessionStorage.setItem(PRIVATE_CHAT_PREF_KEY, enabled ? "1" : "0");
  } catch (e) {}
}

function clearPrivateChatExpiryTimer() {
  if (privateChatExpiryTimer) {
    clearTimeout(privateChatExpiryTimer);
    privateChatExpiryTimer = null;
  }
}

function schedulePrivateChatExpiry(chat) {
  if (!isPrivateChat(chat)) return;
  clearPrivateChatExpiryTimer();
  privateChatExpiryTimer = setTimeout(() => {
    expirePrivateChat(chat.id);
  }, PRIVATE_CHAT_EXPIRY_MS);
}

function touchPrivateChatActivity(chat) {
  if (!isPrivateChat(chat)) return;
  chat.last_activity_at = messageTimestampNow();
  currentPrivateChat = chat;
  schedulePrivateChatExpiry(chat);
}

function expirePrivateChat(id) {
  if (!currentPrivateChat || currentPrivateChat.id !== id) return;
  const wasActive = currentChatId === id;
  loadedChats.delete(id);
  currentPrivateChat = null;
  clearPrivateChatExpiryTimer();
  if (wasActive) {
    currentChatId = null;
    window.__SESSION_ID__ = null;
    showWelcome();
    updatePrivateChatActiveUI();
    if (window.NexRouter) {
      window.NexRouter.navigate("/chat", { replace: true });
    } else {
      history.replaceState(null, "", "/chat");
    }
  }
}

function isPrivateChatVisualActive() {
  return (
    isCurrentChatPrivate() ||
    (privateChatEnabled && shouldShowPrivateChatToggle())
  );
}

function privateChatFrameTransitionMs() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? 0
    : PRIVATE_CHAT_FRAME_MS;
}

function clearPrivateChatFrameExitTimer() {
  if (privateChatFrameExitTimer != null) {
    clearTimeout(privateChatFrameExitTimer);
    privateChatFrameExitTimer = null;
  }
}

function revealPrivateChatFrame() {
  if (!chatMain) return;
  chatMain.classList.remove("private-chat-active--visible");
  if (privateChatFrameTransitionMs() === 0) {
    chatMain.classList.add("private-chat-active--visible");
    return;
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      chatMain?.classList.add("private-chat-active--visible");
    });
  });
}

function updatePrivateChatActiveUI() {
  const active = isPrivateChatVisualActive();
  const frameActive = chatMain?.classList.contains("private-chat-active");

  chatConversation?.classList.toggle("chat-conversation--private", active);
  privateChatToggleWrap?.classList.toggle("is-on", active);
  syncPrivateChatToggleVisibility();
  syncChatShareButtonUI();
  secretModeLabel?.classList.toggle("hidden", !active);
  if (secretModeLabel) {
    secretModeLabel.setAttribute("aria-hidden", active ? "false" : "true");
  }

  if (active) {
    clearPrivateChatFrameExitTimer();
    chatMain?.classList.add("private-chat-active");
    privateChatFrameNotice?.classList.remove("hidden");
    if (!chatMain?.classList.contains("private-chat-active--visible")) {
      revealPrivateChatFrame();
    }
  } else if (frameActive) {
    chatMain?.classList.remove("private-chat-active--visible");
    clearPrivateChatFrameExitTimer();
    const ms = privateChatFrameTransitionMs();
    privateChatFrameExitTimer = setTimeout(() => {
      chatMain?.classList.remove("private-chat-active");
      privateChatFrameNotice?.classList.add("hidden");
      privateChatFrameExitTimer = null;
    }, ms);
  } else {
    clearPrivateChatFrameExitTimer();
    chatMain?.classList.remove("private-chat-active", "private-chat-active--visible");
    privateChatFrameNotice?.classList.add("hidden");
  }
}

function syncPrivateChatToggleUI() {
  if (privateChatToggle) {
    privateChatToggle.checked = privateChatEnabled;
  }
  const hint = document.getElementById("privateChatHint");
  if (hint && window.t) {
    hint.textContent = window.t("privateChatHint");
  }
  if (privateChatToggleWrap && window.t) {
    privateChatToggleWrap.title = window.t("privateChatHint");
    privateChatToggle?.setAttribute("aria-label", window.t("privateChatAria"));
  }
  updatePrivateChatActiveUI();
}

function shouldUpdateSessionHistory(chat) {
  return chat && !isPrivateChat(chat);
}

function migrateLegacyChats() {
  const legacyRaw = localStorage.getItem(LEGACY_STORAGE_KEY);
  if (!legacyRaw) return;
  const legacy = JSON.parse(legacyRaw);
  if (!Array.isArray(legacy)) return;

  const index = [];
  for (const chat of legacy) {
    if (!chat?.id || !chat.messages?.length) continue;
    index.push({ id: chat.id, title: chat.title || "新しいチャット" });
    localStorage.setItem(
      messagesStorageKey(chat.id),
      JSON.stringify({ messages: chat.messages })
    );
  }
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(index));
  localStorage.removeItem(LEGACY_STORAGE_KEY);
}

function loadSessionsIndex() {
  migrateLegacyChats();
  const raw = localStorage.getItem(SESSIONS_KEY);
  if (!raw) return [];
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) return [];
  return parsed.map(enrichSessionIndexEntry);
}

function saveSessionsIndex() {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}

function markSessionIndexMutation(ms = 2500) {
  suppressSessionIndexUntil = Date.now() + ms;
}

function shouldSuppressSessionIndex() {
  return Date.now() < suppressSessionIndexUntil;
}

function mergeSessionIndexEntry(meta, existing) {
  if (!meta?.id) return null;
  const entry = enrichSessionIndexEntry({
    id: meta.id,
    title: String(meta.title || "").trim() || existing?.title || DEFAULT_SESSION_TITLE,
    updated_at: meta.updated_at || existing?.updated_at,
    created_at: meta.created_at || existing?.created_at,
  });
  if (meta.favorite === true) {
    entry.favorite = true;
  } else if (meta.favorite === false) {
    delete entry.favorite;
  } else if (existing?.favorite) {
    entry.favorite = true;
  }
  return entry;
}

function applySessionsIndexEvent(msg) {
  if (shouldSuppressSessionIndex()) return;
  const action = msg?.action;
  if (!action) return;

  if (action === "deleted") {
    const id = msg.session_id;
    if (!id || !sessions.some((s) => s.id === id)) return;
    sessions = sessions.filter((s) => s.id !== id);
    loadedChats.delete(id);
    localStorage.removeItem(messagesStorageKey(id));
    saveSessionsIndex();
    if (currentChatId === id) {
      currentChatId = null;
      navigateToNewChat();
      return;
    }
    renderHistory();
    return;
  }

  const meta = msg.session;
  if (!meta?.id) return;
  const idx = sessions.findIndex((s) => s.id === meta.id);
  const isNew = idx < 0;
  const existing = idx >= 0 ? sessions[idx] : null;
  const entry = mergeSessionIndexEntry(meta, existing);
  if (!entry) return;

  if (idx >= 0) {
    const prevTitle = sessions[idx].title;
    const prevFavorite = Boolean(sessions[idx].favorite);
    sessions[idx] = entry;
    saveSessionsIndex();
    const cached = loadedChats.get(entry.id);
    if (cached) cached.title = entry.title;
    const titleChanged = prevTitle !== entry.title;
    const favoriteChanged = prevFavorite !== Boolean(entry.favorite);
    if (titleChanged && !favoriteChanged) {
      const titleEl = findHistoryTitleElement(entry.id);
      if (titleEl) {
        void fadeHistoryItemTitle(titleEl, entry.title);
        return;
      }
    }
    renderHistory();
    return;
  }

  sessions.unshift(entry);
  saveSessionsIndex();
  ensureCurrentSessionVisible();
  renderHistory({ enteringIds: [entry.id] });
}

let chatSessionsInitPromise = null;
const chatPersistTimers = new Map();

function ensureChatSessionsReady() {
  if (!chatSessionsInitPromise) {
    chatSessionsInitPromise = initChatSessionsFromServer();
  }
  return chatSessionsInitPromise;
}

async function fetchSessionsFromServer() {
  const res = await fetch("/api/chat/sessions");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || "セッション一覧の取得に失敗しました");
  }
  return Array.isArray(data.sessions) ? data.sessions : [];
}

async function fetchSessionFromServer(id) {
  const res = await fetch(`/api/chat/sessions/${encodeURIComponent(id)}`);
  const data = await res.json().catch(() => ({}));
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(data.error || "メッセージの取得に失敗しました");
  }
  return {
    messages: Array.isArray(data.messages) ? data.messages : [],
    session: data.session && typeof data.session === "object" ? data.session : null,
  };
}

function resolveSessionTitle(chat, sessionIndex = null) {
  const idx =
    sessionIndex !== null && sessionIndex >= 0
      ? sessionIndex
      : sessions.findIndex((s) => s.id === chat?.id);
  const fromChat = String(chat?.title || "").trim();
  const fromIndex = idx >= 0 ? String(sessions[idx]?.title || "").trim() : "";
  if (fromChat && fromChat !== DEFAULT_SESSION_TITLE) return fromChat;
  if (fromIndex && fromIndex !== DEFAULT_SESSION_TITLE) return fromIndex;
  return fromChat || fromIndex || DEFAULT_SESSION_TITLE;
}

function applyServerSessionMeta(sessionMeta) {
  if (!sessionMeta?.id) return;
  const idx = sessions.findIndex((s) => s.id === sessionMeta.id);
  const title = String(sessionMeta.title || "").trim();
  const entry = enrichSessionIndexEntry({
    id: sessionMeta.id,
    title: title || (idx >= 0 ? sessions[idx].title : DEFAULT_SESSION_TITLE),
    updated_at: sessionMeta.updated_at,
    favorite: sessionMeta.favorite,
    created_at: sessionMeta.created_at,
  });
  if (idx >= 0) {
    if (sessions[idx].favorite) entry.favorite = true;
    if (sessions[idx].created_at && !entry.created_at) {
      entry.created_at = sessions[idx].created_at;
    }
    entry.title = resolveSessionTitle({ id: entry.id, title: entry.title }, idx);
    sessions[idx] = entry;
  } else {
    sessions.unshift(entry);
  }
  saveSessionsIndex();
  const cached = loadedChats.get(entry.id);
  if (cached) cached.title = entry.title;
}

async function uploadLocalSessionsToServer(localSessions) {
  const messagesById = {};
  for (const entry of localSessions) {
    if (!entry?.id) continue;
    const messages = readMessagesFromStorage(entry.id);
    if (messages.length) messagesById[entry.id] = messages;
  }
  const res = await fetch("/api/chat/sessions/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessions: localSessions, messages_by_id: messagesById }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || "ローカル履歴の同期に失敗しました");
  }
  return Array.isArray(data.sessions) ? data.sessions : [];
}

async function persistChatToServer(chat) {
  if (!chat?.id || isPrivateChat(chat)) return;
  const idx = sessions.findIndex((s) => s.id === chat.id);
  const payload = {
    title: resolveSessionTitle(chat, idx),
    messages: serializeMessages(chat.messages),
    updated_at: latestMessageTimestamp(chat.messages) || messageTimestampNow(),
  };
  const res = await fetch(`/api/chat/sessions/${encodeURIComponent(chat.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "チャットの保存に失敗しました");
  }
}

function schedulePersistChatToServer(chat) {
  if (!chat?.id || isPrivateChat(chat)) return;
  const prev = chatPersistTimers.get(chat.id);
  if (prev) clearTimeout(prev);
  chatPersistTimers.set(
    chat.id,
    setTimeout(() => {
      chatPersistTimers.delete(chat.id);
      persistChatToServer(chat).catch((err) => {
        console.warn("chat server persist failed", err);
      });
    }, 450)
  );
}

async function persistSessionMetaToServer(sessionId, fields) {
  const res = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "セッション情報の保存に失敗しました");
  }
}

function hydrateSessionsFromLocal() {
  migrateLegacyChats();
  const localList = loadSessionsIndex();
  if (!localList.length) return false;
  sessions = localList.map(enrichSessionIndexEntry);
  renderHistory({ entering: true });
  return true;
}

async function syncChatSessionsFromServer() {
  const before = JSON.stringify(sessions);
  try {
    let serverList = await fetchSessionsFromServer();
    const localList = loadSessionsIndex();
    if (!serverList.length && localList.length) {
      serverList = await uploadLocalSessionsToServer(localList);
    }
    if (serverList.length) {
      sessions = serverList.map(enrichSessionIndexEntry);
    } else if (!sessions.length && localList.length) {
      sessions = localList.map(enrichSessionIndexEntry);
    } else if (!sessions.length) {
      sessions = [];
    }
    saveSessionsIndex();
  } catch (err) {
    console.warn("chat sessions server init failed", err);
    if (!sessions.length) {
      sessions = loadSessionsIndex();
    }
  }
  const after = JSON.stringify(sessions);
  if (before !== after) {
    renderHistory();
  } else if (!before || before === "[]") {
    renderHistory({ entering: true });
  }
}

async function initChatSessionsFromServer() {
  if (!hydrateSessionsFromLocal()) {
    sessions = [];
  }
  await syncChatSessionsFromServer();
}

function readMessagesFromStorage(id) {
  const raw = localStorage.getItem(messagesStorageKey(id));
  if (!raw) return [];
  try {
    const data = JSON.parse(raw);
    const messages = Array.isArray(data.messages) ? data.messages : [];
    return messages.map((msg) => {
      if (!msg || msg.role !== "user" || msg.content == null) return msg;
      const normalized = window.normalizeUserMessageContent?.(msg.content) ?? msg.content;
      if (normalized === msg.content) return msg;
      return { ...msg, content: normalized };
    });
  } catch {
    return [];
  }
}

function withCreatedAt(out, msg) {
  if (msg.created_at) out.created_at = msg.created_at;
  return out;
}

function serializeMessage(msg) {
  if (!msg || typeof msg !== "object") return msg;
  if (msg.role === "search") {
    const c = msg.content || {};
    return withCreatedAt(
      {
        role: "search",
        content: {
          queries: Array.isArray(c.queries) ? c.queries.map((q) => ({ ...q })) : [],
          sites: Array.isArray(c.sites) ? c.sites.map((s) => ({ ...s })) : [],
          urls: Array.isArray(c.urls) ? c.urls.map((u) => ({ ...u })) : [],
          collapsed: Boolean(c.collapsed),
          complete: Boolean(c.complete),
        },
      },
      msg
    );
  }
  if (msg.role === "reasoning") {
    const c = msg.content || {};
    return withCreatedAt(
      {
        role: "reasoning",
        content: {
          text: typeof c.text === "string" ? c.text : "",
          collapsed: Boolean(c.collapsed),
          complete: Boolean(c.complete),
        },
      },
      msg
    );
  }
  if (msg.role === "tool_trace") {
    const c = msg.content || {};
    const entries = Array.isArray(c.entries) ? c.entries : [];
    return withCreatedAt(
      {
        role: "tool_trace",
        content: {
          entries: entries.map((e) => ({
            name: String(e.name || ""),
            label: String(e.label || e.name || ""),
            duration_ms: Number(e.duration_ms) || 0,
            ok: e.ok !== false,
            error: e.error ? String(e.error) : null,
          })),
          collapsed: Boolean(c.collapsed),
          complete: Boolean(c.complete),
        },
      },
      msg
    );
  }
  if (msg.role === "assistant") {
    const out = { role: "assistant", content: msg.content };
    if (msg.showActions) out.showActions = true;
    if (msg.tasksToolUsed) out.tasksToolUsed = true;
    return withCreatedAt(out, msg);
  }
  return withCreatedAt({ role: msg.role, content: msg.content }, msg);
}

function serializeMessages(messages) {
  return (messages || []).map(serializeMessage);
}

function stripSyncOnlyMessageUiState(msg) {
  if (!msg || typeof msg !== "object") return msg;
  const out = { ...msg };
  if (out.content && typeof out.content === "object") {
    if (out.role === "reasoning" || out.role === "search" || out.role === "tool_trace") {
      const { collapsed, ...content } = out.content;
      out.content = { ...content };
    }
  }
  return out;
}

function serializeMessagesForSync(messages) {
  return serializeMessages(messages).map(stripSyncOnlyMessageUiState);
}

function findLastUserMessageIndex(messages) {
  for (let i = (messages?.length || 0) - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === "user") return i;
  }
  return -1;
}

function findReasoningIndexInCurrentTurn(chat) {
  const msgs = chat?.messages || [];
  const start = findLastUserMessageIndex(msgs) + 1;
  for (let i = msgs.length - 1; i >= start; i -= 1) {
    if (msgs[i]?.role === "reasoning") return i;
  }
  return -1;
}

function findOpenReasoningIndexInCurrentTurn(chat) {
  const msgs = chat?.messages || [];
  const start = findLastUserMessageIndex(msgs) + 1;
  for (let i = msgs.length - 1; i >= start; i -= 1) {
    if (msgs[i]?.role !== "reasoning") continue;
    if (!msgs[i].content?.complete) return i;
    const el = messagesEl.querySelector(`.message-reasoning[data-message-index="${i}"]`);
    const cover = el?.querySelector("#reasoningProcessCover");
    if (cover && !cover.classList.contains("is-complete")) return i;
  }
  return -1;
}

function reasoningSlotIsComplete(messageEl, chat, messageIndex) {
  if (!messageEl || messageIndex === null || messageIndex < 0) return false;
  const cover = messageEl.querySelector("#reasoningProcessCover");
  if (cover?.classList.contains("is-complete")) return true;
  return Boolean(chat?.messages?.[messageIndex]?.content?.complete);
}

function clearCompletedReasoningSlot(slot, chat) {
  if (!slot?.el) return;
  if (reasoningSlotIsComplete(slot.el, chat, slot.index)) {
    slot.el = null;
    slot.index = null;
  }
}

function mergeReasoningContent(localContent = {}, remoteContent = {}) {
  const localText = String(localContent.text || "");
  const remoteText = String(remoteContent.text || "");
  return {
    text: localText.length >= remoteText.length ? localText : remoteText,
    complete: Boolean(localContent.complete || remoteContent.complete),
    collapsed:
      typeof localContent.collapsed === "boolean"
        ? localContent.collapsed
        : typeof remoteContent.collapsed === "boolean"
          ? remoteContent.collapsed
          : getReasoningCardsDefaultCollapsed(),
  };
}

function mergeRemoteMessagesDuringPassive(chat, remoteMessages) {
  const local = chat.messages || [];
  const remote = (remoteMessages || []).map((m) => stripSyncOnlyMessageUiState({ ...m }));
  const merged = remote.map((m) => ({ ...m }));
  const limit = Math.min(local.length, merged.length);
  for (let i = 0; i < limit; i += 1) {
    const localMsg = local[i];
    const remoteMsg = merged[i];
    if (localMsg?.role === "reasoning" && remoteMsg?.role === "reasoning") {
      merged[i] = {
        ...remoteMsg,
        content: mergeReasoningContent(localMsg.content, remoteMsg.content),
      };
      continue;
    }
    if (localMsg?.role === "search" && remoteMsg?.role === "search") {
      merged[i] = {
        ...remoteMsg,
        content: {
          ...remoteMsg.content,
          collapsed:
            typeof localMsg.content?.collapsed === "boolean"
              ? localMsg.content.collapsed
              : false,
          complete: Boolean(localMsg.content?.complete || remoteMsg.content?.complete),
        },
      };
    }
  }
  if (local.length > merged.length) {
    for (let i = merged.length; i < local.length; i += 1) {
      merged.push({ ...local[i] });
    }
  }
  chat.messages = merged;
}

function dedupeReasoningInCurrentTurn(chat) {
  const msgs = chat?.messages || [];
  const lastUser = findLastUserMessageIndex(msgs);
  let changed = false;
  for (let i = msgs.length - 1; i > lastUser + 1; i -= 1) {
    if (msgs[i]?.role !== "reasoning" || msgs[i - 1]?.role !== "reasoning") continue;
    const a = msgs[i - 1]?.content || {};
    const b = msgs[i]?.content || {};
    const scoreA = (a.text?.length || 0) + (a.complete ? 100000 : 0);
    const scoreB = (b.text?.length || 0) + (b.complete ? 100000 : 0);
    const drop = scoreB > scoreA ? i - 1 : i;
    msgs.splice(drop, 1);
    changed = true;
    i = Math.min(i, drop);
  }
  if (changed) chat.messages = msgs;
  return changed;
}

function bindReasoningMessageEl(chat, index) {
  if (!chat || index < 0 || chat.messages[index]?.role !== "reasoning") return null;
  let el = messagesEl.querySelector(`.message-reasoning[data-message-index="${index}"]`);
  const msg = chat.messages[index];
  if (!el) {
    el = appendReasoningMessageToDom(cloneReasoningState(msg.content), index, false);
  }
  el._reasoningState = el._reasoningState || { text: "" };
  const storedText = String(msg.content?.text || "");
  if (storedText.length >= String(el._reasoningState.text || "").length) {
    el._reasoningState.text = storedText;
  }
  renderReasoningCoverText(el);
  const cover = el.querySelector("#reasoningProcessCover");
  if (cover) {
    const collapsed = resolveReasoningCollapsed(msg.content);
    if (msg.content?.complete && !cover.classList.contains("is-complete")) {
      completeReasoningCover(cover, el, collapsed);
    } else {
      setReasoningCoverCollapsed(cover, el, collapsed);
    }
  }
  return el;
}

function ensureReasoningStreamSlot(chat, showAvatar = null) {
  const existingIndex = findOpenReasoningIndexInCurrentTurn(chat);
  if (existingIndex >= 0) {
    const el = bindReasoningMessageEl(chat, existingIndex);
    if (el) return { index: existingIndex, el };
  }
  return ensureReasoningMessageSlot(chat, showAvatar);
}

function finalizeReasoningInCurrentTurn(chat) {
  if (!chat?.messages?.length) return;
  const lastUser = findLastUserMessageIndex(chat.messages);
  for (let i = lastUser + 1; i < chat.messages.length; i += 1) {
    if (chat.messages[i]?.role !== "reasoning") continue;
    const el = bindReasoningMessageEl(chat, i);
    finalizeReasoningIfOpen(el, chat, i);
    persistReasoningMessage(chat, i, el);
  }
}

function committedAssistantTextInCurrentTurn(chat) {
  const msgs = chat?.messages || [];
  const lastUser = findLastUserMessageIndex(msgs);
  let text = "";
  for (let i = lastUser + 1; i < msgs.length; i += 1) {
    if (msgs[i]?.role === "assistant") {
      text += String(msgs[i].content || "");
    }
  }
  return text;
}

function applyAuthoritativeAssistantContent(chat, segmentText, authoritative) {
  const auth = String(authoritative || "");
  if (!auth) return String(segmentText || "");
  const committed = committedAssistantTextInCurrentTurn(chat);
  const pending = String(segmentText || "");
  const localFull = committed + pending;
  if (auth.length <= localFull.length) return pending;
  if (!committed || auth.startsWith(committed)) {
    return auth.slice(committed.length);
  }
  if (auth.length > committed.length) {
    return auth.slice(committed.length);
  }
  return pending;
}

const LS_QUOTA_MAX_RETRIES = 2;

function _evictOldestNonEssentialSession() {
  const sorted = sortSessionsForDisplay(sessions);
  for (const s of sorted) {
    if (s.id === currentChatId) continue;
    if (s.favorite) continue;
    const key = messagesStorageKey(s.id);
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        localStorage.removeItem(key);
        loadedChats.delete(s.id);
        return true;
      }
    } catch (_) {}
  }
  for (const s of sorted) {
    if (s.id === currentChatId) continue;
    const key = messagesStorageKey(s.id);
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        localStorage.removeItem(key);
        loadedChats.delete(s.id);
        return true;
      }
    } catch (_) {}
  }
  return false;
}

function writeMessagesToStorage(id, messages) {
  const payload = serializeMessages(messages);
  const key = messagesStorageKey(id);
  const value = JSON.stringify({ messages: payload });
  for (let attempt = 0; attempt <= LS_QUOTA_MAX_RETRIES; attempt++) {
    try {
      localStorage.setItem(key, value);
      return payload;
    } catch (e) {
      if (attempt < LS_QUOTA_MAX_RETRIES && _evictOldestNonEssentialSession()) {
        continue;
      }
      console.warn("localStorage quota exceeded, message save failed for", id);
      return payload;
    }
  }
  return payload;
}

function loadChatById(id, { preferStorage = false } = {}) {
  if (currentPrivateChat?.id === id) {
    loadedChats.set(id, currentPrivateChat);
    return currentPrivateChat;
  }

  const fromStorage = readMessagesFromStorage(id);
  const cached = loadedChats.get(id);

  if (cached && !preferStorage) {
    if (fromStorage.length > cached.messages.length) {
      cached.messages = fromStorage;
    }
    return cached;
  }

  // localStorage にメッセージが無い場合、IndexedDB から復元を試みる
  if (!fromStorage.length) {
    window.NexIndexedDB?.loadSession?.(id)?.then?.((record) => {
      if (record && Array.isArray(record.messages) && record.messages.length) {
        const chat = loadedChats.get(id);
        if (chat) {
          chat.messages = record.messages;
          writeMessagesToStorage(id, record.messages);
        }
      }
    });
  }

  const idx = sessions.findIndex((s) => s.id === id);
  const meta = idx >= 0 ? sessions[idx] : null;
  const chat = {
    id,
    title: resolveSessionTitle({ id, title: meta?.title }, idx),
    messages: fromStorage,
  };
  loadedChats.set(id, chat);
  return chat;
}

function isHistoryMessage(m) {
  if (m.role === "user") return true;
  if (m.role === "search") return true;
  if (m.role === "reasoning") {
    return reasoningCardsEnabled() && Boolean(String(m.content?.text || "").trim());
  }
  if (m.role === "tool_trace") {
    return toolTraceEnabled() && Array.isArray(m.content?.entries) && m.content.entries.length > 0;
  }
  if (m.role === "assistant") return Boolean(String(m.content || "").trim());
  return false;
}

function normalizeMessageContentKey(content) {
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part?.type === "text") return String(part.text || "");
        return JSON.stringify(part);
      })
      .join("\n")
      .trim();
  }
  if (content && typeof content === "object") return JSON.stringify(content);
  return String(content ?? "").trim();
}

function messageEntryMatches(a, b) {
  if (!a || !b) return false;
  if ((a.role || "").toLowerCase() !== (b.role || "").toLowerCase()) return false;
  if (normalizeMessageContentKey(a.content) !== normalizeMessageContentKey(b.content)) {
    return false;
  }
  const atA = (a.created_at || "").trim();
  const atB = (b.created_at || "").trim();
  if (!atA || !atB) return false;
  return atA === atB;
}

function chatHasMessageEntry(chat, entry) {
  return (chat?.messages || []).some((msg) => messageEntryMatches(msg, entry));
}

function messagesForApi(chat) {
  return chat.messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => {
      const out = { role: m.role, content: m.content };
      if (m.created_at) out.created_at = m.created_at;
      return out;
    });
}

function isLastAssistantInTurn(chat, messageIndex) {
  const msgs = chat?.messages;
  if (!msgs || msgs[messageIndex]?.role !== "assistant") return false;
  for (let i = messageIndex + 1; i < msgs.length; i++) {
    if (msgs[i].role === "user") return true;
    if (msgs[i].role === "assistant") return false;
  }
  return true;
}

function mergeChatState(chat) {
  if (!chat?.id) return getCurrentChat();
  if (currentChatId && chat.id !== currentChatId) {
    return getCurrentChat();
  }
  const stored = loadedChats.get(chat.id);
  if (!stored) {
    loadedChats.set(chat.id, chat);
    return chat;
  }
  if (stored !== chat) {
    stored.messages = chat.messages;
  }
  const idx = sessions.findIndex((s) => s.id === stored.id);
  stored.title = resolveSessionTitle(stored, idx);
  return stored;
}

function sessionUpdatedAtMs(meta) {
  if (!meta) return 0;
  const parsed = Date.parse(meta.updated_at || "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function latestMessageTimestamp(messages) {
  let latest = "";
  for (const msg of messages || []) {
    const ts = msg?.created_at;
    if (typeof ts === "string" && ts && (!latest || ts > latest)) latest = ts;
  }
  return latest;
}

function enrichSessionIndexEntry(entry) {
  if (!entry?.id) return entry;
  if (entry.updated_at) return entry;
  const fromMessages = latestMessageTimestamp(readMessagesFromStorage(entry.id));
  if (fromMessages) return { ...entry, updated_at: fromMessages };
  return entry;
}

function syncSessionIndex(chat) {
  if (!chat) return;
  const idx = sessions.findIndex((s) => s.id === chat.id);
  if (chat.messages?.some(isHistoryMessage)) {
    const title = resolveSessionTitle(chat, idx);
    chat.title = title;
    const entry = {
      id: chat.id,
      title,
      updated_at: latestMessageTimestamp(chat.messages) || messageTimestampNow(),
    };
    if (idx >= 0) {
      if (sessions[idx].favorite) entry.favorite = true;
      if (sessions[idx].created_at) entry.created_at = sessions[idx].created_at;
      sessions[idx] = entry;
    } else {
      sessions.unshift(entry);
    }
  } else if (idx >= 0) {
    sessions.splice(idx, 1);
  }
  saveSessionsIndex();
}

function sortSessionsForDisplay(list) {
  const favorites = [];
  const rest = [];
  for (const s of list) {
    if (s.favorite) favorites.push(s);
    else rest.push(s);
  }
  const byRecent = (a, b) => sessionUpdatedAtMs(b) - sessionUpdatedAtMs(a);
  favorites.sort(byRecent);
  rest.sort(byRecent);
  return favorites.concat(rest);
}

function getOpenHistoryMenuItem() {
  const menu = document.querySelector(".history-item-menu:not(.hidden)");
  return menu?.closest(".history-item") ?? null;
}

function isHistoryMenuOpen() {
  return Boolean(getOpenHistoryMenuItem());
}

function syncHistoryMenuOpenState() {
  if (!chatHistory) return;
  const anchor = getOpenHistoryMenuItem();
  const open = Boolean(anchor);
  chatHistory.classList.toggle("history-has-open-menu", open);
  chatHistory.querySelectorAll(".history-item").forEach((el) => {
    el.classList.toggle("history-item--menu-anchor", el === anchor);
    el.classList.toggle("history-item--menu-dimmed", open && el !== anchor);
  });
}

function closeHistoryMenus() {
  document.querySelectorAll(".history-item-menu").forEach((menu) => {
    menu.classList.add("hidden");
    const btn = menu
      .closest(".history-item-menu-wrap")
      ?.querySelector(".history-item-menu-btn");
    btn?.setAttribute("aria-expanded", "false");
  });
  syncHistoryMenuOpenState();
}

function toggleSessionFavorite(id, event) {
  event?.stopPropagation();
  event?.preventDefault();
  closeHistoryMenus();
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx < 0) return;
  if (sessions[idx].favorite) delete sessions[idx].favorite;
  else sessions[idx].favorite = true;
  markSessionIndexMutation();
  saveSessionsIndex();
  renderHistory();
  persistSessionMetaToServer(id, { favorite: Boolean(sessions[idx]?.favorite) }).catch(
    (err) => console.warn("favorite sync failed", err)
  );
}

function findHistoryTitleElement(sessionId) {
  if (!chatHistory || !sessionId) return null;
  const item = chatHistory.querySelector(`.history-item[data-session-id="${sessionId}"]`);
  if (!item?.querySelector(".history-item-title-input")) {
    return item?.querySelector(".history-item-title") ?? null;
  }
  return null;
}

function fadeHistoryItemTitle(titleEl, newTitle) {
  const next = String(newTitle || "").trim();
  if (!titleEl || !next || titleEl.textContent === next) {
    return Promise.resolve();
  }
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    titleEl.textContent = next;
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    let settled = false;
    let phase = "out";

    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(fallbackTimer);
      titleEl.removeEventListener("transitionend", onTransitionEnd);
      titleEl.style.opacity = "";
      resolve();
    };

    const onTransitionEnd = (event) => {
      if (event.target !== titleEl || event.propertyName !== "opacity") return;
      if (phase === "out") {
        phase = "in";
        titleEl.textContent = next;
        requestAnimationFrame(() => {
          titleEl.style.opacity = "1";
        });
        return;
      }
      finish();
    };

    const fallbackTimer = setTimeout(() => {
      if (!settled) {
        titleEl.textContent = next;
        finish();
      }
    }, 480);

    titleEl.addEventListener("transitionend", onTransitionEnd);
    requestAnimationFrame(() => {
      titleEl.style.opacity = "0";
    });
  });
}

function renameSession(id, newTitle) {
  const trimmed = (newTitle || "").trim();
  if (!trimmed) return;
  const idx = sessions.findIndex((s) => s.id === id);
  if (idx < 0) return;
  sessions[idx].title = trimmed;
  const cached = loadedChats.get(id);
  if (cached) cached.title = trimmed;
  saveSessionsIndex();
  persistSessionMetaToServer(id, { title: trimmed }).catch((err) =>
    console.warn("title sync failed", err)
  );
  const titleEl = findHistoryTitleElement(id);
  if (titleEl) {
    void fadeHistoryItemTitle(titleEl, trimmed);
    return;
  }
  renderHistory();
}

function startSessionTitleEdit(id, titleEl) {
  if (!titleEl || titleEl.dataset.editing === "1") return;
  const current = titleEl.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "history-item-title-input";
  input.value = current;
  input.setAttribute("aria-label", "会話名");
  titleEl.dataset.editing = "1";
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  let finished = false;
  const finish = (save) => {
    if (finished || !input.isConnected) return;
    finished = true;
    const nextTitle = save ? input.value.trim() || current : current;
    if (save && nextTitle !== current) {
      renameSession(id, nextTitle);
      return;
    }
    const span = document.createElement("span");
    span.className = "history-item-title";
    const meta = sessions.find((s) => s.id === id);
    if (meta?.favorite) span.classList.add("history-item-title--favorite");
    span.textContent = nextTitle;
    input.replaceWith(span);
  };

  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    }
    if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    }
  });
  input.addEventListener("blur", () => finish(true));
}

function saveChats(chatRef = null) {
  const targetId = chatRef?.id || currentChatId;
  if (!targetId) return;

  let chat = chatRef ? mergeChatState(chatRef) : getCurrentChat();
  if (!chat || chat.id !== targetId) {
    chat = loadChatById(targetId);
  }
  if (!chat) return;

  currentChatId = targetId;
  loadedChats.set(chat.id, chat);

  if (isPrivateChat(chat)) {
    currentPrivateChat = chat;
    touchPrivateChatActivity(chat);
    updatePrivateChatActiveUI();
    return;
  }

  try {
    chat.messages = writeMessagesToStorage(chat.id, chat.messages);
  } catch (e) {
    return;
  }
  // IndexedDB へも保存（大容量セッション対応）
  try {
    window.NexIndexedDB?.saveSession?.(chat.id, {
      title: chat.title,
      messages: chat.messages,
    });
  } catch (e) {}
  syncSessionIndex(chat);
  schedulePersistChatToServer(chat);
  scheduleBroadcastSessionMessages(chat);
}

function getCurrentChat() {
  if (!currentChatId) return null;
  return loadChatById(currentChatId);
}

chatSessionsInitPromise = initChatSessionsFromServer();

function sessionUrl(id) {
  return `/chat/session/${id}`;
}

function navigateToSession(id, replace = false) {
  if (!id) return;
  currentChatId = id;
  window.__SESSION_ID__ = id;
  if (window.NexRouter) {
    window.NexRouter.navigate(sessionUrl(id), { replace });
    return;
  }
  loadSession(id);
  const url = sessionUrl(id);
  if (replace) history.replaceState({ sessionId: id }, "", url);
  else history.pushState({ sessionId: id }, "", url);
}

function navigateToNewChat() {
  window.__welcomeRefreshNext = true;
  window.NexSidebar?.close?.();
  currentChatId = null;
  window.__SESSION_ID__ = null;
  updatePrivateChatActiveUI();
  if (window.NexRouter) {
    window.NexRouter.navigate("/chat", { replace: false });
    return;
  }
  loadSession(null);
  history.pushState(null, "", "/chat");
}

function createPrivateSessionOnFirstMessage() {
  const id = newUuid();
  const now = messageTimestampNow();
  const chat = {
    id,
    private: true,
    title: window.t?.("privateChatLabel") || "プライベートチャット",
    messages: [],
    created_at: now,
    last_activity_at: now,
  };
  currentPrivateChat = chat;
  currentChatId = id;
  loadedChats.set(id, chat);
  updatePrivateChatActiveUI();
  if (window.NexRouter) {
    window.NexRouter.navigate(sessionUrl(id), { replace: true });
  } else {
    history.replaceState({ sessionId: id }, "", sessionUrl(id));
  }
  return chat;
}

function createSessionOnFirstMessage() {
  if (privateChatEnabled) {
    return createPrivateSessionOnFirstMessage();
  }
  const id = newUuid();
  const now = messageTimestampNow();
  const chat = {
    id,
    title: "新しいチャット",
    messages: [],
  };
  currentChatId = id;
  window.__SESSION_ID__ = id;
  chat.messages = writeMessagesToStorage(id, []);
  loadedChats.set(id, chat);
  sessions.unshift({
    id,
    title: DEFAULT_SESSION_TITLE,
    updated_at: now,
    created_at: now,
  });
  saveSessionsIndex();
  return chat;
}

function navigateToChatSession(sessionId, { replace = true } = {}) {
  if (!sessionId) return;
  if (window.NexRouter) {
    void window.NexRouter.navigate(sessionUrl(sessionId), { replace });
  } else {
    history.replaceState({ sessionId }, "", sessionUrl(sessionId));
  }
}

function welcomeLayoutTransitionMs() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : WELCOME_LAYOUT_MS;
}

function syncChatWelcomeLayout() {
  if (!chatMain || !welcomeEl) return;
  const welcomeActive =
    !welcomeEl.classList.contains("hidden") && !welcomeEl.classList.contains("welcome--exit");
  chatMain.classList.toggle("chat-main--welcome", welcomeActive);
  updateChatSessionTitleBar();
}

function hideWelcome(options = {}) {
  if (!welcomeEl) return;
  if (welcomeEl.classList.contains("hidden")) {
    syncChatWelcomeLayout();
    return;
  }
  if (welcomeEl.classList.contains("welcome--exit") && !options.immediate) {
    return;
  }
  const immediate = Boolean(options.immediate) || welcomeLayoutTransitionMs() === 0;
  clearTimeout(welcomeEl._welcomeExitTimer);
  if (immediate) {
    welcomeEl.classList.remove("welcome--exit");
    welcomeEl.classList.add("hidden");
    syncChatWelcomeLayout();
    return;
  }
  syncChatWelcomeLayout();
  welcomeEl.classList.add("welcome--exit");
  welcomeEl._welcomeExitTimer = setTimeout(() => {
    welcomeEl.classList.remove("welcome--exit");
    welcomeEl.classList.add("hidden");
  }, welcomeLayoutTransitionMs());
}

function triggerWelcomeEnterAnimation() {
  if (!welcomeEl || welcomeEl.classList.contains("hidden")) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  welcomeEl.classList.remove("welcome--enter");
  void welcomeEl.offsetWidth;
  welcomeEl.classList.add("welcome--enter");
  clearTimeout(welcomeEl._welcomeEnterTimer);
  welcomeEl._welcomeEnterTimer = setTimeout(() => {
    welcomeEl.classList.remove("welcome--enter");
  }, 720);
}

function showWelcome(options = {}) {
  const wasHidden = welcomeEl.classList.contains("hidden");
  clearTimeout(welcomeEl._welcomeExitTimer);
  welcomeEl.classList.remove("welcome--exit", "hidden");
  messagesEl.classList.add("hidden");
  messagesEl.innerHTML = "";
  syncChatWelcomeLayout();
  updatePrivateChatActiveUI();
  const refresh = Boolean(options.refresh || window.__welcomeRefreshNext);
  window.__welcomeRefreshNext = false;
  if (refresh) {
    window.updateWelcomeHeading?.({ refresh: true });
    triggerWelcomeEnterAnimation();
  } else if (!window.__welcomeContentReady) {
    window.updateWelcomeHeading?.();
  } else if (wasHidden) {
    triggerWelcomeEnterAnimation();
  }
}

function ensureCurrentSessionVisible() {
  if (!currentChatId || isCurrentChatPrivate()) return;
  const sorted = sortSessionsForDisplay(sessions);
  const idx = sorted.findIndex((s) => s.id === currentChatId);
  if (idx < 0) return;
  const required = idx + 1;
  if (required > historyVisibleCount) {
    historyVisibleCount = Math.ceil(required / HISTORY_PAGE_SIZE) * HISTORY_PAGE_SIZE;
  }
}

function createHistoryItemElement(sessionMeta) {
  const item = document.createElement("div");
  item.className = `history-item${sessionMeta.id === currentChatId ? " active" : ""}${
    sessionMeta.favorite ? " history-item--favorite" : ""
  }${isSessionIdGenerating(sessionMeta.id) ? " history-item--generating" : ""}`;
  item.dataset.sessionId = sessionMeta.id;
  item.onclick = (e) => {
    if (item.querySelector(".history-item-title-input")) return;
    if (e.target.closest(".history-item-menu-wrap")) return;
    if (isHistoryMenuOpen()) {
      closeHistoryMenus();
      return;
    }
    window.NexSidebar?.close?.();
    loadChat(sessionMeta.id);
  };

  const title = document.createElement("span");
  title.className = `history-item-title${
    sessionMeta.favorite ? " history-item-title--favorite" : ""
  }`;
  title.textContent = sessionMeta.title;

  const spinner = document.createElement("span");
  spinner.className = `history-item-spinner${
    isSessionIdGenerating(sessionMeta.id) ? "" : " hidden"
  }`;
  spinner.setAttribute("aria-hidden", "true");

  const menuWrap = document.createElement("div");
  menuWrap.className = "history-item-menu-wrap";

  const menuBtn = document.createElement("button");
  menuBtn.type = "button";
  menuBtn.className = "history-item-menu-btn";
  menuBtn.setAttribute("aria-label", "会話の操作");
  menuBtn.setAttribute("aria-haspopup", "menu");
  menuBtn.setAttribute("aria-expanded", "false");
  menuBtn.textContent = "⋯";

  const menu = document.createElement("div");
  menu.className = "history-item-menu hidden";
  menu.setAttribute("role", "menu");

  const favoriteBtn = document.createElement("button");
  favoriteBtn.type = "button";
  favoriteBtn.className = "history-item-menu-item";
  favoriteBtn.setAttribute("role", "menuitem");
  favoriteBtn.setAttribute("aria-pressed", String(Boolean(sessionMeta.favorite)));
  favoriteBtn.textContent = "お気に入り";
  favoriteBtn.addEventListener("click", (e) => toggleSessionFavorite(sessionMeta.id, e));

  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "history-item-menu-item";
  renameBtn.setAttribute("role", "menuitem");
  renameBtn.textContent = "名前の変更";
  renameBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    closeHistoryMenus();
    const titleEl = item.querySelector(".history-item-title");
    if (titleEl) startSessionTitleEdit(sessionMeta.id, titleEl);
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "history-item-menu-item history-item-menu-item--danger";
  deleteBtn.setAttribute("role", "menuitem");
  deleteBtn.textContent = "削除";
  deleteBtn.addEventListener("click", (e) => deleteChat(sessionMeta.id, e));

  menu.append(favoriteBtn, renameBtn, deleteBtn);
  menuWrap.append(menuBtn, menu);

  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    const isOpen = !menu.classList.contains("hidden");
    closeHistoryMenus();
    if (!isOpen) {
      menu.classList.remove("hidden");
      menuBtn.setAttribute("aria-expanded", "true");
      syncHistoryMenuOpenState();
    }
  });

  menu.addEventListener("click", (e) => e.stopPropagation());
  menu.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    closeHistoryMenus();
    menuBtn.focus();
  });

  item.append(title, spinner, menuWrap);
  return item;
}

function captureHistoryItemPositions() {
  const map = new Map();
  if (!chatHistory) return map;
  chatHistory.querySelectorAll(".history-item[data-session-id]").forEach((el) => {
    const id = el.dataset.sessionId;
    if (!id) return;
    map.set(id, el.getBoundingClientRect());
  });
  return map;
}

function animateHistoryReorder(prevPositions) {
  if (!chatHistory || !prevPositions?.size) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  chatHistory.querySelectorAll(".history-item[data-session-id]").forEach((el) => {
    const prev = prevPositions.get(el.dataset.sessionId);
    if (!prev) return;
    const next = el.getBoundingClientRect();
    const dy = prev.top - next.top;
    const dx = prev.left - next.left;
    if (Math.abs(dy) < 2 && Math.abs(dx) < 2) return;

    el.classList.add("history-item--reorder");
    el.style.transform = `translate(${dx}px, ${dy}px)`;

    const cleanup = () => {
      el.classList.remove("history-item--reorder");
      el.style.transform = "";
    };

    const onTransitionEnd = (event) => {
      if (event.target !== el || event.propertyName !== "transform") return;
      el.removeEventListener("transitionend", onTransitionEnd);
      cleanup();
    };

    el.addEventListener("transitionend", onTransitionEnd);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.transform = "";
      });
    });
    setTimeout(() => {
      el.removeEventListener("transitionend", onTransitionEnd);
      if (el.classList.contains("history-item--reorder")) cleanup();
    }, 400);
  });
}

function renderHistory(options = {}) {
  if (!chatHistory) return;

  const { entering = false, loadMore = false, enteringIds = null } = options;
  let animateFrom = -1;

  if (loadMore) {
    const prev = historyVisibleCount;
    historyVisibleCount = Math.min(sessions.length, historyVisibleCount + HISTORY_PAGE_SIZE);
    animateFrom = prev;
  }

  ensureCurrentSessionVisible();

  const sorted = sortSessionsForDisplay(sessions);
  let list = sorted.slice(0, historyVisibleCount);

  // Filter by search query
  if (historySearchQuery) {
    const q = historySearchQuery.toLowerCase();
    list = sorted.filter((s) => {
      const title = (s.title || s.slug || "").toLowerCase();
      return title.includes(q);
    });
  }

  const hasMore = !historySearchQuery && sorted.length > historyVisibleCount;

  const prevPositions =
    entering || loadMore ? null : captureHistoryItemPositions();

  chatHistory.innerHTML = "";

  if (list.length === 0) {
    const empty = document.createElement("p");
    empty.className = `history-empty${entering ? " history-empty--enter" : ""}`;
    empty.dataset.i18n = "historyEmpty";
    empty.textContent = window.t ? window.t("historyEmpty") : "会話履歴はありません!";
    chatHistory.appendChild(empty);
    syncHistoryMenuOpenState();
    return;
  }

  if (entering) animateFrom = 0;

  const fragment = document.createDocumentFragment();
  const enteringIdSet =
    enteringIds?.length > 0 ? new Set(enteringIds) : null;
  list.forEach((chat, i) => {
    const item = createHistoryItemElement(chat);
    if (enteringIdSet?.has(chat.id)) {
      item.classList.add("history-item--enter");
      item.style.animationDelay = "0ms";
    } else if (animateFrom >= 0 && i >= animateFrom) {
      item.classList.add("history-item--enter");
      item.style.animationDelay = `${(i - animateFrom) * 45}ms`;
    }
    fragment.appendChild(item);
  });
  chatHistory.appendChild(fragment);

  if (hasMore) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "history-load-more";
    moreBtn.textContent = "もっと見る";
    moreBtn.onclick = () => renderHistory({ loadMore: true });
    chatHistory.appendChild(moreBtn);
  }
  if (prevPositions?.size) {
    animateHistoryReorder(prevPositions);
  }
  syncHistoryMenuOpenState();
  syncGeneratingSessionUI();
}

function loadChat(id) {
  navigateToSession(id);
}

async function deleteChat(id, event) {
  event.stopPropagation();
  event.preventDefault();
  markSessionIndexMutation();
  unmarkSessionGenerating(id);
  sessions = sessions.filter((s) => s.id !== id);
  loadedChats.delete(id);
  localStorage.removeItem(messagesStorageKey(id));
  saveSessionsIndex();
  try {
    await fetch(`/api/chat/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch (err) {
    console.warn("chat delete sync failed", err);
  }
  if (currentChatId === id) {
    currentChatId = null;
    navigateToNewChat();
    return;
  }
  renderHistory();
}

const RENDER_MESSAGES_BATCH = 24;

function appendStoredMessageToDom(chat, msg, index) {
  if (msg.role === "search") {
    appendSearchMessageToDom(cloneSearchState(msg.content), index, false);
  } else if (msg.role === "reasoning" && reasoningCardsEnabled()) {
    appendReasoningMessageToDom(cloneReasoningState(msg.content), index, false);
  } else if (msg.role === "tool_trace" && toolTraceEnabled()) {
    appendToolTraceMessageToDom(cloneToolTraceState(msg.content), index, false);
  } else if (msg.role === "assistant") {
    const showActions =
      msg.showActions === true ||
      (msg.showActions !== false && isLastAssistantInTurn(chat, index));
    const showAvatar = isFirstInAssistantTurn(chat, index);
    appendMessage(
      "assistant",
      getMessageDisplayContent(msg.role, msg.content),
      false,
      index,
      showAvatar,
      showActions,
      msg.created_at,
      msg.tasksToolUsed === true
    );
  } else if (msg.role === "user") {
    appendMessage(
      "user",
      msg.content,
      false,
      index,
      true,
      true,
      msg.created_at
    );
  }
}

async function hydrateAllMessageDiagrams() {
  if (!messagesEl) return;
  try {
    await window.loadDiagramLibraries?.();
  } catch (_) {}
  const chat = getCurrentChat();
  if (!chat) return;
  for (let index = 0; index < chat.messages.length; index += 1) {
    const msg = chat.messages[index];
    if (msg.role !== "assistant") continue;
    const content = getMessageDisplayContent(msg.role, msg.content);
    if (!content || !/```(?:mermaid|flow|sequence)/i.test(content)) continue;
    const el = messagesEl.querySelector(`[data-message-index="${index}"] .message-content`);
    if (!el) continue;
    if (!el.querySelector(".md-diagram")) {
      await window.applyMarkdownContent?.(el, content);
    }
    await window.hydrateDiagramPlaceholders?.(el, { root: el });
    await window.enhanceDiagramBlocksInElement?.(el, content, {});
    el.querySelectorAll(".md-diagram-inner").forEach((inner) => {
      window.normalizeDiagramSvg?.(inner);
    });
    window.bindSequenceDiagramResize?.();
  }
}

function renderMessages() {
  const editSession = activeUserMessageEdit
    ? {
        idx: activeUserMessageEdit.idx,
        originalText: activeUserMessageEdit.originalText,
      }
    : null;
  const editDraft = editSession && messageInput ? messageInput.value : "";
  activeUserMessageEdit = null;
  const chat = getCurrentChat();
  if (!chat || chat.messages.length === 0) {
    showWelcome();
    return;
  }

  normalizeAllToolTracesInChat(chat);

  updatePrivateChatActiveUI();

  hideWelcome({ immediate: true });
  messagesEl.classList.remove("hidden");
  window.cancelStreamingMarkdown?.();
  messagesEl.innerHTML = "";

  const startedAt = getConversationStartedAt(chat);
  if (startedAt) {
    messagesEl.appendChild(createConversationHeaderElement(startedAt));
  }

  const messages = chat.messages;
  const hydrateRenderedDiagrams = () => {
    hydrateAllMessageDiagrams().catch(() => {});
  };

  const finishRenderMessages = () => {
    if (editSession) {
      activeUserMessageEdit = editSession;
      if (messageInput) {
        messageInput.value = editDraft;
        autoResize();
      }
      applyUserMessageEditChrome();
      window.chatMessageScroll?.scrollToMessage?.(editSession.idx);
      return;
    }
    scrollChatToBottom(true);
  };

  if (messages.length <= RENDER_MESSAGES_BATCH) {
    messages.forEach((msg, index) => appendStoredMessageToDom(chat, msg, index));
    if (!editSession) scrollChatToBottom(true);
    hydrateRenderedDiagrams();
    finishRenderMessages();
    return;
  }

  let index = 0;
  const renderBatch = () => {
    const end = Math.min(index + RENDER_MESSAGES_BATCH, messages.length);
    for (; index < end; index += 1) {
      appendStoredMessageToDom(chat, messages[index], index);
    }
    if (index < messages.length) {
      requestAnimationFrame(renderBatch);
      return;
    }
    if (!editSession) scrollChatToBottom(true);
    hydrateRenderedDiagrams();
    finishRenderMessages();
  };
  renderBatch();
}


const ICON_THUMB_UP =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z"/></svg>';
const ICON_THUMB_DOWN =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2c0 1.1.9 2 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L9.83 23 16.41 16.41c.37-.36.59-.86.59-1.41V5c0-1.1-.9-2-2-2zm4 0v12h4V3h-4z"/></svg>';
const ICON_COPY =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';
const ICON_TRASH =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>';
const ICON_EDIT =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>';
const ICON_REGENERATE =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08a5.99 5.99 0 0 1-5.65 4c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';
const ICON_FLAG =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6h-5.6z"/></svg>';

function formatUserDisplayContent(content) {
  const normalized = window.normalizeUserMessageContent?.(content) ?? content;
  if (typeof normalized === "string") return normalized;
  if (Array.isArray(normalized)) {
    return normalized
      .filter((p) => p.type === "text")
      .map((p) => p.text || "")
      .join("\n")
      .trim();
  }
  return String(content ?? "");
}

function getMessageDisplayContent(role, content) {
  if (role === "user") return formatUserDisplayContent(content);
  if (role === "search" || role === "reasoning" || role === "tool_trace") return "";
  return typeof content === "string" ? content : formatUserDisplayContent(content);
}

function buildShareMessagesPayload(chat) {
  const out = [];
  for (const m of chat?.messages || []) {
    if (m.role !== "user" && m.role !== "assistant") continue;
    const content = getMessageDisplayContent(m.role, m.content);
    if (!content) continue;
    const entry = { role: m.role, content };
    if (m.created_at) entry.created_at = m.created_at;
    out.push(entry);
  }
  return out;
}

function resetChatShareState() {
  currentChatShareState = {
    visibility: "private",
    share_id: null,
    url: null,
    collab_mode: "private",
    collab_id: null,
    collab_url: null,
  };
  syncChatShareButtonUI();
}

function closeChatSharePanel() {
  chatSharePanel?.classList.add("hidden");
  chatShareBtn?.setAttribute("aria-expanded", "false");
}

function toggleChatSharePanel() {
  if (!chatSharePanel || !chatShareBtn) return;
  const hidden = chatSharePanel.classList.toggle("hidden");
  chatShareBtn.setAttribute("aria-expanded", hidden ? "false" : "true");
  if (!hidden) {
    fetchChatShareState();
    fetchChatCollabState();
  }
}

async function fetchChatCollabState() {
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat) || sessionAccess.role === "viewer") {
    return;
  }
  try {
    const res = await fetch(
      `/api/chat/collab?session_id=${encodeURIComponent(chat.id)}`
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok || getCurrentChat()?.id !== chat.id) return;
    currentChatShareState = {
      ...currentChatShareState,
      collab_mode: data.collab_mode || "private",
      collab_id: data.collab_id || null,
      collab_url: data.url || null,
    };
    syncChatShareButtonUI();
  } catch {
    /* ignore */
  }
}

async function fetchChatShareState() {
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat)) {
    resetChatShareState();
    return;
  }
  const token = ++chatShareFetchToken;
  try {
    const res = await fetch(
      `/api/chat/share?session_id=${encodeURIComponent(chat.id)}`
    );
    const data = await res.json().catch(() => ({}));
    if (token !== chatShareFetchToken || getCurrentChat()?.id !== chat.id) return;
    if (!res.ok) return;
    currentChatShareState = {
      visibility: data.visibility || "private",
      share_id: data.share_id || null,
      url: data.url || null,
    };
    syncChatShareButtonUI();
  } catch {
    if (token === chatShareFetchToken) {
      resetChatShareState();
    }
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    return true;
  } catch {
    return false;
  } finally {
    document.body.removeChild(ta);
  }
}

async function updateChatShareVisibility(visibility) {
  if (chatShareInFlight) return;
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat)) {
    window.NexNotify?.showError(
      window.t?.("chatSharePrivateError") || "プライベートチャットは共有できません"
    );
    return;
  }
  if (visibility === currentChatShareState.visibility) return;

  const messages = buildShareMessagesPayload(chat);
  if (visibility !== "private" && !messages.length) {
    window.NexNotify?.showError(
      window.t?.("chatShareEmptyError") || "共有できるメッセージがありません"
    );
    return;
  }

  chatShareInFlight = true;
  chatShareBtn?.classList.add("is-loading");
  chatShareBtn?.setAttribute("disabled", "disabled");
  chatShareVisibility?.querySelectorAll(".chat-share-visibility-btn").forEach((btn) => {
    btn.disabled = true;
  });

  try {
    const res = await fetch("/api/chat/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: chat.id,
        title: chat.title || "",
        messages,
        visibility,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        data.error || window.t?.("chatShareError") || "共有設定の更新に失敗しました"
      );
    }
    currentChatShareState = {
      visibility: data.visibility || "private",
      share_id: data.share_id || null,
      url: data.url || null,
    };
    syncChatShareButtonUI();
    if (isChatSharedVisibility(currentChatShareState.visibility) && currentChatShareState.url) {
      const copied = await copyTextToClipboard(currentChatShareState.url);
      if (copied) {
        window.NexNotify?.showSuccess(
          window.t?.("chatShareCopied") || "共有リンクをコピーしました",
          { durationMs: 4000 }
        );
      }
    }
  } catch (err) {
    window.NexNotify?.showError(
      err.message || window.t?.("chatShareError") || "共有設定の更新に失敗しました"
    );
  } finally {
    chatShareInFlight = false;
    chatShareBtn?.classList.remove("is-loading");
    chatShareBtn?.removeAttribute("disabled");
    chatShareVisibility?.querySelectorAll(".chat-share-visibility-btn").forEach((btn) => {
      btn.disabled = false;
    });
  }
}

async function copyChatShareLink() {
  if (!currentChatShareState.url) return;
  const copied = await copyTextToClipboard(currentChatShareState.url);
  if (copied) {
    window.NexNotify?.showSuccess(
      window.t?.("chatShareCopied") || "共有リンクをコピーしました",
      { durationMs: 4000 }
    );
  }
}

async function updateChatCollabMode(collabMode) {
  if (chatShareInFlight) return;
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat)) {
    window.NexNotify?.showError(
      window.t?.("chatSharePrivateError") || "プライベートチャットは共有できません"
    );
    return;
  }
  if (!sessionHasPermission("manage_share")) return;
  if ((currentChatShareState.collab_mode || "private") === collabMode) return;

  chatShareInFlight = true;
  chatShareBtn?.classList.add("is-loading");
  try {
    let data;
    try {
      data = await window.NexChatSocket.updateCollabShare(
        chat.id,
        collabMode,
        getSessionOwner(chat.id)
      );
    } catch {
      const res = await fetch("/api/chat/collab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: chat.id, collab_mode: collabMode }),
      });
      data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || "共有設定の更新に失敗しました");
      }
    }
    markLocalMutation();
    currentChatShareState = {
      ...currentChatShareState,
      collab_mode: data.collab_mode || collabMode,
      collab_id: data.collab_id || null,
      collab_url: data.url || null,
    };
    syncChatShareButtonUI();
    if (isCollabSharedMode(currentChatShareState.collab_mode) && currentChatShareState.collab_url) {
      const copied = await copyTextToClipboard(currentChatShareState.collab_url);
      if (copied) {
        window.NexNotify?.showSuccess(
          window.t?.("chatShareCollabCopied") || "ライブ共有リンクをコピーしました",
          { durationMs: 4000 }
        );
      }
    }
  } catch (err) {
    window.NexNotify?.showError(
      err.message || window.t?.("chatShareError") || "共有設定の更新に失敗しました"
    );
  } finally {
    chatShareInFlight = false;
    chatShareBtn?.classList.remove("is-loading");
  }
}

async function copyChatCollabLink() {
  if (!currentChatShareState.collab_url) return;
  const copied = await copyTextToClipboard(currentChatShareState.collab_url);
  if (copied) {
    window.NexNotify?.showSuccess(
      window.t?.("chatShareCollabCopied") || "ライブ共有リンクをコピーしました",
      { durationMs: 4000 }
    );
  }
}

function applySessionSettings(settings, { remote = false } = {}) {
  if (!settings || typeof settings !== "object") return;
  if (remote) suppressRealtimeUntil = Date.now() + 1200;
  if (settings.model_id && window.setSelectedModel) {
    window.setSelectedModel(settings.model_id);
  }
  if (settings.custom_agent_id && window.customAgentSelect?.selectAgent) {
    window.customAgentSelect.selectAgent(settings.custom_agent_id);
  }
  if (settings.chat_tools && window.chatToolsBar?.setToolEnabled) {
    Object.entries(settings.chat_tools).forEach(([toolId, enabled]) => {
      window.chatToolsBar.setToolEnabled(toolId, Boolean(enabled));
    });
  }
}

function collectSessionSettings() {
  const settings = {};
  const modelId = window.__SELECTED_MODEL_ID__ || window.getSelectedModelId?.();
  if (modelId) settings.model_id = modelId;
  const agentId = window.customAgentSelect?.getSelectedAgentId?.();
  if (agentId) settings.custom_agent_id = agentId;
  const tools = window.chatToolsBar?.getChatToolsPayload?.();
  if (tools && Object.keys(tools).length) settings.chat_tools = tools;
  return settings;
}

function scheduleBroadcastSessionSettings() {
  if (!currentChatId || shouldSuppressRealtime()) return;
  const chat = getCurrentChat();
  if (!chat || isPrivateChat(chat) || !canEditSessionSettings()) return;
  window.clearTimeout(window.__sessionSettingsTimer__);
  window.__sessionSettingsTimer__ = window.setTimeout(() => {
    const settings = collectSessionSettings();
    if (!Object.keys(settings).length) return;
    markLocalMutation();
    window.NexChatSocket?.sessionSave?.(
      chat.id,
      { settings },
      getSessionOwner(chat.id)
    ).catch(() => {});
  }, 400);
}

function scheduleBroadcastSessionMessages(chat) {
  if (!chat?.id || isPrivateChat(chat) || shouldSuppressRealtime()) return;
  if (isLoading || isPassiveGenerating) return;
  if (sessionSyncTimer) clearTimeout(sessionSyncTimer);
  sessionSyncTimer = setTimeout(() => {
    sessionSyncTimer = null;
    if (shouldSuppressRealtime()) return;
    window.NexChatSocket?.sessionSave?.(
      chat.id,
      { messages: serializeMessagesForSync(chat.messages) },
      getSessionOwner(chat.id)
    ).catch(() => {});
  }, 500);
}

function broadcastSessionMessagesReplace(chat) {
  if (!chat?.id || isPrivateChat(chat)) return;
  markLocalMutation();
  window.NexChatSocket?.sessionSave?.(
    chat.id,
    { messages: serializeMessagesForSync(chat.messages) },
    getSessionOwner(chat.id)
  ).catch(() => {});
}

async function abortSessionGenerationIfNeeded() {
  const rid = sessionGeneration.requestId;
  if (!rid) return;
  window.NexChatSocket?.stop?.(rid);
  stopPassiveStreamWatch();
  clearSessionGeneration(rid);
  await new Promise((resolve) => setTimeout(resolve, 80));
}

function renderMessageAppend(chat, newMessages, startIndex) {
  if (!messagesEl || messagesEl.classList.contains("hidden")) {
    hideWelcome({ immediate: true });
    messagesEl.classList.remove("hidden");
    const startedAt = getConversationStartedAt(chat);
    if (startedAt && !messagesEl.querySelector(".conversation-header")) {
      messagesEl.appendChild(createConversationHeaderElement(startedAt));
    }
  }
  hideWelcome({ immediate: true });
  messagesEl.classList.remove("hidden");
  for (let i = 0; i < newMessages.length; i++) {
    appendStoredMessageToDom(chat, newMessages[i], startIndex + i);
  }
  scrollChatToBottom();
}

function applyRemoteSessionPatch(patch, meta = {}) {
  if (!patch) return;
  const sessionId = meta.session_id || patch.session_id || currentChatId;
  if (!sessionId || sessionId !== currentChatId) return;
  if (shouldSuppressRealtime()) return;

  if (patch.settings) {
    applySessionSettings(patch.settings, { remote: true });
  }
  if (patch.collab_mode) {
    currentChatShareState = {
      ...currentChatShareState,
      collab_mode: patch.collab_mode,
      collab_id: patch.collab_id || currentChatShareState.collab_id,
      collab_url: patch.collab_url || currentChatShareState.collab_url,
    };
    syncChatShareButtonUI();
  }
  if (patch.title) {
    const chat = getCurrentChat();
    if (chat) applySessionTitle(chat, patch.title);
  }

  let chat = loadedChats.get(sessionId) || loadChatById(sessionId);
  if (!chat) return;

  if (Array.isArray(patch.messages)) {
    const localLen = chat.messages?.length || 0;
    const remoteLen = patch.messages.length;
    if (remoteLen < localLen) {
      return;
    }
    if (isPassiveGenerating) {
      if (remoteLen >= localLen) {
        mergeRemoteMessagesDuringPassive(chat, patch.messages);
        loadedChats.set(sessionId, chat);
        writeMessagesToStorage(sessionId, chat.messages);
      }
      return;
    }
    const remoteMessages = patch.messages.map((m) => stripSyncOnlyMessageUiState({ ...m }));
    if (getCurrentChat()?.id === sessionId && !isLoading && localLen > 0 && remoteLen > localLen) {
      const newMessages = remoteMessages.slice(localLen);
      chat.messages = remoteMessages;
      loadedChats.set(sessionId, chat);
      writeMessagesToStorage(sessionId, chat.messages);
      renderMessageAppend(chat, newMessages, localLen);
      return;
    }
    chat.messages = remoteMessages;
    loadedChats.set(sessionId, chat);
    writeMessagesToStorage(sessionId, chat.messages);
    if (getCurrentChat()?.id === sessionId && !isLoading) renderMessages();
    return;
  }

  if (patch.message_append) {
    applyRemoteUserMessage(patch.message_append, {
      session_id: sessionId,
      owner: meta.owner,
      editor: meta.editor,
    });
  }
}

function stopPassiveStreamWatch() {
  const sessionId = passiveStreamSessionId;
  if (passiveFinalizeTimer) {
    window.clearTimeout(passiveFinalizeTimer);
    passiveFinalizeTimer = null;
  }
  if (passiveStreamOff) {
    passiveStreamOff();
    passiveStreamOff = null;
  }
  passiveStreamRequestId = null;
  passiveStreamSessionId = null;
  isPassiveGenerating = false;
  if (sessionId) unmarkSessionGenerating(sessionId);
  syncSessionGenerationUI();
}

function applyRemoteUserMessage(message, meta = {}) {
  if (!message || meta.session_id !== currentChatId) return;
  if (shouldSuppressRealtime()) return;
  if (isLoading && localGenerationRequestId) return;

  const sessionId = meta.session_id || currentChatId;
  let chat = loadedChats.get(sessionId) || loadChatById(sessionId);
  if (!chat) return;

  const hadEntry = chatHasMessageEntry(chat, message);
  if (!hadEntry) {
    chat.messages.push({ ...message });
    loadedChats.set(sessionId, chat);
    writeMessagesToStorage(sessionId, chat.messages);
  }

  if (getCurrentChat()?.id !== sessionId) return;
  if (isLoading && localGenerationRequestId) return;

  if (isPassiveGenerating) {
    if (!hadEntry) {
      const index = chat.messages.length - 1;
      appendStoredMessageToDom(chat, chat.messages[index], index);
      scrollChatToBottom();
    }
    if (!document.getElementById("streamingMessage")) {
      const showAvatar = isFirstInAssistantTurn(chat, chat.messages.length);
      showAssistantPending(showAvatar);
    }
    return;
  }
  renderMessages();
}

function refreshPassiveStreamPending(chat) {
  if (!isPassiveGenerating || !chat) return;
  renderMessages();
  const showAvatar = isFirstInAssistantTurn(chat, chat.messages.length);
  showAssistantPending(showAvatar);
  const openIdx = findOpenReasoningIndexInCurrentTurn(chat);
  return openIdx >= 0 ? bindReasoningMessageEl(chat, openIdx) : null;
}

function startPassiveStreamWatch(sessionId, requestId) {
  if (!sessionId || !requestId) return;
  if (localGenerationRequestId === requestId) return;

  const chat = getCurrentChat();
  if (!chat || chat.id !== sessionId) return;

  if (passiveStreamRequestId === requestId) {
    if (isPassiveGenerating && !document.getElementById("streamingMessage")) {
      refreshPassiveStreamPending(chat);
    }
    return;
  }

  stopPassiveStreamWatch();
  passiveStreamRequestId = requestId;
  passiveStreamSessionId = sessionId;
  isPassiveGenerating = true;
  markSessionGenerating(sessionId);
  chatStickToBottom = true;
  syncSessionGenerationUI();

  let turnAvatarUsed = false;
  const takeTurnAvatar = () => {
    if (turnAvatarUsed) return false;
    turnAvatarUsed = true;
    return true;
  };

  const reopenPassiveStreaming = (showAvatar = false) => showAssistantPending(showAvatar);

  let segmentText = "";
  let streamingEl = null;
  let contentEl = null;
  let searchMessageIndex = null;
  let searchMessageEl = null;
  let reasoningMessageIndex = null;
  let reasoningMessageEl = null;
  let toolTraceMessageIndex = null;
  let toolTraceMessageEl = null;
  let passiveTurnFinalized = false;

  const rebindPassiveReasoning = () => {
    const idx = findOpenReasoningIndexInCurrentTurn(chat);
    reasoningMessageIndex = idx >= 0 ? idx : null;
    reasoningMessageEl = idx >= 0 ? bindReasoningMessageEl(chat, idx) : null;
  };

  renderMessages();
  rebindPassiveReasoning();
  streamingEl = reopenPassiveStreaming(takeTurnAvatar());
  contentEl = streamingEl?.querySelector(".message-content");

  const finalizePassiveTurn = () => {
    if (passiveTurnFinalized) return;
    passiveTurnFinalized = true;
    finalizeReasoningIfOpen(reasoningMessageEl, chat, reasoningMessageIndex);
    dedupeReasoningInCurrentTurn(chat);
    rebindPassiveReasoning();
    finalizeReasoningInCurrentTurn(chat);
    if (searchMessageEl) {
      const cover = searchMessageEl.querySelector("#searchProcessCover");
      if (cover && !cover.classList.contains("is-complete")) {
        finalizeSearchCoverOnStop(searchMessageEl, { stopped: false });
      }
      persistSearchMessage(chat, searchMessageIndex, searchMessageEl);
    }
    if (toolTraceMessageEl) {
      const tCover = toolTraceMessageEl.querySelector("#toolTraceCover");
      if (tCover && !tCover.classList.contains("is-complete")) {
        completeToolTraceCover(tCover, toolTraceMessageEl, true);
      }
      persistToolTraceMessage(chat, toolTraceMessageIndex, toolTraceMessageEl);
    }
    finalizeReplyTurn(
      chat,
      segmentText,
      searchMessageIndex,
      searchMessageEl,
      reasoningMessageIndex,
      reasoningMessageEl,
      takeTurnAvatar,
      false,
      toolTraceMessageIndex,
      toolTraceMessageEl
    );
    segmentText = "";
  };

  const schedulePassiveFinalize = (statusMsg) => {
    if (passiveFinalizeTimer) {
      window.clearTimeout(passiveFinalizeTimer);
    }
    passiveFinalizeTimer = window.setTimeout(() => {
      passiveFinalizeTimer = null;
      if (passiveTurnFinalized) return;
      const authoritative = String(statusMsg?.assistant_content || "");
      if (authoritative) {
        segmentText = applyAuthoritativeAssistantContent(chat, segmentText, authoritative);
        if (contentEl && segmentText) {
          contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
          window.scheduleStreamingMarkdown?.(contentEl, stripThinking(segmentText));
        }
      }
      finalizePassiveTurn();
      stopPassiveStreamWatch();
      clearSessionGeneration(requestId);
    }, 48);
  };

  const clearPassiveStreamingSlot = () => {
    if (!streamingEl) return;
    removeStreamingMessage();
    streamingEl = null;
    contentEl = null;
  };

  const ensurePassiveSearchSlot = () => {
    if (searchMessageEl) return;
    if (reasoningMessageEl) {
      const rCover = reasoningMessageEl.querySelector("#reasoningProcessCover");
      if (rCover && !rCover.classList.contains("is-complete")) {
        completeReasoningCover(
          rCover,
          reasoningMessageEl,
          rCover.classList.contains("is-collapsed")
        );
        syncReasoningMessageToChat(chat, reasoningMessageIndex, reasoningMessageEl);
      }
    }
    if (segmentText.trim() && streamingEl) {
      clearPassiveStreamingSlot();
      if (!isSearchPrefaceOnly(segmentText)) {
        commitAssistantSegment(chat, segmentText, takeTurnAvatar(), false);
      }
      segmentText = "";
    } else if (streamingEl) {
      clearPassiveStreamingSlot();
    }
    const slot = ensureSearchMessageSlot(chat, takeTurnAvatar());
    searchMessageIndex = slot.index;
    searchMessageEl = slot.el;
    if (toolTraceMessageEl) {
      const pinned = syncPinnedToolTraceSlot(chat, {
        index: toolTraceMessageIndex,
        el: toolTraceMessageEl,
      });
      toolTraceMessageIndex = pinned.index;
      toolTraceMessageEl = pinned.el;
    }
  };

  const ensurePassiveToolTraceSlot = () => {
    if (!toolTraceEnabled() || toolTraceMessageEl) return;
    if (segmentText.trim() && streamingEl) {
      clearPassiveStreamingSlot();
      commitAssistantSegment(chat, segmentText, takeTurnAvatar(), false);
      segmentText = "";
    } else if (streamingEl) {
      clearPassiveStreamingSlot();
    }
    const slot = ensureToolTraceMessageSlot(chat, takeTurnAvatar());
    toolTraceMessageIndex = slot.index;
    toolTraceMessageEl = slot.el;
  };

  const streamHandlers = {
    onChunk: (chunk) => {
      finalizeReasoningIfOpen(reasoningMessageEl, chat, reasoningMessageIndex);
      if (!contentEl) {
        streamingEl = reopenPassiveStreaming(false);
        contentEl = streamingEl?.querySelector(".message-content");
      }
      if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
        messagesEl.appendChild(streamingEl);
      }
      segmentText += chunk;
      contentEl?.classList.remove("is-stream-waiting", "is-stream-stopped");
      window.scheduleStreamingMarkdown?.(contentEl, stripThinking(segmentText));
      scrollChatToBottom();
    },
    onSearch: (searchEvent) => {
      if (searchEvent.type === "intent" || searchEvent.type === "start") {
        if (!searchMessageEl) ensurePassiveSearchSlot();
      }
      if (!searchMessageEl) return;
      handleSearchStreamEvent(searchMessageEl, searchEvent);
      syncSearchMessageToChat(chat, searchMessageIndex, searchMessageEl);
    },
    onReasoning: (reasoningEvent) => {
      if (!reasoningCardsEnabled()) return;
      const slot = { el: reasoningMessageEl, index: reasoningMessageIndex };
      clearCompletedReasoningSlot(slot, chat);
      reasoningMessageEl = slot.el;
      reasoningMessageIndex = slot.index;
      if (!reasoningMessageEl) {
        rebindPassiveReasoning();
      }
      if ((reasoningEvent.type === "delta" || reasoningEvent.type === "done") && !reasoningMessageEl) {
        if (reasoningEvent.type === "delta") {
          if (segmentText.trim() && streamingEl) {
            clearPassiveStreamingSlot();
            commitAssistantSegment(chat, segmentText, takeTurnAvatar(), false);
            segmentText = "";
          } else if (streamingEl) {
            clearPassiveStreamingSlot();
          }
        }
        const created = ensureReasoningStreamSlot(chat, takeTurnAvatar());
        reasoningMessageIndex = created.index;
        reasoningMessageEl = created.el;
        if (toolTraceMessageEl) {
          const pinned = syncPinnedToolTraceSlot(chat, {
            index: toolTraceMessageIndex,
            el: toolTraceMessageEl,
          });
          toolTraceMessageIndex = pinned.index;
          toolTraceMessageEl = pinned.el;
        }
      }
      if (!reasoningMessageEl) return;
      handleReasoningStreamEvent(reasoningMessageEl, reasoningEvent);
      syncReasoningMessageToChat(chat, reasoningMessageIndex, reasoningMessageEl);
      if (reasoningEvent.type === "done") {
        saveChats(chat);
      }
    },
    onToolTrace: (trace) => {
      if (!toolTraceEnabled()) return;
      ensurePassiveToolTraceSlot();
      if (!toolTraceMessageEl) return;
      const pinned = handleToolTraceEvent(toolTraceMessageEl, trace);
      toolTraceMessageIndex = pinned.index;
      toolTraceMessageEl = pinned.el;
      syncToolTraceMessageToChat(chat, toolTraceMessageIndex, toolTraceMessageEl);
      saveChats(chat);
    },
    onMeta: (meta) => {
      if (meta.segment_start && reasoningMessageEl) {
        finalizeReasoningIfOpen(reasoningMessageEl, chat, reasoningMessageIndex);
      }
      if (meta.segment_end && segmentText.trim()) {
        clearPassiveStreamingSlot();
        commitAssistantSegment(chat, segmentText, takeTurnAvatar(), false);
        segmentText = "";
      }
      if (meta.content_replace) {
        segmentText = String(meta.content_replace || "");
        if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
          messagesEl.appendChild(streamingEl);
        }
        if (contentEl) {
          window.scheduleStreamingMarkdown?.(contentEl, stripThinking(segmentText));
          scrollChatToBottom();
        }
        return;
      }
      if (meta.segment_start) {
        if (segmentText.trim() && !meta.discard_previous) {
          clearPassiveStreamingSlot();
          commitAssistantSegment(chat, segmentText, takeTurnAvatar(), false);
        }
        segmentText = "";
        if (meta.discard_previous) {
          if (streamingEl && contentEl) {
            messagesEl.appendChild(streamingEl);
            if (!contentEl.classList.contains("is-stream-waiting")) {
              contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
              window.cancelStreamingMarkdown?.(contentEl);
              contentEl.innerHTML = "";
            }
          } else {
            clearPassiveStreamingSlot();
            streamingEl = reopenPassiveStreaming(false);
            contentEl = streamingEl?.querySelector(".message-content");
          }
        } else {
          clearPassiveStreamingSlot();
          streamingEl = reopenPassiveStreaming(false);
          contentEl = streamingEl?.querySelector(".message-content");
        }
      }
    },
  };

  passiveStreamOff = window.NexChatSocket.onEvent((msg) => {
    if (msg.session_id && msg.session_id !== sessionId) return;
    if (msg.type === "chat.generation.started" && msg.request_id) {
      if (msg.request_id !== requestId) return;
      segmentText = "";
      streamingEl = reopenPassiveStreaming(false);
      contentEl = streamingEl?.querySelector(".message-content");
      return;
    }
    if (msg.type === "chat.snapshot" && msg.request_id === requestId) {
      window.NexChatSocket.replaySnapshot(msg, (ev) => {
        applyChatStreamPayload(ev.data, streamHandlers);
      });
      return;
    }
    if (msg.type === "chat.event" && msg.request_id === requestId) {
      applyChatStreamPayload(msg.data, streamHandlers);
      return;
    }
    if (msg.type === "chat.status" && msg.request_id === requestId) {
      if (msg.status && msg.status !== "running") {
        schedulePassiveFinalize(msg);
      }
      return;
    }
    if (msg.type === "chat.generation.ended" && msg.request_id === requestId) {
      if (!passiveTurnFinalized) {
        schedulePassiveFinalize(msg);
      }
      return;
    }
  });
}

function handleSessionGenerationStarted(msg) {
  const sessionId = msg.session_id || currentChatId;
  if (!sessionId || !msg.request_id) return;
  markSessionGenerating(sessionId);
  if (sessionId !== currentChatId) return;
  if (msg.user_message) {
    applyRemoteUserMessage(msg.user_message, {
      session_id: sessionId,
      owner: msg.owner,
      editor: msg.started_by,
    });
  }
  setSessionGeneration(msg.request_id, msg.started_by || null);
  if (localGenerationRequestId === msg.request_id) return;
  const selfName = (currentUser.username || "").trim().toLowerCase();
  const startedBy = (msg.started_by || "").trim().toLowerCase();
  if (isLoading && startedBy === selfName) return;
  startPassiveStreamWatch(sessionId, msg.request_id);
}

function handleSessionGenerationEnded(msg) {
  const sessionId = msg.session_id;
  if (!msg.request_id) return;
  if (sessionId && sessionId === currentChatId) {
    stopPassiveStreamWatch();
    clearSessionGeneration(msg.request_id);
  }
  if (sessionId) unmarkSessionGenerating(sessionId);
}

function handleChatRealtimeMessage(msg) {
  if (msg.type === "sessions.index") {
    applySessionsIndexEvent(msg);
    return;
  }

  const sessionId = msg.session_id || currentChatId;
  if (!sessionId) return;

  if (msg.type === "session.state") {
    if (msg.session_id !== currentChatId) return;
    applySessionAccess({
      owner: msg.owner,
      role: msg.role,
      permissions: msg.permissions,
      collab_mode: msg.collab_mode,
    });
    if (shouldSuppressRealtime() || isLoading || isPassiveGenerating) {
      if (msg.settings) applySessionSettings(msg.settings, { remote: true });
      return;
    }
    const localChat = getCurrentChat();
    if (
      localChat &&
      Array.isArray(msg.messages) &&
      msg.messages.length < (localChat.messages?.length || 0)
    ) {
      if (msg.settings) applySessionSettings(msg.settings, { remote: true });
      return;
    }
    if (Array.isArray(msg.messages)) {
      applyRemoteSessionPatch(
        { messages: msg.messages, settings: msg.settings, title: msg.title },
        { session_id: msg.session_id, owner: msg.owner }
      );
    } else if (msg.settings) {
      applySessionSettings(msg.settings, { remote: true });
    }
    return;
  }

  if (msg.type === "joined" && msg.session_id === currentChatId) {
    applySessionAccess({
      owner: msg.owner,
      role: msg.role,
      permissions: msg.permissions,
      collab_mode: msg.collab_mode,
    });
    return;
  }

  if (msg.type === "session.updated" && msg.session_id === currentChatId) {
    applyRemoteSessionPatch(msg.patch, {
      session_id: msg.session_id,
      owner: msg.owner,
      editor: msg.editor,
    });
    return;
  }

  if (msg.type === "chat.user_message" && msg.session_id === currentChatId) {
    applyRemoteUserMessage(msg.message, {
      session_id: msg.session_id,
      owner: msg.owner,
      editor: msg.editor,
    });
    return;
  }

  if (msg.type === "chat.generation.started" && msg.session_id) {
    handleSessionGenerationStarted(msg);
    return;
  }

  if (msg.type === "chat.generation.ended" && msg.session_id) {
    handleSessionGenerationEnded(msg);
    return;
  }

  if (
    msg.type === "chat.status" &&
    msg.session_id &&
    msg.request_id &&
    localGenerationRequestId !== msg.request_id &&
    msg.status &&
    msg.status !== "running"
  ) {
    handleSessionGenerationEnded(msg);
    return;
  }

  if (
    (msg.type === "chat.event" || msg.type === "chat.snapshot") &&
    msg.session_id === currentChatId &&
    msg.request_id &&
    localGenerationRequestId !== msg.request_id
  ) {
    if (!sessionGeneration.requestId) {
      setSessionGeneration(msg.request_id, null);
    }
    startPassiveStreamWatch(sessionId, msg.request_id);
  }
}

function initChatRealtimeSync() {
  window.NexChatSocket?.onEvent?.(handleChatRealtimeMessage);
  window.addEventListener("nexgate:session-settings-changed", () => {
    scheduleBroadcastSessionSettings();
  });
  if (window.__SHARED_CHAT__?.session_id) {
    applySessionAccess(window.__SHARED_CHAT__);
    void loadSession(window.__SHARED_CHAT__.session_id);
  }
}

function isFirstInAssistantTurn(chat, messageIndex) {
  for (let i = messageIndex - 1; i >= 0; i--) {
    const role = chat.messages[i]?.role;
    if (role === "user") return true;
    if (
      role === "assistant" ||
      role === "search" ||
      role === "reasoning" ||
      role === "tool_trace"
    ) {
      return false;
    }
  }
  return true;
}

function cloneSearchState(state) {
  return {
    queries: [...(state?.queries || [])],
    sites: [...(state?.sites || [])],
    urls: [...(state?.urls || [])],
    collapsed: Boolean(state?.collapsed),
    complete: Boolean(state?.complete),
  };
}

function createSearchMessageData() {
  return { queries: [], sites: [], urls: [], collapsed: false, complete: false };
}

const REASONING_COLLAPSED_PREF_KEY = "nexgate_reasoning_cards_collapsed";

function getReasoningCardsDefaultCollapsed() {
  try {
    const stored = localStorage.getItem(REASONING_COLLAPSED_PREF_KEY);
    if (stored === "0" || stored === "false") return false;
    if (stored === "1" || stored === "true") return true;
  } catch (_) {}
  return true;
}

function setReasoningCardsDefaultCollapsed(collapsed) {
  try {
    localStorage.setItem(REASONING_COLLAPSED_PREF_KEY, collapsed ? "1" : "0");
  } catch (_) {}
}

function resolveReasoningCollapsed(state) {
  if (typeof state?.collapsed === "boolean") return state.collapsed;
  return getReasoningCardsDefaultCollapsed();
}

function cloneReasoningState(state) {
  return {
    text: typeof state?.text === "string" ? state.text : "",
    collapsed: resolveReasoningCollapsed(state),
    complete: Boolean(state?.complete),
  };
}

function createReasoningMessageData() {
  return { text: "", collapsed: getReasoningCardsDefaultCollapsed(), complete: false };
}

function cloneToolTraceEntry(entry) {
  return {
    name: String(entry?.name || ""),
    label: String(entry?.label || entry?.name || ""),
    duration_ms: Number(entry?.duration_ms) || 0,
    ok: entry?.ok !== false,
    error: entry?.error ? String(entry.error) : null,
  };
}

function cloneToolTraceState(state) {
  const entries = Array.isArray(state?.entries) ? state.entries : [];
  return {
    entries: entries.map(cloneToolTraceEntry),
    collapsed: Boolean(state?.collapsed),
    complete: Boolean(state?.complete),
  };
}

function createToolTraceMessageData() {
  return { entries: [], collapsed: false, complete: false };
}

function formatToolTraceDuration(ms) {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`;
  return `${Math.round(n)}ms`;
}

function toolTraceSummaryText(entries) {
  const list = Array.isArray(entries) ? entries : [];
  if (!list.length) return "";
  const totalMs = list.reduce((sum, e) => sum + (Number(e.duration_ms) || 0), 0);
  return `${list.length} · ${formatToolTraceDuration(totalMs)}`;
}

function commitAssistantSegment(
  chat,
  text,
  showAvatar = null,
  showActions = false,
  tasksToolUsed = false
) {
  const finalText = stripThinking(text);
  if (!finalText) return null;
  const index = chat.messages.length;
  const createdAt = messageTimestampNow();
  const msg = {
    role: "assistant",
    content: finalText,
    showActions: Boolean(showActions),
    created_at: createdAt,
  };
  if (tasksToolUsed) msg.tasksToolUsed = true;
  chat.messages.push(msg);
  const avatar =
    showAvatar !== null ? showAvatar : isFirstInAssistantTurn(chat, index);
  appendMessage(
    "assistant",
    finalText,
    true,
    index,
    avatar,
    showActions,
    createdAt,
    tasksToolUsed
  );
  pinToolTraceInCurrentTurn(chat);
  saveChats(chat);
  return index;
}

function promoteStreamingAssistantMessage(
  chat,
  text,
  showAvatar = null,
  showActions = false,
  tasksToolUsed = false
) {
  const streamingEl = document.getElementById("streamingMessage");
  const finalText = stripThinking(text);
  if (!streamingEl || !finalText) return null;

  // 確定前に必ず末尾へ移動（ツールトレース等が後ろにあっても安全）
  if (streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
    messagesEl.appendChild(streamingEl);
  }

  const index = chat.messages.length;
  const createdAt = messageTimestampNow();
  const msg = {
    role: "assistant",
    content: finalText,
    showActions: Boolean(showActions),
    created_at: createdAt,
  };
  if (tasksToolUsed) msg.tasksToolUsed = true;
  chat.messages.push(msg);

  const avatarVisible =
    showAvatar !== null ? showAvatar : isFirstInAssistantTurn(chat, index);
  streamingEl.removeAttribute("id");
  streamingEl.dataset.messageIndex = String(index);
  streamingEl.id = `chat-msg-${index}`;
  streamingEl.classList.toggle("message-follow", !avatarVisible);
  if (tasksToolUsed) {
    streamingEl.dataset.tasksToolUsed = "true";
  }

  const contentEl = streamingEl.querySelector(".message-content");
  if (contentEl) {
    window.applyMarkdownContent?.(contentEl, finalText, { finalize: true });
    window.enhanceChatImagesInElement?.(contentEl);
  }

  streamingEl.querySelector(".message-actions")?.remove();
  if (showActions) {
    attachMessageActions(streamingEl, finalText, {
      showTasksLink: Boolean(tasksToolUsed),
      messageIndex: index,
    });
  }

  streamingEl.querySelector(".message-meta")?.remove();
  attachMessageMeta(streamingEl, "assistant", createdAt);

  pinToolTraceInCurrentTurn(chat);
  saveChats(chat);
  return index;
}

function syncSearchMessageToChat(chat, messageIndex, messageEl) {
  const msg = chat.messages[messageIndex];
  if (!msg || msg.role !== "search" || !messageEl?._searchState) return;
  const cover = messageEl.querySelector("#searchProcessCover");
  msg.content = {
    ...cloneSearchState(messageEl._searchState),
    collapsed: Boolean(cover?.classList.contains("is-collapsed")),
    complete: Boolean(cover?.classList.contains("is-complete")),
  };
}

function persistSearchMessage(chat, messageIndex, messageEl = null) {
  const el =
    messageEl ||
    messagesEl.querySelector(`[data-message-index="${messageIndex}"]`);
  if (!el?._searchState || chat.messages[messageIndex]?.role !== "search") return;
  syncSearchMessageToChat(chat, messageIndex, el);
  saveChats(chat);
}

function appendSearchMessageToDom(data, messageIndex, scroll = true, showAvatar = null) {
  hideWelcome();
  messagesEl.classList.remove("hidden");

  const chat = getCurrentChat();
  const avatarVisible =
    showAvatar !== null
      ? showAvatar
      : chat
        ? isFirstInAssistantTurn(chat, messageIndex)
        : true;

  const div = document.createElement("div");
  div.className = `message assistant message-search${avatarVisible ? "" : " message-follow"}`;
  div.dataset.messageIndex = String(messageIndex);

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = "AI";

  const body = document.createElement("div");
  body.className = `message-body has-search-cover${data.collapsed ? " is-cover-collapsed" : ""}`;

  const cover = createSearchCoverElement();
  if (data.complete) {
    const title = cover.querySelector(".search-process-title");
    if (title) title.textContent = "Web検索完了";
    cover.querySelector(".search-process-typing")?.remove();
    cover.classList.add("is-complete");
    if (data.collapsed) {
      cover.classList.add("is-collapsed");
      cover.classList.remove("is-expanded");
    }
  }

  body.appendChild(cover);
  div.appendChild(avatar);
  div.appendChild(body);

  div._searchState = {
    queries: [...data.queries],
    sites: [...data.sites],
    urls: [...data.urls],
  };

  bindSearchCoverToggle(cover, div);
  renderSearchCoverLists(div);
  if (data.complete) updateSearchCoverSummary(cover, div._searchState);

  messagesEl.appendChild(div);
  if (scroll) scrollChatToBottom();
  return div;
}

function createToolTraceCoverElement() {
  const cover = document.createElement("div");
  cover.className = "tool-trace-cover is-expanded";
  cover.id = "toolTraceCover";
  cover.innerHTML = `
    <button type="button" class="tool-trace-toggle" aria-expanded="true">
      <span class="typing tool-trace-typing" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="tool-trace-title"></span>
      <span class="tool-trace-summary"></span>
      <svg class="tool-trace-chevron" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
    </button>
    <div class="tool-trace-body">
      <ul class="tool-trace-list"></ul>
    </div>
  `;
  const title = cover.querySelector(".tool-trace-title");
  if (title) title.textContent = window.t?.("toolTraceTitle") || "ツール";
  return cover;
}

function bindToolTraceCoverToggle(cover, messageEl) {
  const toggle = cover.querySelector(".tool-trace-toggle");
  if (!toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "1";
  toggle.addEventListener("click", () => {
    const collapsed = cover.classList.toggle("is-collapsed");
    cover.classList.toggle("is-expanded", !collapsed);
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const body = messageEl.closest(".message-body");
    if (body) body.classList.toggle("is-cover-collapsed", collapsed);
  });
}

function renderToolTraceList(messageEl) {
  const cover = messageEl?.querySelector("#toolTraceCover");
  const listEl = cover?.querySelector(".tool-trace-list");
  const state = messageEl?._toolTraceState;
  if (!listEl || !state) return;
  listEl.innerHTML = "";
  for (const entry of state.entries) {
    const li = document.createElement("li");
    li.className = `tool-trace-item${entry.ok === false ? " tool-trace-item--error" : ""}`;
    const name = document.createElement("span");
    name.className = "tool-trace-name";
    name.textContent = entry.label || entry.name || "tool";
    const ms = document.createElement("span");
    ms.className = "tool-trace-ms";
    ms.textContent = formatToolTraceDuration(entry.duration_ms);
    li.appendChild(name);
    li.appendChild(ms);
    if (entry.error) {
      const err = document.createElement("span");
      err.className = "tool-trace-error";
      err.textContent = entry.error;
      li.appendChild(err);
    }
    listEl.appendChild(li);
  }
  updateToolTraceCoverSummary(cover, state.entries);
}

function updateToolTraceCoverSummary(cover, entries) {
  const summary = cover?.querySelector(".tool-trace-summary");
  if (summary) summary.textContent = toolTraceSummaryText(entries);
}

function completeToolTraceCover(cover, messageEl, collapsed = true) {
  if (!cover) return;
  const title = cover.querySelector(".tool-trace-title");
  if (title) title.textContent = window.t?.("toolTraceDone") || "ツール完了";
  cover.querySelector(".tool-trace-typing")?.remove();
  cover.classList.add("is-complete");
  if (collapsed) {
    cover.classList.add("is-collapsed");
    cover.classList.remove("is-expanded");
    const toggle = cover.querySelector(".tool-trace-toggle");
    toggle?.setAttribute("aria-expanded", "false");
    messageEl?.querySelector(".message-body")?.classList.add("is-cover-collapsed");
  }
  renderToolTraceList(messageEl);
}

function syncToolTraceMessageToChat(chat, messageIndex, messageEl) {
  const msg = chat.messages[messageIndex];
  if (!msg || msg.role !== "tool_trace" || !messageEl?._toolTraceState) return;
  const cover = messageEl.querySelector("#toolTraceCover");
  msg.content = {
    ...cloneToolTraceState(messageEl._toolTraceState),
    collapsed: Boolean(cover?.classList.contains("is-collapsed")),
    complete: Boolean(cover?.classList.contains("is-complete")),
  };
}

function persistToolTraceMessage(chat, messageIndex, messageEl = null) {
  const el =
    messageEl ||
    messagesEl.querySelector(`[data-message-index="${messageIndex}"]`);
  if (!el?._toolTraceState || chat.messages[messageIndex]?.role !== "tool_trace") return;
  syncToolTraceMessageToChat(chat, messageIndex, el);
  saveChats(chat);
}

function appendToolTraceMessageToDom(data, messageIndex, scroll = true, showAvatar = null) {
  hideWelcome();
  messagesEl.classList.remove("hidden");

  const chat = getCurrentChat();
  const avatarVisible =
    showAvatar !== null
      ? showAvatar
      : chat
        ? isFirstInAssistantTurn(chat, messageIndex)
        : true;

  const div = document.createElement("div");
  div.className = `message assistant message-tool-trace${avatarVisible ? "" : " message-follow"}`;
  div.dataset.messageIndex = String(messageIndex);

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = "AI";

  const body = document.createElement("div");
  body.className = `message-body has-tool-trace-cover${data.collapsed ? " is-cover-collapsed" : ""}`;

  const cover = createToolTraceCoverElement();
  if (data.complete) {
    completeToolTraceCover(cover, div, data.collapsed);
  }

  body.appendChild(cover);
  div.appendChild(avatar);
  div.appendChild(body);

  div._toolTraceState = {
    entries: (data.entries || []).map(cloneToolTraceEntry),
  };

  bindToolTraceCoverToggle(cover, div);
  renderToolTraceList(div);
  if (data.complete) updateToolTraceCoverSummary(cover, div._toolTraceState.entries);

  messagesEl.appendChild(div);
  if (scroll) scrollChatToBottom();
  return div;
}

function findToolTraceIndexInCurrentTurn(chat) {
  const msgs = chat?.messages || [];
  const start = findLastUserMessageIndex(msgs) + 1;
  let found = -1;
  for (let i = start; i < msgs.length; i += 1) {
    if (msgs[i]?.role === "tool_trace") found = i;
  }
  return found;
}

function normalizeAllToolTracesInChat(chat) {
  if (!toolTraceEnabled() || !chat?.messages?.length) return;
  const msgs = chat.messages;
  let turnStart = 0;
  while (turnStart < msgs.length) {
    if (msgs[turnStart]?.role !== "user") {
      turnStart += 1;
      continue;
    }
    let turnEnd = turnStart + 1;
    while (turnEnd < msgs.length && msgs[turnEnd]?.role !== "user") {
      turnEnd += 1;
    }
    let toolIdx = -1;
    for (let j = turnStart + 1; j < turnEnd; j += 1) {
      if (msgs[j]?.role === "tool_trace") toolIdx = j;
    }
    if (toolIdx >= 0 && toolIdx !== turnEnd - 1) {
      const [msg] = msgs.splice(toolIdx, 1);
      msgs.splice(turnEnd - 1, 0, msg);
    }
    turnStart = turnEnd;
  }
}

function remapMessageIndicesAfterMove(fromIndex, toIndex) {
  messagesEl
    .querySelectorAll(
      ".message[data-message-index], .message-reasoning[data-message-index], .message-search[data-message-index], .message-tool-trace[data-message-index]"
    )
    .forEach((el) => {
      let i = Number(el.dataset.messageIndex);
      if (!Number.isFinite(i)) return;
      if (i === fromIndex) {
        el.dataset.messageIndex = String(toIndex);
        return;
      }
      if (fromIndex < toIndex) {
        if (i > fromIndex && i <= toIndex) {
          el.dataset.messageIndex = String(i - 1);
        }
      } else if (fromIndex > toIndex) {
        if (i >= toIndex && i < fromIndex) {
          el.dataset.messageIndex = String(i + 1);
        }
      }
    });
}

function repositionToolTraceDomElement(toolTraceEl) {
  if (!toolTraceEl || !messagesEl) return;
  const streaming = document.getElementById("streamingMessage");
  if (streaming?.parentNode === messagesEl) {
    streaming.insertAdjacentElement("afterend", toolTraceEl);
    return;
  }
  const scrollBtn = document.getElementById("chatScrollToBottomBtn");
  if (scrollBtn?.parentNode === messagesEl) {
    messagesEl.insertBefore(toolTraceEl, scrollBtn);
    return;
  }
  messagesEl.appendChild(toolTraceEl);
}

function pinToolTraceInCurrentTurn(chat, toolTraceIndex = null, toolTraceEl = null) {
  if (!toolTraceEnabled() || !chat) {
    return { index: toolTraceIndex, el: toolTraceEl };
  }
  let idx =
    Number.isFinite(Number(toolTraceIndex)) && chat.messages[toolTraceIndex]?.role === "tool_trace"
      ? Number(toolTraceIndex)
      : findToolTraceIndexInCurrentTurn(chat);
  if (idx < 0) return { index: toolTraceIndex, el: toolTraceEl };

  const targetIndex = chat.messages.length - 1;
  if (idx !== targetIndex) {
    const fromIndex = idx;
    const [msg] = chat.messages.splice(fromIndex, 1);
    chat.messages.push(msg);
    const newIndex = chat.messages.length - 1;
    remapMessageIndicesAfterMove(fromIndex, newIndex);
    idx = newIndex;
  }

  const el =
    toolTraceEl ||
    messagesEl.querySelector(`.message-tool-trace[data-message-index="${idx}"]`);
  if (el) repositionToolTraceDomElement(el);
  return { index: idx, el: el || toolTraceEl };
}

function syncPinnedToolTraceSlot(chat, slot) {
  if (!toolTraceEnabled() || !slot?.el) return slot;
  return pinToolTraceInCurrentTurn(chat, slot.index, slot.el);
}

function ensureToolTraceMessageSlot(chat, showAvatar = null) {
  const state = createToolTraceMessageData();
  const index = chat.messages.length;
  chat.messages.push({ role: "tool_trace", content: cloneToolTraceState(state) });
  const el = appendToolTraceMessageToDom(
    chat.messages[index].content,
    index,
    true,
    showAvatar
  );
  const pinned = pinToolTraceInCurrentTurn(chat, index, el);
  saveChats(chat);
  return pinned;
}

function handleToolTraceEvent(messageEl, trace) {
  const idx = Number(messageEl?.dataset.messageIndex);
  if (!messageEl || !trace) {
    return { index: Number.isFinite(idx) ? idx : null, el: messageEl };
  }
  if (!messageEl._toolTraceState) {
    messageEl._toolTraceState = { entries: [] };
  }
  messageEl._toolTraceState.entries.push(cloneToolTraceEntry(trace));
  renderToolTraceList(messageEl);
  const chat = getCurrentChat();
  let slot = { index: idx, el: messageEl };
  if (chat && Number.isFinite(idx)) {
    slot = pinToolTraceInCurrentTurn(chat, idx, messageEl);
  }
  scrollChatToBottom();
  return slot;
}

function finalizeAllActiveToolTraceCovers() {
  messagesEl.querySelectorAll(".message-tool-trace").forEach((messageEl) => {
    const cover = messageEl.querySelector("#toolTraceCover");
    if (cover && !cover.classList.contains("is-complete")) {
      completeToolTraceCover(cover, messageEl, true);
      const idx = Number(messageEl.dataset.messageIndex);
      if (Number.isFinite(idx)) {
        persistToolTraceMessage(getCurrentChat(), idx, messageEl);
      }
    }
  });
}

function createReasoningCoverElement(collapsed = true) {
  const cover = document.createElement("div");
  cover.className = `reasoning-process-cover${collapsed ? " is-collapsed" : " is-expanded"}`;
  cover.id = "reasoningProcessCover";
  cover.innerHTML = `
    <button type="button" class="reasoning-process-toggle" aria-expanded="${collapsed ? "false" : "true"}">
      <span class="typing reasoning-process-typing" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="reasoning-process-title">推論中</span>
      <span class="reasoning-process-summary"></span>
      <svg class="reasoning-process-chevron" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
    </button>
    <div class="reasoning-process-body">
      <div class="reasoning-process-text"></div>
    </div>
  `;
  return cover;
}

function bindReasoningCoverToggle(cover, messageEl) {
  const toggle = cover.querySelector(".reasoning-process-toggle");
  if (!toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "1";
  toggle.addEventListener("click", () => {
    const collapsed = !cover.classList.contains("is-collapsed");
    setReasoningCoverCollapsed(cover, messageEl, collapsed);
    setReasoningCardsDefaultCollapsed(collapsed);
    const chat = getCurrentChat();
    const idx = messageEl.dataset.messageIndex;
    if (chat && idx !== undefined) {
      persistReasoningMessage(chat, Number(idx), messageEl);
    }
  });
}

function setReasoningCoverCollapsed(cover, messageEl, collapsed) {
  if (!cover) return;
  const body = messageEl?.querySelector(".message-body");
  const toggle = cover.querySelector(".reasoning-process-toggle");
  cover.classList.toggle("is-collapsed", collapsed);
  cover.classList.toggle("is-expanded", !collapsed);
  toggle?.setAttribute("aria-expanded", String(!collapsed));
  body?.classList.toggle("is-cover-collapsed", collapsed);
}

function updateReasoningCoverSummary(cover, text) {
  const summary = cover?.querySelector(".reasoning-process-summary");
  if (!summary) return;
  const trimmed = (text || "").trim();
  if (!trimmed) {
    summary.textContent = "";
    return;
  }
  const oneLine = trimmed.replace(/\s+/g, " ");
  summary.textContent =
    oneLine.length > 72 ? `${oneLine.slice(0, 72)}…` : oneLine;
}

function renderReasoningCoverText(messageEl) {
  const cover = messageEl?.querySelector("#reasoningProcessCover");
  const textEl = cover?.querySelector(".reasoning-process-text");
  if (!textEl) return;
  const text = messageEl._reasoningState?.text || "";
  textEl.textContent = text;
  updateReasoningCoverSummary(cover, text);
  scrollChatToBottom();
}

function completeReasoningCover(cover, messageEl, collapsed = true) {
  if (!cover) return;
  const title = cover.querySelector(".reasoning-process-title");
  if (title) {
    title.textContent = "";
    title.classList.add("hidden");
    title.setAttribute("aria-hidden", "true");
  }
  cover.querySelector(".reasoning-process-typing")?.remove();
  cover.classList.add("is-complete");
  renderReasoningCoverText(messageEl);
  setReasoningCoverCollapsed(cover, messageEl, collapsed);
}

function syncReasoningMessageToChat(chat, messageIndex, messageEl) {
  const msg = chat.messages[messageIndex];
  if (!msg || msg.role !== "reasoning" || !messageEl?._reasoningState) return;
  const cover = messageEl.querySelector("#reasoningProcessCover");
  msg.content = {
    ...cloneReasoningState(messageEl._reasoningState),
    collapsed: Boolean(cover?.classList.contains("is-collapsed")),
    complete: Boolean(cover?.classList.contains("is-complete")),
  };
}

function persistReasoningMessage(chat, messageIndex, messageEl = null) {
  const el =
    messageEl ||
    messagesEl.querySelector(`[data-message-index="${messageIndex}"]`);
  if (!el?._reasoningState || chat.messages[messageIndex]?.role !== "reasoning") return;
  syncReasoningMessageToChat(chat, messageIndex, el);
  saveChats(chat);
}

function finalizeReasoningIfOpen(reasoningMessageEl, chat, reasoningMessageIndex) {
  if (!reasoningMessageEl || reasoningMessageIndex === null || !chat) return;
  const rCover = reasoningMessageEl.querySelector("#reasoningProcessCover");
  if (!rCover || rCover.classList.contains("is-complete")) return;
  completeReasoningCover(rCover, reasoningMessageEl, rCover.classList.contains("is-collapsed"));
  syncReasoningMessageToChat(chat, reasoningMessageIndex, reasoningMessageEl);
}

function appendReasoningMessageToDom(data, messageIndex, scroll = true, showAvatar = null) {
  hideWelcome();
  messagesEl.classList.remove("hidden");

  const chat = getCurrentChat();
  const avatarVisible =
    showAvatar !== null
      ? showAvatar
      : chat
        ? isFirstInAssistantTurn(chat, messageIndex)
        : true;

  const div = document.createElement("div");
  div.className = `message assistant message-reasoning${avatarVisible ? "" : " message-follow"}`;
  div.dataset.messageIndex = String(messageIndex);

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = "AI";

  const collapsed = resolveReasoningCollapsed(data);
  const body = document.createElement("div");
  body.className = `message-body has-reasoning-cover${collapsed ? " is-cover-collapsed" : ""}`;

  const cover = createReasoningCoverElement(collapsed);
  body.appendChild(cover);
  div.appendChild(avatar);
  div.appendChild(body);

  div._reasoningState = { text: data.text || "" };
  bindReasoningCoverToggle(cover, div);
  renderReasoningCoverText(div);
  if (data.complete) {
    completeReasoningCover(cover, div, collapsed);
  } else {
    setReasoningCoverCollapsed(cover, div, collapsed);
  }

  messagesEl.appendChild(div);
  if (scroll) scrollChatToBottom();
  return div;
}

function ensureReasoningMessageSlot(chat, showAvatar = null) {
  const state = createReasoningMessageData();
  const index = chat.messages.length;
  chat.messages.push({ role: "reasoning", content: cloneReasoningState(state) });
  const el = appendReasoningMessageToDom(
    chat.messages[index].content,
    index,
    true,
    showAvatar
  );
  pinToolTraceInCurrentTurn(chat);
  const finalIndex = Number(el.dataset.messageIndex);
  saveChats(chat);
  return { index: Number.isFinite(finalIndex) ? finalIndex : index, el };
}

function handleReasoningStreamEvent(messageEl, event) {
  if (!messageEl || !event?.type) return;
  if (!messageEl._reasoningState) {
    messageEl._reasoningState = { text: "" };
  }
  const cover = messageEl.querySelector("#reasoningProcessCover");
  if (event.type === "delta" && event.text) {
    messageEl._reasoningState.text += event.text;
    renderReasoningCoverText(messageEl);
  }
  if (event.type === "done" && cover) {
    completeReasoningCover(cover, messageEl, cover.classList.contains("is-collapsed"));
  }
}

function createTasksNavLink() {
  if (window.__USER__?.tasks_enabled !== true) return null;
  const link = document.createElement("a");
  link.href = "/tasks";
  link.className = "message-action-tasks-link";
  link.textContent =
    typeof window.t === "function" ? window.t("chatTasksLink") : "TASKSページに移動する";
  link.addEventListener("click", (e) => {
    e.preventDefault();
    if (window.NexRouter?.navigate) {
      window.NexRouter.navigate("/tasks");
    } else {
      window.location.href = "/tasks";
    }
  });
  return link;
}

function bindLongPressAction(button, onLongPress, { durationMs = 500 } = {}) {
  let timer = null;
  let longPressFired = false;

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    button.classList.remove("is-long-pressing");
  };

  button.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || button.disabled) return;
    longPressFired = false;
    button.classList.add("is-long-pressing");
    timer = setTimeout(() => {
      longPressFired = true;
      clearTimer();
      onLongPress();
    }, durationMs);
  });

  button.addEventListener("pointerup", clearTimer);
  button.addEventListener("pointerleave", clearTimer);
  button.addEventListener("pointercancel", clearTimer);

  button.addEventListener("click", (e) => {
    if (longPressFired) {
      e.preventDefault();
      e.stopPropagation();
      longPressFired = false;
    }
  });
}

function findUserMessageIndexForAssistant(chat, assistantMessageIndex) {
  const idx = Number(assistantMessageIndex);
  if (!chat || !Number.isFinite(idx) || idx < 0 || chat.messages[idx]?.role !== "assistant") {
    return null;
  }
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (chat.messages[i]?.role === "user") return i;
  }
  return null;
}

function createMessageActions(plainText, { showTasksLink = false, messageIndex = null } = {}) {
  const actions = document.createElement("div");
  actions.className = "message-actions";

  const goodBtn = document.createElement("button");
  goodBtn.type = "button";
  goodBtn.className = "message-action-btn";
  goodBtn.dataset.action = "good";
  goodBtn.setAttribute("aria-label", "良い回答");
  goodBtn.innerHTML = ICON_THUMB_UP;

  const badBtn = document.createElement("button");
  badBtn.type = "button";
  badBtn.className = "message-action-btn";
  badBtn.dataset.action = "bad";
  badBtn.setAttribute("aria-label", "悪い回答");
  badBtn.innerHTML = ICON_THUMB_DOWN;

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "message-action-btn";
  copyBtn.dataset.action = "copy";
  copyBtn.setAttribute("aria-label", "コピー");
  copyBtn.innerHTML = ICON_COPY;

  goodBtn.addEventListener("click", () => {
    goodBtn.classList.toggle("is-active");
    if (goodBtn.classList.contains("is-active")) {
      badBtn.classList.remove("is-active");
    }
    sendMessageFeedback({ rating: 1, messageIndex, plainText });
  });

  badBtn.addEventListener("click", () => {
    badBtn.classList.toggle("is-active");
    if (badBtn.classList.contains("is-active")) {
      goodBtn.classList.remove("is-active");
    }
    sendMessageFeedback({ rating: -1, messageIndex, plainText });
  });

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(plainText);
      copyBtn.classList.add("is-copied");
      copyBtn.setAttribute("aria-label", "コピーしました");
      setTimeout(() => {
        copyBtn.classList.remove("is-copied");
        copyBtn.setAttribute("aria-label", "コピー");
      }, 2000);
    } catch (e) {}
  });

  actions.append(goodBtn, badBtn);
  if (showTasksLink) {
    const tasksLink = createTasksNavLink();
    if (tasksLink) actions.append(tasksLink);
  }
  actions.append(copyBtn);

  // Report button
  const reportBtn = document.createElement("button");
  reportBtn.type = "button";
  reportBtn.className = "message-action-btn";
  reportBtn.dataset.action = "report";
  reportBtn.setAttribute("aria-label", "問題を報告");
  reportBtn.innerHTML = ICON_FLAG;
  reportBtn.addEventListener("click", () => {
    openReportOverlay();
  });
  actions.append(reportBtn);

  if (messageIndex !== null) {
    const regenBtn = document.createElement("button");
    regenBtn.type = "button";
    regenBtn.className = "message-action-btn";
    regenBtn.dataset.action = "regenerate";
    regenBtn.setAttribute("aria-label", "長押しで再生成");
    regenBtn.innerHTML = ICON_REGENERATE;
    const assistantIdx = Number(messageIndex);
    bindLongPressAction(regenBtn, () => {
      const chat = getCurrentChat();
      const userIdx = findUserMessageIndexForAssistant(chat, assistantIdx);
      if (userIdx !== null) {
        void regenerateFromMessage(userIdx);
      }
    });
    actions.append(regenBtn);
  }

  return actions;
}

function createUserMessageActions(messageIndex) {
  const actions = document.createElement("div");
  actions.className = "message-actions message-actions--user";

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "message-action-btn";
  deleteBtn.setAttribute("aria-label", "以降の会話を削除");
  deleteBtn.innerHTML = ICON_TRASH;
  const idx = Number(messageIndex);
  deleteBtn.addEventListener("click", () => {
    void deleteFromMessage(idx);
  });

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "message-action-btn";
  editBtn.setAttribute("aria-label", "編集");
  editBtn.innerHTML = ICON_EDIT;
  editBtn.addEventListener("click", () => editFromMessage(idx));

  const regenBtn = document.createElement("button");
  regenBtn.type = "button";
  regenBtn.className = "message-action-btn";
  regenBtn.setAttribute("aria-label", "再生成");
  regenBtn.innerHTML = ICON_REGENERATE;
  regenBtn.addEventListener("click", () => regenerateFromMessage(idx));

  actions.append(deleteBtn, editBtn, regenBtn);
  return actions;
}

function attachUserMessageActions(messageEl, messageIndex) {
  const body = messageEl.querySelector(".message-body");
  if (!body || body.querySelector(".message-actions")) return;
  body.appendChild(createUserMessageActions(messageIndex));
}

function resolveUserMessageIndex(messageIndex) {
  const idx = Number(messageIndex);
  if (!Number.isFinite(idx)) return null;
  const chat = getCurrentChat();
  if (!chat || idx < 0 || idx >= chat.messages.length) return null;
  if (chat.messages[idx]?.role !== "user") return null;
  return { chat, idx };
}

async function deleteFromMessage(messageIndex) {
  cancelUserMessageEdit();
  if (isLoading) return;
  const resolved = resolveUserMessageIndex(messageIndex);
  if (!resolved) return;
  const { chat, idx } = resolved;
  const ok = await window.NexNotify?.confirm(
    "このメッセージと、それ以降の会話をすべて削除しますか？",
    { danger: true, confirmLabel: "削除" }
  );
  if (!ok) return;

  await abortSessionGenerationIfNeeded();
  markLocalMutation();
  chat.messages = chat.messages.slice(0, idx);
  saveChats(chat);
  broadcastSessionMessagesReplace(chat);
  if (shouldUpdateSessionHistory(chat)) renderHistory();

  if (chat.messages.length === 0) {
    showWelcome();
    return;
  }
  renderMessages();
}

function clearEditingMessageHighlight() {
  messagesEl
    ?.querySelectorAll(".message.user.is-editing")
    .forEach((el) => el.classList.remove("is-editing"));
}

function highlightEditingMessage(idx) {
  clearEditingMessageHighlight();
  messagesEl
    ?.querySelector(`.message.user[data-message-index="${idx}"]`)
    ?.classList.add("is-editing");
}

function applyUserMessageEditChrome() {
  const editing = Boolean(activeUserMessageEdit);
  chatMain?.classList.toggle("chat-message-edit-active", editing);
  messageEditNotice?.classList.toggle("hidden", !editing);
  if (messageInput) {
    if (!messageInput.dataset.defaultPlaceholder) {
      messageInput.dataset.defaultPlaceholder = messageInput.placeholder;
    }
    messageInput.placeholder = editing
      ? "編集内容を入力..."
      : messageInput.dataset.defaultPlaceholder;
  }
  if (editing && messageEditNoticeText && activeUserMessageEdit) {
    const chat = getCurrentChat();
    const hasFollowing =
      (chat?.messages.length ?? 0) > activeUserMessageEdit.idx + 1;
    messageEditNoticeText.textContent = hasFollowing
      ? "メッセージを編集中。このメッセージより後の会話は送信時に削除されます。"
      : "メッセージを編集中。";
    highlightEditingMessage(activeUserMessageEdit.idx);
  } else {
    clearEditingMessageHighlight();
  }
  updateSendBtn();
}

function cancelUserMessageEdit(options = {}) {
  if (!activeUserMessageEdit) return;
  activeUserMessageEdit = null;
  if (messageInput) {
    messageInput.value = "";
    autoResize();
  }
  applyUserMessageEditChrome();
  if (options.rerender) {
    renderMessages();
  }
}

function startUserMessageEdit(idx) {
  if (isLoading || !messageInput) return;
  cancelUserMessageEdit();

  const chat = getCurrentChat();
  if (!chat?.messages[idx]) return;

  const text = formatUserDisplayContent(chat.messages[idx].content);
  activeUserMessageEdit = { idx, originalText: text };
  messageInput.value = text;
  autoResize();
  applyUserMessageEditChrome();
  window.chatMessageScroll?.scrollToMessage?.(idx);
  messageInput.focus();
  messageInput.setSelectionRange(text.length, text.length);
}

async function commitUserMessageEdit(text) {
  if (!activeUserMessageEdit || isLoading) return;

  const { idx, originalText } = activeUserMessageEdit;
  const newText = (text ?? messageInput?.value ?? "").trim();

  if (!newText || newText === originalText.trim()) {
    cancelUserMessageEdit();
    return;
  }

  const resolved = resolveUserMessageIndex(idx);
  if (!resolved) return;
  const { chat } = resolved;

  const hasFollowing = chat.messages.length > idx + 1;
  if (hasFollowing) {
    const editOk = await window.NexNotify?.confirm(
      "このメッセージ以降の会話を削除し、編集した内容で再送信しますか？",
      { danger: true, confirmLabel: "送信" }
    );
    if (!editOk) return;
  }

  activeUserMessageEdit = null;
  if (messageInput) {
    messageInput.value = "";
    autoResize();
  }
  applyUserMessageEditChrome();

  await abortSessionGenerationIfNeeded();
  markLocalMutation();
  chat.messages = chat.messages.slice(0, idx + 1);
  chat.messages[idx] = {
    role: "user",
    content: newText,
    created_at: messageTimestampNow(),
  };
  saveChats(chat);
  broadcastSessionMessagesReplace(chat);
  if (shouldUpdateSessionHistory(chat)) renderHistory();
  renderMessages();

  await requestAssistantReply(chat);
}

function editFromMessage(messageIndex) {
  if (isLoading) return;
  const resolved = resolveUserMessageIndex(messageIndex);
  if (!resolved) return;
  startUserMessageEdit(resolved.idx);
}

async function regenerateFromMessage(messageIndex) {
  if (isLoading) return;
  const resolved = resolveUserMessageIndex(messageIndex);
  if (!resolved) return;
  const { chat, idx } = resolved;

  chat.messages = chat.messages.slice(0, idx + 1);
  saveChats(chat);
  renderMessages();
  await requestAssistantReply(chat);
}

function attachMessageActions(
  messageEl,
  plainText,
  { showTasksLink = false, messageIndex = null } = {}
) {
  let body = messageEl.querySelector(".message-body");
  if (!body) {
    const content = messageEl.querySelector(".message-content");
    if (!content) return;
    body = document.createElement("div");
    body.className = "message-body";
    content.parentNode.insertBefore(body, content);
    body.appendChild(content);
  }
  if (body.querySelector(".message-actions")) return;
  body.appendChild(createMessageActions(plainText, { showTasksLink, messageIndex }));
}

function sendMessageFeedback({ rating, messageIndex, plainText }) {
  try {
    const sessionId = currentChatId || "";
    const variant = window.__AB_VARIANT__?.response_style || null;
    const payload = {
      rating,
      session_id: sessionId,
      message_index: messageIndex == null ? -1 : messageIndex,
      variant,
    };
    fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    }).catch(() => {});
  } catch (e) {}
}

function appendMessage(
  role,
  content,
  scroll = true,
  messageIndex = null,
  showAvatar = true,
  showActions = true,
  createdAt = null,
  tasksToolUsed = false
) {
  hideWelcome();
  messagesEl.classList.remove("hidden");

  const div = document.createElement("div");
  const followClass = role === "assistant" && !showAvatar ? " message-follow" : "";
  div.className = `message ${role}${followClass}`;
  if (messageIndex !== null) {
    div.dataset.messageIndex = String(messageIndex);
    div.id = `chat-msg-${messageIndex}`;
  }

  if (role === "assistant") {
    div.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-body">
        <div class="message-content markdown-body"></div>
      </div>
    `;
    if (tasksToolUsed) {
      div.dataset.tasksToolUsed = "true";
    }
    if (showActions) {
      attachMessageActions(div, content, {
        showTasksLink: Boolean(tasksToolUsed),
        messageIndex,
      });
    }
  } else {
    div.innerHTML = `
      <div class="message-avatar">You</div>
      <div class="message-body">
        <div class="message-content"></div>
      </div>
    `;
    window.populateUserMessageContent?.(div.querySelector(".message-content"), content);
    if (messageIndex !== null) {
      attachUserMessageActions(div, messageIndex);
    }
  }

  if (createdAt) {
    attachMessageMeta(div, role, createdAt);
  }

  messagesEl.appendChild(div);

  if (role === "assistant") {
    const contentEl = div.querySelector(".message-content");
    if (typeof content === "string" && content.trim()) {
      window.applyMarkdownContent?.(contentEl, content);
    }
    window.enhanceChatImagesInElement?.(contentEl);
  }

  if (scroll) {
    scrollChatToBottom(role === "user");
  }
}

function removeStreamingMessage() {
  const streaming = document.getElementById("streamingMessage");
  const contentEl = streaming?.querySelector(".message-content");
  if (contentEl) window.cancelStreamingMarkdown?.(contentEl);
  streaming?.remove();
}

function renderStreamingWaitingHtml(text = "回答を生成しています") {
  const label = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `
    <div class="stream-waiting">
      <span class="typing" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="stream-waiting-text">${label}</span>
    </div>
  `;
}

function renderImageGenerationWaitingHtml(label) {
  const safeLabel = escapeHtmlText(
    label || window.t?.("imageGenerationInProgress") || "画像を生成しています…"
  );
  return `
    <div class="image-gen-waiting" role="status" aria-live="polite" aria-busy="true">
      <div class="image-gen-waiting__skeleton" aria-hidden="true"></div>
      <div class="stream-waiting image-gen-waiting__status">
        <span class="typing" aria-hidden="true"><span></span><span></span><span></span></span>
        <span class="stream-waiting-text">${safeLabel}</span>
      </div>
    </div>
  `;
}

function updateImageGenerationPreface(contentEl, segmentText) {
  if (!contentEl) return;
  const preface = stripThinking(segmentText || "").trim();
  let prefaceEl = contentEl.querySelector(".image-gen-preface");
  if (!preface) {
    prefaceEl?.remove();
    return;
  }
  if (!prefaceEl) {
    prefaceEl = document.createElement("div");
    prefaceEl.className = "image-gen-preface markdown-body";
    contentEl.insertBefore(prefaceEl, contentEl.firstChild);
  }
  void window.applyMarkdownContent?.(prefaceEl, preface);
}

function showImageGenerationWaiting(contentEl, segmentText, label) {
  if (!contentEl) return;
  contentEl.classList.add("is-image-generating");
  contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
  updateImageGenerationPreface(contentEl, segmentText);
  if (!contentEl.querySelector(".image-gen-waiting")) {
    contentEl.insertAdjacentHTML("beforeend", renderImageGenerationWaitingHtml(label));
  } else {
    const labelEl = contentEl.querySelector(".image-gen-waiting__status .stream-waiting-text");
    const nextLabel =
      label || window.t?.("imageGenerationInProgress") || "画像を生成しています…";
    if (labelEl && labelEl.textContent !== nextLabel) {
      labelEl.textContent = nextLabel;
    }
  }
}

function escapeHtmlText(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function createSearchCoverElement() {
  const cover = document.createElement("div");
  cover.className = "search-process-cover is-expanded";
  cover.id = "searchProcessCover";
  cover.innerHTML = `
    <button type="button" class="search-process-toggle" aria-expanded="true">
      <span class="typing search-process-typing" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="search-process-title">Webを検索中</span>
      <span class="search-process-summary"></span>
      <svg class="search-process-chevron" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
    </button>
    <div class="search-process-body">
      <section class="search-process-section">
        <h4 class="search-process-label">検索ワード</h4>
        <ul class="search-process-list search-query-list"></ul>
      </section>
      <section class="search-process-section">
        <h4 class="search-process-label">検索サイト</h4>
        <ul class="search-process-list search-site-list"></ul>
      </section>
      <section class="search-process-section">
        <h4 class="search-process-label">候補URL</h4>
        <ul class="search-process-list search-url-list"></ul>
      </section>
    </div>
  `;
  return cover;
}

function resolveSearchCoverState(stateOrMessageEl) {
  if (!stateOrMessageEl) {
    return { queries: [], sites: [], urls: [] };
  }
  if (stateOrMessageEl._searchState) {
    return stateOrMessageEl._searchState;
  }
  if (
    Array.isArray(stateOrMessageEl.queries) ||
    Array.isArray(stateOrMessageEl.sites) ||
    Array.isArray(stateOrMessageEl.urls)
  ) {
    return stateOrMessageEl;
  }
  return getSearchCoverState(stateOrMessageEl);
}

function updateSearchCoverSummary(cover, stateOrMessageEl) {
  const summary = cover?.querySelector(".search-process-summary");
  if (!summary) return;
  const state = resolveSearchCoverState(stateOrMessageEl);
  const queries = state.queries || [];
  const sites = state.sites || [];
  const urls = state.urls || [];
  const parts = [];
  if (urls.length) parts.push(`結果 ${urls.length}件`);
  else if (queries.length) parts.push(`クエリ ${queries.length}件`);
  if (sites.length && !urls.length) parts.push(`サイト ${sites.length}件`);
  summary.textContent = parts.length ? parts.join(" · ") : "";
}

function setSearchCoverCollapsed(cover, messageEl, collapsed) {
  if (!cover) return;
  const body = messageEl?.querySelector(".message-body");
  const toggle = cover.querySelector(".search-process-toggle");
  cover.classList.toggle("is-collapsed", collapsed);
  cover.classList.toggle("is-expanded", !collapsed);
  toggle?.setAttribute("aria-expanded", String(!collapsed));
  body?.classList.toggle("is-cover-collapsed", collapsed);
}

function collapseSearchCover(cover, messageEl) {
  if (!cover) return;
  const title = cover.querySelector(".search-process-title");
  if (title) title.textContent = "Web検索完了";
  cover.querySelector(".search-process-typing")?.remove();
  cover.classList.remove("is-active");
  updateSearchCoverSummary(cover, getSearchCoverState(messageEl));
  cover.classList.add("is-complete");
  setSearchCoverCollapsed(cover, messageEl, true);
}

function finalizeSearchCoverOnStop(messageEl, { stopped = false } = {}) {
  if (!messageEl) return;
  const cover = messageEl.querySelector("#searchProcessCover");
  if (!cover || cover.classList.contains("is-complete")) return;

  const title = cover.querySelector(".search-process-title");
  if (title) title.textContent = stopped ? "Web検索を停止" : "Web検索完了";
  cover.querySelector(".search-process-typing")?.remove();
  cover.classList.remove("is-active");
  cover.querySelectorAll(".search-process-placeholder").forEach((node) => node.remove());
  updateSearchCoverSummary(cover, messageEl);
  cover.classList.add("is-complete");
  setSearchCoverCollapsed(cover, messageEl, true);

  const chat = getCurrentChat();
  const idx = messageEl.dataset.messageIndex;
  if (chat && idx !== undefined && messageEl._searchState) {
    syncSearchMessageToChat(chat, Number(idx), messageEl);
    saveChats(chat);
  }
}

function finalizeAllActiveSearchCovers(options = {}) {
  messagesEl?.querySelectorAll("#searchProcessCover").forEach((cover) => {
    if (cover.classList.contains("is-complete")) return;
    const messageEl = cover.closest(".message");
    if (messageEl) finalizeSearchCoverOnStop(messageEl, options);
  });
}

function bindSearchCoverToggle(cover, messageEl) {
  const toggle = cover.querySelector(".search-process-toggle");
  if (!toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "1";
  toggle.addEventListener("click", () => {
    setSearchCoverCollapsed(cover, messageEl, !cover.classList.contains("is-collapsed"));
    const chat = getCurrentChat();
    const idx = messageEl.dataset.messageIndex;
    if (chat && idx !== undefined) {
      persistSearchMessage(chat, Number(idx), messageEl);
    }
  });
}

function getSearchCoverState(messageEl) {
  if (!messageEl._searchState) {
    messageEl._searchState = { queries: [], sites: [], urls: [] };
  }
  return messageEl._searchState;
}

function clearSearchPlaceholder(list) {
  list?.querySelector(".search-process-placeholder")?.remove();
}

function isSearchPrefaceOnly(text) {
  const t = String(text || "").trim();
  if (!t || t.length > 160) return false;
  return (
    /最新(の)?情報|確認します|調べます|検索します|お調べします|変わるため/.test(t) &&
    !/\*\*[^*]+\*\*/.test(t) &&
    !/https?:\/\//.test(t)
  );
}

function appendSearchQueryRow(list, query, provider) {
  if (!list) return;
  clearSearchPlaceholder(list);
  const li = document.createElement("li");
  li.className = "search-query-item";
  li.innerHTML = `<span class="search-query-text">${escapeHtmlText(query)}</span>${provider ? ` <span class="search-query-provider">${escapeHtmlText(provider)}</span>` : ""}`;
  list.appendChild(li);
}

function appendSearchSiteRow(list, site, provider) {
  if (!list) return;
  clearSearchPlaceholder(list);
  const li = document.createElement("li");
  li.className = "search-site-item";
  li.innerHTML = `<span class="search-site-dot"></span>${escapeHtmlText(site)}<span class="search-site-provider">${escapeHtmlText(provider)}</span>`;
  list.appendChild(li);
}

function appendSearchUrlRow(list, hit) {
  if (!list) return;
  clearSearchPlaceholder(list);
  const li = document.createElement("li");
  li.className = "search-url-item";
  const href = escapeHtmlText(hit.url);
  const title = escapeHtmlText(hit.title || hit.url);
  const site = hit.site ? `<span class="search-url-site">${escapeHtmlText(hit.site)}</span>` : "";
  const dateLabel = hit.dateLabel
    ? `<span class="search-url-date">${escapeHtmlText(hit.dateLabel)}</span>`
    : "";
  li.innerHTML = `<a href="${href}" target="_blank" rel="noopener noreferrer">${title}</a>${site}${dateLabel}`;
  list.appendChild(li);
}

function renderSearchCoverLists(messageEl) {
  const cover = messageEl?.querySelector("#searchProcessCover");
  if (!cover) return;
  const state = getSearchCoverState(messageEl);

  const queryList = cover.querySelector(".search-query-list");
  const siteList = cover.querySelector(".search-site-list");
  const urlList = cover.querySelector(".search-url-list");

  if (queryList) {
    queryList.innerHTML = "";
    if (!state.queries.length) {
      queryList.innerHTML = `<li class="search-process-placeholder">検索ワードを準備しています…</li>`;
    } else {
      state.queries.forEach((q) => appendSearchQueryRow(queryList, q.query, q.provider));
    }
  }

  if (siteList) {
    siteList.innerHTML = "";
    if (!state.sites.length) {
      siteList.innerHTML = `<li class="search-process-placeholder">サイトを探索しています…</li>`;
    } else {
      state.sites.forEach((s) => appendSearchSiteRow(siteList, s.site, s.provider));
    }
  }

  if (urlList) {
    urlList.innerHTML = "";
    if (!state.urls.length) {
      urlList.innerHTML = `<li class="search-process-placeholder">候補URLを収集中…</li>`;
    } else {
      state.urls.forEach((u) => appendSearchUrlRow(urlList, u));
    }
  }

  scrollChatToBottom();
}

function ensureSearchCover(messageEl) {
  const body = messageEl?.querySelector(".message-body");
  if (!body || body.querySelector("#searchProcessCover")) return;
  messageEl.classList.add("is-searching");
  body.classList.add("has-search-cover");
  const content = body.querySelector(".message-content");
  if (content) {
    content.innerHTML = "";
  }
  const cover = createSearchCoverElement();
  body.insertBefore(cover, content);
  bindSearchCoverToggle(cover, messageEl);
  renderSearchCoverLists(messageEl);
}

function handleSearchStreamEvent(messageEl, event) {
  if (!messageEl || !event?.type) return;
  ensureSearchCover(messageEl);
  const state = getSearchCoverState(messageEl);
  const cover = messageEl.querySelector("#searchProcessCover");
  if (!cover) return;

  cover.classList.add("is-active");

  if (event.type === "intent") {
    const title = cover.querySelector(".search-process-title");
    if (title) title.textContent = "Web検索を実行します";
    const summary = cover.querySelector(".search-process-summary");
    if (summary && event.reason) summary.textContent = event.reason;
    for (const q of event.queries || []) {
      const exists = state.queries.some((item) => item.query === q);
      if (!exists) {
        state.queries.push({ query: q, provider: "" });
        appendSearchQueryRow(cover.querySelector(".search-query-list"), q, "");
      }
    }
    scrollChatToBottom();
    return;
  }

  if (event.type === "start") {
    cover.classList.add("is-active");
    const title = cover.querySelector(".search-process-title");
    if (title && title.textContent === "Web検索を準備しています") {
      title.textContent = "Webを検索中";
    }
    renderSearchCoverLists(messageEl);
    return;
  }

  if (event.type === "query") {
    const exists = state.queries.some(
      (q) => q.query === event.query && q.provider === event.provider
    );
    if (!exists) {
      state.queries.push({ query: event.query, provider: event.provider || "" });
      appendSearchQueryRow(
        cover.querySelector(".search-query-list"),
        event.query,
        event.provider || ""
      );
      updateSearchCoverSummary(cover, state);
    }
    scrollChatToBottom();
    return;
  }

  if (event.type === "hit") {
    const urlKey = event.url || event.title;
    if (!state.urls.some((u) => (u.url || u.title) === urlKey)) {
      const hit = {
        title: event.title,
        url: event.url,
        site: event.site,
        provider: event.provider,
        date: event.date || "",
        dateLabel: event.date_label || "日付不明",
      };
      state.urls.push(hit);
      appendSearchUrlRow(cover.querySelector(".search-url-list"), hit);
    }
    if (event.site) {
      const siteKey = `${event.site}|${event.provider || ""}`;
      if (!state.sites.some((s) => `${s.site}|${s.provider || ""}` === siteKey)) {
        state.sites.push({ site: event.site, provider: event.provider || "" });
        appendSearchSiteRow(
          cover.querySelector(".search-site-list"),
          event.site,
          event.provider || ""
        );
      }
    }
    updateSearchCoverSummary(cover, state);
    scrollChatToBottom();
    return;
  }

  if (event.type === "done") {
    renderSearchCoverLists(messageEl);
    collapseSearchCover(cover, messageEl);
    scrollChatToBottom();
  }
}

function handleFetchStreamEvent(messageEl, event) {
  if (!messageEl || !event?.type) return;
  ensureSearchCover(messageEl);
  const state = getSearchCoverState(messageEl);
  const cover = messageEl.querySelector("#searchProcessCover");
  if (!cover) return;

  cover.classList.add("is-active");

  if (event.type === "intent") {
    const title = cover.querySelector(".search-process-title");
    if (title) title.textContent = "ページを取得中";
    const summary = cover.querySelector(".search-process-summary");
    if (summary) {
      summary.textContent = event.reason || event.url || "";
    }
    if (event.url && !state.urls.some((u) => u.url === event.url)) {
      const hit = { title: event.url, url: event.url, site: "", provider: "fetch" };
      state.urls.push(hit);
      appendSearchUrlRow(cover.querySelector(".search-url-list"), hit);
    }
    scrollChatToBottom();
    return;
  }

  if (event.type === "url") {
    if (event.url && !state.urls.some((u) => u.url === event.url)) {
      const hit = { title: event.url, url: event.url, site: "", provider: "fetch" };
      state.urls.push(hit);
      appendSearchUrlRow(cover.querySelector(".search-url-list"), hit);
      updateSearchCoverSummary(cover, state);
    }
    scrollChatToBottom();
    return;
  }

  if (event.type === "done") {
    const title = cover.querySelector(".search-process-title");
    if (title) {
      title.textContent = event.ok === false ? "ページ取得に失敗" : "ページを取得しました";
    }
    renderSearchCoverLists(messageEl);
    collapseSearchCover(cover, messageEl);
    scrollChatToBottom();
  }
}

function hideSearchCover(messageEl) {
  finalizeSearchCoverOnStop(messageEl);
}

function setStreamingWaiting(contentEl) {
  if (!contentEl) return;
  window.cancelStreamingMarkdown?.(contentEl);
  contentEl.classList.add("is-stream-waiting");
  contentEl.classList.remove("is-stream-stopped");
  contentEl.innerHTML = renderStreamingWaitingHtml();
}

function setStreamingStopped(contentEl) {
  if (!contentEl) return;
  window.cancelStreamingMarkdown?.(contentEl);
  contentEl.classList.remove("is-stream-waiting");
  contentEl.classList.add("is-stream-stopped");
  contentEl.innerHTML = `<p class="stream-stopped-text">停止されました</p>`;
}

function showAssistantPending(showAvatar = true, showWaiting = true) {
  removeStreamingMessage();
  hideWelcome();
  messagesEl.classList.remove("hidden");

  const div = document.createElement("div");
  div.className = `message assistant${showAvatar ? "" : " message-follow"}`;
  div.id = "streamingMessage";
  div.innerHTML = `
    <div class="message-avatar">AI</div>
    <div class="message-body">
      <div class="message-content markdown-body${showWaiting ? " is-stream-waiting" : ""}">
        ${showWaiting ? renderStreamingWaitingHtml() : ""}
      </div>
    </div>
  `;
  messagesEl.appendChild(div);
  scrollChatToBottom();
  return div;
}

function isToolPlanningContent(text) {
  const t = (text || "").trim();
  if (!t || t.length > 600) return false;
  if (!/ようです|しましょう|しますね/.test(t)) return false;
  const lineRe =
    /^(?:ユーザー(?:は|の)[^\n。]{0,120}(?:確認|取得|調べ)[^\n。]{0,80}ようです|(?:Gmail|カレンダー|受信|予定|メール)[^\n。]{0,80}(?:取得|確認)しましょう)[。.]?\s*$/i;
  const planRe =
    /確認したいようです|(?:一覧|予定|メール).{0,40}(?:取得|確認)しましょう/;
  const hintRe = /(?:Gmail|カレンダー|受信|予定|メール|google_calendar|gmail_list)/i;
  const userRe = /^ユーザー(?:は|の)/;
  const parts = t.split(/(?<=[。.!?])\s*/).map((p) => p.trim()).filter(Boolean);
  if (parts.length) {
    return parts.every(
      (chunk) =>
        lineRe.test(chunk) ||
        (planRe.test(chunk) && (hintRe.test(chunk) || userRe.test(chunk)))
    );
  }
  return planRe.test(t) && (hintRe.test(t) || /^ユーザー(?:は|の)/.test(t));
}

function stripAssistantArtifacts(text) {
  if (!text) return "";
  let t = String(text);
  t = t.replace(/<\/?[｜|]+DSML[｜|]+[^>]*>/gi, "");
  t = t.replace(/<\/?[｜|]+(?:DSML[｜|]+)?(?:invoke|function_calls?|parameter)[｜|][^>]*>/gi, "");
  t = t.replace(/DSML[｜|]+tool_calls/gi, "");
  let cut = t.length;
  const markers = ["<｜｜DSML", "</｜｜DSML", "<|DSML", "<｜DSML", "DSML｜｜tool_calls"];
  for (const m of markers) {
    const i = t.indexOf(m);
    if (i >= 0) cut = Math.min(cut, i);
  }
  t = t.slice(0, cut);
  const thinkRe = new RegExp("<" + "think" + ">[\\s\\S]*?<" + "/think" + ">", "gi");
  t = t.replace(thinkRe, "");
  t = t.replace(
    /(?:検索結果に[^。\n]*スニペット[^。\n]*含まれていません[。.]?|より詳細な情報を取得します[。.]?)\s*/gi,
    ""
  );
  t = t.replace(/<+\s*$/g, "");
  t = t.trim();
  if (isToolPlanningContent(t)) return "";
  return t;
}

function stripThinking(text) {
  return stripAssistantArtifacts(text);
}

function buildGeneratedImageMarkdown(url, alt) {
  const safeUrl = String(url || "").replace(/\s+/g, "");
  const label = String(alt || "generated image").replace(/[\[\]()]/g, "");
  if (!safeUrl) return "";
  return `\n\n![${label}](${safeUrl})\n\n`;
}

function extractGeneratedImageIds(text) {
  const re = /\/api\/generated-images\/([a-f0-9]{32})/gi;
  const ids = [];
  let m;
  while ((m = re.exec(String(text || ""))) !== null) {
    ids.push(m[1].toLowerCase());
  }
  return ids;
}

function assistantReplyNearDuplicate(prev, finalText) {
  if (!finalText || !prev) return false;
  if (finalText === prev) return true;
  const prevIds = new Set(extractGeneratedImageIds(prev));
  const finalIds = extractGeneratedImageIds(finalText);
  if (finalIds.some((id) => !prevIds.has(id))) return false;
  return (
    finalText.length > 80 &&
    prev.length > 80 &&
    finalText.slice(0, 120) === prev.slice(0, 120)
  );
}


function parseSseDataFromPart(part) {
  if (!part?.trim()) return null;
  const dataLine = part
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("data:"));
  if (!dataLine) return null;
  const raw = dataLine.slice(5).trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

window.parseSseDataFromPart = parseSseDataFromPart;

function applyChatStreamPayload(data, handlers) {
  if (!data) return null;
  const {
    onChunk,
    onSearch,
    onMeta,
    onReasoning,
    onFetch,
    onTasksUpdated,
    onTasksToolUsed,
    onMemoryUpdated,
    onMemoryToolUsed,
    onImageGeneration,
    onToolTrace,
    onAskUser,
    isAborted,
  } = handlers;
  if (isAborted?.()) return null;
  if (data.error) throw new Error(data.error);
  if (data.search) onSearch?.(data.search);
  if (data.fetch) onFetch?.(data.fetch);
  if (data.image_generation) onImageGeneration?.(data.image_generation);
  if (data.reasoning) onReasoning?.(data.reasoning);
  if (data.segment_end) onMeta?.({ segment_end: true });
  if (data.segment_start) {
    onMeta?.({
      segment_start: true,
      discard_previous: Boolean(data.discard_previous),
    });
  }
  if (data.content_replace) {
    onMeta?.({ content_replace: data.content_replace });
  }
  if (data.content) onChunk?.(data.content);
  window.NexFullInfoPanel?.handleSseData?.(data);
  if (data.tasks_tool_used) onTasksToolUsed?.();
  if (data.tasks_updated) onTasksUpdated?.();
  if (data.memory_tool_used) onMemoryToolUsed?.();
  if (data.memory_updated) onMemoryUpdated?.();
  if (data.computelab_tool_used) {
    window.dispatchEvent(new CustomEvent("nexgate:computelab-tool-used"));
  }
  if (data.tool_trace) onToolTrace?.(data.tool_trace);
  if (data.ask_user) onAskUser?.(data.ask_user);
  if (data.done) return { paused: Boolean(data.paused_for_user) };
  return null;
}

async function readChatStream(
  response,
  onChunk,
  signal,
  onSearch,
  onMeta,
  onReasoning,
  onFetch,
  onTasksUpdated,
  onTasksToolUsed,
  onMemoryUpdated,
  onMemoryToolUsed,
  onImageGeneration,
  onToolTrace,
  onAskUser
) {
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
      const data = parseSseDataFromPart(part);
      if (!data) continue;
      if (data.error) throw new Error(data.error);
      if (data.search) onSearch?.(data.search);
      if (data.fetch) onFetch?.(data.fetch);
      if (data.image_generation) onImageGeneration?.(data.image_generation);
      if (data.reasoning) onReasoning?.(data.reasoning);
      if (data.segment_end) onMeta?.({ segment_end: true });
      if (data.segment_start) {
        onMeta?.({
          segment_start: true,
          discard_previous: Boolean(data.discard_previous),
        });
      }
      if (data.content_replace) {
        onMeta?.({ content_replace: data.content_replace });
      }
        if (data.content) onChunk(data.content);
        window.NexFullInfoPanel?.handleSseData?.(data);
        if (data.tasks_tool_used) onTasksToolUsed?.();
      if (data.tasks_updated) onTasksUpdated?.();
      if (data.memory_tool_used) onMemoryToolUsed?.();
      if (data.memory_updated) onMemoryUpdated?.();
      if (data.computelab_tool_used) {
        window.dispatchEvent(new CustomEvent("nexgate:computelab-tool-used"));
      }
      if (data.tool_trace) onToolTrace?.(data.tool_trace);
      if (data.ask_user) onAskUser?.(data.ask_user);
      if (data.done) return { paused: Boolean(data.paused_for_user) };
    }
  }
  return {};
}

function fallbackSessionTitle(text) {
  const t = String(text || "").trim();
  if (!t) return "新しいチャット";
  return t.slice(0, 30) + (t.length > 30 ? "…" : "");
}

function applySessionTitle(chat, title) {
  if (isPrivateChat(chat)) return;
  const trimmed = String(title || "").trim();
  if (!trimmed || chat.title === trimmed) return;
  chat.title = trimmed;
  const idx = sessions.findIndex((s) => s.id === chat.id);
  if (idx >= 0) {
    sessions[idx].title = trimmed;
  } else if (chat.messages?.some(isHistoryMessage)) {
    sessions.unshift({
      id: chat.id,
      title: trimmed,
      updated_at: latestMessageTimestamp(chat.messages) || messageTimestampNow(),
    });
  }
  saveSessionsIndex();
  const cached = loadedChats.get(chat.id);
  if (cached) cached.title = trimmed;
  persistSessionMetaToServer(chat.id, { title: trimmed }).catch((err) =>
    console.warn("title sync failed", err)
  );
  saveChats(chat);
  if (!shouldUpdateSessionHistory(chat)) {
    updateChatSessionTitleBar();
    return;
  }
  const titleEl = findHistoryTitleElement(chat.id);
  if (titleEl) {
    void fadeHistoryItemTitle(titleEl, trimmed);
    updateChatSessionTitleBar();
    return;
  }
  renderHistory();
}

function updateTitle(chat, firstMessage) {
  applySessionTitle(chat, fallbackSessionTitle(firstMessage));
}

async function generateSessionTitle(chat, firstMessage) {
  if (isPrivateChat(chat)) return;
  const message = String(firstMessage || "").trim();
  if (!message) return;

  try {
    const res = await fetch("/api/chat/session-title", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        model: window.__SELECTED_MODEL_ID__ || window.__MODELS__?.[0]?.id || null,
      }),
    });
    let title = "";
    if (res.ok) {
      const data = await res.json();
      title = String(data.title || "").trim();
    }
    if (!title) title = fallbackSessionTitle(message);
    if (getCurrentChat()?.id !== chat.id) return;
    applySessionTitle(chat, title);
  } catch {
    if (getCurrentChat()?.id !== chat.id) return;
    updateTitle(chat, message);
  }
}

function stopGeneration() {
  const stopRequestId =
    localGenerationRequestId ||
    passiveStreamRequestId ||
    sessionGeneration.requestId ||
    window.NexChatSocket?.getActiveRequestId?.();
  const stopSessionId = localGenerationSessionId || passiveStreamSessionId || currentChatId;
  const messageEl = document.getElementById("streamingMessage");
  const contentEl = messageEl?.querySelector(".message-content");
  finalizeAllActiveSearchCovers({ stopped: true });
  finalizeAllActiveToolTraceCovers();
  if (contentEl?.classList.contains("is-stream-waiting") && !contentEl.classList.contains("is-stream-stopped")) {
    setStreamingStopped(contentEl);
  }
  chatAbortController?.abort();
  if (stopRequestId) {
    window.NexChatSocket?.stop?.(stopRequestId);
  }
}

function ensureSearchMessageSlot(chat, showAvatar = null) {
  const state = createSearchMessageData();
  const index = chat.messages.length;
  chat.messages.push({ role: "search", content: cloneSearchState(state) });
  const el = appendSearchMessageToDom(
    chat.messages[index].content,
    index,
    true,
    showAvatar
  );
  pinToolTraceInCurrentTurn(chat);
  const finalIndex = Number(el.dataset.messageIndex);
  saveChats(chat);
  return { index: Number.isFinite(finalIndex) ? finalIndex : index, el };
}

function lastAssistantContent(chat) {
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    const msg = chat.messages[i];
    if (msg?.role === "assistant" && typeof msg.content === "string") {
      return msg.content.trim();
    }
  }
  return "";
}

function finalizeReplyTurn(
  chat,
  segmentText,
  searchMessageIndex,
  searchMessageEl,
  reasoningMessageIndex,
  reasoningMessageEl,
  takeTurnAvatar,
  tasksToolUsed = false,
  toolTraceMessageIndex = null,
  toolTraceMessageEl = null
) {
  window.flushStreamingMarkdown?.();
  if (reasoningMessageIndex !== null) {
    finalizeReasoningIfOpen(reasoningMessageEl, chat, reasoningMessageIndex);
    persistReasoningMessage(chat, reasoningMessageIndex, reasoningMessageEl);
  }
  if (toolTraceMessageIndex !== null && toolTraceMessageEl) {
    const tCover = toolTraceMessageEl.querySelector("#toolTraceCover");
    if (tCover && !tCover.classList.contains("is-complete")) {
      completeToolTraceCover(tCover, toolTraceMessageEl, true);
    }
    persistToolTraceMessage(chat, toolTraceMessageIndex, toolTraceMessageEl);
  }
  if (searchMessageIndex !== null && searchMessageEl) {
    const cover = searchMessageEl.querySelector("#searchProcessCover");
    if (cover && !cover.classList.contains("is-complete")) {
      finalizeSearchCoverOnStop(searchMessageEl, {
        stopped: Boolean(chatAbortController?.signal?.aborted),
      });
    }
    persistSearchMessage(chat, searchMessageIndex, searchMessageEl);
  }
  const finalText = stripThinking(segmentText);
  const prev = lastAssistantContent(chat);
  const isNearDuplicate = assistantReplyNearDuplicate(prev, finalText);
  if (finalText && !isNearDuplicate) {
    const showAvatar = takeTurnAvatar ? takeTurnAvatar() : true;
    const promoted = promoteStreamingAssistantMessage(
      chat,
      segmentText,
      showAvatar,
      true,
      tasksToolUsed
    );
    if (!promoted) {
      removeStreamingMessage();
      commitAssistantSegment(chat, segmentText, showAvatar, true, tasksToolUsed);
    }
  } else {
    removeStreamingMessage();
  }
  markLocalMutation(3500);
  saveChats(chat);
  updatePrivateChatActiveUI();
}

async function requestAssistantReply(chat) {
  chat = mergeChatState(chat);
  const sessionId = chat?.id;
  if (!chat?.messages.length || isLoading) {
    if (sessionId) unmarkSessionGenerating(sessionId);
    return;
  }
  if (sessionGeneration.requestId && !localGenerationRequestId) {
    if (isPassiveGenerating) {
      if (sessionId) unmarkSessionGenerating(sessionId);
      window.NexNotify?.showError(
        window.t?.("chatGenerationInProgress") || "このセッションでは既に生成が進行中です"
      );
      return;
    }
    clearSessionGeneration(sessionGeneration.requestId);
  }

  currentChatId = sessionId;

  const getReplyChat = () => {
    const active = loadedChats.get(sessionId);
    if (active) return active;
    return mergeChatState(chat);
  };

  markLocalMutation(3500);
  isLoading = true;
  localGenerationSessionId = sessionId;
  markSessionGenerating(sessionId);
  chatStickToBottom = true;
  chatAbortController = new AbortController();
  syncSessionGenerationUI();

  let turnAvatarUsed = false;
  const takeTurnAvatar = () => {
    if (turnAvatarUsed) return false;
    turnAvatarUsed = true;
    return true;
  };

  let streamingEl = showAssistantPending(false);
  let contentEl = streamingEl.querySelector(".message-content");
  let segmentText = "";
  let searchMessageIndex = null;
  let searchMessageEl = null;
  let reasoningMessageIndex = null;
  let reasoningMessageEl = null;
  let toolTraceMessageIndex = null;
  let toolTraceMessageEl = null;
  let turnTasksToolUsed = false;
  let turnGeneratedImageUrl = "";
  let turnImageGenerating = false;

  const onMeta = (meta) => {
    if (meta.segment_end && segmentText.trim()) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
      commitAssistantSegment(getReplyChat(), segmentText, takeTurnAvatar(), false);
      segmentText = "";
    }
    if (meta.segment_start && reasoningMessageEl) {
      const rCover = reasoningMessageEl.querySelector("#reasoningProcessCover");
      if (rCover && !rCover.classList.contains("is-complete")) {
        completeReasoningCover(
          rCover,
          reasoningMessageEl,
          rCover.classList.contains("is-collapsed")
        );
        syncReasoningMessageToChat(getReplyChat(), reasoningMessageIndex, reasoningMessageEl);
      }
    }
    if (meta.content_replace) {
      segmentText = String(meta.content_replace || "");
      if (!contentEl) {
        streamingEl = showAssistantPending(false);
        contentEl = streamingEl.querySelector(".message-content");
      }
      if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
        messagesEl.appendChild(streamingEl);
      }
      if (contentEl) {
        contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
        window.scheduleStreamingMarkdown?.(
          contentEl,
          stripThinking(segmentText)
        );
        scrollChatToBottom();
      }
      return;
    }
    if (meta.segment_start) {
      if (segmentText.trim() && !meta.discard_previous) {
        removeStreamingMessage();
        streamingEl = null;
        contentEl = null;
        commitAssistantSegment(getReplyChat(), segmentText, false, false);
      }
      segmentText = "";
      if (meta.discard_previous) {
        if (streamingEl && contentEl) {
          messagesEl.appendChild(streamingEl);
          if (!contentEl.classList.contains("is-stream-waiting")) {
            contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
            window.cancelStreamingMarkdown?.(contentEl);
            contentEl.innerHTML = "";
          }
        } else {
          removeStreamingMessage();
          streamingEl = showAssistantPending(false, false);
          contentEl = streamingEl.querySelector(".message-content");
        }
      } else {
        removeStreamingMessage();
        streamingEl = null;
        contentEl = null;
        streamingEl = showAssistantPending(false);
        contentEl = streamingEl.querySelector(".message-content");
      }
    }
  };

  const onReasoning = (reasoningEvent) => {
    if (!reasoningCardsEnabled()) return;
    const replyChat = getReplyChat();
    const slot = { el: reasoningMessageEl, index: reasoningMessageIndex };
    clearCompletedReasoningSlot(slot, replyChat);
    reasoningMessageEl = slot.el;
    reasoningMessageIndex = slot.index;
    if ((reasoningEvent.type === "delta" || reasoningEvent.type === "done") && !reasoningMessageEl) {
      if (reasoningEvent.type === "delta") {
        if (segmentText.trim() && streamingEl) {
          removeStreamingMessage();
          streamingEl = null;
          contentEl = null;
          commitAssistantSegment(replyChat, segmentText, takeTurnAvatar(), false);
          segmentText = "";
        } else if (streamingEl) {
          removeStreamingMessage();
          streamingEl = null;
          contentEl = null;
        }
      }
      const created = ensureReasoningStreamSlot(replyChat, takeTurnAvatar());
      reasoningMessageIndex = created.index;
      reasoningMessageEl = created.el;
      if (toolTraceMessageEl) {
        const pinned = syncPinnedToolTraceSlot(replyChat, {
          index: toolTraceMessageIndex,
          el: toolTraceMessageEl,
        });
        toolTraceMessageIndex = pinned.index;
        toolTraceMessageEl = pinned.el;
      }
    }
    if (!reasoningMessageEl) return;
    handleReasoningStreamEvent(reasoningMessageEl, reasoningEvent);
    syncReasoningMessageToChat(replyChat, reasoningMessageIndex, reasoningMessageEl);
    if (reasoningEvent.type === "done") {
      saveChats(replyChat);
    }
  };

  const ensureToolTraceSlot = () => {
    if (!toolTraceEnabled() || toolTraceMessageEl) return;
    const replyChat = getReplyChat();
    if (segmentText.trim() && streamingEl) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
      commitAssistantSegment(replyChat, segmentText, takeTurnAvatar(), false);
      segmentText = "";
    } else if (streamingEl) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
    }
    const slot = ensureToolTraceMessageSlot(replyChat, takeTurnAvatar());
    toolTraceMessageIndex = slot.index;
    toolTraceMessageEl = slot.el;
  };

  const onToolTrace = (trace) => {
    if (!toolTraceEnabled() || chatAbortController?.signal.aborted) return;
    ensureToolTraceSlot();
    if (!toolTraceMessageEl) return;
    const pinned = handleToolTraceEvent(toolTraceMessageEl, trace);
    toolTraceMessageIndex = pinned.index;
    toolTraceMessageEl = pinned.el;
    syncToolTraceMessageToChat(getReplyChat(), toolTraceMessageIndex, toolTraceMessageEl);
    saveChats(getReplyChat());
  };

  const ensureSearchSlot = () => {
    const replyChat = getReplyChat();
    if (searchMessageEl) return;
    if (reasoningMessageEl) {
      const rCover = reasoningMessageEl.querySelector("#reasoningProcessCover");
      if (rCover && !rCover.classList.contains("is-complete")) {
        completeReasoningCover(
          rCover,
          reasoningMessageEl,
          rCover.classList.contains("is-collapsed")
        );
        syncReasoningMessageToChat(replyChat, reasoningMessageIndex, reasoningMessageEl);
      }
    }
    if (segmentText.trim() && streamingEl) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
      if (!isSearchPrefaceOnly(segmentText)) {
        commitAssistantSegment(replyChat, segmentText, takeTurnAvatar(), false);
      }
      segmentText = "";
    } else if (streamingEl) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
    }
    const slot = ensureSearchMessageSlot(replyChat, takeTurnAvatar());
    searchMessageIndex = slot.index;
    searchMessageEl = slot.el;
    if (toolTraceMessageEl) {
      const pinned = syncPinnedToolTraceSlot(replyChat, {
        index: toolTraceMessageIndex,
        el: toolTraceMessageEl,
      });
      toolTraceMessageIndex = pinned.index;
      toolTraceMessageEl = pinned.el;
    }
  };

  const onFetch = (fetchEvent) => {
    if (chatAbortController?.signal.aborted) return;
    if (fetchEvent.type === "intent") {
      ensureSearchSlot();
    }
    if (!searchMessageEl) return;
    handleFetchStreamEvent(searchMessageEl, fetchEvent);
    syncSearchMessageToChat(getReplyChat(), searchMessageIndex, searchMessageEl);
    if (fetchEvent.type === "done") {
      const cover = searchMessageEl.querySelector("#searchProcessCover");
      if (cover) cover.classList.add("is-complete");
      syncSearchMessageToChat(getReplyChat(), searchMessageIndex, searchMessageEl);
      saveChats(getReplyChat());
    }
  };

  const onSearch = (searchEvent) => {
    if (chatAbortController?.signal.aborted) return;
    const replyChat = getReplyChat();
    if (searchEvent.type === "intent" || searchEvent.type === "start") {
      if (searchMessageEl) return;
      ensureSearchSlot();
    }
    if (!searchMessageEl) return;
    handleSearchStreamEvent(searchMessageEl, searchEvent);
    syncSearchMessageToChat(getReplyChat(), searchMessageIndex, searchMessageEl);
    if (searchEvent.type === "done") {
      const cover = searchMessageEl.querySelector("#searchProcessCover");
      if (cover) cover.classList.add("is-complete");
      syncSearchMessageToChat(getReplyChat(), searchMessageIndex, searchMessageEl);
      saveChats(getReplyChat());
    }
  };

  try {
    const locationContext = await window.NexGeolocation?.getLocationContextForChat?.();
    const chatBody = {
      messages: messagesForApi(chat),
      model: window.__SELECTED_MODEL_ID__ || window.__MODELS__?.[0]?.id || null,
      session_id: sessionId || null,
      owner: getSessionOwner(sessionId),
    };
    if (locationContext) {
      chatBody.location_context = locationContext;
    }
    const chatTools = window.chatToolsBar?.getChatToolsPayload?.();
    if (chatTools && Object.keys(chatTools).length) {
      chatBody.chat_tools = chatTools;
    }
    const customAgentId = window.customAgentSelect?.getSelectedAgentId?.();
    if (customAgentId) {
      chatBody.custom_agent_id = customAgentId;
      const customAgent = window.customAgentSelect?.getSelectedAgent?.();
      if (customAgent?.model_id) {
        chatBody.model = customAgent.model_id;
      }
    }

    const onTasksUpdated = () => {
      if (window.__USER__?.tasks_enabled !== true) return;
      if (window.NexRouter?.getActiveView?.() !== "tasks") return;
      window.tasksApp?.reloadFromServer?.();
    };

    const onTasksToolUsed = () => {
      turnTasksToolUsed = true;
    };

    const onMemoryUpdated = () => {
      if (window.__USER__?.memory_enabled !== true) return;
      if (window.NexRouter?.getActiveView?.() === "settings") {
        window.memorySettingsApp?.load?.();
      }
      window.NexNotify?.showInfo?.(window.t("memoryChatSavedNotice"));
    };

    const onMemoryToolUsed = () => {};

    const onImageGeneration = (evt) => {
      if (chatAbortController?.signal.aborted) return;
      if (evt.type === "intent" || evt.type === "start") {
        if (!contentEl) {
          streamingEl = showAssistantPending(false);
          contentEl = streamingEl?.querySelector(".message-content");
        }
        if (contentEl) {
          turnImageGenerating = true;
          const note = window.t("imageGenerationInProgress");
          showImageGenerationWaiting(contentEl, segmentText, note);
          scrollChatToBottom();
        }
      }
      if (evt.type === "error") {
        turnImageGenerating = false;
        if (contentEl) {
          contentEl.classList.remove("is-image-generating");
          const errText = evt.message || "画像生成に失敗しました";
          segmentText = segmentText ? `${segmentText}\n\n${errText}` : errText;
          applyMarkdownContent(contentEl, stripThinking(segmentText));
          scrollChatToBottom();
        }
      }
      if (evt.type === "done" && evt.url) {
        turnImageGenerating = false;
        if (!contentEl) {
          streamingEl = showAssistantPending(false);
          contentEl = streamingEl?.querySelector(".message-content");
        }
        turnGeneratedImageUrl = String(evt.url || "").replace(/\s+/g, "");
        segmentText = window.stripOtherGeneratedImageMarkdown?.(
          segmentText,
          turnGeneratedImageUrl
        ) ?? segmentText;
        const md = buildGeneratedImageMarkdown(evt.url, evt.prompt);
        const urlKey = turnGeneratedImageUrl;
        if (urlKey && !segmentText.replace(/\s+/g, "").includes(urlKey)) {
          segmentText += md;
        }
        if (contentEl) {
          contentEl.classList.remove(
            "is-stream-waiting",
            "is-stream-stopped",
            "is-image-generating"
          );
          applyMarkdownContent(contentEl, stripThinking(segmentText));
          scrollChatToBottom();
        }
      }
    };

    const onAskUser = (payload) => {
      if (chatAbortController?.signal.aborted) return;
      if (!window.NexUserQuestionModal?.enabled?.()) return;
      window.NexUserQuestionModal.show(payload);
    };

    const streamHandlers = {
      onChunk: (chunk) => {
        if (chatAbortController?.signal.aborted) return;
        if (!contentEl) {
          streamingEl = showAssistantPending(false);
          contentEl = streamingEl.querySelector(".message-content");
        }
        if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
          messagesEl.appendChild(streamingEl);
        }
        segmentText += chunk;
        if (turnImageGenerating) {
          updateImageGenerationPreface(contentEl, segmentText);
          scrollChatToBottom();
          return;
        }
        if (turnGeneratedImageUrl) {
          segmentText =
            window.stripOtherGeneratedImageMarkdown?.(
              segmentText,
              turnGeneratedImageUrl
            ) ?? segmentText;
        }
        contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
        window.scheduleStreamingMarkdown?.(
          contentEl,
          stripThinking(segmentText)
        );
        scrollChatToBottom();
      },
      onSearch,
      onMeta,
      onReasoning,
      onFetch,
      onTasksUpdated,
      onTasksToolUsed,
      onMemoryUpdated,
      onMemoryToolUsed,
      onImageGeneration,
      onToolTrace,
      onAskUser,
      isAborted: () => chatAbortController?.signal.aborted,
    };

    await window.NexChatSocket.ensureReady();
    window.NexChatSocket.joinSession(sessionId, getSessionOwner(sessionId));
    scheduleBroadcastSessionSettings();

    let activeRequestId = null;
    let streamError = null;
    const offSocket = window.NexChatSocket.onEvent((msg) => {
      if (
        msg.type === "chat.error" &&
        (!activeRequestId || msg.request_id === activeRequestId)
      ) {
        if (msg.code === "generation_in_progress" && msg.active_request_id) {
          setSessionGeneration(msg.active_request_id, null);
          startPassiveStreamWatch(sessionId, msg.active_request_id);
        }
        streamError = new Error(msg.error || "エラーが発生しました");
        return;
      }
      if (msg.type === "chat.snapshot") {
        if (msg.session_id && msg.session_id !== sessionId) return;
        activeRequestId = msg.request_id || activeRequestId;
        window.NexChatSocket.replaySnapshot(msg, (ev) => {
          try {
            applyChatStreamPayload(ev.data, streamHandlers);
          } catch (err) {
            streamError = err;
          }
        });
        return;
      }
      if (msg.type !== "chat.event") return;
      if (msg.session_id && msg.session_id !== sessionId) return;
      if (activeRequestId && msg.request_id !== activeRequestId) return;
      try {
        applyChatStreamPayload(msg.data, streamHandlers);
      } catch (err) {
        streamError = err;
      }
    });

    let request_id;
    let completion;
    try {
      ({ request_id, completion } = await window.NexChatSocket.sendChat(chatBody));
    } catch (err) {
      if (err.code === "generation_in_progress" && err.active_request_id) {
        setSessionGeneration(err.active_request_id, null);
        startPassiveStreamWatch(sessionId, err.active_request_id);
      }
      throw err;
    }
    activeRequestId = request_id;
    localGenerationRequestId = request_id;
    setSessionGeneration(request_id, currentUser.username);
    const completionResult = await completion;
    offSocket();
    if (streamError) throw streamError;

    const streamResult = { paused: Boolean(completionResult?.paused) };
    if (completionResult?.assistant_content) {
      segmentText = applyAuthoritativeAssistantContent(
        getReplyChat(),
        segmentText,
        completionResult.assistant_content
      );
    }

    finalizeReplyTurn(
      getReplyChat(),
      segmentText,
      searchMessageIndex,
      searchMessageEl,
      reasoningMessageIndex,
      reasoningMessageEl,
      takeTurnAvatar,
      turnTasksToolUsed,
      toolTraceMessageIndex,
      toolTraceMessageEl
    );
    if (streamResult?.paused) {
      return;
    }
  } catch (err) {
    if (err.name === "AbortError") {
      finalizeReplyTurn(
        getReplyChat(),
        segmentText,
        searchMessageIndex,
        searchMessageEl,
        reasoningMessageIndex,
        reasoningMessageEl,
        takeTurnAvatar,
        turnTasksToolUsed,
        toolTraceMessageIndex,
        toolTraceMessageEl
      );
    } else {
      removeStreamingMessage();
      const replyChat = getReplyChat();
      const index = replyChat.messages.length;
      const createdAt = messageTimestampNow();
      replyChat.messages.push({
        role: "assistant",
        content: `エラー: ${err.message}`,
        created_at: createdAt,
      });
      appendMessage("assistant", `エラー: ${err.message}`, true, index, true, true, createdAt);
      saveChats(replyChat);
    }
  } finally {
    chatAbortController = null;
    isLoading = false;
    localGenerationRequestId = null;
    if (localGenerationSessionId) {
      unmarkSessionGenerating(localGenerationSessionId);
      localGenerationSessionId = null;
    }
    syncSessionGenerationUI();
    touchPrivateChatActivity(getReplyChat());
    const syncedChat = getReplyChat();
    if (syncedChat) saveChats(syncedChat);
  }
}

async function resumeUserQuestionReply(chat, token, { answers = [], dismissed = false } = {}) {
  chat = mergeChatState(chat);
  if (!chat || !token || isLoading) return;

  const sessionId = chat.id;
  currentChatId = sessionId;
  const getReplyChat = () => loadedChats.get(sessionId) || mergeChatState(chat);

  isLoading = true;
  localGenerationSessionId = sessionId;
  markSessionGenerating(sessionId);
  chatStickToBottom = true;
  chatAbortController = new AbortController();
  updateSendBtn();

  let turnAvatarUsed = false;
  const takeTurnAvatar = () => {
    if (turnAvatarUsed) return false;
    turnAvatarUsed = true;
    return true;
  };

  let streamingEl = showAssistantPending(false);
  let contentEl = streamingEl.querySelector(".message-content");
  let segmentText = "";
  let searchMessageIndex = null;
  let searchMessageEl = null;
  let reasoningMessageIndex = null;
  let reasoningMessageEl = null;
  let toolTraceMessageIndex = null;
  let toolTraceMessageEl = null;
  let turnTasksToolUsed = false;
  let turnGeneratedImageUrl = "";
  let turnImageGenerating = false;

  const onMeta = (meta) => {
    if (meta.segment_end && segmentText.trim()) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
      commitAssistantSegment(getReplyChat(), segmentText, takeTurnAvatar(), false);
      segmentText = "";
    }
    if (meta.segment_start) {
      if (segmentText.trim() && !meta.discard_previous) {
        removeStreamingMessage();
        streamingEl = null;
        contentEl = null;
        commitAssistantSegment(getReplyChat(), segmentText, false, false);
      }
      segmentText = "";
      if (meta.discard_previous) {
        if (streamingEl && contentEl) {
          messagesEl.appendChild(streamingEl);
          if (!contentEl.classList.contains("is-stream-waiting")) {
            contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
            window.cancelStreamingMarkdown?.(contentEl);
            contentEl.innerHTML = "";
          }
        } else {
          removeStreamingMessage();
          streamingEl = showAssistantPending(false, false);
          contentEl = streamingEl.querySelector(".message-content");
        }
      } else {
        removeStreamingMessage();
        streamingEl = null;
        contentEl = null;
        streamingEl = showAssistantPending(false);
        contentEl = streamingEl.querySelector(".message-content");
      }
    }
    if (meta.content_replace) {
      segmentText = String(meta.content_replace || "");
      if (!contentEl) {
        streamingEl = showAssistantPending(false);
        contentEl = streamingEl.querySelector(".message-content");
      }
      if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
        messagesEl.appendChild(streamingEl);
      }
      if (contentEl) {
        contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
        window.scheduleStreamingMarkdown?.(contentEl, stripThinking(segmentText));
        scrollChatToBottom();
      }
    }
  };

  const onReasoning = (reasoningEvent) => {
    if (!reasoningCardsEnabled()) return;
    const replyChat = getReplyChat();
    const slot = { el: reasoningMessageEl, index: reasoningMessageIndex };
    clearCompletedReasoningSlot(slot, replyChat);
    reasoningMessageEl = slot.el;
    reasoningMessageIndex = slot.index;
    if ((reasoningEvent.type === "delta" || reasoningEvent.type === "done") && !reasoningMessageEl) {
      if (reasoningEvent.type === "delta") {
        if (segmentText.trim() && streamingEl) {
          removeStreamingMessage();
          streamingEl = null;
          contentEl = null;
          commitAssistantSegment(replyChat, segmentText, takeTurnAvatar(), false);
          segmentText = "";
        } else if (streamingEl) {
          removeStreamingMessage();
          streamingEl = null;
          contentEl = null;
        }
      }
      const created = ensureReasoningStreamSlot(replyChat, takeTurnAvatar());
      reasoningMessageIndex = created.index;
      reasoningMessageEl = created.el;
      if (toolTraceMessageEl) {
        const pinned = syncPinnedToolTraceSlot(replyChat, {
          index: toolTraceMessageIndex,
          el: toolTraceMessageEl,
        });
        toolTraceMessageIndex = pinned.index;
        toolTraceMessageEl = pinned.el;
      }
    }
    if (!reasoningMessageEl) return;
    handleReasoningStreamEvent(reasoningMessageEl, reasoningEvent);
    syncReasoningMessageToChat(replyChat, reasoningMessageIndex, reasoningMessageEl);
    if (reasoningEvent.type === "done") saveChats(replyChat);
  };

  const ensureResumeToolTraceSlot = () => {
    if (!toolTraceEnabled() || toolTraceMessageEl) return;
    const replyChat = getReplyChat();
    if (segmentText.trim() && streamingEl) {
      removeStreamingMessage();
      streamingEl = null;
      contentEl = null;
      commitAssistantSegment(replyChat, segmentText, takeTurnAvatar(), false);
      segmentText = "";
    }
    const slot = ensureToolTraceMessageSlot(replyChat, takeTurnAvatar());
    toolTraceMessageIndex = slot.index;
    toolTraceMessageEl = slot.el;
  };

  const onToolTrace = (trace) => {
    if (!toolTraceEnabled()) return;
    ensureResumeToolTraceSlot();
    if (!toolTraceMessageEl) return;
    const pinned = handleToolTraceEvent(toolTraceMessageEl, trace);
    toolTraceMessageIndex = pinned.index;
    toolTraceMessageEl = pinned.el;
    syncToolTraceMessageToChat(getReplyChat(), toolTraceMessageIndex, toolTraceMessageEl);
    saveChats(getReplyChat());
  };

  try {
    const streamHandlers = {
      onChunk: (chunk) => {
        if (chatAbortController?.signal.aborted) return;
        if (!contentEl) {
          streamingEl = showAssistantPending(false);
          contentEl = streamingEl.querySelector(".message-content");
        }
        if (streamingEl && streamingEl.parentNode === messagesEl && streamingEl.nextElementSibling) {
          messagesEl.appendChild(streamingEl);
        }
        segmentText += chunk;
        contentEl.classList.remove("is-stream-waiting", "is-stream-stopped");
        window.scheduleStreamingMarkdown?.(contentEl, stripThinking(segmentText));
        scrollChatToBottom();
      },
      onMeta,
      onReasoning,
      onToolTrace,
      isAborted: () => chatAbortController?.signal.aborted,
    };

    await window.NexChatSocket.ensureReady();
    window.NexChatSocket.joinSession(sessionId, getSessionOwner(sessionId));

    let activeRequestId = null;
    let streamError = null;
    const offSocket = window.NexChatSocket.onEvent((msg) => {
      if (
        msg.type === "chat.error" &&
        (!activeRequestId || msg.request_id === activeRequestId)
      ) {
        streamError = new Error(msg.error || "エラーが発生しました");
        return;
      }
      if (msg.type === "chat.snapshot") {
        if (msg.session_id && msg.session_id !== sessionId) return;
        activeRequestId = msg.request_id || activeRequestId;
        window.NexChatSocket.replaySnapshot(msg, (ev) => {
          try {
            applyChatStreamPayload(ev.data, streamHandlers);
          } catch (err) {
            streamError = err;
          }
        });
        return;
      }
      if (msg.type !== "chat.event") return;
      if (msg.session_id && msg.session_id !== sessionId) return;
      if (activeRequestId && msg.request_id !== activeRequestId) return;
      try {
        applyChatStreamPayload(msg.data, streamHandlers);
      } catch (err) {
        streamError = err;
      }
    });

    const { request_id, completion } = await window.NexChatSocket.resumeUserQuestions({
      token,
      answers,
      dismissed,
      session_id: sessionId || null,
      owner: getSessionOwner(sessionId),
    });
    activeRequestId = request_id;
    const completionResult = await completion;
    offSocket();
    if (streamError) throw streamError;

    if (completionResult?.assistant_content) {
      segmentText = applyAuthoritativeAssistantContent(
        getReplyChat(),
        segmentText,
        completionResult.assistant_content
      );
    }

    finalizeReplyTurn(
      getReplyChat(),
      segmentText,
      searchMessageIndex,
      searchMessageEl,
      reasoningMessageIndex,
      reasoningMessageEl,
      takeTurnAvatar,
      turnTasksToolUsed,
      toolTraceMessageIndex,
      toolTraceMessageEl
    );
  } catch (err) {
    if (err.name !== "AbortError") {
      removeStreamingMessage();
      const replyChat = getReplyChat();
      const index = replyChat.messages.length;
      const createdAt = messageTimestampNow();
      replyChat.messages.push({
        role: "assistant",
        content: `エラー: ${err.message}`,
        created_at: createdAt,
      });
      appendMessage("assistant", `エラー: ${err.message}`, true, index, true, true, createdAt);
      saveChats(replyChat);
    }
  } finally {
    chatAbortController = null;
    isLoading = false;
    if (localGenerationSessionId) {
      unmarkSessionGenerating(localGenerationSessionId);
      localGenerationSessionId = null;
    }
    syncSessionGenerationUI();
    updateSendBtn();
    touchPrivateChatActivity(getReplyChat());
  }
}

window.NexUserQuestions = {
  onSubmit(token, answers) {
    const chat = getCurrentChat();
    if (chat) void resumeUserQuestionReply(chat, token, { answers, dismissed: false });
  },
  onDismiss(token) {
    const chat = getCurrentChat();
    if (chat) void resumeUserQuestionReply(chat, token, { answers: [], dismissed: true });
  },
};

function getPlanChatBlockMessage() {
  const u = window.__USER__;
  if (!u) return null;
  if (u.plan_chat_enabled === false) {
    return "現在のプランではチャットを利用できません。プラン/課金ページからアップグレードしてください。";
  }
  if (u.usage_status === "blocked") {
    if (u.on_demand_billing_enabled && (u.balance || 0) < 10) {
      return "残高が不足しています。プラン/課金ページからチャージしてください。";
    }
    return "今月の利用枠の上限に達しました。プラン/課金ページをご確認ください。";
  }
  return null;
}

function notifyChatRestriction(message, { showBillingLink = true } = {}) {
  if (typeof window.showChatRestrictionNotice === "function") {
    window.showChatRestrictionNotice(message, { showBillingLink });
  }
}

async function sendMessage(text) {
  if (activeUserMessageEdit) {
    await commitUserMessageEdit(text);
    return;
  }
  if (!canSendInSession()) return;
  if (window.getSystemFeatures?.().chat_disabled) {
    notifyChatRestriction("現在、チャットは制限されています", { showBillingLink: false });
    return;
  }
  const planBlock = getPlanChatBlockMessage();
  if (planBlock) {
    notifyChatRestriction(planBlock, {
      showBillingLink: /プラン|課金|アップグレード/.test(planBlock),
    });
    return;
  }
  const usageWarn = window.__USER__?.usage_warning;
  if (usageWarn && !window.__USAGE_OVER_WARNED__) {
    window.__USAGE_OVER_WARNED__ = true;
    notifyChatRestriction(usageWarn, { showBillingLink: true });
  }
  const attachments = window.chatInput?.consumeAttachments() ?? [];
  const hasContent = window.chatInput?.hasPendingContent(text) ?? Boolean(text?.trim());
  if (!hasContent || isLoading) return;
  if (isSessionGenerating() && !isLoading) {
    window.NexNotify?.showError(
      window.t?.("chatGenerationInProgress") || "このセッションでは既に生成が進行中です"
    );
    return;
  }

  if (!getCurrentChat()) {
    createSessionOnFirstMessage();
  }
  const chat = getCurrentChat();
  if (!chat) return;

  const apiContent = window.chatInput?.buildUserContentForApi(text, attachments) ?? text;
  const displayText = window.chatInput?.buildUserDisplayText(text, attachments) ?? text;

  const userCreatedAt = messageTimestampNow();
  const userMessage = {
    role: "user",
    content: apiContent,
    created_at: userCreatedAt,
  };
  markLocalMutation(4000);
  chat.messages.push(userMessage);
  saveChats(chat);
  if (chat.messages.length === 1) {
    void generateSessionTitle(chat, displayText);
    navigateToChatSession(chat.id, { replace: true });
  }
  markSessionGenerating(chat.id);
  if (shouldUpdateSessionHistory(chat)) renderHistory();

  renderMessages();
  updatePrivateChatActiveUI();
  messageInput.value = "";
  autoResize();
  updateSendBtn();

  await requestAssistantReply(chat);
}

function autoResize() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + "px";
}

function updateSendBtn() {
  if (!sendBtn) return;
  const trimmed = messageInput.value.trim();
  const hasContent =
    window.chatInput?.hasPendingContent(messageInput.value) ?? trimmed.length > 0;

  const generating = isSessionGenerating();
  sendBtn.classList.toggle("is-generating", generating);
  if (generating) {
    sendBtn.classList.add("active");
    sendBtn.disabled = false;
    sendBtn.setAttribute("aria-label", "停止");
    return;
  }

  if (activeUserMessageEdit) {
    const changed = trimmed !== activeUserMessageEdit.originalText.trim();
    const canSend = hasContent && changed && canSendInSession();
    sendBtn.classList.toggle("active", canSend);
    sendBtn.disabled = !canSend;
    sendBtn.setAttribute("aria-label", "編集を送信");
    return;
  }

  sendBtn.classList.toggle("active", hasContent && canSendInSession());
  sendBtn.disabled = !hasContent || !canSendInSession();
  sendBtn.setAttribute("aria-label", "送信");
}

window.updateSendBtn = updateSendBtn;

function isChatViewActive() {
  return window.NexRouter?.getActiveView?.() === "chat";
}

function setActiveSession(id) {
  currentChatId = id || null;
  window.__SESSION_ID__ = id || null;
  if (window.__SHARED_CHAT__?.session_id === id) {
    applySessionAccess(window.__SHARED_CHAT__);
  } else if (!id) {
    applySessionAccess({
      owner: currentUser.username,
      role: "owner",
      permissions: ["view", "chat", "edit_settings", "manage_share"],
      collab_mode: "private",
    });
  }
  renderHistory();
  updatePrivateChatActiveUI();
  syncSessionCollaborationUI();
  window.updateChatInputIndicators?.();
}

async function loadSessionContent(id) {
  cancelUserMessageEdit();
  if (!id) {
    resetChatShareState();
    showWelcome();
    updatePrivateChatActiveUI();
    return;
  }

  if (isLoading && id === currentChatId) {
    updatePrivateChatActiveUI();
    return;
  }

  if (currentPrivateChat?.id === id) {
    resetChatShareState();
    currentChatId = id;
    window.__SESSION_ID__ = id;
    loadedChats.set(id, currentPrivateChat);
    updatePrivateChatActiveUI();
    if (!currentPrivateChat.messages?.length) {
      showWelcome();
      return;
    }
    renderMessages();
    return;
  }

  let fromStorage = readMessagesFromStorage(id);
  let hasIndexEntry = sessions.some((s) => s.id === id);
  const sharedOwner =
    window.__SHARED_CHAT__?.session_id === id ? window.__SHARED_CHAT__.owner : null;

  if (sharedOwner) {
    try {
      const params = new URLSearchParams({
        owner: sharedOwner,
        session_id: id,
      });
      const res = await fetch(`/api/chat/collab/session?${params}`);
      const remote = await res.json().catch(() => ({}));
      if (res.ok) {
        if (remote.access) applySessionAccess(remote.access);
        if (remote.settings) applySessionSettings(remote.settings, { remote: true });
        if (Array.isArray(remote.messages) && remote.messages.length) {
          fromStorage = writeMessagesToStorage(id, remote.messages);
        }
        if (remote.session) {
          if (!sessions.some((s) => s.id === id)) {
            sessions.unshift({
              id,
              title: remote.session.title || DEFAULT_SESSION_TITLE,
              updated_at: remote.session.updated_at || messageTimestampNow(),
              _shared: true,
            });
            saveSessionsIndex();
          }
          hasIndexEntry = true;
        }
      }
    } catch (err) {
      console.warn("shared session fetch failed", err);
    }
  }

  if (!fromStorage.length && hasIndexEntry) {
    try {
      const remote = await fetchSessionFromServer(id);
      if (remote === null) {
        hasIndexEntry = false;
      } else {
        if (remote.session) applyServerSessionMeta(remote.session);
        if (remote.messages.length) {
          fromStorage = writeMessagesToStorage(id, remote.messages);
        }
      }
    } catch (err) {
      console.warn("chat messages fetch failed", err);
    }
  }

  if (!hasIndexEntry && fromStorage.length === 0 && !loadedChats.has(id)) {
    try {
      const remote = await fetchSessionFromServer(id);
      if (remote?.messages?.length) {
        fromStorage = writeMessagesToStorage(id, remote.messages);
        if (remote.session) {
          applyServerSessionMeta(remote.session);
        } else {
          const meta = {
            id,
            title: DEFAULT_SESSION_TITLE,
            updated_at: latestMessageTimestamp(remote.messages) || messageTimestampNow(),
          };
          if (!sessions.some((s) => s.id === id)) {
            sessions.unshift(meta);
            saveSessionsIndex();
          }
        }
        hasIndexEntry = true;
      }
    } catch (err) {
      console.warn("chat messages fetch failed", err);
    }
  }

  if (!hasIndexEntry && fromStorage.length === 0 && !loadedChats.has(id)) {
    currentChatId = null;
    renderHistory();
    if (window.NexRouter) {
      window.NexRouter.navigate("/chat", { replace: true });
    } else {
      history.replaceState(null, "", "/chat");
      showWelcome();
    }
    return;
  }

  const cached = loadedChats.get(id);
  if (cached?.messages?.length > fromStorage.length) {
    writeMessagesToStorage(id, cached.messages);
    fromStorage = cached.messages;
  } else {
    loadedChats.delete(id);
  }
  const chat = loadChatById(id, { preferStorage: true });
  currentChatId = id;
  window.__SESSION_ID__ = id;

  if (!chat.messages?.length) {
    showWelcome();
    return;
  }
  renderMessages();
  updatePrivateChatActiveUI();
  updateChatSessionTitleBar();
  fetchChatShareState();
  fetchChatCollabState();
  syncSessionCollaborationUI();
}

async function loadSession(id) {
  await ensureChatSessionsReady();
  setActiveSession(id || null);
  if (!id) {
    if (isChatViewActive()) await loadSessionContent(null);
    return;
  }
  if (!isChatViewActive()) return;
  await loadSessionContent(id);
  window.NexChatSocket?.joinSession?.(id, getSessionOwner(id));
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".history-item-menu-wrap")) {
    closeHistoryMenus();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (activeUserMessageEdit) {
      cancelUserMessageEdit();
      e.preventDefault();
      return;
    }
    closeHistoryMenus();
  }
});

messageEditNoticeCancel?.addEventListener("click", () => {
  cancelUserMessageEdit();
});

window.chatApp = { loadSession, renderHistory, setActiveSession, canSendInSession };

chatArea?.addEventListener("scroll", onChatAreaScroll, { passive: true });
chatArea?.addEventListener(
  "wheel",
  (e) => {
    if (e.deltaY >= 0) return;
    if (isChatGenerationScrollActive()) {
      if (e.deltaY < -48) {
        chatStickToBottom = false;
        updateChatScrollButton();
      }
      return;
    }
    chatStickToBottom = false;
    updateChatScrollButton();
  },
  { passive: true }
);
let chatTouchLastY = null;
chatArea?.addEventListener(
  "touchstart",
  (e) => {
    chatTouchLastY = e.touches[0]?.clientY ?? null;
  },
  { passive: true }
);
chatArea?.addEventListener(
  "touchmove",
  (e) => {
    const y = e.touches[0]?.clientY;
    if (chatTouchLastY != null && y != null && y > chatTouchLastY + 4) {
      const delta = y - chatTouchLastY;
      if (!isChatGenerationScrollActive() || delta > 24) {
        chatStickToBottom = false;
        updateChatScrollButton();
      }
    }
    if (y != null) chatTouchLastY = y;
  },
  { passive: true }
);
chatScrollToBottomBtn?.addEventListener("click", () => {
  scrollChatToBottom(true);
});

messageInput.addEventListener("input", () => {
  autoResize();
  updateSendBtn();
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey) return;
  if (e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  sendMessage(messageInput.value);
});

sendBtn.addEventListener("click", () => {
  if (isLoading) {
    stopGeneration();
    return;
  }
  sendMessage(messageInput.value);
});

if (newChatBtn) {
  newChatBtn.addEventListener("click", navigateToNewChat);
}

// Session search
function applyHistorySearch(query) {
  historySearchQuery = query.trim();
  historyVisibleCount = HISTORY_PAGE_SIZE;
  renderHistory();
  if (sidebarSessionSearchClear) {
    sidebarSessionSearchClear.classList.toggle("hidden", !historySearchQuery);
  }
}

if (sidebarSessionSearchInput) {
  sidebarSessionSearchInput.addEventListener("input", () => {
    clearTimeout(historySearchTimer);
    historySearchTimer = setTimeout(() => {
      applyHistorySearch(sidebarSessionSearchInput.value);
    }, 200);
  });
  sidebarSessionSearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      sidebarSessionSearchInput.value = "";
      applyHistorySearch("");
      sidebarSessionSearchInput.blur();
    }
  });
}

if (sidebarSessionSearchClear) {
  sidebarSessionSearchClear.addEventListener("click", () => {
    sidebarSessionSearchInput.value = "";
    applyHistorySearch("");
    sidebarSessionSearchInput.focus();
  });
}

document.querySelectorAll(".suggestion").forEach((btn) => {
  btn.addEventListener("click", () => {
    sendMessage(btn.dataset.prompt);
  });
});

privateChatEnabled = loadPrivateChatPref();
syncPrivateChatToggleUI();

if (privateChatToggle) {
  privateChatToggle.addEventListener("change", () => {
    if (!shouldShowPrivateChatToggle()) {
      privateChatToggle.checked = privateChatEnabled;
      return;
    }
    privateChatEnabled = privateChatToggle.checked;
    savePrivateChatPref(privateChatEnabled);
    syncPrivateChatToggleUI();
  });
}

if (chatShareBtn) {
  chatShareBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleChatSharePanel();
  });
}

if (chatSharePanel) {
  chatSharePanel.addEventListener("click", (e) => e.stopPropagation());
}

if (chatShareVisibility) {
  chatShareVisibility.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-share-visibility-btn");
    if (!btn?.dataset.visibility) return;
    updateChatShareVisibility(btn.dataset.visibility);
  });
}

if (chatShareCopyBtn) {
  chatShareCopyBtn.addEventListener("click", () => {
    copyChatShareLink();
  });
}

if (chatShareCollab) {
  chatShareCollab.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-share-collab-btn");
    if (!btn?.dataset.collabMode) return;
    if (btn.dataset.collabMode === "private") {
      updateChatCollabMode("private");
      return;
    }
    updateChatCollabMode(btn.dataset.collabMode);
  });
}

if (chatShareCollabCopyBtn) {
  chatShareCollabCopyBtn.addEventListener("click", () => {
    copyChatCollabLink();
  });
}

initChatRealtimeSync();

document.addEventListener("click", closeChatSharePanel);

// ── Report Overlay ────────────────────────────────────────

function openReportOverlay() {
  // Remove existing overlay if any
  const existing = document.querySelector(".report-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.className = "report-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "reportOverlayTitle");
  overlay.innerHTML = `
    <div class="report-overlay-backdrop"></div>
    <div class="report-dialog">
      <div class="report-dialog-header">
        <h2 id="reportOverlayTitle" class="report-dialog-title">問題を報告する</h2>
        <button type="button" class="report-dialog-close" aria-label="閉じる">&times;</button>
      </div>
      <div class="report-dialog-body">
        <label for="reportDescription" class="report-label">具体的にどのような問題ですか？</label>
        <textarea id="reportDescription" class="report-textarea" rows="5" maxlength="2000" placeholder="問題の詳細を入力してください…"></textarea>
        <p class="report-hint">内容が外部へ公開されることはありません</p>
      </div>
      <div class="report-dialog-footer">
        <button type="button" class="report-cancel-btn">キャンセル</button>
        <button type="button" class="report-submit-btn" disabled>送信する</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  document.body.classList.add("report-open");

  const textarea = overlay.querySelector("#reportDescription");
  const submitBtn = overlay.querySelector(".report-submit-btn");
  const cancelBtn = overlay.querySelector(".report-cancel-btn");
  const closeBtn = overlay.querySelector(".report-dialog-close");
  const backdrop = overlay.querySelector(".report-overlay-backdrop");

  const closeOverlay = () => {
    document.body.classList.remove("report-open");
    overlay.remove();
  };

  textarea.addEventListener("input", () => {
    submitBtn.disabled = !textarea.value.trim();
  });

  cancelBtn.addEventListener("click", closeOverlay);
  closeBtn.addEventListener("click", closeOverlay);
  backdrop.addEventListener("click", closeOverlay);

  submitBtn.addEventListener("click", async () => {
    const description = textarea.value.trim();
    if (!description) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "送信中…";

    try {
      const chat = getCurrentChat();
      const sessionId = chat?.id || "";
      const res = await fetch("/api/chat/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, session_id: sessionId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "送信に失敗しました");

      window.NexNotify?.showSuccess("ご協力ありがとうございます");
      closeOverlay();
    } catch (e) {
      window.NexNotify?.showError(e.message || "送信に失敗しました");
      submitBtn.disabled = false;
      submitBtn.textContent = "送信する";
    }
  });

  // Focus textarea
  setTimeout(() => textarea.focus(), 100);
}

updateSendBtn();
syncChatWelcomeLayout();

const initialPlanBlock = getPlanChatBlockMessage();
if (initialPlanBlock) {
  notifyChatRestriction(initialPlanBlock, {
    showBillingLink: /プラン|課金|アップグレード/.test(initialPlanBlock),
  });
} else if (window.getSystemFeatures?.().chat_disabled) {
  notifyChatRestriction("現在、チャットは制限されています", { showBillingLink: false });
}
