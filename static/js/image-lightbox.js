(function () {
  let overlay = null;
  let stageEl = null;
  let stageImg = null;
  let detailsPanel = null;
  let detailsOpen = false;
  let currentSrc = "";
  let scale = 1;
  let panX = 0;
  let panY = 0;
  let isPanning = false;
  let panStartX = 0;
  let panStartY = 0;
  let panOriginX = 0;
  let panOriginY = 0;
  let wheelBound = false;

  const MIN_SCALE = 1;
  const MAX_SCALE = 8;
  const ZOOM_SENSITIVITY = 0.0012;

  const ICON_DOWNLOAD =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>';
  const ICON_INFO =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>';
  const ICON_CLOSE =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';

  function t(key) {
    return window.t?.(key) || key;
  }

  function isFinePointer() {
    return window.matchMedia("(pointer: fine)").matches;
  }

  function guessFormatFromUrl(url) {
    const path = String(url || "").split("?")[0].toLowerCase();
    if (path.endsWith(".png")) return "PNG";
    if (path.endsWith(".webp")) return "WebP";
    if (path.endsWith(".gif")) return "GIF";
    if (path.endsWith(".jpeg") || path.endsWith(".jpg")) return "JPEG";
    return "—";
  }

  function filenameFromUrl(url) {
    try {
      const u = new URL(url);
      const base = u.pathname.split("/").pop() || "image";
      if (/\.(jpe?g|png|webp|gif)$/i.test(base)) return base;
      return `${base.replace(/[^\w.-]+/g, "_") || "nexgate-image"}.jpg`;
    } catch {
      return "nexgate-image.jpg";
    }
  }

  function setDetailRow(id, value) {
    const el = overlay?.querySelector(`#${id}`);
    if (!el) return;
    el.textContent = value || "—";
  }

  function updateLightboxLabels() {
    if (!overlay) return;
    overlay.querySelector("#chatImageLightboxDownload")?.setAttribute(
      "aria-label",
      t("imageLightboxDownload")
    );
    overlay.querySelector("#chatImageLightboxDetailsBtn")?.setAttribute(
      "aria-label",
      t("imageLightboxDetails")
    );
    overlay.querySelector("#chatImageLightboxClose")?.setAttribute(
      "aria-label",
      t("imageLightboxClose")
    );
    const title = overlay.querySelector("#chatImageLightboxDetailsTitle");
    if (title) title.textContent = t("imageLightboxDetailsTitle");
    overlay.querySelectorAll("[data-i18n-dt]").forEach((dt) => {
      const key = dt.getAttribute("data-i18n-dt");
      if (key) dt.textContent = t(key);
    });
  }

  function applyImageTransform() {
    if (!stageImg) return;
    const zoomed = scale > 1.001;
    stageImg.style.transform = zoomed
      ? `translate(${panX}px, ${panY}px) scale(${scale})`
      : "";
    stageImg.classList.toggle("is-zoomed", zoomed);
    stageEl?.classList.toggle("is-zoomed", zoomed);
  }

  function resetZoom() {
    scale = 1;
    panX = 0;
    panY = 0;
    isPanning = false;
    stageImg?.classList.remove("is-panning");
    applyImageTransform();
  }

  function zoomAt(clientX, clientY, deltaY) {
    if (!stageEl || !stageImg || !isFinePointer()) return;
    const rect = stageEl.getBoundingClientRect();
    const cx = clientX - rect.left - rect.width / 2;
    const cy = clientY - rect.top - rect.height / 2;
    const factor = 1 - deltaY * ZOOM_SENSITIVITY;
    const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
    if (Math.abs(nextScale - scale) < 0.0001) return;

    if (nextScale <= MIN_SCALE) {
      resetZoom();
      return;
    }

    const ratio = nextScale / scale;
    panX = cx - ratio * (cx - panX);
    panY = cy - ratio * (cy - panY);
    scale = nextScale;
    applyImageTransform();
  }

  function onWheel(e) {
    if (!overlay || overlay.classList.contains("hidden") || !isFinePointer()) return;
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY);
  }

  function onPointerDown(e) {
    if (!stageImg || scale <= 1 || !isFinePointer()) return;
    if (e.button !== 0) return;
    isPanning = true;
    panStartX = e.clientX;
    panStartY = e.clientY;
    panOriginX = panX;
    panOriginY = panY;
    stageImg.classList.add("is-panning");
    stageImg.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }

  function onPointerMove(e) {
    if (!isPanning) return;
    panX = panOriginX + (e.clientX - panStartX);
    panY = panOriginY + (e.clientY - panStartY);
    applyImageTransform();
  }

  function onPointerUp(e) {
    if (!isPanning) return;
    isPanning = false;
    stageImg?.classList.remove("is-panning");
    stageImg?.releasePointerCapture?.(e.pointerId);
  }

  function bindZoomHandlers() {
    if (!stageEl || wheelBound) return;
    stageEl.addEventListener("wheel", onWheel, { passive: false });
    stageImg?.addEventListener("pointerdown", onPointerDown);
    stageImg?.addEventListener("pointermove", onPointerMove);
    stageImg?.addEventListener("pointerup", onPointerUp);
    stageImg?.addEventListener("pointercancel", onPointerUp);
    wheelBound = true;
  }

  function ensureOverlay() {
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "chatImageLightbox";
    overlay.className = "chat-image-lightbox hidden";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-hidden", "true");
    overlay.setAttribute("aria-label", t("imageLightboxTitle"));

    overlay.innerHTML = `
      <button type="button" class="chat-image-lightbox-backdrop" id="chatImageLightboxBackdrop" tabindex="-1" aria-hidden="true"></button>
      <div class="chat-image-lightbox-toolbar">
        <button type="button" class="chat-image-lightbox-tool" id="chatImageLightboxDownload" title="">${ICON_DOWNLOAD}</button>
        <button type="button" class="chat-image-lightbox-tool" id="chatImageLightboxDetailsBtn" aria-pressed="false" title="">${ICON_INFO}</button>
        <button type="button" class="chat-image-lightbox-tool chat-image-lightbox-tool--close" id="chatImageLightboxClose" title="">${ICON_CLOSE}</button>
      </div>
      <div class="chat-image-lightbox-stage" id="chatImageLightboxStage">
        <img class="chat-image-lightbox-img" id="chatImageLightboxImg" alt="" draggable="false" />
      </div>
      <aside class="chat-image-lightbox-details hidden" id="chatImageLightboxDetails" aria-labelledby="chatImageLightboxDetailsTitle">
        <h2 class="chat-image-lightbox-details-title" id="chatImageLightboxDetailsTitle"></h2>
        <dl class="chat-image-lightbox-meta">
          <dt data-i18n-dt="imageLightboxAlt">説明</dt>
          <dd id="chatImageLightboxMetaAlt"></dd>
          <dt data-i18n-dt="imageLightboxUrl">URL</dt>
          <dd id="chatImageLightboxMetaUrl" class="chat-image-lightbox-meta-url"></dd>
          <dt data-i18n-dt="imageLightboxDimensions">サイズ</dt>
          <dd id="chatImageLightboxMetaSize"></dd>
          <dt data-i18n-dt="imageLightboxType">形式</dt>
          <dd id="chatImageLightboxMetaType"></dd>
        </dl>
      </aside>
    `;

    document.body.appendChild(overlay);

    stageEl = overlay.querySelector("#chatImageLightboxStage");
    stageImg = overlay.querySelector("#chatImageLightboxImg");
    detailsPanel = overlay.querySelector("#chatImageLightboxDetails");

    overlay.querySelector("#chatImageLightboxClose").addEventListener("click", closeLightbox);
    overlay.querySelector("#chatImageLightboxBackdrop").addEventListener("click", closeLightbox);
    overlay.querySelector("#chatImageLightboxDownload").addEventListener("click", () => {
      if (currentSrc) void downloadImage(currentSrc);
    });
    overlay.querySelector("#chatImageLightboxDetailsBtn").addEventListener("click", toggleDetails);
    stageImg?.addEventListener("click", (e) => e.stopPropagation());
    stageImg?.addEventListener("dblclick", (e) => {
      e.preventDefault();
      e.stopPropagation();
      resetZoom();
    });
    stageEl?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget && scale <= 1) closeLightbox();
    });

    bindZoomHandlers();
    document.addEventListener("keydown", onKeydown);
    updateLightboxLabels();
    return overlay;
  }

  function onKeydown(e) {
    if (!overlay || overlay.classList.contains("hidden")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeLightbox();
    }
  }

  function toggleDetails() {
    detailsOpen = !detailsOpen;
    detailsPanel?.classList.toggle("hidden", !detailsOpen);
    const btn = overlay?.querySelector("#chatImageLightboxDetailsBtn");
    btn?.classList.toggle("is-active", detailsOpen);
    btn?.setAttribute("aria-pressed", detailsOpen ? "true" : "false");
  }

  function closeLightbox() {
    if (!overlay) return;
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("chat-image-lightbox-open");
    detailsOpen = false;
    detailsPanel?.classList.add("hidden");
    overlay.querySelector("#chatImageLightboxDetailsBtn")?.classList.remove("is-active");
    overlay.querySelector("#chatImageLightboxDetailsBtn")?.setAttribute("aria-pressed", "false");
    resetZoom();
    if (stageImg) {
      stageImg.removeAttribute("src");
      stageImg.alt = "";
    }
    currentSrc = "";
  }

  async function downloadImage(url) {
    const name = filenameFromUrl(url);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("fetch failed");
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = name;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      window.NexNotify?.showSuccess?.(t("imageLightboxDownloadStarted"));
    } catch {
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.NexNotify?.showInfo?.(t("imageLightboxDownloadFallback"));
    }
  }

  function populateMeta(img) {
    const src = img.currentSrc || img.src || "";
    const alt = img.alt || "";
    setDetailRow("chatImageLightboxMetaAlt", alt);
    setDetailRow("chatImageLightboxMetaUrl", src);
    setDetailRow("chatImageLightboxMetaType", guessFormatFromUrl(src));
    setDetailRow("chatImageLightboxMetaSize", "—");

    const applySize = () => {
      if (!img.naturalWidth) return;
      setDetailRow(
        "chatImageLightboxMetaSize",
        `${img.naturalWidth} × ${img.naturalHeight} px`
      );
    };
    if (img.complete && img.naturalWidth) {
      applySize();
    } else {
      img.addEventListener("load", applySize, { once: true });
    }
  }

  function openLightbox(thumb) {
    if (!thumb?.src) return;
    ensureOverlay();
    updateLightboxLabels();
    resetZoom();

    currentSrc = thumb.currentSrc || thumb.src;
    stageImg.src = currentSrc;
    stageImg.alt = thumb.alt || "";

    populateMeta(stageImg);

    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("chat-image-lightbox-open");
    overlay.querySelector("#chatImageLightboxClose")?.focus();
  }

  function isZoomableChatImage(el) {
    return Boolean(el?.tagName === "IMG" && el.closest(".message-content.markdown-body"));
  }

  document.addEventListener("click", (e) => {
    const img = e.target.closest(".message-content.markdown-body img");
    if (!isZoomableChatImage(img)) return;
    e.preventDefault();
    e.stopPropagation();
    openLightbox(img);
  });

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const img = e.target;
      if (!isZoomableChatImage(img)) return;
      e.preventDefault();
      openLightbox(img);
    },
    true
  );

  function enhanceChatImagesInElement(root) {
    if (!root) return;
    root.querySelectorAll(".message-content img").forEach((img) => {
      img.classList.add("chat-image-zoomable");
      if (!img.hasAttribute("tabindex")) img.setAttribute("tabindex", "0");
      img.setAttribute("role", "button");
      const label = img.alt
        ? `${t("imageLightboxZoomHint")}: ${img.alt}`
        : t("imageLightboxZoomHint");
      img.setAttribute("aria-label", label);
    });
  }

  window.enhanceChatImagesInElement = enhanceChatImagesInElement;
  window.closeChatImageLightbox = closeLightbox;

  const origApply = window.applyMarkdownContent;
  if (typeof origApply === "function") {
    window.applyMarkdownContent = async function (element, markdownText, options) {
      await origApply(element, markdownText, options);
      enhanceChatImagesInElement(element);
    };
  }
})();
