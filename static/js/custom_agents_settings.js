const customAgentsListScreen = document.getElementById("customAgentsListScreen");
const customAgentsEditorScreen = document.getElementById("customAgentsEditorScreen");
const panelAgent = document.getElementById("panel-agent");
const customAgentsList = document.getElementById("customAgentsList");
const customAgentsEmpty = document.getElementById("customAgentsEmpty");
const customAgentsMsg = document.getElementById("customAgentsMsg");
const customAgentsEditorMsg = document.getElementById("customAgentsEditorMsg");
const customAgentsAdd = document.getElementById("customAgentsAdd");
const customAgentsBackList = document.getElementById("customAgentsBackList");
const customAgentsEditorHeading = document.getElementById("customAgentsEditorHeading");
const customAgentsEditorSubheading = document.getElementById("customAgentsEditorSubheading");
const customAgentsForm = document.getElementById("customAgentsForm");
const customAgentsFavoriteBtn = document.getElementById("customAgentsFavoriteBtn");
const customAgentsName = document.getElementById("customAgentsName");
const customAgentsNameDisplay = document.getElementById("customAgentsNameDisplay");
const customAgentsCreatedAt = document.getElementById("customAgentsCreatedAt");
const customAgentsDescription = document.getElementById("customAgentsDescription");
const customAgentsDescriptionDisplay = document.getElementById("customAgentsDescriptionDisplay");
const customAgentsUuidDisplay = document.getElementById("customAgentsUuidDisplay");
const customAgentsCopyUuid = document.getElementById("customAgentsCopyUuid");
const customAgentsVisibilitySelect = document.getElementById("customAgentsVisibilitySelect");
const customAgentsVisibilityDisplay = document.getElementById("customAgentsVisibilityDisplay");
const customAgentsShareLinkField = document.getElementById("customAgentsShareLinkField");
const customAgentsShareLinkDisplay = document.getElementById("customAgentsShareLinkDisplay");
const customAgentsCopyShareLink = document.getElementById("customAgentsCopyShareLink");
const customAgentsUsageField = document.getElementById("customAgentsUsageField");
const customAgentsUsageCount = document.getElementById("customAgentsUsageCount");
const customAgentsModel = document.getElementById("customAgentsModel");
const customAgentsModelDisplay = document.getElementById("customAgentsModelDisplay");
const customAgentsInstructions = document.getElementById("customAgentsInstructions");
const customAgentsKnowledgeList = document.getElementById("customAgentsKnowledgeList");
const customAgentsKnowledgeEmpty = document.getElementById("customAgentsKnowledgeEmpty");
const customAgentsKnowledgeAdd = document.getElementById("customAgentsKnowledgeAdd");
const customAgentsOwnerSection = document.getElementById("customAgentsOwnerSection");
const customAgentsOwnerBadge = document.getElementById("customAgentsOwnerBadge");
const customAgentsNonOwnerNotice = document.getElementById("customAgentsNonOwnerNotice");
const customAgentsForceReasoning = document.getElementById("customAgentsForceReasoning");
const customAgentsReasoningDisplay = document.getElementById("customAgentsReasoningDisplay");
const customAgentsShowPersonality = document.getElementById("customAgentsShowPersonality");
const customAgentsShowKnowledge = document.getElementById("customAgentsShowKnowledge");
const customAgentsPersonalityEditorWrap = document.getElementById("customAgentsPersonalityEditorWrap");
const customAgentsPersonalityHiddenMsg = document.getElementById("customAgentsPersonalityHiddenMsg");
const customAgentsKnowledgeEditorWrap = document.getElementById("customAgentsKnowledgeEditorWrap");
const customAgentsKnowledgeHiddenMsg = document.getElementById("customAgentsKnowledgeHiddenMsg");
const customAgentsSave = document.getElementById("customAgentsSave");

const CUSTOM_AGENT_TABS = ["basics", "personality", "knowledge"];

let customAgents = [];
let editingAgentId = null;
let editorTab = "basics";
let editorFavorite = false;
let editorVisibility = "private";
let editorShareUrl = null;
let editorUsageCount = 0;
let customAgentsSaving = false;
let agentsLoaded = false;
let modelsSelectPopulated = false;
let openBasicsEditor = null;
let editorUuid = "";
let editorIsOwner = true;
let editorForceReasoning = false;
let editorReasoningDisplay = "hide";
let editorShowPersonality = false;
let editorShowKnowledge = false;

function showListMsg(text, isError) {
  if (!customAgentsMsg) return;
  customAgentsMsg.textContent = text;
  customAgentsMsg.classList.remove("hidden", "success", "error");
  customAgentsMsg.classList.add(isError ? "error" : "success");
}

function showEditorMsg(text, isError) {
  if (!customAgentsEditorMsg) return;
  customAgentsEditorMsg.textContent = text;
  customAgentsEditorMsg.classList.remove("hidden", "success", "error");
  customAgentsEditorMsg.classList.add(isError ? "error" : "success");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function agentDisplayName(agent) {
  return (agent?.name || "").trim() || window.t("customAgentsUntitled");
}

function editingAgent() {
  return customAgents.find((a) => a.id === editingAgentId) || null;
}

async function copyTextToClipboard(text) {
  const value = (text || "").trim();
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    showEditorMsg(window.t("customAgentsCopied"), false);
  } catch {
    showEditorMsg(window.t("customAgentsCopyFailed"), true);
  }
}

function populateModelSelect(selectedId) {
  if (!customAgentsModel) return;
  if (!modelsSelectPopulated) {
    const models = Array.isArray(window.__MODELS__) ? window.__MODELS__ : [];
    const opts = [
      `<option value="">${escapeHtml(window.t("customAgentsModelDefault"))}</option>`,
      ...models.map(
        (m) =>
          `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name || m.id)}</option>`
      ),
    ];
    customAgentsModel.innerHTML = opts.join("");
    modelsSelectPopulated = true;
  }
  customAgentsModel.value = selectedId || "";
}

function visibilityLabel(visibility) {
  const key =
    {
      public: "customAgentsVisibilityPublic",
      unlisted: "customAgentsVisibilityUnlisted",
      private: "customAgentsVisibilityPrivate",
    }[visibility] || "customAgentsVisibilityPrivate";
  return window.t(key);
}

function modelLabel(modelId) {
  const id = (modelId || "").trim();
  if (!id) return window.t("customAgentsModelDefault");
  const models = Array.isArray(window.__MODELS__) ? window.__MODELS__ : [];
  const match = models.find((m) => m.id === id);
  return match?.name || id;
}

function displayOrDash(text) {
  const value = (text || "").trim();
  return value || "—";
}

function closeBasicsEditors() {
  document.querySelectorAll("[data-basics-editor]").forEach((el) => {
    el.classList.add("hidden");
  });
  document.querySelectorAll(".custom-agents-meta-main").forEach((el) => {
    el.classList.remove("hidden");
  });
  openBasicsEditor = null;
}

function openBasicsEditorField(field) {
  closeBasicsEditors();
  const row = document.querySelector(`[data-basics-field="${field}"]`);
  if (!row) return;
  row.querySelector(".custom-agents-meta-main")?.classList.add("hidden");
  const editor = row.querySelector(`[data-basics-editor="${field}"]`);
  editor?.classList.remove("hidden");
  const input = editor?.querySelector("input, textarea, select");
  input?.focus();
  if (input?.select) {
    try {
      input.select();
    } catch {
      /* ignore */
    }
  }
  openBasicsEditor = field;
}

function commitBasicsEditorField(field) {
  if (field === "visibility" && customAgentsVisibilitySelect) {
    editorVisibility = customAgentsVisibilitySelect.value || "private";
    const agent = editingAgent();
    if (editorVisibility === "private") {
      editorShareUrl = null;
    } else if (
      agent?.share_url &&
      (agent.visibility === "unlisted" || agent.visibility === "public")
    ) {
      editorShareUrl = agent.share_url;
    } else {
      editorShareUrl = null;
    }
  }
  renderBasicsDisplays();
  closeBasicsEditors();
}

function updateFavoriteButton() {
  if (!customAgentsFavoriteBtn) return;
  customAgentsFavoriteBtn.classList.toggle("is-active", editorFavorite);
  customAgentsFavoriteBtn.setAttribute("aria-pressed", editorFavorite ? "true" : "false");
  const icon = customAgentsFavoriteBtn.querySelector(".custom-agents-favorite-icon");
  if (icon) icon.textContent = editorFavorite ? "★" : "☆";
}

function updateOwnerSection() {
  customAgentsOwnerSection?.classList.toggle("hidden", !editorIsOwner);
  customAgentsNonOwnerNotice?.classList.toggle("hidden", editorIsOwner);
  customAgentsOwnerBadge?.classList.toggle("hidden", !editorIsOwner);
  const canViewPersonality = editorIsOwner || editorShowPersonality;
  customAgentsPersonalityEditorWrap?.classList.toggle("hidden", !canViewPersonality);
  customAgentsPersonalityHiddenMsg?.classList.toggle("hidden", canViewPersonality);
  if (customAgentsInstructions) customAgentsInstructions.readOnly = !editorIsOwner;

  const canEditKnowledge = editorIsOwner || editorShowKnowledge;
  customAgentsKnowledgeEditorWrap?.classList.toggle("hidden", !canEditKnowledge);
  customAgentsKnowledgeHiddenMsg?.classList.toggle("hidden", canEditKnowledge);
  const knowledgeReadOnly = !editorIsOwner;
  customAgentsKnowledgeList
    ?.querySelectorAll(".custom-agents-k-input, .custom-agents-k-tags, .custom-agents-k-textarea, .custom-agents-k-remove")
    .forEach((el) => {
      if (el.classList.contains("custom-agents-k-remove")) {
        el.disabled = knowledgeReadOnly;
      } else {
        el.readOnly = knowledgeReadOnly;
      }
    });
  if (customAgentsKnowledgeAdd) customAgentsKnowledgeAdd.disabled = knowledgeReadOnly;
  if (customAgentsForceReasoning) customAgentsForceReasoning.disabled = !editorIsOwner;
  if (customAgentsReasoningDisplay) customAgentsReasoningDisplay.disabled = !editorIsOwner;
  if (customAgentsShowPersonality) customAgentsShowPersonality.disabled = !editorIsOwner;
  if (customAgentsShowKnowledge) customAgentsShowKnowledge.disabled = !editorIsOwner;
}

function updateBasicsMeta() {
  updateFavoriteButton();
  const isShared = editorVisibility === "unlisted" || editorVisibility === "public";
  customAgentsShareLinkField?.classList.toggle("hidden", !isShared || !editorShareUrl);
  const showUsage = editorVisibility === "public";
  customAgentsUsageField?.classList.toggle("hidden", !showUsage);
  updateOwnerSection();
}

function renderBasicsDisplays() {
  if (customAgentsNameDisplay) {
    customAgentsNameDisplay.textContent = displayOrDash(
      customAgentsName?.value || window.t("customAgentsUntitled")
    );
  }
  if (customAgentsDescriptionDisplay) {
    customAgentsDescriptionDisplay.textContent = displayOrDash(customAgentsDescription?.value);
  }
  if (customAgentsUuidDisplay) {
    customAgentsUuidDisplay.textContent = displayOrDash(editorUuid);
  }
  if (customAgentsVisibilityDisplay) {
    customAgentsVisibilityDisplay.textContent = visibilityLabel(editorVisibility);
  }
  if (customAgentsShareLinkDisplay) {
    customAgentsShareLinkDisplay.textContent = displayOrDash(editorShareUrl);
  }
  if (customAgentsUsageCount) {
    customAgentsUsageCount.textContent = String(editorUsageCount ?? 0);
  }
  if (customAgentsModelDisplay) {
    customAgentsModelDisplay.textContent = modelLabel(customAgentsModel?.value);
  }
  updateBasicsMeta();
}

function fillBasicsFromAgent(agent) {
  editorFavorite = Boolean(agent.favorite);
  editorVisibility = agent.visibility || "private";
  editorShareUrl = agent.share_url || null;
  editorUsageCount = Number(agent.usage_count) || 0;
  editorUuid = agent.id || "";
  editorIsOwner = agent.is_owner !== false;
  editorForceReasoning = Boolean(agent.force_reasoning);
  editorReasoningDisplay = agent.reasoning_display || "hide";
  editorShowPersonality = Boolean(agent.show_personality);
  editorShowKnowledge = Boolean(agent.show_knowledge);
  if (customAgentsName) customAgentsName.value = agent.name || "";
  if (customAgentsCreatedAt) {
    customAgentsCreatedAt.textContent = agent.created_label || agent.created_at || "—";
  }
  if (customAgentsDescription) customAgentsDescription.value = agent.description || "";
  if (customAgentsVisibilitySelect) {
    customAgentsVisibilitySelect.value = editorVisibility;
  }
  if (customAgentsForceReasoning) customAgentsForceReasoning.checked = editorForceReasoning;
  if (customAgentsReasoningDisplay) {
    customAgentsReasoningDisplay.value = editorReasoningDisplay;
  }
  if (customAgentsShowPersonality) customAgentsShowPersonality.checked = editorShowPersonality;
  if (customAgentsShowKnowledge) customAgentsShowKnowledge.checked = editorShowKnowledge;
  populateModelSelect(agent.model_id || "");
  closeBasicsEditors();
  renderBasicsDisplays();
}

function showEditorTab(tabId) {
  if (!CUSTOM_AGENT_TABS.includes(tabId)) tabId = "basics";
  editorTab = tabId;
  document.querySelectorAll("[data-agent-tab]").forEach((btn) => {
    const active = btn.dataset.agentTab === tabId;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-agent-panel]").forEach((panel) => {
    const active = panel.dataset.agentPanel === tabId;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function syncAgentEditorUrl(agentId, options = {}) {
  const { syncUrl = true } = options;
  if (!syncUrl) return;
  const hashPart = agentId ? `agent/edit/${encodeURIComponent(agentId)}` : "agent";
  const path = `/settings#${hashPart}`;
  if (location.pathname === "/settings" || location.pathname === "/settings/") {
    if (location.pathname + location.hash !== path) {
      history.pushState(history.state, "", path);
    }
  }
}

function showListScreen(options = {}) {
  const { syncUrl = false } = options;
  editingAgentId = null;
  editorTab = "basics";
  editorUuid = "";
  closeBasicsEditors();
  renderKnowledgeList([]);
  customAgentsForm?.reset();
  document.documentElement.setAttribute("data-custom-agents-screen", "list");
  panelAgent?.setAttribute("data-custom-agents-screen", "list");
  customAgentsListScreen?.classList.remove("hidden");
  customAgentsEditorScreen?.classList.add("hidden");
  customAgentsEditorScreen?.setAttribute("aria-hidden", "true");
  if (syncUrl) {
    const path = "/settings#agent";
    if (location.pathname === "/settings" || location.pathname === "/settings/") {
      history.pushState(history.state, "", path);
    }
  }
}

function newKnowledgeItemId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `k-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function normalizeKnowledgeItems(agent) {
  const items = Array.isArray(agent?.knowledge_items) ? agent.knowledge_items : [];
  if (items.length) return items;
  const legacy = (agent?.knowledge || "").trim();
  if (!legacy) return [];
  return [{ id: newKnowledgeItemId(), title: "", tags: "", content: legacy }];
}

function buildKnowledgeItemElement(item, index) {
  const li = document.createElement("li");
  li.className = "custom-agents-knowledge-item";
  li.dataset.id = item.id || newKnowledgeItemId();

  const head = document.createElement("div");
  head.className = "custom-agents-knowledge-item-head";
  const indexEl = document.createElement("span");
  indexEl.className = "custom-agents-knowledge-item-index";
  indexEl.textContent = String(index + 1);
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "custom-agents-k-remove";
  removeBtn.textContent = window.t("customAgentsKnowledgeRemove");
  removeBtn.addEventListener("click", () => {
    li.remove();
    renderKnowledgeListState();
  });
  head.append(indexEl, removeBtn);

  const fields = document.createElement("div");
  fields.className = "custom-agents-knowledge-fields";

  const row = document.createElement("div");
  row.className = "custom-agents-knowledge-row";

  const titleWrap = document.createElement("div");
  titleWrap.className = "custom-agents-knowledge-field custom-agents-knowledge-field--title";
  const titleLabel = document.createElement("label");
  titleLabel.className = "custom-agents-k-label";
  titleLabel.textContent = window.t("customAgentsKnowledgeFieldTitle");
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "custom-agents-k-input";
  titleInput.dataset.knowledgeField = "title";
  titleInput.maxLength = 120;
  titleInput.value = item.title || "";
  titleWrap.append(titleLabel, titleInput);

  const tagsWrap = document.createElement("div");
  tagsWrap.className = "custom-agents-knowledge-field custom-agents-knowledge-field--tags";
  const tagsLabel = document.createElement("label");
  tagsLabel.className = "custom-agents-k-label";
  tagsLabel.textContent = window.t("customAgentsKnowledgeFieldTags");
  const tagsInput = document.createElement("input");
  tagsInput.type = "text";
  tagsInput.className = "custom-agents-k-tags";
  tagsInput.dataset.knowledgeField = "tags";
  tagsInput.maxLength = 200;
  tagsInput.placeholder = window.t("customAgentsKnowledgeFieldTagsPlaceholder");
  tagsInput.value = item.tags || "";
  tagsWrap.append(tagsLabel, tagsInput);
  row.append(titleWrap, tagsWrap);

  const contentWrap = document.createElement("div");
  contentWrap.className = "custom-agents-knowledge-field custom-agents-knowledge-field--content";
  const contentLabel = document.createElement("label");
  contentLabel.className = "custom-agents-k-label";
  contentLabel.textContent = window.t("customAgentsKnowledgeFieldContent");
  const contentInput = document.createElement("textarea");
  contentInput.className = "custom-agents-k-textarea";
  contentInput.dataset.knowledgeField = "content";
  contentInput.rows = 5;
  contentInput.maxLength = 16000;
  contentInput.value = item.content || "";
  contentWrap.append(contentLabel, contentInput);

  fields.append(row, contentWrap);
  li.append(head, fields);
  return li;
}

function renderKnowledgeList(items) {
  if (!customAgentsKnowledgeList) return;
  customAgentsKnowledgeList.innerHTML = "";
  const list = Array.isArray(items) ? items : [];
  list.forEach((item, index) => {
    customAgentsKnowledgeList.appendChild(buildKnowledgeItemElement(item, index));
  });
  renderKnowledgeListState();
  updateOwnerSection();
}

function renderKnowledgeListState() {
  const count = customAgentsKnowledgeList?.children.length ?? 0;
  customAgentsKnowledgeEmpty?.classList.toggle("hidden", count > 0);
}

function collectKnowledgeItems() {
  const items = [];
  customAgentsKnowledgeList?.querySelectorAll(".custom-agents-knowledge-item").forEach((row) => {
    items.push({
      id: row.dataset.id || newKnowledgeItemId(),
      title: row.querySelector('[data-knowledge-field="title"]')?.value.trim() ?? "",
      tags: row.querySelector('[data-knowledge-field="tags"]')?.value.trim() ?? "",
      content: row.querySelector('[data-knowledge-field="content"]')?.value.trim() ?? "",
    });
  });
  return items;
}

function addKnowledgeItem(item = {}) {
  const count = customAgentsKnowledgeList?.children.length ?? 0;
  const entry = {
    id: item.id || newKnowledgeItemId(),
    title: item.title || "",
    tags: item.tags || "",
    content: item.content || "",
  };
  customAgentsKnowledgeList?.appendChild(buildKnowledgeItemElement(entry, count));
  renderKnowledgeListState();
  updateOwnerSection();
  customAgentsKnowledgeList?.lastElementChild?.querySelector('[data-knowledge-field="title"]')?.focus();
}

function knowledgePreviewText(agent) {
  const items = normalizeKnowledgeItems(agent);
  if (!items.length) return "";
  const first = items[0];
  const title = (first.title || "").trim();
  const content = (first.content || "").trim();
  if (title) return title;
  return content.slice(0, 120);
}

function showEditorScreen(agent, options = {}) {
  const { syncUrl = false } = options;
  if (!agent?.id) return;
  editingAgentId = agent.id;
  if (customAgentsInstructions) customAgentsInstructions.value = agent.instructions || "";
  renderKnowledgeList(normalizeKnowledgeItems(agent));
  if (customAgentsEditorHeading) {
    customAgentsEditorHeading.textContent = window.t("customAgentsEdit");
  }
  if (customAgentsEditorSubheading) {
    customAgentsEditorSubheading.textContent = agentDisplayName(agent);
  }
  document.documentElement.setAttribute("data-custom-agents-screen", "editor");
  panelAgent?.setAttribute("data-custom-agents-screen", "editor");
  customAgentsListScreen?.classList.add("hidden");
  customAgentsEditorScreen?.classList.remove("hidden");
  customAgentsEditorScreen?.setAttribute("aria-hidden", "false");
  customAgentsEditorMsg?.classList.add("hidden");
  fillBasicsFromAgent(agent);
  showEditorTab("basics");
  if (customAgentsSave) customAgentsSave.disabled = false;
  customAgentsName?.focus();
  syncAgentEditorUrl(agent.id, { syncUrl });
}

function closeEditor(options = {}) {
  showListScreen(options);
}

function buildCustomAgentItem(agent) {
  const li = document.createElement("li");
  li.className = "custom-agents-list-item";
  li.dataset.id = agent.id;
  const name = agentDisplayName(agent);
  const desc = (agent.description || "").trim();
  const knowledgePreview = knowledgePreviewText(agent);
  const preview = desc || knowledgePreview || (agent.instructions || "").trim().slice(0, 120);
  const previewText = preview.length > 120 ? `${preview.slice(0, 120)}…` : preview;
  const fav = agent.favorite
    ? `<span class="custom-agents-list-favorite" aria-hidden="true">★</span>`
    : "";
  li.innerHTML = `
    <button type="button" class="custom-agents-list-item-main">
      ${fav}
      <span class="custom-agents-list-item-name">${escapeHtml(name)}</span>
      <span class="custom-agents-list-item-desc">${escapeHtml(previewText || "—")}</span>
    </button>
    <div class="custom-agents-list-item-actions">
      <button type="button" class="settings-btn settings-btn--secondary custom-agents-edit">${escapeHtml(window.t("customAgentsEdit"))}</button>
      <button type="button" class="settings-btn settings-btn--secondary custom-agents-delete">${escapeHtml(window.t("customAgentsDelete"))}</button>
    </div>
  `;
  const open = () => showEditorScreen(agent, { syncUrl: true });
  li.querySelector(".custom-agents-list-item-main")?.addEventListener("click", open);
  li.querySelector(".custom-agents-edit")?.addEventListener("click", (e) => {
    e.stopPropagation();
    open();
  });
  li.querySelector(".custom-agents-delete")?.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteCustomAgent(agent.id);
  });
  return li;
}

function renderCustomAgentsList() {
  if (!customAgentsList) return;
  customAgentsList.innerHTML = "";
  const hasItems = customAgents.length > 0;
  customAgentsEmpty?.classList.toggle("hidden", hasItems);
  for (const agent of customAgents) {
    customAgentsList.appendChild(buildCustomAgentItem(agent));
  }
  window.customAgentSelect?.refresh?.();
}

async function loadCustomAgents() {
  if (!customAgentsList) return;
  try {
    const res = await fetch("/api/custom-agents");
    const data = await res.json();
    if (!res.ok) {
      showListMsg(data.error || window.t("loadFailed"), true);
      return;
    }
    customAgents = Array.isArray(data.agents) ? data.agents : [];
    agentsLoaded = true;
    renderCustomAgentsList();
  } catch {
    showListMsg(window.t("networkError"), true);
  }
}

async function createEmptyAgent() {
  if (customAgentsSaving) return;
  customAgentsSaving = true;
  if (customAgentsAdd) customAgentsAdd.disabled = true;
  customAgentsMsg?.classList.add("hidden");
  try {
    const res = await fetch("/api/custom-agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) {
      showListMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    customAgents = [data, ...customAgents];
    renderCustomAgentsList();
    showEditorScreen(data, { syncUrl: true });
  } catch {
    showListMsg(window.t("networkError"), true);
  } finally {
    customAgentsSaving = false;
    if (customAgentsAdd) customAgentsAdd.disabled = false;
  }
}

function collectSaveBody() {
  const body = {
    name: customAgentsName?.value.trim() ?? "",
    description: customAgentsDescription?.value.trim() ?? "",
    instructions: customAgentsInstructions?.value.trim() ?? "",
    knowledge_items: collectKnowledgeItems(),
    favorite: editorFavorite,
    visibility: editorVisibility,
    model_id: customAgentsModel?.value.trim() ?? "",
  };
  if (editorIsOwner) {
    body.force_reasoning = Boolean(customAgentsForceReasoning?.checked);
    body.reasoning_display = customAgentsReasoningDisplay?.value || "hide";
    body.show_personality = Boolean(customAgentsShowPersonality?.checked);
    body.show_knowledge = Boolean(customAgentsShowKnowledge?.checked);
  }
  return body;
}

async function saveCustomAgent() {
  if (customAgentsSaving || !editingAgentId) return;
  if (openBasicsEditor) commitBasicsEditorField(openBasicsEditor);
  customAgentsSaving = true;
  if (customAgentsSave) customAgentsSave.disabled = true;
  customAgentsEditorMsg?.classList.add("hidden");
  try {
    const res = await fetch(`/api/custom-agents/${encodeURIComponent(editingAgentId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectSaveBody()),
    });
    const data = await res.json();
    if (!res.ok) {
      showEditorMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    customAgents = customAgents.map((a) => (a.id === data.id ? data : a));
    renderCustomAgentsList();
    closeEditor({ syncUrl: true });
    showListMsg(window.t("saved"), false);
  } catch {
    showEditorMsg(window.t("networkError"), true);
  } finally {
    customAgentsSaving = false;
    if (customAgentsSave) customAgentsSave.disabled = false;
  }
}

async function deleteCustomAgent(agentId) {
  if (!agentId || customAgentsSaving) return;
  if (!confirm(window.t("customAgentsDeleteConfirm"))) return;
  customAgentsSaving = true;
  customAgentsMsg?.classList.add("hidden");
  try {
    const res = await fetch(`/api/custom-agents/${encodeURIComponent(agentId)}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) {
      showListMsg(data.error || window.t("saveFailed"), true);
      return;
    }
    if (editingAgentId === agentId) {
      closeEditor({ syncUrl: true });
    }
    customAgents = customAgents.filter((a) => a.id !== agentId);
    renderCustomAgentsList();
    showListMsg(window.t("saved"), false);
  } catch {
    showListMsg(window.t("networkError"), true);
  } finally {
    customAgentsSaving = false;
  }
}

async function applyAgentRoute(route, options = {}) {
  const screen = route?.screen || "list";
  if (!agentsLoaded) {
    await loadCustomAgents();
  }
  if (screen === "editor" && route.agentId) {
    const agent = customAgents.find((a) => a.id === route.agentId);
    if (agent) {
      showEditorScreen(agent, { syncUrl: options.syncUrl === true });
      return;
    }
    showListScreen({ syncUrl: options.syncUrl === true });
    return;
  }
  showListScreen({ syncUrl: options.syncUrl === true });
}

if (customAgentsAdd) {
  customAgentsAdd.addEventListener("click", () => createEmptyAgent());
}

if (customAgentsBackList) {
  customAgentsBackList.addEventListener("click", () => {
    if (customAgentsSaving) return;
    closeEditor({ syncUrl: true });
  });
}

if (customAgentsFavoriteBtn) {
  customAgentsFavoriteBtn.addEventListener("click", () => {
    editorFavorite = !editorFavorite;
    updateFavoriteButton();
  });
}

customAgentsForceReasoning?.addEventListener("change", () => {
  editorForceReasoning = Boolean(customAgentsForceReasoning.checked);
});

customAgentsReasoningDisplay?.addEventListener("change", () => {
  editorReasoningDisplay = customAgentsReasoningDisplay.value || "hide";
});

customAgentsShowPersonality?.addEventListener("change", () => {
  editorShowPersonality = Boolean(customAgentsShowPersonality.checked);
  updateOwnerSection();
});

customAgentsShowKnowledge?.addEventListener("change", () => {
  editorShowKnowledge = Boolean(customAgentsShowKnowledge.checked);
  updateOwnerSection();
});

if (customAgentsKnowledgeAdd) {
  customAgentsKnowledgeAdd.addEventListener("click", () => {
    if (!editorIsOwner) return;
    addKnowledgeItem();
  });
}

document.querySelectorAll("[data-edit-basics]").forEach((btn) => {
  btn.addEventListener("click", () => {
    openBasicsEditorField(btn.dataset.editBasics);
  });
});

function bindBasicsFieldBlur(el) {
  el?.addEventListener("keydown", (e) => {
    const field = el.closest("[data-basics-editor]")?.dataset.basicsEditor;
    if (e.key === "Escape") {
      e.preventDefault();
      closeBasicsEditors();
      renderBasicsDisplays();
      return;
    }
    if (e.key === "Enter" && el.tagName !== "TEXTAREA") {
      e.preventDefault();
      if (field) commitBasicsEditorField(field);
    }
  });
  el?.addEventListener("blur", () => {
    const field = el.closest("[data-basics-editor]")?.dataset.basicsEditor;
    if (!field) return;
    setTimeout(() => {
      if (openBasicsEditor === field) commitBasicsEditorField(field);
    }, 120);
  });
}

bindBasicsFieldBlur(customAgentsName);
bindBasicsFieldBlur(customAgentsDescription);

customAgentsVisibilitySelect?.addEventListener("change", () => {
  commitBasicsEditorField("visibility");
});

customAgentsModel?.addEventListener("change", () => {
  commitBasicsEditorField("model");
});

customAgentsModel?.addEventListener("blur", () => {
  if (openBasicsEditor === "model") {
    commitBasicsEditorField("model");
  }
});

if (customAgentsCopyUuid) {
  customAgentsCopyUuid.addEventListener("click", () => {
    copyTextToClipboard(editorUuid);
  });
}

if (customAgentsCopyShareLink) {
  customAgentsCopyShareLink.addEventListener("click", () => {
    copyTextToClipboard(editorShareUrl);
  });
}

document.querySelectorAll("[data-agent-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (customAgentsSaving) return;
    showEditorTab(btn.dataset.agentTab);
  });
});

if (customAgentsForm) {
  customAgentsForm.addEventListener("submit", (e) => {
    e.preventDefault();
    saveCustomAgent();
  });
}

window.customAgentsSettingsApp = {
  load: loadCustomAgents,
  showListScreen,
  showEditorScreen,
  closeEditor,
  applyAgentRoute,
};
