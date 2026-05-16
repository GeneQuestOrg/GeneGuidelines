import { apiGet, ApiRequestError } from "../api/client";
import type { ContentPrSummary, GuidelinePrDetail } from "../types/contentPr";
import type { ContentPrListFilters, ContentPrRepository } from "./types";

const PR_ID_PATTERN = /^PR-\d{3,}$/;

function normalizePrId(prId: string): string | null {
  const trimmed = prId.trim().toUpperCase();
  if (!PR_ID_PATTERN.test(trimmed)) {
    return null;
  }
  return trimmed;
}

export const apiContentPrRepository: ContentPrRepository = {
  async listPrs(filters?: ContentPrListFilters): Promise<readonly ContentPrSummary[]> {
    const params = new URLSearchParams();
    if (filters?.disease != null) {
      params.set("disease", filters.disease);
    }
    if (filters?.status != null) {
      params.set("status", filters.status);
    }
    const query = params.toString();
    const path = query.length > 0 ? `/api/guideline-prs?${query}` : "/api/guideline-prs";
    return apiGet<readonly ContentPrSummary[]>(path);
  },

  async getPrById(prId: string): Promise<GuidelinePrDetail | null> {
    const normalized = normalizePrId(prId);
    if (normalized == null) {
      return null;
    }
    try {
      return await apiGet<GuidelinePrDetail>(
        `/api/guideline-prs/${encodeURIComponent(normalized)}`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },
};
