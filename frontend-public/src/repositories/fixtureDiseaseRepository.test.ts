import { describe, expect, it } from "vitest";
import { fixtureDiseaseRepository } from "./fixtureDiseaseRepository";
import { isValidDiseaseSlug, normalizeDiseaseSlug } from "../router/slug";

describe("fixtureDiseaseRepository", () => {
  it("lists all fixture diseases", async () => {
    const list = await fixtureDiseaseRepository.listDiseases();
    expect(list.length).toBeGreaterThanOrEqual(3);
    expect(list.some((d) => d.slug === "fd")).toBe(true);
  });

  it("gets disease by slug", async () => {
    const fd = await fixtureDiseaseRepository.getDiseaseBySlug("fd");
    expect(fd?.name).toBe("Fibrous Dysplasia");
  });

  it("returns null for invalid slug", async () => {
    expect(await fixtureDiseaseRepository.getDiseaseBySlug("../evil")).toBeNull();
  });

  it("searches by gene name", async () => {
    const hits = await fixtureDiseaseRepository.searchDiseases("GNAS");
    expect(hits.some((d) => d.slug === "fd")).toBe(true);
  });

  it("returns catalog stats", async () => {
    const stats = await fixtureDiseaseRepository.getCatalogStats();
    expect(stats.diseaseCount).toBeGreaterThan(0);
    expect(stats.openPrCount).toBeGreaterThan(0);
  });
});

describe("disease slug helpers", () => {
  it("accepts valid slugs", () => {
    expect(isValidDiseaseSlug("fibrous-dysplasia")).toBe(true);
    expect(normalizeDiseaseSlug("FD")).toBe("fd");
  });

  it("rejects invalid slugs", () => {
    expect(isValidDiseaseSlug("")).toBe(false);
    expect(isValidDiseaseSlug("bad slug")).toBe(false);
    expect(normalizeDiseaseSlug("javascript:alert(1)")).toBeNull();
  });
});
