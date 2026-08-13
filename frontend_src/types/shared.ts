// ============================================================
// NexgateAI - Shared Type Definitions
// ============================================================
// Non-ambient types shared across utility modules.
// Ambient (window) types remain in types/global.d.ts.

/** Toast notification options */
export interface ToastOptions {
  autoDismiss?: boolean;
  durationMs?: number;
}

/** Confirm dialog options */
export interface ConfirmOptions {
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

/** I18n translation dictionary entry */
export type I18nDictionary = Record<string, string>;

/** I18n locale map */
export type I18nLocaleMap = Record<string, I18nDictionary>;

/** Server-injected user object (non-ambient) */
export interface NexgateUserData {
  username: string;
  role: "user" | "admin";
  language?: "ja" | "en";
  [key: string]: unknown;
}
