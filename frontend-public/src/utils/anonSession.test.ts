// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ANON_SESSION_STORAGE_KEY, getAnonSessionId } from "./anonSession";

describe("getAnonSessionId", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("mints and persists a uuid on first use", () => {
    expect(localStorage.getItem(ANON_SESSION_STORAGE_KEY)).toBeNull();
    const id = getAnonSessionId();
    expect(id).toMatch(/[0-9a-f-]{16,}/i);
    expect(localStorage.getItem(ANON_SESSION_STORAGE_KEY)).toBe(id);
  });

  it("returns the same id across calls (stable per browser)", () => {
    const first = getAnonSessionId();
    const second = getAnonSessionId();
    expect(second).toBe(first);
  });

  it("reuses an existing stored id", () => {
    localStorage.setItem(ANON_SESSION_STORAGE_KEY, "preexisting-id");
    expect(getAnonSessionId()).toBe("preexisting-id");
  });
});
