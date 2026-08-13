// ============================================================
// NexgateAI - Global Type Definitions
// ============================================================

import type { ToastOptions, ConfirmOptions, NexgateUserData } from "./shared";

/** Server-injected user object */
interface NexgateUser {
  username: string;
  role: "user" | "admin";
  language?: "ja" | "en";
  [key: string]: unknown;
}

/** AI model definition */
interface NexgateModel {
  id: string;
  name: string;
  provider?: string;
  [key: string]: unknown;
}

/** System feature flags */
interface NexgateSystemFeatures {
  chat_stopped?: boolean;
  search_stopped?: boolean;
  image_generation_stopped?: boolean;
  [key: string]: unknown;
}

/** Chat share state */
interface ChatShareState {
  visibility: "private" | "public" | "login_required";
  share_id: string | null;
  url: string | null;
  collab_mode: "private" | "participate" | "view_only";
  collab_id: string | null;
  collab_url: string | null;
}

/** Session access info */
interface SessionAccess {
  owner: string;
  role: "owner" | "editor" | "viewer";
  permissions: string[];
  collab_mode: string;
}

// -----------------------------------------------------------
// Global window extensions (server-injected)
// -----------------------------------------------------------
declare global {
  interface Window {
    __USER__: NexgateUser;
    __SESSION_ID__: string | null;
    __SHARED_CHAT__?: unknown;
    __INITIAL_VIEW__: string;
    __MODELS__: NexgateModel[];
    __DEFAULT_MODEL_ID__: string;
    __SYSTEM_FEATURES__: NexgateSystemFeatures;
    __API_PORTAL_BASE__: string;
    __STATIC_JS_BASE__: string;
    __IS_ADMIN__: boolean;

    /** UUID generator - set by uuid.ts */
    newUuid: () => string;

    /** Theme / language utilities - set by preferences.ts */
    applyTheme: (theme: string) => void;
    applyChatBackground: (bg: string) => void;
    applyLanguage: (lang: string) => void;
    initPreferences: (user: NexgateUserData) => void;
    t: (key: string) => string;
    chatToolsBar?: { refresh?: () => void };
    updateChatInputIndicators?: () => void;
    customAgentSelect?: { refresh?: () => void };
    refreshTableExportLabels?: (scope?: string) => void;

    /** Markdown streaming callback - set by markdown.js */
    _onStreamingMarkdownApplied?: () => void;

    /** Notification utilities - set by notify.ts */
    NexNotify: {
      showError: (message: string, options?: ToastOptions) => void;
      showInfo: (message: string, options?: ToastOptions) => void;
      showSuccess: (message: string, options?: ToastOptions) => void;
      confirm: (message: string, options?: ConfirmOptions) => Promise<boolean>;
    };
  }
}

export {};
