const memorySettingsList = document.getElementById("memorySettingsList");
const memorySettingsEmpty = document.getElementById("memorySettingsEmpty");
const memorySettingsMsg = document.getElementById("memorySettingsMsg");
const memorySettingsAdd = document.getElementById("memorySettingsAdd");
const memorySettingsSummary = document.getElementById("memorySettingsSummary");
const memorySettingsDialog = document.getElementById("memorySettingsDialog");
const memorySettingsForm = document.getElementById("memorySettingsForm");
const memorySettingsDialogTitle = document.getElementById("memorySettingsDialogTitle");
const memorySettingsTitleInput = document.getElementById("memorySettingsTitle");
const memorySettingsCategory = document.getElementById("memorySettingsCategory");
const memorySettingsContent = document.getElementById("memorySettingsContent");
const memorySettingsCancel = document.getElementById("memorySettingsCancel");

let memoryEntries = [];
let memorySummary = null;
let editingId = null;
let memorySaving = false;

const CATEGORY_KEYS = {
  general: "memoryCategoryGeneral",
  person: "memoryCategoryPerson",
  conversation: "memoryCategoryConversation",
  thing: "memoryCategoryThing",
};

const CATEGORY_ORDER = ["person", "conversation", "thing", "general"];

function showMemoryMsg(text, isError) {
  if (!memorySettingsMsg) return;
  memorySettingsMsg.textContent = text;
  memorySettingsMsg.classList.remove("hidden", "success", "error");
  memorySettingsMsg.classList.add(isError ? "error" : "success");
}

function categoryLabel(cat) {
  const key = CATEGORY_KEYS[cat] || CATEGORY_KEYS.general;
  return window.t?.(key) || cat;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatSummaryText(template, count) {
  return (template || "").replace("{count}", String(count));
}

function openDialog(entry) {
  if (!memorySettingsDialog) return;
  editingId = entry?.id || null;
  if (memorySettingsDialogTitle) {
    memorySettingsDialogTitle.textContent = editingId
      ? window.t("memorySettingsEdit")
      : window.t("memorySettingsAdd");
  }
  if (memorySettingsTitleInput) memorySettingsTitleInput.value = entry?.title || "";
  if (memorySettingsCategory) {
    memorySettingsCategory.value = entry?.category || "general";
  }
  if (memorySettingsContent) memorySettingsContent.value = entry?.content || "";
  memorySettingsDialog.showModal();
}

function closeDialog() {
  editingId = null;
  memorySettingsDialog?.close();
}

function renderSummary() {
  if (!memorySettingsSummary) return;
  const total = memorySummary?.total ?? memoryEntries.length;
  const chips = [
    `<span class="memory-settings-summary-chip">${escapeHtml(formatSummaryText(window.t("memorySettingsSummaryTotal"), total))}</span>`,
  ];
  for (const cat of CATEGORY_ORDER) {
    const count = memorySummary?.by_category?.[cat] ?? memoryEntries.filter((e) => (e.category || "general") === cat).length;
    if (count > 0) {
      chips.push(
        `<span class="memory-settings-summary-chip">${escapeHtml(categoryLabel(cat))}: ${count}</span>`
      );
    }
  }
  memorySettingsSummary.innerHTML = chips.join("");
  memorySettingsSummary.classList.toggle("hidden", total === 0);
}

function buildMemoryItem(entry) {
  const li = document.createElement("li");
  li.className = "memory-settings-item";
  li.dataset.id = entry.id;
  const title = (entry.title || "").trim() || window.t("memorySettingsUntitled");
  const content = (entry.content || "").trim();
  const preview = content.length > 200 ? `${content.slice(0, 200)}…` : content;
  const sourceBadge =
    entry.source === "chat"
      ? `<span class="memory-settings-item-badge memory-settings-item-badge--source">${escapeHtml(window.t("memorySettingsSavedFromChat"))}</span>`
      : "";
  li.innerHTML = `
    <div class="memory-settings-item-head">
      <span class="memory-settings-item-title">${escapeHtml(title)}</span>
      <span class="memory-settings-item-badge">${escapeHtml(categoryLabel(entry.category))}</span>
      ${sourceBadge}
    </div>
    <p class="memory-settings-item-body">${escapeHtml(preview)}</p>
    <div class="memory-settings-item-actions">
      <button type="button" class="settings-btn settings-btn--secondary memory-settings-edit">${escapeHtml(window.t("memorySettingsEdit"))}</button>
      <button type="button" class="settings-btn settings-btn--secondary memory-settings-delete">${escapeHtml(window.t("memorySettingsDelete"))}</button>
    </div>
  `;
  li.querySelector(".memory-settings-edit")?.addEventListener("click", () => openDialog(entry));
  li.querySelector(".memory-settings-delete")?.addEventListener("click", () => deleteMemory(entry.id));
  return li;
}

function renderMemoryList() {
  if (!memorySettingsList) return;
  memorySettingsList.innerHTML = "";
  const hasItems = memoryEntries.length > 0;
  memorySettingsEmpty?.classList.toggle("hidden", hasItems);
  renderSummary();
  if (!hasItems) return;

  const grouped = {};
  for (const entry of memoryEntries) {
    const cat = entry.category || "general";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(entry);
  }

  for (const cat of CATEGORY_ORDER) {
    const items = grouped[cat];
    if (!items?.length) continue;
    const section = document.createElement("li");
    section.className = "memory-settings-section";
    section.innerHTML = `<h3 class="memory-settings-section-title">${escapeHtml(categoryLabel(cat))}</h3>`;
    const inner = document.createElement("ul");
    inner.className = "memory-settings-section-list";
    for (const entry of items) {
      inner.appendChild(buildMemoryItem(entry));
    }
    section.appendChild(inner);
    memorySettingsList.appendChild(section);
  }
}

async function loadMemories() {
  if (!isMemoryEnabled()) return;
  memorySettingsMsg?.classList.add("hidden");
  try {
    const res = await fetch("/api/memory", { credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) {
      showMemoryMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    memoryEntries = Array.isArray(data.memories) ? data.memories : [];
    memorySummary = data.summary || null;
    renderMemoryList();
  } catch {
    showMemoryMsg(window.t("networkError"), true);
  }
}

function isMemoryEnabled() {
  return window.__USER__?.memory_enabled === true;
}

async function saveMemoryFromForm(e) {
  e.preventDefault();
  if (memorySaving || !isMemoryEnabled()) return;
  const content = memorySettingsContent?.value.trim() || "";
  if (!content) {
    showMemoryMsg(window.t("memorySettingsContentRequired"), true);
    return;
  }
  const payload = {
    title: memorySettingsTitleInput?.value.trim() || "",
    content,
    category: memorySettingsCategory?.value || "general",
  };

  memorySaving = true;
  memorySettingsMsg?.classList.add("hidden");

  try {
    const url = editingId ? `/api/memory/${encodeURIComponent(editingId)}` : "/api/memory";
    const method = editingId ? "PUT" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showMemoryMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    closeDialog();
    await loadMemories();
    showMemoryMsg(window.t("saved"), false);
  } catch {
    showMemoryMsg(window.t("networkError"), true);
  } finally {
    memorySaving = false;
  }
}

async function deleteMemory(id) {
  if (!id || memorySaving || !isMemoryEnabled()) return;
  const ok = await window.NexNotify?.confirm(window.t("memorySettingsDeleteConfirm"), {
    title: window.t("memorySettingsDelete"),
    confirmLabel: window.t("memorySettingsDelete"),
    danger: true,
  });
  if (!ok) return;

  memorySaving = true;
  memorySettingsMsg?.classList.add("hidden");

  try {
    const res = await fetch(`/api/memory/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    const data = await res.json();
    if (!res.ok) {
      showMemoryMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    await loadMemories();
    showMemoryMsg(window.t("saved"), false);
  } catch {
    showMemoryMsg(window.t("networkError"), true);
  } finally {
    memorySaving = false;
  }
}

if (memorySettingsAdd) {
  memorySettingsAdd.addEventListener("click", () => openDialog(null));
}

if (memorySettingsCancel) {
  memorySettingsCancel.addEventListener("click", () => closeDialog());
}

if (memorySettingsForm) {
  memorySettingsForm.addEventListener("submit", saveMemoryFromForm);
}

window.memorySettingsApp = { load: loadMemories };

if (isMemoryEnabled()) {
  loadMemories();
}
