import { GUIDELINE_DOCUMENTS, GUIDELINE_META } from "../data";
import type { GuidelineMeta } from "../types";
import { normalizeDiseaseSlug } from "./slug";
import type { GuidelineRepository } from "./types";

export const fixtureGuidelineRepository: GuidelineRepository = {
  async getGuidelineMeta(diseaseSlug: string): Promise<GuidelineMeta | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    return GUIDELINE_META[normalized] ?? null;
  },

  async getGuidelineDocument(diseaseSlug: string) {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    return GUIDELINE_DOCUMENTS[normalized] ?? null;
  },
};
