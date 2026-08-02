import { afterEach, describe, expect, it, vi } from "vitest";
import { getDonatePageUrl, getSupportUrl, isDirectCheckout } from "./supportUrl";

describe("supportUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("falls back to the localised donate page when no payment link is set", () => {
    vi.stubEnv("VITE_STRIPE_DONATE_URL", "");

    expect(getSupportUrl("pl")).toBe("https://genequest.org/donacje");
    expect(getSupportUrl("en")).toBe("https://genequest.org/en/donacje");
    expect(isDirectCheckout()).toBe(false);
  });

  it("sends unknown locales to the English donate page", () => {
    expect(getDonatePageUrl("de")).toBe("https://genequest.org/en/donacje");
  });

  it("prefers the Stripe payment link when configured", () => {
    vi.stubEnv("VITE_STRIPE_DONATE_URL", "  https://buy.stripe.com/abc123  ");

    expect(getSupportUrl("pl")).toBe("https://buy.stripe.com/abc123");
    expect(getSupportUrl("en")).toBe("https://buy.stripe.com/abc123");
    expect(isDirectCheckout()).toBe(true);
  });

  it("treats a blank payment link as unconfigured — never a dead CTA", () => {
    vi.stubEnv("VITE_STRIPE_DONATE_URL", "   ");

    expect(getSupportUrl("pl")).toBe("https://genequest.org/donacje");
    expect(isDirectCheckout()).toBe(false);
  });
});
