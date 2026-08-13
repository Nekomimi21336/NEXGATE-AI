const modelSelectBtn = document.getElementById("modelSelectBtn");
const modelSelectMenu = document.getElementById("modelSelectMenu");
const modelSelectTrigger = document.querySelector(".model-select-trigger");
const modelSelectTriggerDesc = document.getElementById("modelSelectTriggerDesc");
const MODEL_STORAGE_KEY = "nexgate_selected_model";

let models = Array.isArray(window.__MODELS__) ? [...window.__MODELS__] : [];

function loadStoredModelId() {
  try {
    const stored = localStorage.getItem(MODEL_STORAGE_KEY);
    if (stored && models.some((m) => m.id === stored)) return stored;
  } catch (_) {}
  return null;
}

function persistSelectedModel() {
  if (!selectedModelId) return;
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, selectedModelId);
  } catch (_) {}
}

let selectedModelId =
  loadStoredModelId() ||
  window.__DEFAULT_MODEL_ID__ ||
  (models[0] && models[0].id) ||
  null;
if (selectedModelId && !models.some((m) => m.id === selectedModelId)) {
  selectedModelId = (models[0] && models[0].id) || null;
}

function getSelectedModel() {
  return models.find((m) => m.id === selectedModelId) || null;
}

window.getSelectedModel = getSelectedModel;

function modelDescriptionText(model) {
  if (!model) return "";
  const desc = String(model.description ?? "").trim();
  if (desc) return desc;
  return String(model.tier ?? "").trim();
}

function updateModelTrigger() {
  const model = getSelectedModel();
  if (modelSelectTrigger) {
    modelSelectTrigger.textContent = model ? model.name : "モデルを選択";
  }
  if (modelSelectTriggerDesc) {
    const desc = modelDescriptionText(model);
    modelSelectTriggerDesc.textContent = desc;
    modelSelectTriggerDesc.classList.toggle("hidden", !desc);
  }
  if (modelSelectBtn) {
    const desc = modelDescriptionText(model);
    modelSelectBtn.setAttribute(
      "aria-label",
      model
        ? desc
          ? `モデル: ${model.name}（${desc}）`
          : `モデル: ${model.name}`
        : "モデルを選択"
    );
  }
}

function setSelectedModel(modelId) {
  if (!modelId || !models.some((m) => m.id === modelId)) return;
  selectedModelId = modelId;
  window.__SELECTED_MODEL_ID__ = modelId;
  persistSelectedModel();
  updateModelTrigger();
  renderModelMenu();
  window.updatePerformanceReasoningInEnglishState?.();
  window.dispatchEvent(new CustomEvent("nexgate:session-settings-changed"));
}

function closeModelMenu() {
  if (!modelSelectMenu || !modelSelectBtn) return;
  modelSelectMenu.classList.add("hidden");
  modelSelectBtn.setAttribute("aria-expanded", "false");
}

function toggleModelMenu() {
  if (!modelSelectMenu || !modelSelectBtn) return;
  const willOpen = modelSelectMenu.classList.contains("hidden");
  if (willOpen) {
    window.customAgentSelect?.closeMenu?.();
  }
  const hidden = modelSelectMenu.classList.toggle("hidden");
  modelSelectBtn.setAttribute("aria-expanded", String(!hidden));
}

function renderModelMenu() {
  if (!modelSelectMenu) return;

  modelSelectMenu.innerHTML = "";

  if (models.length === 0) {
    const empty = document.createElement("p");
    empty.className = "model-select-empty";
    empty.textContent = "モデルがありません";
    modelSelectMenu.appendChild(empty);
    return;
  }

  models.forEach((model) => {
    const isSelected = model.id === selectedModelId;
    const option = document.createElement("button");
    option.type = "button";
    option.className = "model-select-option" + (isSelected ? " is-selected" : "");
    option.dataset.id = model.id;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", isSelected ? "true" : "false");
    option.innerHTML = `
      <span class="model-select-option-name">${escapeHtml(model.name)}</span>
      <span class="model-select-option-tier">${escapeHtml(model.tier)}</span>
    `;
    option.addEventListener("click", (e) => {
      e.stopPropagation();
      setSelectedModel(model.id);
      closeModelMenu();
    });
    modelSelectMenu.appendChild(option);
  });
}

function escapeHtml(text) {
  const el = document.createElement("span");
  el.textContent = text != null ? text : "";
  return el.innerHTML;
}

window.refreshModels = function (nextModels) {
  models = Array.isArray(nextModels) ? [...nextModels] : [];
  window.__MODELS__ = models;
  const stored = loadStoredModelId();
  selectedModelId =
    (stored && models.some((m) => m.id === stored) && stored) ||
    window.__DEFAULT_MODEL_ID__ ||
    (models[0] && models[0].id) ||
    null;
  if (selectedModelId && !models.some((m) => m.id === selectedModelId)) {
    selectedModelId = (models[0] && models[0].id) || null;
  }
  window.__SELECTED_MODEL_ID__ = selectedModelId;
  updateModelTrigger();
  renderModelMenu();
  window.updatePerformanceReasoningInEnglishState?.();
};

window.setSelectedModel = setSelectedModel;
window.closeModelMenu = closeModelMenu;
window.getSelectedModelId = function () {
  return selectedModelId;
};

if (modelSelectBtn && modelSelectMenu) {
  if (selectedModelId) {
    window.__SELECTED_MODEL_ID__ = selectedModelId;
  }
  updateModelTrigger();
  renderModelMenu();

  modelSelectBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleModelMenu();
  });

  document.addEventListener("click", closeModelMenu);
  modelSelectMenu.addEventListener("click", (e) => e.stopPropagation());
}
