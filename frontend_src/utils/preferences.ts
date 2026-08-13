// ============================================================
// NexgateAI - Theme & Language Preferences
// ============================================================

import type { I18nLocaleMap, NexgateUserData } from "../types/shared";
import { I18N_JA } from "./i18n";

const THEME_TRANSITION_MS = 280;
const THEME_STORAGE_KEY = "nexgate_theme";
const CHAT_BG_STORAGE_KEY = "nexgate_chat_background";
const LANG_STORAGE_KEY = "nexgate_lang";

// -----------------------------------------------------------
// I18n
// -----------------------------------------------------------

const LOCALE_MAP: I18nLocaleMap = {
  ja: I18N_JA,
};

/**
 * Translate a key to the user's current language.
 * Falls back to Japanese if the key or locale is missing.
 */
export function t(key: string): string {
  const lang = window.__USER__?.language || "ja";
  const dict = LOCALE_MAP[lang] || I18N_JA;
  return dict[key] || key;
}

// -----------------------------------------------------------
// Theme
// -----------------------------------------------------------

function isReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Apply a theme (dark | light | midnight | system) and persist it.
 */
export function applyTheme(theme: string): void {
  const root = document.documentElement;
  const prev = root.getAttribute("data-theme");

  if (theme === "system") {
    root.removeAttribute("data-theme");
    localStorage.removeItem(THEME_STORAGE_KEY);
  } else {
    root.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }

  // Smooth transition class
  if (!isReducedMotion() && prev !== theme) {
    root.classList.add("theme-transition");
    window.setTimeout(
      () => root.classList.remove("theme-transition"),
      THEME_TRANSITION_MS
    );
  }
}

/**
 * Apply a chat background (simple | grid) and persist it.
 */
export function applyChatBackground(bg: string): void {
  document.documentElement.setAttribute("data-chat-bg", bg);
  localStorage.setItem(CHAT_BG_STORAGE_KEY, bg);
}

/**
 * Apply a UI language and persist it.
 */
export function applyLanguage(lang: string): void {
  localStorage.setItem(LANG_STORAGE_KEY, lang);
  // Notify downstream consumers
  window.chatToolsBar?.refresh?.();
  window.updateChatInputIndicators?.();
  window.customAgentSelect?.refresh?.();
  window.refreshTableExportLabels?.();
}

// -----------------------------------------------------------
// Initialization
// -----------------------------------------------------------

/**
 * Initialize preferences from stored values or defaults.
 * Called once on page load.
 */
export function initPreferences(_user: NexgateUserData): void {
  // Restore theme
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme && storedTheme !== "system") {
    document.documentElement.setAttribute("data-theme", storedTheme);
  }

  // Restore chat background
  const storedBg = localStorage.getItem(CHAT_BG_STORAGE_KEY);
  if (storedBg) {
    document.documentElement.setAttribute("data-chat-bg", storedBg);
  }
}

// Expose globally for backward compatibility
window.applyTheme = applyTheme;
window.applyChatBackground = applyChatBackground;
window.applyLanguage = applyLanguage;
window.initPreferences = initPreferences;
window.t = t;

// Auto-init if user data is available (mimics original behavior)
if (window.__USER__) {
  initPreferences(window.__USER__);
}
