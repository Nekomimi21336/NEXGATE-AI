(function () {

  if (window.__USER__?.tasks_enabled !== true) return;



  const CARD_TYPES = ["todo", "task", "list", "memo"];

  const STORAGE_PREFIX = "nexgate_tasks_";

  const SAVE_DELAY_MS = 280;

  const CARD_WIDTH = 260;

  const CARD_GAP = 16;



  const boardInner = document.getElementById("tasksBoardInner");

  const tasksEmpty = document.getElementById("tasksEmpty");

  const tasksAddBtn = document.getElementById("tasksAddBtn");

  const tasksTypeMenu = document.getElementById("tasksTypeMenu");

  const tasksArrangeBtn = document.getElementById("tasksArrangeBtn");



  if (!boardInner || !tasksAddBtn) return;



  let state = { layoutMode: "free", cards: [] };

  let saveTimer = null;

  let dragState = null;

  let serverSyncReady = false;



  function storageKey() {

    return `${STORAGE_PREFIX}${window.__USER__?.username || "default"}`;

  }



  function t(key) {

    return window.t?.(key) || key;

  }



  function normalizeLoaded(parsed) {

    if (!parsed || !Array.isArray(parsed.cards)) return { layoutMode: "free", cards: [] };

    return {

      layoutMode: parsed.layoutMode === "grid" ? "grid" : "free",

      cards: parsed.cards.filter((c) => c && CARD_TYPES.includes(c.type)),

    };

  }



  function loadStateLocal() {

    try {

      const raw = localStorage.getItem(storageKey());

      if (!raw) return { layoutMode: "free", cards: [] };

      return normalizeLoaded(JSON.parse(raw));

    } catch {

      return { layoutMode: "free", cards: [] };

    }

  }



  async function fetchStateFromServer() {

    const res = await fetch("/api/tasks", { credentials: "same-origin" });

    if (!res.ok) return null;

    const data = await res.json();

    return normalizeLoaded(data);

  }



  async function persistStateToServer() {

    const res = await fetch("/api/tasks", {

      method: "PUT",

      headers: { "Content-Type": "application/json" },

      credentials: "same-origin",

      body: JSON.stringify(state),

    });

    return res.ok;

  }



  function scheduleSave() {

    clearTimeout(saveTimer);

    saveTimer = setTimeout(() => {

      try {

        localStorage.setItem(storageKey(), JSON.stringify(state));

      } catch (e) {}

      if (serverSyncReady) {

        persistStateToServer().catch(() => {});

      }

    }, SAVE_DELAY_MS);

  }



  function defaultPosition(index) {

    const col = index % 4;

    const row = Math.floor(index / 4);

    return {

      x: 24 + col * (CARD_WIDTH + CARD_GAP),

      y: 24 + row * (CARD_GAP + 120),

    };

  }



  function newItem(text) {

    return { id: window.newUuid(), text: text || "", done: false };

  }



  function createCard(type) {

    const index = state.cards.length;

    const pos = defaultPosition(index);

    const card = {

      id: window.newUuid(),

      type,

      title: "",

      body: "",

      items: type === "todo" || type === "list" ? [newItem("")] : [],

      x: pos.x,

      y: pos.y,

      createdAt: Date.now(),

    };

    state.cards.push(card);

    if (state.layoutMode === "grid") applyLayoutMode();

    scheduleSave();

    render();

    focusNewCard(card.id);

    return card;

  }



  function focusNewCard(id) {

    requestAnimationFrame(() => {

      const el = boardInner.querySelector(`[data-card-id="${id}"]`);

      const title = el?.querySelector(".tasks-card-title");

      const body = el?.querySelector(".tasks-card-memo, .tasks-card-notes");

      (title || body)?.focus();

    });

  }



  function removeCard(id) {

    state.cards = state.cards.filter((c) => c.id !== id);

    scheduleSave();

    render();

  }



  function findCard(id) {

    return state.cards.find((c) => c.id === id);

  }



  function applyLayoutMode() {

    boardInner.classList.toggle("tasks-board-inner--grid", state.layoutMode === "grid");

  }



  function arrangeCards() {

    state.layoutMode = "grid";

    scheduleSave();

    applyLayoutMode();

    render();

  }



  function setTypeMenuOpen(open) {

    tasksTypeMenu.classList.toggle("hidden", !open);

    tasksAddBtn.setAttribute("aria-expanded", open ? "true" : "false");

  }



  function typeLabel(type) {

    const map = {

      todo: "tasksCardTypeTodo",

      task: "tasksCardTypeTask",

      list: "tasksCardTypeList",

      memo: "tasksCardTypeMemo",

    };

    return t(map[type] || type);

  }



  function escapeHtml(s) {

    return String(s)

      .replace(/&/g, "&amp;")

      .replace(/</g, "&lt;")

      .replace(/>/g, "&gt;")

      .replace(/"/g, "&quot;");

  }



  function renderChecklist(card) {

    const items = card.items || [];

    const rows = items

      .map(

        (item) => `

      <li class="tasks-check-item" data-item-id="${escapeHtml(item.id)}">

        <label class="tasks-check-label">

          <input type="checkbox" class="tasks-check-input" data-action="toggle-item" ${item.done ? "checked" : ""} />

          <input type="text" class="tasks-check-text" data-action="item-text" value="${escapeHtml(item.text)}" placeholder="${escapeHtml(t("tasksItemPlaceholder"))}" />

        </label>

        <button type="button" class="tasks-check-remove" data-action="remove-item" data-i18n-aria="tasksRemoveItem" aria-label="${escapeHtml(t("tasksRemoveItem"))}">×</button>

      </li>`

      )

      .join("");

    return `

      <ul class="tasks-checklist">${rows}</ul>

      <button type="button" class="tasks-add-item-btn" data-action="add-item" data-card-id="${escapeHtml(card.id)}">${escapeHtml(t("tasksAddItem"))}</button>`;

  }



  function renderCard(card) {

    const style =

      state.layoutMode === "free" && Number.isFinite(card.x) && Number.isFinite(card.y)

        ? ` style="left:${card.x}px;top:${card.y}px"`

        : "";

    const showTitle = card.type !== "memo";

    const titleBlock = showTitle

      ? `<input type="text" class="tasks-card-title" data-action="title" value="${escapeHtml(card.title)}" placeholder="${escapeHtml(t("tasksTitlePlaceholder"))}" />`

      : "";

    let bodyHtml = "";

    if (card.type === "memo") {

      bodyHtml = `<textarea class="tasks-card-memo" data-action="body" rows="6" placeholder="${escapeHtml(t("tasksMemoPlaceholder"))}">${escapeHtml(card.body || card.title || "")}</textarea>`;

    } else if (card.type === "task") {

      bodyHtml = `<textarea class="tasks-card-notes" data-action="body" rows="4" placeholder="${escapeHtml(t("tasksNotesPlaceholder"))}">${escapeHtml(card.body)}</textarea>`;

    } else if (card.type === "todo" || card.type === "list") {

      bodyHtml = renderChecklist(card);

    }



    return `

      <article class="tasks-card tasks-card--${card.type}" data-card-id="${escapeHtml(card.id)}"${style}>

        <header class="tasks-card-header">

          <span class="tasks-card-type-badge">${escapeHtml(typeLabel(card.type))}</span>

          ${titleBlock}

          <button type="button" class="tasks-card-delete" data-action="delete" data-i18n-aria="tasksDeleteCard" aria-label="${escapeHtml(t("tasksDeleteCard"))}">×</button>

        </header>

        <div class="tasks-card-body">${bodyHtml}</div>

      </article>`;

  }



  function updateEmptyState() {

    const empty = state.cards.length === 0;

    tasksEmpty.classList.toggle("hidden", !empty);

  }



  function render() {

    const existing = boardInner.querySelectorAll(".tasks-card");

    existing.forEach((el) => el.remove());

    state.cards.forEach((card) => {

      const wrap = document.createElement("div");

      wrap.innerHTML = renderCard(card);

      const el = wrap.firstElementChild;

      boardInner.appendChild(el);

      bindCardEvents(el, card);

    });

    applyLayoutMode();

    updateEmptyState();

  }



  function bindCardEvents(cardEl, card) {

    if (state.layoutMode === "free") enableDrag(cardEl, card);



    cardEl.querySelector('[data-action="delete"]')?.addEventListener("click", () => removeCard(card.id));



    cardEl.querySelector('[data-action="title"]')?.addEventListener("input", (e) => {

      card.title = e.target.value;

      scheduleSave();

    });



    const bodyEl = cardEl.querySelector('[data-action="body"]');

    if (bodyEl) {

      bodyEl.addEventListener("input", (e) => {

        card.body = e.target.value;

        if (card.type === "memo") card.title = card.body.slice(0, 80);

        scheduleSave();

      });

    }



    cardEl.querySelector('[data-action="add-item"]')?.addEventListener("click", () => {

      card.items.push(newItem(""));

      scheduleSave();

      render();

      focusNewCard(card.id);

    });



    cardEl.querySelectorAll('[data-action="toggle-item"]').forEach((input) => {

      input.addEventListener("change", () => {

        const row = input.closest(".tasks-check-item");

        const itemId = row?.dataset.itemId;

        const item = card.items.find((i) => i.id === itemId);

        if (item) {

          item.done = input.checked;

          scheduleSave();

        }

      });

    });



    cardEl.querySelectorAll('[data-action="item-text"]').forEach((input) => {

      input.addEventListener("input", () => {

        const row = input.closest(".tasks-check-item");

        const itemId = row?.dataset.itemId;

        const item = card.items.find((i) => i.id === itemId);

        if (item) {

          item.text = input.value;

          scheduleSave();

        }

      });

      input.addEventListener("keydown", (e) => {

        if (e.key !== "Enter") return;

        e.preventDefault();

        const row = input.closest(".tasks-check-item");

        const itemId = row?.dataset.itemId;

        const idx = card.items.findIndex((i) => i.id === itemId);

        card.items.splice(idx + 1, 0, newItem(""));

        scheduleSave();

        render();

        focusNewCard(card.id);

      });

    });



    cardEl.querySelectorAll('[data-action="remove-item"]').forEach((btn) => {

      btn.addEventListener("click", () => {

        const row = btn.closest(".tasks-check-item");

        const itemId = row?.dataset.itemId;

        card.items = card.items.filter((i) => i.id !== itemId);

        if (card.items.length === 0) card.items.push(newItem(""));

        scheduleSave();

        render();

      });

    });

  }



  function enableDrag(cardEl, card) {

    const header = cardEl.querySelector(".tasks-card-header");

    if (!header) return;

    header.style.cursor = "grab";



    header.addEventListener("pointerdown", (e) => {

      if (e.button !== 0) return;

      if (e.target.closest("input, textarea, button")) return;

      e.preventDefault();

      if (state.layoutMode !== "free") {

        state.layoutMode = "free";

        scheduleSave();

      }

      boardInner.classList.remove("tasks-board-inner--grid");

      const boardRect = boardInner.getBoundingClientRect();

      const rect = cardEl.getBoundingClientRect();

      const startLeft = card.x ?? rect.left - boardRect.left + boardInner.scrollLeft;

      const startTop = card.y ?? rect.top - boardRect.top + boardInner.scrollTop;

      dragState = {

        card,

        cardEl,

        pointerId: e.pointerId,

        startX: e.clientX,

        startY: e.clientY,

        startLeft,

        startTop,

      };

      card.x = startLeft;

      card.y = startTop;

      cardEl.style.left = `${startLeft}px`;

      cardEl.style.top = `${startTop}px`;

      cardEl.classList.add("is-dragging");

      header.setPointerCapture(e.pointerId);

      header.style.cursor = "grabbing";

    });



    header.addEventListener("pointermove", (e) => {

      if (!dragState || dragState.card.id !== card.id) return;

      const dx = e.clientX - dragState.startX;

      const dy = e.clientY - dragState.startY;

      const x = Math.max(0, dragState.startLeft + dx);

      const y = Math.max(0, dragState.startTop + dy);

      dragState.card.x = x;

      dragState.card.y = y;

      dragState.cardEl.style.left = `${x}px`;

      dragState.cardEl.style.top = `${y}px`;

    });



    const endDrag = (e) => {

      if (!dragState || dragState.card.id !== card.id) return;

      if (e.pointerId !== dragState.pointerId) return;

      dragState.cardEl.classList.remove("is-dragging");

      header.style.cursor = "grab";

      dragState = null;

      scheduleSave();

      try {

        header.releasePointerCapture(e.pointerId);

      } catch (err) {}

    };



    header.addEventListener("pointerup", endDrag);

    header.addEventListener("pointercancel", endDrag);

  }



  async function reloadFromServer() {

    const remote = await fetchStateFromServer();

    if (!remote) return;

    state = remote;

    applyLayoutMode();

    render();

    setTypeMenuOpen(false);

  }



  async function onShow() {

    const local = loadStateLocal();

    const remote = await fetchStateFromServer();

    if (remote && (remote.cards.length > 0 || !local.cards.length)) {

      state = remote;

    } else {

      state = local;

      if (local.cards.length > 0) {

        await persistStateToServer();

      }

    }

    serverSyncReady = true;

    try {

      localStorage.setItem(storageKey(), JSON.stringify(state));

    } catch (e) {}

    applyLayoutMode();

    render();

    setTypeMenuOpen(false);

  }



  tasksAddBtn.addEventListener("click", (e) => {

    e.stopPropagation();

    setTypeMenuOpen(tasksTypeMenu.classList.contains("hidden"));

  });



  tasksTypeMenu.querySelectorAll(".tasks-type-option").forEach((btn) => {

    btn.addEventListener("click", () => {

      const type = btn.dataset.type;

      if (CARD_TYPES.includes(type)) createCard(type);

      setTypeMenuOpen(false);

    });

  });



  tasksArrangeBtn?.addEventListener("click", () => arrangeCards());



  document.addEventListener("click", (e) => {

    if (!tasksAddBtn.contains(e.target) && !tasksTypeMenu.contains(e.target)) {

      setTypeMenuOpen(false);

    }

  });



  document.addEventListener("keydown", (e) => {

    if (e.key === "Escape") setTypeMenuOpen(false);

  });



  window.tasksApp = { onShow, createCard, arrangeCards, reloadFromServer };



  if (window.NexRouter?.getActiveView?.() === "tasks") onShow();

})();

