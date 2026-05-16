import { afterEach, describe, expect, it, vi } from "vitest";
import { getAdminAppUrl, getLegacyOpsUrl, isAdminLinkVisible } from "./adminUrl";

describe("adminUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to local admin port in dev", () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_ADMIN_URL", "");
    expect(getAdminAppUrl()).toBe("http://localhost:5174");
    expect(isAdminLinkVisible()).toBe(true);
  });

  it("uses VITE_ADMIN_URL when set", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_ADMIN_URL", "https://admin.example.com/");
    expect(getAdminAppUrl()).toBe("https://admin.example.com");
  });

  it("exposes legacy ops URL in dev", () => {
    vi.stubEnv("DEV", true);
    expect(getLegacyOpsUrl()).toBe("http://localhost:5175");
  });
});
