function getSystemFeatures() {
  return window.__SYSTEM_FEATURES__ || {};
}

function applySystemFeatures(features) {
  if (features) window.__SYSTEM_FEATURES__ = features;
  const f = getSystemFeatures();

  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");

  window.chatInput?.syncAttachButtonState?.();

  const embedWebSearch = document.getElementById("embedWebSearchEnabled");
  if (embedWebSearch) {
    if (typeof window.syncEmbedFormFromUser === "function") {
      window.syncEmbedFormFromUser();
    } else {
      embedWebSearch.disabled = Boolean(f.search_disabled);
    }
  }

  window.chatInput?.refreshIntelligentSearchIndicator?.();

  const chatBlocked = Boolean(f.chat_disabled);
  if (messageInput) {
    messageInput.disabled = chatBlocked;
    messageInput.placeholder = chatBlocked
      ? "チャットは現在制限されています"
      : messageInput.dataset.defaultPlaceholder || "メッセージを入力...";
  }
  if (sendBtn) sendBtn.disabled = chatBlocked;
}

if (document.getElementById("messageInput") && !document.getElementById("messageInput").dataset.defaultPlaceholder) {
  document.getElementById("messageInput").dataset.defaultPlaceholder =
    document.getElementById("messageInput").placeholder;
}

applySystemFeatures(getSystemFeatures());
window.applySystemFeatures = applySystemFeatures;
window.getSystemFeatures = getSystemFeatures;
