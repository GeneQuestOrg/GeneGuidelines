import { apiGet, ApiRequestError } from "../api/client";
import type { ParentPathway } from "../types/parentPathway";
import { normalizeDiseaseSlug } from "./slug";

export async function fetchParentPathway(
  diseaseSlug: string,
): Promise<ParentPathway | null> {
  const normalized = normalizeDiseaseSlug(diseaseSlug);
  if (normalized == null) {
    return null;
  }
  try {
    return await apiGet<ParentPathway>(
      `/api/diseases/${encodeURIComponent(normalized)}/pathway`,
    );
  } catch (err) {
    if (err instanceof ApiRequestError && err.status === 404) {
      return null;
    }
    throw err;
  }
}
