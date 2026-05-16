import { apiGet } from "../api/client";
import type { ResearchRun, ResearchRunsResponse } from "../types/researchRun";
import type { ResearchRunsRepository } from "./types";

export const apiResearchRunsRepository: ResearchRunsRepository = {
  async listActiveRuns(limit = 3): Promise<readonly ResearchRun[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    const payload = await apiGet<ResearchRunsResponse>(
      `/api/research-runs?${params.toString()}`,
    );
    return payload.runs;
  },
};
