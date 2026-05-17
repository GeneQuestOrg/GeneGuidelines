import { apiGet, ApiRequestError } from "../api/client";
import type { OfficialGuideline } from "../types/officialGuideline";
import { normalizeDiseaseSlug } from "./slug";
import type { OfficialGuidelineRepository } from "./types";

export const apiOfficialGuidelineRepository: OfficialGuidelineRepository = {
  async getForDisease(diseaseSlug: string): Promise<OfficialGuideline | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<OfficialGuideline>(
        `/api/diseases/${encodeURIComponent(normalized)}/official-guideline`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },
};
