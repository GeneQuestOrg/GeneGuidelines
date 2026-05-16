import { apiGet, ApiRequestError } from "../api/client";
import type { GuidelineDocument } from "../types/guidelineDocument";
import type { GuidelineMeta } from "../types";
import { normalizeDiseaseSlug } from "./slug";
import type { GuidelineRepository } from "./types";

export const apiGuidelineRepository: GuidelineRepository = {
  async getGuidelineMeta(diseaseSlug: string): Promise<GuidelineMeta | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<GuidelineMeta>(
        `/api/diseases/${encodeURIComponent(normalized)}/guideline`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  async getGuidelineDocument(diseaseSlug: string): Promise<GuidelineDocument | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<GuidelineDocument>(
        `/api/diseases/${encodeURIComponent(normalized)}/guideline/document`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },
};
