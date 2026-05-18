import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiDiseaseRepository } from "./apiDiseaseRepository";

describe("apiDiseaseRepository", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("lists diseases from GET /api/diseases", async () => {
    const mockDisease = {
      slug: "fd",
      name: "Fibrous Dysplasia",
      nameShort: "FD",
      omim: "174800",
      gene: "GNAS",
      inheritance: "Somatic",
      summary: "Summary",
      types: [],
      related: [],
      prevalenceText: "rare",
      status: "consensus",
      statusBy: null,
      statusDate: null,
      aiDraftDate: null,
      openPRs: 0,
      doctorsCount: 0,
      trialsCount: 0,
      coverage: "full",
      accent: "teal",
    };
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () => JSON.stringify([mockDisease]),
    } as Response);

    const list = await apiDiseaseRepository.listDiseases();
    expect(list).toHaveLength(1);
    expect(fetch).toHaveBeenCalledWith(
      "/api/diseases",
      expect.objectContaining({
        headers: { Accept: "application/json" },
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("returns null for 404 disease", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "Disease not found" }),
    } as Response);

    const result = await apiDiseaseRepository.getDiseaseBySlug("missing");
    expect(result).toBeNull();
  });
});
