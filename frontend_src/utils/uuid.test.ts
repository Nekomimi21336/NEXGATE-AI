// ============================================================
// Tests: UUID Generator
// ============================================================
import { describe, it, expect } from "vitest";
import { newUuid } from "./uuid";

describe("newUuid", () => {
  it("should return a string", () => {
    const id = newUuid();
    expect(typeof id).toBe("string");
  });

  it("should match UUID v4 format", () => {
    const id = newUuid();
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );
  });

  it("should generate unique values", () => {
    const ids = new Set(Array.from({ length: 100 }, () => newUuid()));
    expect(ids.size).toBe(100);
  });

  it("should be exposed on window", () => {
    expect(window.newUuid).toBeDefined();
    expect(typeof window.newUuid).toBe("function");
    expect(window.newUuid()).toMatch(/^[0-9a-f-]+$/i);
  });
});
