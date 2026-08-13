(function () {
  const MAX_ATTACHMENTS = 5;
  const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
  const MAX_IMAGE_MB = MAX_IMAGE_BYTES / (1024 * 1024);
  const MAX_PDF_BYTES = 20 * 1024 * 1024;
  const MAX_PDF_MB = MAX_PDF_BYTES / (1024 * 1024);
  const ALLOWED_PDF_MIME = "application/pdf";
  const IMAGE_LONG_EDGE_MAX = 1568;
  const IMAGE_JPEG_QUALITY = 0.85;
  const ALLOWED_IMAGE_MIMES = new Set([
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
  ]);

  let pendingAttachments = [];

  const attachBtn = document.getElementById("attachBtn");
  const attachMenu = document.getElementById("attachMenu");
  const attachDeepResearchBtn = document.getElementById("attachDeepResearchBtn");
  const deepResearchIndicator = document.getElementById("deepResearchIndicator");
  const intelligentSearchIndicator = document.getElementById("intelligentSearchIndicator");
  const imageGenerationIndicator = document.getElementById("imageGenerationIndicator");
  const imageGenPopover = document.getElementById("imageGenPopover");
  const imageGenModelSelect = document.getElementById("imageGenModelSelect");
  const imageGenSizeSelect = document.getElementById("imageGenSizeSelect");
  let imageGenOptionsCache = null;
  let imageGenSaveTimer = null;
  const fileInput = document.getElementById("fileInput");
  const photoInput = document.getElementById("photoInput");
  const cameraInput = document.getElementById("cameraInput");
  const attachmentPreview = document.getElementById("attachmentPreview");
  const ocrCardArea = document.getElementById("ocrCardArea");

  function formatFileSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function isPngHeader(bytes) {
    return (
      bytes.length >= 4 &&
      bytes[0] === 0x89 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x4e &&
      bytes[3] === 0x47
    );
  }

  function isJpegHeader(bytes) {
    return bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  }

  function isGifHeader(bytes) {
    return (
      bytes.length >= 3 &&
      bytes[0] === 0x47 &&
      bytes[1] === 0x49 &&
      bytes[2] === 0x46
    );
  }

  function isPdfHeader(bytes) {
    return (
      bytes.length >= 4 &&
      bytes[0] === 0x25 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x44 &&
      bytes[3] === 0x46
    );
  }

  function isWebpHeader(bytes) {
    return (
      bytes.length >= 12 &&
      bytes[0] === 0x52 &&
      bytes[1] === 0x49 &&
      bytes[2] === 0x46 &&
      bytes[3] === 0x46 &&
      bytes[8] === 0x57 &&
      bytes[9] === 0x45 &&
      bytes[10] === 0x42 &&
      bytes[11] === 0x50
    );
  }

  async function readFileHeader(file, length = 12) {
    const slice = file.slice(0, length);
    const buffer = await slice.arrayBuffer();
    return new Uint8Array(buffer);
  }

  function mimeFromMagic(bytes) {
    if (isPngHeader(bytes)) return "image/png";
    if (isJpegHeader(bytes)) return "image/jpeg";
    if (isGifHeader(bytes)) return "image/gif";
    if (isWebpHeader(bytes)) return "image/webp";
    return "";
  }

  async function isValidPdfFile(file) {
    if (!file || typeof file.size !== "number") return false;
    const header = await readFileHeader(file, 4);
    if (!isPdfHeader(header)) return false;
    const declared = (file.type || "").toLowerCase();
    if (declared && declared !== ALLOWED_PDF_MIME && declared !== "application/x-pdf") {
      return false;
    }
    return true;
  }

  async function isValidImageFile(file) {
    if (!file || typeof file.size !== "number") return false;
    const header = await readFileHeader(file);
    const magicMime = mimeFromMagic(header);
    if (!magicMime) return false;
    const declared = (file.type || "").toLowerCase();
    if (declared && ALLOWED_IMAGE_MIMES.has(declared) && declared !== magicMime) {
      if (declared === "image/jpg" && magicMime === "image/jpeg") {
        return true;
      }
      return false;
    }
    return ALLOWED_IMAGE_MIMES.has(magicMime);
  }

  function extensionForMime(mime) {
    if (mime === "image/png") return "png";
    if (mime === "image/jpeg") return "jpg";
    if (mime === "image/gif") return "gif";
    if (mime === "image/webp") return "webp";
    return "png";
  }

  async function normalizeImageFile(file, fallbackName) {
    const valid = await isValidImageFile(file);
    if (!valid) return null;
    const header = await readFileHeader(file);
    const mime = mimeFromMagic(header) || (file.type || "image/png").toLowerCase();
    const name =
      (file.name && file.name.trim()) ||
      fallbackName ||
      `image-${Date.now()}.${extensionForMime(mime)}`;
    if (file.type === mime && file.name) return file;
    return new File([file], name, { type: mime, lastModified: file.lastModified });
  }

  async function compressImageFileForUpload(file) {
    const objectUrl = URL.createObjectURL(file);
    try {
      const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = () => reject(new Error("image load failed"));
        el.src = objectUrl;
      });
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      if (!w || !h) return file;

      const longEdge = Math.max(w, h);
      const scale =
        longEdge > IMAGE_LONG_EDGE_MAX ? IMAGE_LONG_EDGE_MAX / longEdge : 1;
      const dw = Math.max(1, Math.round(w * scale));
      const dh = Math.max(1, Math.round(h * scale));

      const canvas = document.createElement("canvas");
      canvas.width = dw;
      canvas.height = dh;
      const ctx = canvas.getContext("2d");
      if (!ctx) return file;
      ctx.drawImage(img, 0, 0, dw, dh);

      const blob = await new Promise((resolve) => {
        canvas.toBlob(resolve, "image/jpeg", IMAGE_JPEG_QUALITY);
      });
      if (!blob) return file;

      const baseName = (file.name || "image").replace(/\.[^.]+$/, "") || "image";
      return new File([blob], `${baseName}.jpg`, {
        type: "image/jpeg",
        lastModified: file.lastModified,
      });
    } catch {
      return file;
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  function isChatToolEnabled(toolId) {
    const bar = window.chatToolsBar;
    if (!bar || typeof bar.isToolEnabled !== "function") return false;
    return bar.isToolEnabled(toolId);
  }

  function isIntelligentSearchEnabled() {
    if (window.getSystemFeatures?.().search_disabled) return false;
    if (window.__USER__?.web_search_enabled === false) return false;
    return isChatToolEnabled("web_search");
  }

  function isDeepResearchAvailable() {
    if (window.getSystemFeatures?.().search_disabled) return false;
    if (window.__USER__?.deep_research_enabled !== true) return false;
    return true;
  }

  function isDeepResearchEnabled() {
    if (!isDeepResearchAvailable()) return false;
    return isChatToolEnabled("deep_research");
  }

  function updateIntelligentSearchIndicator() {
    if (!intelligentSearchIndicator) return;
    const on = isIntelligentSearchEnabled();
    intelligentSearchIndicator.classList.toggle("hidden", !on);
    intelligentSearchIndicator.setAttribute(
      "aria-label",
      on ? "IntelligentSearch 有効" : "IntelligentSearch 無効"
    );
  }

  function isImageGenerationEnabled() {
    if (window.__USER__?.image_generation_enabled !== true) return false;
    return isChatToolEnabled("image_generation");
  }

  function updateImageGenerationIndicator() {
    if (!imageGenerationIndicator) return;
    const on = isImageGenerationEnabled();
    imageGenerationIndicator.classList.toggle("hidden", !on);
    imageGenerationIndicator.setAttribute(
      "aria-label",
      on ? "画像生成 有効" : "画像生成 無効"
    );
  }

  function updateDeepResearchIndicator() {
    if (!deepResearchIndicator) return;
    const on = isDeepResearchEnabled();
    deepResearchIndicator.classList.toggle("hidden", !on);
    deepResearchIndicator.classList.toggle("is-active", on);
    deepResearchIndicator.setAttribute(
      "aria-label",
      on ? window.t("deepResearchTooltipTitle") : window.t("chatToolDeepResearch")
    );
  }

  function updateAttachMenu() {
    if (!attachDeepResearchBtn) return;
    const available = isDeepResearchAvailable();
    attachDeepResearchBtn.classList.toggle("hidden", !available);
    if (!available) {
      attachDeepResearchBtn.classList.remove("is-active");
      attachDeepResearchBtn.setAttribute("aria-checked", "false");
      return;
    }
    const on = isDeepResearchEnabled();
    attachDeepResearchBtn.classList.toggle("is-active", on);
    attachDeepResearchBtn.setAttribute("aria-checked", on ? "true" : "false");
  }

  function toggleDeepResearch() {
    if (!isDeepResearchAvailable()) {
      window.NexNotify?.showError?.(window.t("deepResearchUnavailable"));
      return;
    }
    const bar = window.chatToolsBar;
    if (!bar?.setToolEnabled) return;
    const next = !isDeepResearchEnabled();
    if (next) {
      bar.setToolEnabled("web_search", true);
    }
    bar.setToolEnabled("deep_research", next);
    updateAttachMenu();
    updateDeepResearchIndicator();
    updateIntelligentSearchIndicator();
  }

  function updateChatInputIndicators() {
    window.chatToolsBar?.refresh?.();
    updateIntelligentSearchIndicator();
    updateImageGenerationIndicator();
    updateDeepResearchIndicator();
    updateAttachMenu();
    if (!isImageGenerationEnabled()) closeImageGenPopover();
  }

  window.updateChatInputIndicators = updateChatInputIndicators;
  window.invalidateImageGenOptions = () => {
    imageGenOptionsCache = null;
  };

  function closeImageGenPopover() {
    if (!imageGenPopover || !imageGenerationIndicator) return;
    imageGenPopover.classList.add("hidden");
    imageGenerationIndicator.classList.remove("is-active");
    imageGenerationIndicator.setAttribute("aria-expanded", "false");
  }

  function applyImageGenPrefsToForm(prefs, options) {
    if (!prefs) return;
    if (imageGenModelSelect && options?.models?.length) {
      imageGenModelSelect.innerHTML = options.models
        .map(
          (m) =>
            `<option value="${escapeAttr(m.id)}"${m.id === prefs.model_id ? " selected" : ""}>${escapeHtml(m.display_name || m.id)}</option>`
        )
        .join("");
    }
    if (imageGenSizeSelect && options?.size_presets?.length) {
      const preset = prefs.size_preset || "custom";
      imageGenSizeSelect.innerHTML = options.size_presets
        .map(
          (p) =>
            `<option value="${escapeAttr(p.id)}"${p.id === preset ? " selected" : ""}>${escapeHtml(p.label)}</option>`
        )
        .join("");
    }
  }

  async function loadImageGenOptions() {
    if (imageGenOptionsCache) return imageGenOptionsCache;
    const res = await fetch("/api/image-generation/options");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "設定の読み込みに失敗しました");
    imageGenOptionsCache = data;
    return data;
  }

  async function saveImageGenPrefs(patch) {
    const res = await fetch("/api/settings/image-generation", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存に失敗しました");
    if (data.user) window.__USER__ = data.user;
    if (data.options) {
      imageGenOptionsCache = data.options;
      applyImageGenPrefsToForm(data.options.prefs, data.options);
    }
    return data;
  }

  function scheduleImageGenSave() {
    if (!imageGenModelSelect || !imageGenSizeSelect) return;
    clearTimeout(imageGenSaveTimer);
    imageGenSaveTimer = setTimeout(async () => {
      try {
        await saveImageGenPrefs({
          model_id: imageGenModelSelect.value,
          size_preset: imageGenSizeSelect.value,
        });
      } catch (err) {
        window.NexNotify?.showError?.(err.message);
      }
    }, 280);
  }

  async function openImageGenPopover() {
    if (!isImageGenerationEnabled() || !imageGenPopover) return;
    closeAttachMenu();
    try {
      const options = await loadImageGenOptions();
      applyImageGenPrefsToForm(options.prefs, options);
      imageGenPopover.classList.remove("hidden");
      imageGenerationIndicator?.classList.add("is-active");
      imageGenerationIndicator?.setAttribute("aria-expanded", "true");
    } catch (err) {
      window.NexNotify?.showError?.(err.message);
    }
  }

  function toggleImageGenPopover() {
    if (!imageGenPopover) return;
    if (imageGenPopover.classList.contains("hidden")) {
      openImageGenPopover();
    } else {
      closeImageGenPopover();
    }
  }

  if (imageGenerationIndicator) {
    imageGenerationIndicator.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleImageGenPopover();
    });
  }

  if (imageGenModelSelect) {
    imageGenModelSelect.addEventListener("change", scheduleImageGenSave);
  }
  if (imageGenSizeSelect) {
    imageGenSizeSelect.addEventListener("change", scheduleImageGenSave);
  }

  if (imageGenPopover) {
    imageGenPopover.addEventListener("click", (e) => e.stopPropagation());
  }

  document.addEventListener("click", () => {
    closeAttachMenu();
    closeImageGenPopover();
  });

  if (deepResearchIndicator) {
    deepResearchIndicator.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!isDeepResearchEnabled()) return;
      window.chatToolsBar?.setToolEnabled?.("deep_research", false);
      updateDeepResearchIndicator();
      updateAttachMenu();
    });
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/'/g, "&#39;");
  }

  function closeAttachMenu() {
    if (!attachMenu || !attachBtn) return;
    attachMenu.classList.add("hidden");
    attachBtn.setAttribute("aria-expanded", "false");
  }

  function toggleAttachMenu() {
    if (!attachMenu || !attachBtn) return;
    const hidden = attachMenu.classList.toggle("hidden");
    attachBtn.setAttribute("aria-expanded", String(!hidden));
  }

  function normalizeImageDataUrl(dataUrl) {
    if (typeof dataUrl !== "string") return "";
    const trimmed = dataUrl.trim();
    if (!trimmed.startsWith("data:")) return trimmed;
    const comma = trimmed.indexOf(",");
    if (comma < 0) return trimmed;
    const meta = trimmed.slice(5, comma);
    if (!meta.includes(";base64")) return trimmed;
    let mime = meta.split(";")[0].trim().toLowerCase();
    if (mime === "image/jpg" || mime === "image/pjpeg") mime = "image/jpeg";
    if (mime === "image/x-png") mime = "image/png";
    return `data:${mime};base64,${trimmed.slice(comma + 1)}`;
  }

  function readFileAsPdfDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        if (typeof result !== "string" || !result.startsWith("data:application/pdf")) {
          reject(new Error("invalid pdf data url"));
          return;
        }
        resolve(result);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        if (typeof result !== "string" || !result.startsWith("data:image/")) {
          reject(new Error("invalid data url"));
          return;
        }
        resolve(normalizeImageDataUrl(result));
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsText(file, "utf-8");
    });
  }

  function isFileUploadEnabled() {
    if (window.__IS_ADMIN__) return true;
    if (window.getSystemFeatures?.().upload_disabled) return false;
    return window.__USER__?.file_upload_enabled !== false;
  }

  function uploadBlockedMessage() {
    if (window.getSystemFeatures?.().upload_disabled) {
      return "ファイルのアップロードは現在制限されています";
    }
    return "現在のプランではファイルのアップロードは利用できません";
  }

  function syncAttachButtonState() {
    if (!attachBtn) return;
    const uploadOk = isFileUploadEnabled();
    const canSend =
      typeof window.chatApp?.canSendInSession === "function"
        ? window.chatApp.canSendInSession()
        : true;
    attachBtn.disabled = !uploadOk || !canSend;
    if (!uploadOk) {
      attachBtn.title = uploadBlockedMessage();
    } else if (!canSend) {
      attachBtn.title = "このセッションでは送信できません";
    } else {
      attachBtn.title = "";
    }
  }

  function isOcrEnabled() {
    if (window.getSystemFeatures?.().upload_disabled) return false;
    return window.__USER__?.ocr_enabled === true;
  }

  function imageAttachments() {
    return pendingAttachments.filter((a) => a.kind === "image");
  }

  function pdfAttachments() {
    return pendingAttachments.filter((a) => a.kind === "pdf");
  }

  function showUserError(message) {
    const planOrRestriction = /プラン|制限されています|上限/.test(message);
    if (planOrRestriction && typeof window.showChatRestrictionNotice === "function") {
      window.showChatRestrictionNotice(message, {
        showBillingLink: /プラン|課金|アップグレード/.test(message),
      });
      return;
    }
    window.NexNotify?.showError(message);
  }

  async function addAttachmentFromFile(file, options = {}) {
    if (!isFileUploadEnabled()) {
      showUserError("現在のプランではファイルのアップロードは利用できません");
      return;
    }
    if (pendingAttachments.length >= MAX_ATTACHMENTS) {
      showUserError(`添付は最大${MAX_ATTACHMENTS}件までです`);
      return;
    }

    const looksLikePdf =
      (file.type || "").toLowerCase() === ALLOWED_PDF_MIME ||
      (await isValidPdfFile(file));

    if (looksLikePdf) {
      if (!isFileUploadEnabled()) {
        showUserError("現在のプランではファイルのアップロードは利用できません");
        return;
      }
      if (file.size > MAX_PDF_BYTES) {
        showUserError(`PDFは${MAX_PDF_MB}MB以下にしてください`);
        return;
      }
      const validPdf = await isValidPdfFile(file);
      if (!validPdf) {
        showUserError("PDF形式のファイルのみ添付できます");
        return;
      }
      let dataUrl;
      try {
        dataUrl = await readFileAsPdfDataUrl(file);
      } catch {
        showUserError("PDFの読み込みに失敗しました");
        return;
      }
      pendingAttachments.push({
        id: newUuid(),
        kind: "pdf",
        name: file.name || `document-${Date.now()}.pdf`,
        size: file.size,
        dataUrl,
      });
      renderAttachmentPreview();
      renderAttachmentInfoCards();
      window.updateSendBtn?.();
      return;
    }

    const looksLikeImage =
      (file.type || "").toLowerCase().startsWith("image/") ||
      options.forceImage ||
      (await isValidImageFile(file));

    if (looksLikeImage) {
      const imageFile = await normalizeImageFile(
        file,
        options.fallbackName || `clipboard-${Date.now()}.png`
      );
      if (!imageFile) {
        showUserError("PNG、JPEG、GIF、WebP形式の画像のみ添付できます");
        return;
      }
      const uploadFile = await compressImageFileForUpload(imageFile);
      if (uploadFile.size > MAX_IMAGE_BYTES) {
        showUserError(`画像は${MAX_IMAGE_MB}MB以下にしてください`);
        return;
      }
      let dataUrl;
      try {
        dataUrl = await readFileAsDataUrl(uploadFile);
      } catch {
        showUserError("画像の読み込みに失敗しました");
        return;
      }
      pendingAttachments.push({
        id: newUuid(),
        kind: "image",
        name: uploadFile.name,
        size: uploadFile.size,
        dataUrl,
      });
      renderAttachmentPreview();
      renderAttachmentInfoCards();
      window.updateSendBtn?.();
      return;
    }

    if (file.size > MAX_IMAGE_BYTES) {
      showUserError(`ファイルは${MAX_IMAGE_MB}MB以下にしてください`);
      return;
    }

    let text = "";
    try {
      text = await readFileAsText(file);
    } catch (e) {
      showUserError("このファイルは読み込めません");
      return;
    }
    pendingAttachments.push({
      id: newUuid(),
      kind: "text",
      name: file.name,
      size: file.size,
      text: text.slice(0, 8000),
    });
    renderAttachmentPreview();
    renderAttachmentInfoCards();
    window.updateSendBtn?.();
  }

  async function handleFiles(fileList, options = {}) {
    const files = Array.from(fileList || []);
    for (const file of files) {
      await addAttachmentFromFile(file, options);
    }
  }

  async function handlePaste(event) {
    if (!isFileUploadEnabled()) {
      showUserError(uploadBlockedMessage());
      return;
    }
    const items = event.clipboardData?.items;
    if (!items?.length) return;

    const imageItems = [];
    for (const item of items) {
      if (item.kind !== "file") continue;
      const type = (item.type || "").toLowerCase();
      if (!type || type.startsWith("image/")) {
        imageItems.push(item);
      }
    }
    if (!imageItems.length) return;

    event.preventDefault();
    for (const item of imageItems) {
      const blob = item.getAsFile();
      if (!blob) continue;
      const ext = extensionForMime((blob.type || "image/png").toLowerCase());
      const file = new File([blob], `clipboard-${Date.now()}.${ext}`, {
        type: blob.type || "image/png",
      });
      await addAttachmentFromFile(file, { forceImage: true, fallbackName: file.name });
    }
  }

  const chatDropZone = document.getElementById("chatConversation");

  function hasFileDragPayload(dataTransfer) {
    if (!dataTransfer?.types?.length) return false;
    return Array.from(dataTransfer.types).includes("Files");
  }

  function setChatDropZoneActive(active) {
    chatDropZone?.classList.toggle("is-drag-over", active);
    document.getElementById("chatMain")?.classList.toggle("chat-drag-over", active);
  }

  async function handleFileDrop(event) {
    if (!isFileUploadEnabled()) {
      showUserError(uploadBlockedMessage());
      return;
    }
    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.length) return;

    event.preventDefault();
    setChatDropZoneActive(false);
    await handleFiles(files);
  }

  function handleChatDragEnter(event) {
    if (!isFileUploadEnabled()) return;
    if (!hasFileDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    setChatDropZoneActive(true);
  }

  function handleChatDragOver(event) {
    if (!isFileUploadEnabled()) return;
    if (!hasFileDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  }

  function handleChatDragLeave(event) {
    if (!isFileUploadEnabled()) return;
    const zone = event.currentTarget;
    if (event.relatedTarget && zone.contains(event.relatedTarget)) return;
    setChatDropZoneActive(false);
  }

  function removeAttachment(id) {
    pendingAttachments = pendingAttachments.filter((a) => a.id !== id);
    renderAttachmentPreview();
    renderAttachmentInfoCards();
    window.updateSendBtn?.();
  }

  function renderAttachmentPreview() {
    if (!attachmentPreview) return;

    if (pendingAttachments.length === 0) {
      attachmentPreview.classList.add("hidden");
      attachmentPreview.innerHTML = "";
      return;
    }

    attachmentPreview.classList.remove("hidden");
    attachmentPreview.innerHTML = "";

    pendingAttachments.forEach((att) => {
      const chip = document.createElement("div");
      chip.className = "attachment-chip";

      if (att.kind === "image") {
        const thumb = document.createElement("img");
        thumb.src = att.dataUrl;
        thumb.alt = att.name;
        chip.appendChild(thumb);

        const meta = document.createElement("div");
        meta.className = "attachment-chip-meta";
        const nameEl = document.createElement("span");
        nameEl.className = "attachment-chip-name";
        nameEl.textContent = att.name;
        nameEl.title = att.name;
        const sizeEl = document.createElement("span");
        sizeEl.className = "attachment-chip-size";
        sizeEl.textContent = formatFileSize(att.size);
        meta.appendChild(nameEl);
        meta.appendChild(sizeEl);
        chip.appendChild(meta);
      } else if (att.kind === "pdf") {
        const icon = document.createElement("span");
        icon.className = "attachment-chip-pdf-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "PDF";
        chip.appendChild(icon);

        const meta = document.createElement("div");
        meta.className = "attachment-chip-meta";
        const nameEl = document.createElement("span");
        nameEl.className = "attachment-chip-name";
        nameEl.textContent = att.name;
        nameEl.title = att.name;
        const sizeEl = document.createElement("span");
        sizeEl.className = "attachment-chip-size";
        sizeEl.textContent = formatFileSize(att.size);
        meta.appendChild(nameEl);
        meta.appendChild(sizeEl);
        chip.appendChild(meta);
      } else {
        const meta = document.createElement("div");
        meta.className = "attachment-chip-meta";
        const label = document.createElement("span");
        label.className = "attachment-chip-name";
        label.textContent = att.name;
        label.title = att.name;
        const sizeEl = document.createElement("span");
        sizeEl.className = "attachment-chip-size";
        sizeEl.textContent = formatFileSize(att.size);
        meta.appendChild(label);
        meta.appendChild(sizeEl);
        chip.appendChild(meta);
      }

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "attachment-chip-remove";
      removeBtn.setAttribute("aria-label", "添付を削除");
      removeBtn.textContent = "×";
      removeBtn.onclick = () => removeAttachment(att.id);
      chip.appendChild(removeBtn);

      attachmentPreview.appendChild(chip);
    });
  }

  function renderAttachmentInfoCards() {
    if (!ocrCardArea) return;
    const images = imageAttachments();
    const pdfs = pdfAttachments();
    const showOcr = images.length > 0 && isOcrEnabled();
    const showPdf = pdfs.length > 0 && isFileUploadEnabled();

    if (!showOcr && !showPdf) {
      ocrCardArea.classList.add("hidden");
      ocrCardArea.innerHTML = "";
      return;
    }

    ocrCardArea.classList.remove("hidden");
    ocrCardArea.innerHTML = "";

    if (showOcr) {
      const card = document.createElement("div");
      card.className = "ocr-card";

      const title = document.createElement("p");
      title.className = "ocr-card-title";
      title.textContent = "画像内の文字を抽出";
      card.appendChild(title);

      const desc = document.createElement("p");
      desc.className = "ocr-card-desc";
      desc.textContent =
        "送信時にサーバーで画像を解析し、文字と文書構造を抽出してテキストとしてAIへ渡します。";
      card.appendChild(desc);

      ocrCardArea.appendChild(card);
    }

    if (showPdf) {
      const card = document.createElement("div");
      card.className = "ocr-card";

      const title = document.createElement("p");
      title.className = "ocr-card-title";
      title.textContent = "PDFを読み取る";
      card.appendChild(title);

      const desc = document.createElement("p");
      desc.className = "ocr-card-desc";
      desc.textContent =
        "送信時にサーバーでPDFからテキストを抽出し、PDF本体は送らず抽出テキストとしてAIへ渡します（スキャンPDFは文字が少ない場合があります）。";
      card.appendChild(desc);

      ocrCardArea.appendChild(card);
    }
  }

  function buildUserContentForApi(text, attachments) {
    const parts = [];
    const trimmed = (text || "").trim();

    if (trimmed) {
      parts.push({ type: "text", text: trimmed });
    }

    for (const att of attachments) {
      if (att.kind === "image") {
        parts.push({
          type: "image_url",
          image_url: { url: att.dataUrl },
        });
      } else if (att.kind === "pdf") {
        parts.push({
          type: "pdf_url",
          pdf_url: { url: att.dataUrl },
        });
      } else if (att.kind === "text") {
        parts.push({
          type: "text",
          text: `[ファイル: ${att.name}]\n${att.text}`,
        });
      }
    }

    if (parts.length === 0) return trimmed;
    if (parts.length === 1 && parts[0].type === "text") return parts[0].text;
    return parts;
  }

  function buildUserDisplayText(text, attachments) {
    const trimmed = (text || "").trim();
    if (!attachments.length) return trimmed;

    const names = attachments.map((a) => a.name).join(", ");
    if (trimmed) {
      return `${trimmed}\n\n[添付: ${names}]`;
    }
    return `[添付: ${names}]`;
  }

  async function persistWebSearchPreference(enabled) {
    try {
      const res = await fetch("/api/settings/embed", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ web_search_enabled: Boolean(enabled) }),
      });
      const data = await res.json();
      if (res.ok && data.user) {
        window.__USER__ = data.user;
        updateIntelligentSearchIndicator();
        renderAttachmentInfoCards();
      }
      return res.ok;
    } catch {
      return false;
    }
  }

  window.chatInput = {
    isFileUploadEnabled,
    syncAttachButtonState,
    isWebSearchEnabled() {
      return isIntelligentSearchEnabled();
    },
    setWebSearchEnabled(enabled, options = {}) {
      const { persist = true } = options;
      if (window.__USER__) {
        window.__USER__.web_search_enabled = Boolean(enabled);
      }
      updateIntelligentSearchIndicator();
      if (persist) return persistWebSearchPreference(enabled);
      return Promise.resolve(true);
    },
    refreshIntelligentSearchIndicator() {
      updateIntelligentSearchIndicator();
    },
    consumeAttachments() {
      const list = [...pendingAttachments];
      pendingAttachments = [];
      renderAttachmentPreview();
      renderAttachmentInfoCards();
      window.updateSendBtn?.();
      return list;
    },
    hasPendingContent(text) {
      return Boolean((text || "").trim()) || pendingAttachments.length > 0;
    },
    buildUserContentForApi,
    buildUserDisplayText,
  };

  if (attachBtn && attachMenu) {
    attachBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleAttachMenu();
    });

    attachMenu.addEventListener("click", (e) => e.stopPropagation());
  }

  if (document.getElementById("attachFileBtn")) {
    document.getElementById("attachFileBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      if (!isFileUploadEnabled()) {
        showUserError(uploadBlockedMessage());
        return;
      }
      closeAttachMenu();
      fileInput?.click();
    });
  }

  if (document.getElementById("attachPhotoBtn")) {
    document.getElementById("attachPhotoBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      if (!isFileUploadEnabled()) {
        showUserError(uploadBlockedMessage());
        return;
      }
      closeAttachMenu();
      photoInput?.click();
    });
  }

  if (document.getElementById("attachCameraBtn")) {
    document.getElementById("attachCameraBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      if (!isFileUploadEnabled()) {
        showUserError(uploadBlockedMessage());
        return;
      }
      closeAttachMenu();
      cameraInput?.click();
    });
  }

  if (attachDeepResearchBtn) {
    attachDeepResearchBtn.addEventListener("click", () => {
      closeAttachMenu();
      toggleDeepResearch();
    });
  }

  fileInput?.addEventListener("change", async (e) => {
    await handleFiles(e.target.files);
    e.target.value = "";
  });

  photoInput?.addEventListener("change", async (e) => {
    await handleFiles(e.target.files, { forceImage: true });
    e.target.value = "";
  });

  cameraInput?.addEventListener("change", async (e) => {
    await handleFiles(e.target.files, { forceImage: true });
    e.target.value = "";
  });

  const messageInputEl = document.getElementById("messageInput");
  messageInputEl?.addEventListener("paste", (e) => {
    handlePaste(e);
  });

  document.addEventListener("paste", (e) => {
    if (!document.getElementById("view-chat")?.classList.contains("is-active")) return;
    if (e.target === messageInputEl) return;
    if (!e.target?.closest?.("#chatMain")) return;
    handlePaste(e);
  });

  if (chatDropZone) {
    chatDropZone.addEventListener("dragenter", handleChatDragEnter);
    chatDropZone.addEventListener("dragover", handleChatDragOver);
    chatDropZone.addEventListener("dragleave", handleChatDragLeave);
    chatDropZone.addEventListener("drop", handleFileDrop);
  }

  syncAttachButtonState();
  updateChatInputIndicators();
})();
