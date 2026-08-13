// ============================================================
// Tests: Notify (Toast & Confirm)
// ============================================================
import { describe, it, expect, beforeEach, vi } from "vitest";

// Module-level state (toastRoot, confirmOverlay, confirmResolve) persists
// across tests, so we reset the module for clean state each time.

async function importFresh() {
  return import("./notify");
}

describe("Notify - Toast", () => {
  beforeEach(async () => {
    vi.resetModules();
    document.body.innerHTML = "";
  });

  it("showError should create a toast element", async () => {
    const { showError } = await importFresh();
    showError("Test error message");
    const toast = document.querySelector(".nex-toast--error");
    expect(toast).not.toBeNull();
    expect(toast?.textContent).toContain("Test error message");
  });

  it("showInfo should create a toast element", async () => {
    const { showInfo } = await importFresh();
    showInfo("Test info");
    const toast = document.querySelector(".nex-toast--info");
    expect(toast).not.toBeNull();
  });

  it("showSuccess should create a toast element", async () => {
    const { showSuccess } = await importFresh();
    showSuccess("Test success");
    const toast = document.querySelector(".nex-toast--success");
    expect(toast).not.toBeNull();
  });

  it("should not create toast for empty message", async () => {
    const { showError } = await importFresh();
    showError("");
    const toasts =
      document.querySelectorAll<HTMLElement>(".nex-toast-stack > div");
    expect(toasts.length).toBe(0);
  });
});

describe("Notify - Confirm", () => {
  beforeEach(async () => {
    vi.resetModules();
    document.body.innerHTML = "";
  });

  it("should create a confirm dialog", async () => {
    const { confirm } = await importFresh();
    const promise = confirm("Are you sure?");
    const overlay = document.querySelector(".nex-confirm-overlay");
    expect(overlay).not.toBeNull();
    expect(overlay?.classList.contains("hidden")).toBe(false);

    const cancelBtn =
      overlay?.querySelector<HTMLButtonElement>(".nex-confirm-btn--cancel");
    cancelBtn?.click();

    const result = await promise;
    expect(result).toBe(false);
    expect(overlay?.classList.contains("hidden")).toBe(true);
  });

  it("should resolve true on confirm click", async () => {
    const { confirm } = await importFresh();
    const promise = confirm("Proceed?");
    const overlay = document.querySelector(".nex-confirm-overlay");

    const confirmBtn =
      overlay?.querySelector<HTMLButtonElement>(".nex-confirm-btn--confirm");
    confirmBtn?.click();

    const result = await promise;
    expect(result).toBe(true);
  });

  it("should close on Escape key", async () => {
    const { confirm } = await importFresh();
    const promise = confirm("Escape me");
    const overlay = document.querySelector(".nex-confirm-overlay");
    expect(overlay?.classList.contains("hidden")).toBe(false);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    const result = await promise;
    expect(result).toBe(false);
  });
});
