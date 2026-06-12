import { afterEach, describe, expect, it, vi } from "vitest";
import { getAuth0Config, isAuth0Configured } from "./authConfig";

describe("authConfig env-gating", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is disabled when VITE_AUTH0_DOMAIN is unset", () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "");
    expect(getAuth0Config()).toBeNull();
    expect(isAuth0Configured()).toBe(false);
  });

  it("treats whitespace-only domain as unset", () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "   ");
    expect(isAuth0Configured()).toBe(false);
  });

  it("is enabled and reads all three vars when the domain is set", () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "tenant.eu.auth0.com");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "abc123");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "https://api.geneguidelines.org");
    expect(isAuth0Configured()).toBe(true);
    expect(getAuth0Config()).toEqual({
      domain: "tenant.eu.auth0.com",
      clientId: "abc123",
      audience: "https://api.geneguidelines.org",
    });
  });

  it("trims surrounding whitespace from values", () => {
    vi.stubEnv("VITE_AUTH0_DOMAIN", "  tenant.eu.auth0.com  ");
    vi.stubEnv("VITE_AUTH0_CLIENT_ID", "  abc123  ");
    vi.stubEnv("VITE_AUTH0_AUDIENCE", "");
    expect(getAuth0Config()).toEqual({
      domain: "tenant.eu.auth0.com",
      clientId: "abc123",
      audience: "",
    });
  });
});
