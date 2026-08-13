(function () {
  let socket = null;
  let socketReady = false;
  let reconnectTimer = null;
  let pingTimer = null;
  let joinedSessionId = null;
  let joinedOwner = null;
  const pendingRequests = new Map();
  const eventListeners = new Set();
  let activeRequestId = null;

  function socketUrl() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${location.host}/ws/chat`;
  }

  function currentUsername() {
    return (window.__USER__?.username || "").trim().toLowerCase();
  }

  function send(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }

  function emitToListeners(message) {
    eventListeners.forEach((fn) => {
      try {
        fn(message);
      } catch (e) {
        console.error(e);
      }
    });
  }

  function resolveResponse(data) {
    if (data.type !== "response" || !data.request_id) return false;
    const pending = pendingRequests.get(data.request_id);
    if (!pending) return false;
    window.clearTimeout(pending.timer);
    pendingRequests.delete(data.request_id);
    if (data.ok) pending.resolve(data.data ?? data);
    else pending.reject(new Error(data.error || "request failed"));
    return true;
  }

  function handleMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (resolveResponse(data)) return;
    if (data.type === "chat.accepted" && data.request_id) {
      activeRequestId = data.request_id;
    }
    if (data.type === "chat.status" && data.request_id === activeRequestId) {
      if (data.status && data.status !== "running") {
        activeRequestId = null;
      }
    }
    emitToListeners(data);
  }

  function startPing() {
    stopPing();
    pingTimer = window.setInterval(() => send({ action: "ping" }), 25000);
  }

  function stopPing() {
    if (pingTimer) {
      window.clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, 2000);
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    socket = new WebSocket(socketUrl());
    socket.onopen = () => {
      socketReady = true;
      startPing();
      if (joinedSessionId) {
        send({
          action: "join",
          session_id: joinedSessionId,
          owner: joinedOwner || currentUsername(),
        });
      }
    };
    socket.onmessage = handleMessage;
    socket.onclose = () => {
      socketReady = false;
      stopPing();
      socket = null;
      scheduleReconnect();
    };
    socket.onerror = () => {};
  }

  function ensureReady(timeoutMs = 8000) {
    if (socketReady) return Promise.resolve();
    connect();
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
          reject(new Error("WebSocket に接続できません"));
        }
      }, 40);
    });
  }

  async function wsRequest(action, payload = {}, { timeout = 30000 } = {}) {
    await ensureReady();
    return new Promise((resolve, reject) => {
      const requestId = crypto.randomUUID?.() || String(Date.now());
      const timer = window.setTimeout(() => {
        pendingRequests.delete(requestId);
        reject(new Error("リクエストがタイムアウトしました"));
      }, timeout);
      pendingRequests.set(requestId, { resolve, reject, timer, action });
      if (!send({ action, request_id: requestId, ...payload })) {
        window.clearTimeout(timer);
        pendingRequests.delete(requestId);
        reject(new Error("WebSocket に接続できません"));
      }
    });
  }

  function joinSession(sessionId, owner) {
    const sid = String(sessionId || "").trim();
    if (!sid) return;
    const own = String(owner || currentUsername() || "").trim().toLowerCase();
    if (joinedSessionId === sid && joinedOwner === own) {
      if (!socketReady) connect();
      return;
    }
    if (joinedSessionId && (joinedSessionId !== sid || joinedOwner !== own)) {
      send({
        action: "leave",
        session_id: joinedSessionId,
        owner: joinedOwner || currentUsername(),
      });
    }
    joinedSessionId = sid;
    joinedOwner = own;
    if (socketReady) {
      send({ action: "join", session_id: sid, owner: own });
    } else {
      connect();
    }
  }

  function leaveSession(sessionId, owner) {
    const sid = String(sessionId || "").trim();
    if (!sid) return;
    const own = String(owner || joinedOwner || currentUsername() || "").trim().toLowerCase();
    send({ action: "leave", session_id: sid, owner: own });
    if (joinedSessionId === sid && joinedOwner === own) {
      joinedSessionId = null;
      joinedOwner = null;
    }
  }

  function getJoinedSession() {
    return joinedSessionId
      ? { session_id: joinedSessionId, owner: joinedOwner || currentUsername() }
      : null;
  }

  function waitForRequest(requestId, timeoutMs = 600000) {
    return new Promise((resolve, reject) => {
      let finished = false;
      const finish = (err, result) => {
        if (finished) return;
        finished = true;
        off();
        if (err) reject(err);
        else resolve(result);
      };
      const onEvent = (msg) => {
        if (msg.request_id !== requestId) return;
        if (msg.type === "chat.error") {
          finish(new Error(msg.error || "エラーが発生しました"));
          return;
        }
        if (msg.type === "chat.status" && msg.status && msg.status !== "running") {
          finish(null, {
            status: msg.status,
            paused: Boolean(msg.paused_for_user),
            usage: msg.usage,
            assistant_content: msg.assistant_content || "",
          });
        }
      };
      const off = () => eventListeners.delete(onEvent);
      eventListeners.add(onEvent);
      window.setTimeout(() => finish(new Error("タイムアウトしました")), timeoutMs);
    });
  }

  async function sendChat(body) {
    await ensureReady();
    const owner = body.owner || currentUsername();
    const payload = {
      action: "chat.send",
      ...body,
      owner,
    };
    if (!send(payload)) {
      throw new Error("WebSocket に接続できません");
    }
    const accepted = new Promise((resolve, reject) => {
      const cleanup = () => {
        window.clearTimeout(timer);
        eventListeners.delete(onAccept);
        eventListeners.delete(onFail);
      };
      const timer = window.setTimeout(() => {
        cleanup();
        reject(new Error("リクエストの受付がタイムアウトしました"));
      }, 30000);
      const onFail = (msg) => {
        if (msg.type !== "chat.error") return;
        cleanup();
        const err = new Error(msg.error || "エラーが発生しました");
        err.code = msg.code;
        err.active_request_id = msg.active_request_id;
        reject(err);
      };
      const onAccept = (msg) => {
        if (msg.type !== "chat.accepted" || !msg.request_id) return;
        cleanup();
        resolve(msg.request_id);
      };
      eventListeners.add(onAccept);
      eventListeners.add(onFail);
    });
    const rid = await accepted;
    return { request_id: rid, completion: waitForRequest(rid) };
  }

  async function resumeUserQuestions(body) {
    await ensureReady();
    const payload = {
      action: "chat.resume",
      ...body,
      owner: body.owner || currentUsername(),
    };
    if (!send(payload)) {
      throw new Error("WebSocket に接続できません");
    }
    const accepted = new Promise((resolve, reject) => {
      const cleanup = () => {
        window.clearTimeout(timer);
        eventListeners.delete(onAccept);
        eventListeners.delete(onFail);
      };
      const timer = window.setTimeout(() => {
        cleanup();
        reject(new Error("再開リクエストがタイムアウトしました"));
      }, 30000);
      const onFail = (msg) => {
        if (msg.type !== "chat.error") return;
        cleanup();
        reject(new Error(msg.error || "エラーが発生しました"));
      };
      const onAccept = (msg) => {
        if (msg.type !== "chat.accepted" || !msg.request_id) return;
        cleanup();
        resolve(msg.request_id);
      };
      eventListeners.add(onAccept);
      eventListeners.add(onFail);
    });
    const rid = await accepted;
    return { request_id: rid, completion: waitForRequest(rid) };
  }

  async function sessionSave(sessionId, patch, owner) {
    const sid = String(sessionId || "").trim();
    if (!sid || !patch) return null;
    return wsRequest("session.save", {
      session_id: sid,
      owner: owner || joinedOwner || currentUsername(),
      patch,
    });
  }

  async function updateCollabShare(sessionId, collabMode, owner) {
    const sid = String(sessionId || "").trim();
    if (!sid) return null;
    return wsRequest("session.share", {
      session_id: sid,
      owner: owner || currentUsername(),
      collab_mode: collabMode,
    });
  }

  function stop(requestId) {
    const rid = requestId || activeRequestId;
    if (!rid) return;
    send({ action: "chat.stop", request_id: rid });
  }

  function onEvent(listener) {
    eventListeners.add(listener);
    return () => eventListeners.delete(listener);
  }

  function replaySnapshot(snapshot, handler) {
    if (!snapshot || snapshot.type !== "chat.snapshot" || !Array.isArray(snapshot.events)) return;
    snapshot.events.forEach((entry) => {
      if (entry?.data) {
        handler({
          type: "chat.event",
          request_id: snapshot.request_id,
          owner: snapshot.owner,
          session_id: snapshot.session_id,
          data: entry.data,
        });
      }
    });
  }

  window.NexChatSocket = {
    connect,
    ensureReady,
    joinSession,
    leaveSession,
    getJoinedSession,
    sendChat,
    resumeUserQuestions,
    sessionSave,
    updateCollabShare,
    wsRequest,
    stop,
    onEvent,
    replaySnapshot,
    getActiveRequestId: () => activeRequestId,
  };

  if (document.body && !document.body.classList.contains("auth-page")) {
    connect();
  }
})();
