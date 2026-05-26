import type { ResearchRun, ResearchRunHistoryItem } from "../types/researchRun";
import type { ResearchRunsRepository } from "./types";

// One sample run so the offline/storybook mode renders the section.
const FIXTURE_RUNS: readonly ResearchRun[] = [
  {
    runId: "fixture-run-1",
    diseaseSlug: "noonan",
    flowKey: "pubmed",
    pipeline: "guideline",
    label: "Noonan syndrome — fresh PubMed sweep",
    startedAt: new Date(Date.now() - 4 * 60_000).toISOString(),
    elapsedSec: 240,
    progressPct: 42,
    activity: "Running step: PubMed evidence collection",
  },
];

export const fixtureResearchRunsRepository: ResearchRunsRepository = {
  async listActiveRuns(limit = 3): Promise<readonly ResearchRun[]> {
    return FIXTURE_RUNS.slice(0, limit);
  },

  async listMyActiveRuns(limit = 5): Promise<readonly ResearchRun[]> {
    return FIXTURE_RUNS.slice(0, limit);
  },

  async listMyRunHistory(): Promise<readonly ResearchRunHistoryItem[]> {
    return [];
  },
};
