import { apiGet, ApiRequestError } from "../api/client";
import type { Trial } from "../types/trial";
import { normalizeDiseaseSlug } from "./slug";
import type { TrialRepository } from "./types";

export const apiTrialRepository: TrialRepository = {
  async listAll(): Promise<readonly Trial[]> {
    return apiGet<readonly Trial[]>("/api/trials");
  },

  async listForDisease(diseaseSlug: string): Promise<readonly Trial[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly Trial[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/trials`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },
};
