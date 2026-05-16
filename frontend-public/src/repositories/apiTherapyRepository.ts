import { apiGet, ApiRequestError } from "../api/client";
import type { Therapy } from "../types/therapy";
import { normalizeDiseaseSlug } from "./slug";
import type { TherapyRepository } from "./types";

export const apiTherapyRepository: TherapyRepository = {
  async listForDisease(diseaseSlug: string): Promise<readonly Therapy[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly Therapy[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/therapies`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },
};
