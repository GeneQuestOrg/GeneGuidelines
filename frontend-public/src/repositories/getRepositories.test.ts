import { describe, expect, it, vi } from "vitest";
import { getRepositories } from "./index";
import { fixtureDiseaseRepository } from "./fixtureDiseaseRepository";
import { apiDiseaseRepository } from "./apiDiseaseRepository";

describe("getRepositories", () => {
  it("returns api repos by default (production target)", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "");
    const repos = getRepositories();
    expect(repos.diseases).toBe(apiDiseaseRepository);
  });

  it("returns fixture stubs when VITE_DATA_SOURCE=fixture", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "fixture");
    const repos = getRepositories();
    expect(repos.diseases).toBe(fixtureDiseaseRepository);
    vi.unstubAllEnvs();
  });
});
