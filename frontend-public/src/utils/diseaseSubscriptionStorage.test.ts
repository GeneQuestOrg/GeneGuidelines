// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearStoredSubscriptionRef,
  ensureSubscriptionRef,
  readStoredSubscriptionRef,
} from "./diseaseSubscriptionStorage";

describe("disease subscription storage", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("keeps a random reference per disease, never the email address", () => {
    const ref = ensureSubscriptionRef("fd");
    expect(ref).toMatch(/^[0-9a-f]{32}$/);
    expect(ensureSubscriptionRef("fd")).toBe(ref);
    expect(readStoredSubscriptionRef("fd")).toBe(ref);
    expect(ensureSubscriptionRef("mas")).not.toBe(ref);
    expect(JSON.stringify({ ...localStorage })).not.toContain("@");
  });

  it("deletes an email address an older version stored", () => {
    localStorage.setItem("gg-sub-email-fd", "parent@example.com");
    expect(readStoredSubscriptionRef("fd")).toBeNull();
    expect(localStorage.getItem("gg-sub-email-fd")).toBeNull();
  });

  it("forgets the reference on request", () => {
    ensureSubscriptionRef("fd");
    clearStoredSubscriptionRef("fd");
    expect(readStoredSubscriptionRef("fd")).toBeNull();
  });
});
