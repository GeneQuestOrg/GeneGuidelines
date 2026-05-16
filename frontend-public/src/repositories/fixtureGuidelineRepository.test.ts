import { describe, expect, it } from "vitest";
import { fixtureGuidelineRepository } from "./fixtureGuidelineRepository";

describe("fixtureGuidelineRepository", () => {
  it("returns FD guideline document", async () => {
    const doc = await fixtureGuidelineRepository.getGuidelineDocument("fd");
    expect(doc?.slug).toBe("fd");
    expect(doc?.sections.length).toBeGreaterThan(0);
  });

  it("returns null for unknown slug", async () => {
    expect(
      await fixtureGuidelineRepository.getGuidelineDocument("unknown-slug-xyz"),
    ).toBeNull();
  });
});
