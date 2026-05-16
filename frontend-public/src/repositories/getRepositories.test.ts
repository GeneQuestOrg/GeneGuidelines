import { describe, expect, it, vi } from "vitest";
import { getRepositories } from "./index";
import { fixtureDiseaseRepository } from "./fixtureDiseaseRepository";
import { apiDiseaseRepository } from "./apiDiseaseRepository";

describe("getRepositories", () => {
  it("returns fixture repos by default", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "");
    const repos = getRepositories();
    expect(repos.diseases).toBe(fixtureDiseaseRepository);
  });

  it("returns api stubs when VITE_DATA_SOURCE=api", () => {
    vi.stubEnv("VITE_DATA_SOURCE", "api");
    const repos = getRepositories();
    expect(repos.diseases).toBe(apiDiseaseRepository);
    vi.unstubAllEnvs();
  });
});
