// ============================================================
// Tests: I18n
// ============================================================
import { describe, it, expect } from "vitest";
import { I18N_JA } from "./i18n";

describe("I18N_JA", () => {
  it("should contain expected keys", () => {
    expect(I18N_JA).toBeDefined();
    expect(I18N_JA.settingsTitle).toBe("設定");
    expect(I18N_JA.newChat).toBe("+ 新しいチャット");
    expect(I18N_JA.send).toBe("送信");
    expect(I18N_JA.logout).toBe("ログアウト");
  });

  it("should have all common UI strings", () => {
    const required = [
      "settingsTitle",
      "save",
      "saved",
      "saveFailed",
      "networkError",
      "settings",
      "logout",
      "send",
    ] as const;
    for (const key of required) {
      expect(I18N_JA[key], `Missing key: ${key}`).toBeDefined();
    }
  });
});
