(function () {
  const TOAST_AUTO_MS = 5000;
  let toastRoot = null;
  let confirmOverlay = null;
  let confirmResolve = null;

  function ensureToastRoot() {
    if (toastRoot) return toastRoot;
    toastRoot = document.createElement("div");
    toastRoot.className = "nex-toast-stack";
    toastRoot.setAttribute("role", "region");
    toastRoot.setAttribute("aria-label", "通知");
    document.body.appendChild(toastRoot);
    return toastRoot;
  }

  function removeToast(el) {
    if (!el?.isConnected) return;
    el.classList.add("nex-toast--leaving");
    window.setTimeout(() => el.remove(), 200);
  }

  function showToast(message, type, { autoDismiss = true, durationMs = TOAST_AUTO_MS } = {}) {
    if (!message) return;
    const root = ensureToastRoot();
    const el = document.createElement("div");
    el.className = `nex-toast nex-toast--${type}`;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.setAttribute(
      "aria-live",
      type === "error" ? "assertive" : "polite"
    );

    const text = document.createElement("p");
    text.className = "nex-toast-text";
    text.textContent = message;

    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "nex-toast-dismiss";
    dismiss.setAttribute("aria-label", "閉じる");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", () => removeToast(el));

    el.append(text, dismiss);
    root.appendChild(el);

    if (autoDismiss) {
      window.setTimeout(() => removeToast(el), durationMs);
    }
  }

  function showError(message, options) {
    showToast(message, "error", options);
  }

  function showInfo(message, options) {
    showToast(message, "info", options);
  }

  function showSuccess(message, options) {
    showToast(message, "success", options);
  }

  function finishConfirm(value) {
    if (!confirmResolve) return;
    const resolve = confirmResolve;
    confirmResolve = null;
    confirmOverlay?.classList.add("hidden");
    confirmOverlay?.setAttribute("aria-hidden", "true");
    document.body.classList.remove("nex-confirm-open");
    resolve(value);
  }

  function ensureConfirmOverlay() {
    if (confirmOverlay) return confirmOverlay;

    confirmOverlay = document.createElement("div");
    confirmOverlay.className = "nex-confirm-overlay hidden";
    confirmOverlay.setAttribute("aria-hidden", "true");
    confirmOverlay.innerHTML = `
      <div class="nex-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="nexConfirmTitle" aria-describedby="nexConfirmMessage">
        <p class="nex-confirm-title" id="nexConfirmTitle"></p>
        <p class="nex-confirm-message" id="nexConfirmMessage"></p>
        <div class="nex-confirm-actions">
          <button type="button" class="nex-confirm-btn nex-confirm-btn--cancel">キャンセル</button>
          <button type="button" class="nex-confirm-btn nex-confirm-btn--confirm">OK</button>
        </div>
      </div>
    `;
    document.body.appendChild(confirmOverlay);

    const cancelBtn = confirmOverlay.querySelector(".nex-confirm-btn--cancel");
    const confirmBtn = confirmOverlay.querySelector(".nex-confirm-btn--confirm");

    cancelBtn.addEventListener("click", () => finishConfirm(false));
    confirmBtn.addEventListener("click", () => finishConfirm(true));
    confirmOverlay.addEventListener("click", (e) => {
      if (e.target === confirmOverlay) finishConfirm(false);
    });
    document.addEventListener("keydown", (e) => {
      if (confirmOverlay?.classList.contains("hidden")) return;
      if (e.key === "Escape") {
        e.preventDefault();
        finishConfirm(false);
      }
    });

    return confirmOverlay;
  }

  function confirm(message, options = {}) {
    const {
      title = "確認",
      confirmLabel = "OK",
      cancelLabel = "キャンセル",
      danger = false,
    } = options;

    return new Promise((resolve) => {
      const overlay = ensureConfirmOverlay();
      confirmResolve = resolve;
      overlay.querySelector("#nexConfirmTitle").textContent = title;
      overlay.querySelector("#nexConfirmMessage").textContent = message;
      const confirmBtn = overlay.querySelector(".nex-confirm-btn--confirm");
      const cancelBtn = overlay.querySelector(".nex-confirm-btn--cancel");
      confirmBtn.textContent = confirmLabel;
      cancelBtn.textContent = cancelLabel;
      confirmBtn.classList.toggle("nex-confirm-btn--danger", danger);
      overlay.classList.remove("hidden");
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("nex-confirm-open");
      cancelBtn.focus();
    });
  }

  window.NexNotify = {
    showError,
    showInfo,
    showSuccess,
    confirm,
  };
})();
