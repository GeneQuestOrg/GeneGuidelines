import { apiGet, ApiRequestError } from "../api/client";
import type { CatalogStats, Disease } from "../types";
import { normalizeDiseaseSlug } from "./slug";
import type { DiseaseRepository } from "./types";

export const apiDiseaseRepository: DiseaseRepository = {
  listDiseases(): Promise<readonly Disease[]> {
    return apiGet<readonly Disease[]>("/api/diseases");
  },

  async getDiseaseBySlug(slug: string): Promise<Disease | null> {
    const normalized = normalizeDiseaseSlug(slug);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<Disease>(`/api/diseases/${encodeURIComponent(normalized)}`);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  searchDiseases(query: string): Promise<readonly Disease[]> {
    const q = query.trim();
    if (!q) {
      return apiGet<readonly Disease[]>("/api/diseases");
    }
    const params = new URLSearchParams({ q });
    return apiGet<readonly Disease[]>(`/api/diseases?${params.toString()}`);
  },

  getCatalogStats(): Promise<CatalogStats> {
    return apiGet<CatalogStats>("/api/catalog/stats");
  },
};
