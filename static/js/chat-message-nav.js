(function () {
  const PREVIEW_MAX = 22;
  const navEl = document.getElementById("chatMessageNav");
  const listEl = document.getElementById("chatMessageNavList");
  const messagesEl = document.getElementById("messages");
  const welcomeEl = document.getElementById("welcome");
  let refreshTimer = 0;
  let lastNavSignature = "";
  let navRefreshPausedUntil = 0;

  if (!navEl || !listEl || !messagesEl) return;

  function isChatVisible() {
    return (
      document.getElementById("view-chat")?.classList.contains("is-active") &&
      !messagesEl.classList.contains("hidden") &&
      (!welcomeEl || welcomeEl.classList.contains("hidden"))
    );
  }

  function buildPreview(messageEl) {
    const cached = messageEl.dataset.navPreview;
    if (cached) return cached;

    const contentEl = messageEl.querySelector(".message-content");
    if (!contentEl) return "…";
    let text = contentEl.textContent.replace(/\s+/g, " ").trim();
    if (!text) text = "あなたの発言";
    const preview =
      text.length <= PREVIEW_MAX ? text : `${text.slice(0, PREVIEW_MAX)}…`;
    messageEl.dataset.navPreview = preview;
    return preview;
  }

  function collectNavItems() {
    return Array.from(
      messagesEl.querySelectorAll(".message.user[data-message-index]")
    )
      .map((el) => {
        const index = Number(el.dataset.messageIndex);
        if (!Number.isFinite(index)) return null;
        return {
          index,
          preview: buildPreview(el),
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.index - b.index);
  }

  function navSignature(items) {
    return items.map((item) => `${item.index}\u0001${item.preview}`).join("\u0002");
  }

  function renderNav() {
    if (Date.now() < navRefreshPausedUntil) return;

    const items = collectNavItems();
    if (!isChatVisible() || items.length === 0) {
      lastNavSignature = "";
      navEl.classList.add("hidden");
      listEl.innerHTML = "";
      return;
    }

    const signature = navSignature(items);
    if (signature === lastNavSignature) return;
    lastNavSignature = signature;

    navEl.classList.remove("hidden");
    listEl.innerHTML = "";

    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "chat-message-nav-item chat-message-nav-item--user";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-message-nav-item-btn";
      btn.dataset.messageIndex = String(item.index);
      btn.setAttribute("aria-label", `あなた: ${item.preview}`);

      const dot = document.createElement("span");
      dot.className = "chat-message-nav-dot";
      dot.setAttribute("aria-hidden", "true");

      const label = document.createElement("span");
      label.className = "chat-message-nav-label";
      label.textContent = item.preview;

      btn.appendChild(dot);
      btn.appendChild(label);
      btn.addEventListener("click", () => {
        navRefreshPausedUntil = Date.now() + 1600;
        window.chatMessageScroll?.scrollToMessage?.(item.index);
      });

      li.appendChild(btn);
      listEl.appendChild(li);
    });
  }

  function scheduleRefresh() {
    if (Date.now() < navRefreshPausedUntil) return;
    if (refreshTimer) window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => {
      refreshTimer = 0;
      renderNav();
    }, 80);
  }

  function invalidateNavPreviewCache() {
    lastNavSignature = "";
    messagesEl
      .querySelectorAll(".message.user[data-nav-preview]")
      .forEach((el) => delete el.dataset.navPreview);
  }

  const observer = new MutationObserver((mutations) => {
    const structural = mutations.some(
      (m) => m.type === "childList" && (m.addedNodes.length || m.removedNodes.length)
    );
    if (!structural) return;
    invalidateNavPreviewCache();
    scheduleRefresh();
  });
  observer.observe(messagesEl, { childList: true, subtree: true });

  if (welcomeEl) {
    observer.observe(welcomeEl, {
      attributes: true,
      attributeFilter: ["class"],
    });
  }
  const viewChat = document.getElementById("view-chat");
  if (viewChat) {
    observer.observe(viewChat, {
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  welcomeEl?.addEventListener("transitionend", scheduleRefresh);

  window.chatMessageNav = {
    refresh() {
      invalidateNavPreviewCache();
      renderNav();
    },
  };
  scheduleRefresh();
})();
