// ============================================================
// NexgateAI - Test Setup
// ============================================================
import { vi } from "vitest";

// Provide minimal DOM environment globals not covered by jsdom
if (typeof window.__USER__ === "undefined") {
  window.__USER__ = {
    username: "testuser",
    role: "user",
    language: "ja",
  };
  window.__SESSION_ID__ = null;
  window.__INITIAL_VIEW__ = "chat";
  window.__MODELS__ = [];
  window.__DEFAULT_MODEL_ID__ = "default";
  window.__SYSTEM_FEATURES__ = {};
  window.__API_PORTAL_BASE__ = "";
  window.__STATIC_JS_BASE__ = "/static/js/";
  window.__IS_ADMIN__ = false;
}

// Suppress console noise during tests
vi.spyOn(console, "error").mockImplementation(() => {});
vi.spyOn(console, "warn").mockImplementation(() => {});
