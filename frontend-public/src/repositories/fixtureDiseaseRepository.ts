import { computeCatalogStats, DISEASES } from "../data";
import type { CatalogStats, Disease } from "../types";
import { normalizeDiseaseSlug } from "./slug";
import type { DiseaseRepository } from "./types";

function matchesQuery(disease: Disease, query: string): boolean {
  const s = query.toLowerCase();
  return (
    disease.name.toLowerCase().includes(s) ||
    disease.nameShort.toLowerCase().includes(s) ||
    disease.gene.toLowerCase().includes(s) ||
    disease.summary.toLowerCase().includes(s) ||
    disease.slug.includes(s)
  );
}

export const fixtureDiseaseRepository: DiseaseRepository = {
  async listDiseases(): Promise<readonly Disease[]> {
    return DISEASES;
  },

  async getDiseaseBySlug(slug: string): Promise<Disease | null> {
    const normalized = normalizeDiseaseSlug(slug);
    if (normalized == null) {
      return null;
    }
    return DISEASES.find((d) => d.slug === normalized) ?? null;
  },

  async searchDiseases(query: string): Promise<readonly Disease[]> {
    const q = query.trim();
    if (!q) {
      return DISEASES;
    }
    return DISEASES.filter((d) => matchesQuery(d, q));
  },

  async getCatalogStats(): Promise<CatalogStats> {
    return computeCatalogStats();
  },
};
