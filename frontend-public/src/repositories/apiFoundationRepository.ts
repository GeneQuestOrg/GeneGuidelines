import { apiGet, ApiRequestError } from "../api/client";
import type { Foundation } from "../types/foundation";
import { normalizeDiseaseSlug } from "./slug";
import type { FoundationRepository } from "./types";

export const apiFoundationRepository: FoundationRepository = {
  async listForDisease(diseaseSlug: string): Promise<readonly Foundation[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly Foundation[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/foundations`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },
};
