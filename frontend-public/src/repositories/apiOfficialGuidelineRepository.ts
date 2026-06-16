import { apiGet, ApiRequestError } from "../api/client";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";
import type { GuidelineSynthesis, SynthSectionSignal } from "../types/guidelineSynthesis";
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

  // Backend endpoint lands in GL-4 (backend/guidelines/). Until then a 404 just
  // means "no synthesis yet" → fall back to null (parent sees the level-(c) gate).
  async getSynthesis(diseaseSlug: string): Promise<GuidelineSynthesis | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<GuidelineSynthesis>(
        `/api/diseases/${encodeURIComponent(normalized)}/guideline-synthesis`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  // Backend endpoint lands in GL-4. 404 → no suggestions yet (empty rail).
  async getSuggestions(diseaseSlug: string): Promise<readonly GuidelineSuggestion[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly GuidelineSuggestion[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/guideline-suggestions`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },

  // Backend endpoint lands in GL-4. 404 → no signal yet (empty map).
  async getSynthSignals(
    diseaseSlug: string,
  ): Promise<Readonly<Record<string, SynthSectionSignal>>> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return {};
    }
    try {
      return await apiGet<Readonly<Record<string, SynthSectionSignal>>>(
        `/api/diseases/${encodeURIComponent(normalized)}/synthesis-signals`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return {};
      }
      throw err;
    }
  },
};
