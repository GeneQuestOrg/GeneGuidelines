import { apiGet, ApiRequestError } from "../api/client";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { SourceDoc } from "../types/sourceDoc";
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

  // Backend endpoint lands in GL-4 (backend/guidelines/). Until then a 404 just
  // means "no shelf" — fall back to an empty shelf so the UI degrades cleanly.
  async getShelf(diseaseSlug: string): Promise<readonly SourceDoc[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly SourceDoc[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/source-documents`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },
};
