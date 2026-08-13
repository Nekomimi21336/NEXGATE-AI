// ============================================================
// NexgateAI - Toast Notifications & Confirm Dialog
// ============================================================

import type { ToastOptions, ConfirmOptions } from "../types/shared";

const TOAST_AUTO_MS = 5000;

let toastRoot: HTMLDivElement | null = null;
let confirmOverlay: HTMLDivElement | null = null;
let confirmResolve: ((value: boolean) => void) | null = null;

// -----------------------------------------------------------
// Toast
// -----------------------------------------------------------

function ensureToastRoot(): HTMLDivElement {
  if (toastRoot) return toastRoot;
  toastRoot = document.createElement("div");
  toastRoot.className = "nex-toast-stack";
  toastRoot.setAttribute("role", "region");
  toastRoot.setAttribute("aria-label", "通知");
  document.body.appendChild(toastRoot);
  return toastRoot;
}

function removeToast(el: HTMLDivElement): void {
  if (!el?.isConnected) return;
  el.classList.add("nex-toast--leaving");
  window.setTimeout(() => el.remove(), 200);
}

function showToast(
  message: string,
  type: "error" | "info" | "success",
  { autoDismiss = true, durationMs = TOAST_AUTO_MS }: ToastOptions = {}
): void {
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

export function showError(message: string, options?: ToastOptions): void {
  showToast(message, "error", options);
}

export function showInfo(message: string, options?: ToastOptions): void {
  showToast(message, "info", options);
}

export function showSuccess(message: string, options?: ToastOptions): void {
  showToast(message, "success", options);
}

// -----------------------------------------------------------
// Confirm dialog
// -----------------------------------------------------------

function finishConfirm(value: boolean): void {
  if (!confirmResolve) return;
  const resolve = confirmResolve;
  confirmResolve = null;
  confirmOverlay?.classList.add("hidden");
  confirmOverlay?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("nex-confirm-open");
  resolve(value);
}

function ensureConfirmOverlay(): HTMLDivElement {
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

  const cancelBtn = confirmOverlay.querySelector<HTMLButtonElement>(
    ".nex-confirm-btn--cancel"
  );
  const confirmBtn = confirmOverlay.querySelector<HTMLButtonElement>(
    ".nex-confirm-btn--confirm"
  );

  cancelBtn?.addEventListener("click", () => finishConfirm(false));
  confirmBtn?.addEventListener("click", () => finishConfirm(true));
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

export function confirm(
  message: string,
  options: ConfirmOptions = {}
): Promise<boolean> {
  const {
    title = "確認",
    confirmLabel = "OK",
    cancelLabel = "キャンセル",
    danger = false,
  } = options;

  return new Promise((resolve) => {
    const overlay = ensureConfirmOverlay();
    confirmResolve = resolve;

    const titleEl = overlay.querySelector<HTMLElement>("#nexConfirmTitle");
    const msgEl = overlay.querySelector<HTMLElement>("#nexConfirmMessage");
    const confirmBtn =
      overlay.querySelector<HTMLButtonElement>(".nex-confirm-btn--confirm");
    const cancelBtn =
      overlay.querySelector<HTMLButtonElement>(".nex-confirm-btn--cancel");

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    if (confirmBtn) {
      confirmBtn.textContent = confirmLabel;
      confirmBtn.classList.toggle("nex-confirm-btn--danger", danger);
    }
    if (cancelBtn) cancelBtn.textContent = cancelLabel;

    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("nex-confirm-open");
    cancelBtn?.focus();
  });
}

// Expose globally for backward compatibility
window.NexNotify = {
  showError,
  showInfo,
  showSuccess,
  confirm,
};
