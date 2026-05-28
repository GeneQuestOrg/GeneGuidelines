import { apiGet } from "../api/client";
import type {
  ResearchRun,
  ResearchRunHistoryItem,
  ResearchRunHistoryResponse,
  ResearchRunsResponse,
} from "../types/researchRun";
import type { ResearchRunsRepository } from "./types";

export const apiResearchRunsRepository: ResearchRunsRepository = {
  async listActiveRuns(limit = 3): Promise<readonly ResearchRun[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    const payload = await apiGet<ResearchRunsResponse>(
      `/api/research-runs?${params.toString()}`,
    );
    return payload.runs;
  },

  async listMyActiveRuns(limit = 5): Promise<readonly ResearchRun[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    const payload = await apiGet<ResearchRunsResponse>(
      `/api/research-runs/mine?${params.toString()}`,
    );
    return payload.runs;
  },

  async listMyRunHistory(limit = 20): Promise<readonly ResearchRunHistoryItem[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    const payload = await apiGet<ResearchRunHistoryResponse>(
      `/api/research-runs/mine/history?${params.toString()}`,
    );
    return payload.runs;
  },
};
