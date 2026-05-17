import { apiGet, ApiRequestError, apiPostFormData } from "../api/client";
import type { PrivateContext } from "../types/privateContext";
import { normalizeDiseaseSlug } from "./slug";
import type { PrivateContextRepository } from "./types";

export const apiPrivateContextRepository: PrivateContextRepository = {
  async upload(
    diseaseSlug: string,
    file: File,
  ): Promise<PrivateContext | null> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return null;
    }
    const formData = new FormData();
    formData.append("file", file, file.name);
    try {
      return await apiPostFormData<PrivateContext>(
        `/api/diseases/${encodeURIComponent(normalized)}/private-context`,
        formData,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  async listForDisease(diseaseSlug: string): Promise<readonly PrivateContext[]> {
    const normalized = normalizeDiseaseSlug(diseaseSlug);
    if (normalized == null) {
      return [];
    }
    try {
      return await apiGet<readonly PrivateContext[]>(
        `/api/diseases/${encodeURIComponent(normalized)}/private-contexts`,
      );
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return [];
      }
      throw err;
    }
  },
};
