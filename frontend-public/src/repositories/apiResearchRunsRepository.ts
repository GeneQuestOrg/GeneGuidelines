import { apiGet } from "../api/client";
import type { ResearchRun } from "../types/researchRun";
import type { ResearchRunsRepository } from "./types";

/** Raw run as returned by GET /api/research-runs (camelCase, optional fields). */
interface ResearchRunWire {
  runId: string;
  diseaseSlug: string | null;
  flowKey: string;
  label: string;
  startedAt: string | null;
  elapsedSec: number | null;
  blockedReason?: string | null;
}

export const apiResearchRunsRepository: ResearchRunsRepository = {
  async listActiveRuns(limit = 3): Promise<readonly ResearchRun[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    const payload = await apiGet<{ runs: readonly ResearchRunWire[] }>(
      `/api/research-runs?${params.toString()}`,
    );
    return payload.runs.map((r) => ({
      runId: r.runId,
      diseaseSlug: r.diseaseSlug,
      flowKey: r.flowKey,
      label: r.label,
      startedAt: r.startedAt,
      elapsedSec: r.elapsedSec,
      blockedReason: r.blockedReason ?? null,
    }));
  },
};
