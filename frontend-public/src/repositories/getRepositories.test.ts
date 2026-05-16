import { describe, expect, it, vi } from "vitest";
import { getRepositories } from "./index";
import { fixtureDiseaseRepository } from "./fixtureDiseaseRepository";
import { fixtureResearchRunsRepository } from "./fixtureResearchRunsRepository";
import { apiDiseaseRepository } from "./apiDiseaseRepository";
import { apiResearchRunsRepository } from "./apiResearchRunsRepository";

describe("getRepositories", () => {
  it("returns api repos by default (production target)", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "");
    const repos = getRepositories();
    expect(repos.diseases).toBe(apiDiseaseRepository);
    expect(repos.researchRuns).toBe(apiResearchRunsRepository);
  });

  it("returns fixture stubs when VITE_DATA_SOURCE=fixture", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "fixture");
    const repos = getRepositories();
    expect(repos.diseases).toBe(fixtureDiseaseRepository);
    expect(repos.researchRuns).toBe(fixtureResearchRunsRepository);
    vi.unstubAllEnvs();
  });
});
