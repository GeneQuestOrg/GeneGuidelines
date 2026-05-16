import { CONTENT_PR_DETAILS, CONTENT_PRS } from "../data";
import type { ContentPrSummary, GuidelinePrDetail } from "../types/contentPr";
import { normalizeDiseaseSlug } from "./slug";
import type { ContentPrListFilters, ContentPrRepository } from "./types";

const PR_ID_PATTERN = /^PR-\d{3,}$/;

function normalizePrId(prId: string): string | null {
  const trimmed = prId.trim().toUpperCase();
  if (!PR_ID_PATTERN.test(trimmed)) {
    return null;
  }
  return trimmed;
}

export const fixtureContentPrRepository: ContentPrRepository = {
  async listPrs(filters?: ContentPrListFilters): Promise<readonly ContentPrSummary[]> {
    let rows: readonly ContentPrSummary[] = CONTENT_PRS;
    if (filters?.disease != null) {
      const slug = normalizeDiseaseSlug(filters.disease);
      if (slug == null) {
        return [];
      }
      rows = rows.filter((pr) => pr.disease === slug);
    }
    if (filters?.status != null) {
      rows = rows.filter((pr) => pr.status === filters.status);
    }
    return rows;
  },

  async getPrById(prId: string): Promise<GuidelinePrDetail | null> {
    const normalized = normalizePrId(prId);
    if (normalized == null) {
      return null;
    }
    return CONTENT_PR_DETAILS[normalized] ?? null;
  },
};
