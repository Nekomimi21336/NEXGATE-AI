(function () {
  const KIND_LABELS = {
    turn_start: "Turn start",
    model_request: "Model request",
    assistant_stream: "Output stream",
    tool_invoke: "Tool invoke",
    tool_result: "Tool result",
    tool_trace: "Tool trace",
    reasoning: "Reasoning",
    expert_crawl: "Expert crawl",
    search: "Web search",
    fetch: "Web fetch",
    segment: "Segment",
    turn_done: "Turn done",
    error: "Error",
    expert_knowledge_updated: "Knowledge updated",
  };

  let panelEl = null;
  let logEl = null;
  let turnCount = 0;
  let streamEntry = null;
  let streamBodyEl = null;
  let streamText = "";
  let reasoningEntry = null;
  let reasoningBodyEl = null;
  let reasoningText = "";

  function t(key) {
    return window.t?.(key) || key;
  }

  function enabled() {
    return window.__USER__?.full_info_display_enabled === true;
  }

  function esc(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function formatPayload(data) {
    if (data == null) return "";
    if (typeof data === "string") return data;
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  }

  function formatEntryBody(data) {
    const kind = data.kind || "event";
    const parts = [];
    if (kind === "model_request") {
      if (data.label) parts.push(`label: ${data.label}`);
      if (data.model) parts.push(`model: ${data.model}`);
      if (data.tools?.length) parts.push(`tools: ${data.tools.join(", ")}`);
      if (data.messages) parts.push(formatPayload(data.messages));
    } else if (kind === "turn_start") {
      parts.push(formatPayload(data.messages));
    } else if (kind === "assistant_stream") {
      parts.push(data.text || "");
    } else if (kind === "tool_invoke") {
      parts.push(`name: ${data.name || ""}`);
      parts.push(`id: ${data.tool_call_id || ""}`);
      parts.push(formatPayload(data.arguments));
    } else if (kind === "tool_result") {
      parts.push(`name: ${data.name || ""}`);
      parts.push(`id: ${data.tool_call_id || ""}`);
      parts.push(formatPayload(data.content));
    } else if (kind === "tool_trace") {
      parts.push(formatPayload(data));
    } else if (kind === "reasoning" || kind === "expert_crawl") {
      parts.push(formatPayload(data.data));
    } else if (kind === "search" || kind === "fetch") {
      parts.push(data.data || "");
    } else if (kind === "segment") {
      parts.push(`phase: ${data.phase || ""}`);
      if (data.discard_previous != null) {
        parts.push(`discard_previous: ${data.discard_previous}`);
      }
    } else if (kind === "turn_done") {
      parts.push(formatPayload(data.usage));
    } else if (kind === "error") {
      parts.push(data.message || "");
    } else {
      parts.push(formatPayload(data));
    }
    return parts.filter(Boolean).join("\n");
  }

  function resetBuffers() {
    streamEntry = null;
    streamBodyEl = null;
    streamText = "";
    reasoningEntry = null;
    reasoningBodyEl = null;
    reasoningText = "";
  }

  function destroyPanel() {
    panelEl?.remove();
    panelEl = null;
    logEl = null;
    resetBuffers();
    document.documentElement.classList.remove("full-info-panel-open");
  }

  function ensurePanel() {
    if (!enabled()) {
      destroyPanel();
      return null;
    }
    if (panelEl) return panelEl;

    panelEl = document.createElement("aside");
    panelEl.id = "fullInfoPanel";
    panelEl.className = "full-info-panel";
    panelEl.setAttribute("aria-label", t("fullInfoPanelTitle"));
    panelEl.innerHTML = `
      <div class="full-info-panel-head">
        <span class="full-info-panel-title">${esc(t("fullInfoPanelTitle"))}</span>
        <button type="button" class="full-info-panel-clear">${esc(t("fullInfoPanelClear"))}</button>
      </div>
      <div class="full-info-panel-log" tabindex="0"></div>
    `;
    logEl = panelEl.querySelector(".full-info-panel-log");
    panelEl.querySelector(".full-info-panel-clear")?.addEventListener("click", () => {
      if (logEl) logEl.innerHTML = "";
      turnCount = 0;
      resetBuffers();
    });
    document.body.appendChild(panelEl);
    document.documentElement.classList.add("full-info-panel-open");
    return panelEl;
  }

  function createEntryShell(kind) {
    const entry = document.createElement("div");
    entry.className = `full-info-entry full-info-entry--${kind.replace(/[^a-z0-9_-]/gi, "-")}`;
    const time = new Date().toLocaleTimeString();
    const label = KIND_LABELS[kind] || kind;
    entry.innerHTML = `
      <div class="full-info-entry-head">
        <span class="full-info-entry-kind">${esc(label)}</span>
        <time class="full-info-entry-time">${esc(time)}</time>
      </div>
      <pre class="full-info-entry-body"></pre>
    `;
    return entry;
  }

  function finalizeStreamBuffers() {
    streamEntry = null;
    streamBodyEl = null;
    streamText = "";
    reasoningEntry = null;
    reasoningBodyEl = null;
    reasoningText = "";
  }

  function appendStreamChunk(text) {
    if (!text) return;
    ensurePanel();
    if (!logEl) return;
    if (!streamEntry) {
      streamEntry = createEntryShell("assistant_stream");
      streamBodyEl = streamEntry.querySelector(".full-info-entry-body");
      logEl.appendChild(streamEntry);
    }
    streamText += text;
    if (streamBodyEl) streamBodyEl.textContent = streamText;
    logEl.scrollTop = logEl.scrollHeight;
  }

  function appendReasoningChunk(data) {
    ensurePanel();
    if (!logEl) return;
    const piece =
      data?.type === "delta"
        ? String(data.text || "")
        : formatPayload(data);
    if (!piece) return;
    if (!reasoningEntry) {
      reasoningEntry = createEntryShell("reasoning");
      reasoningBodyEl = reasoningEntry.querySelector(".full-info-entry-body");
      logEl.appendChild(reasoningEntry);
    }
    reasoningText += piece;
    if (reasoningBodyEl) reasoningBodyEl.textContent = reasoningText;
    logEl.scrollTop = logEl.scrollHeight;
  }

  function appendEntry(data) {
    if (!enabled() || !data) return;
    const kind = data.kind || "event";

    if (kind === "assistant_stream") {
      appendStreamChunk(data.text || "");
      return;
    }

    if (kind === "reasoning") {
      appendReasoningChunk(data.data);
      return;
    }

    finalizeStreamBuffers();
    ensurePanel();
    if (!logEl) return;

    const entry = createEntryShell(kind);
    const bodyEl = entry.querySelector(".full-info-entry-body");
    if (bodyEl) bodyEl.textContent = formatEntryBody(data);
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function onTurnStart() {
    if (!enabled()) return;
    turnCount += 1;
    ensurePanel();
    if (!logEl) return;
    const marker = document.createElement("div");
    marker.className = "full-info-turn-marker";
    marker.textContent = `— ${t("fullInfoPanelTurn")} ${turnCount} —`;
    logEl.appendChild(marker);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function handleSseData(data) {
    if (!data?.chat_full_info) return;
    const kind = data.chat_full_info.kind;
    if (kind === "turn_start" || kind === "segment") {
      finalizeStreamBuffers();
    }
    if (kind === "turn_start") {
      onTurnStart();
    }
    appendEntry(data.chat_full_info);
  }

  function refresh() {
    if (enabled()) ensurePanel();
    else destroyPanel();
  }

  window.NexFullInfoPanel = {
    enabled,
    refresh,
    handleSseData,
    onTurnStart,
    clear: () => {
      if (logEl) logEl.innerHTML = "";
      turnCount = 0;
      resetBuffers();
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refresh);
  } else {
    refresh();
  }
})();
