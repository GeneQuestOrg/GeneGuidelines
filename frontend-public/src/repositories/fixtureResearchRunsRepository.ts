import type { ResearchRun } from "../types/researchRun";
import type { ResearchRunsRepository } from "./types";

// One sample run so the offline/storybook mode renders the section.
const FIXTURE_RUNS: readonly ResearchRun[] = [
  {
    runId: "fixture-run-1",
    diseaseSlug: "noonan",
    flowKey: "pubmed",
    label: "Noonan syndrome — fresh PubMed sweep",
    startedAt: new Date(Date.now() - 4 * 60_000).toISOString(),
    elapsedSec: 240,
  },
];

export const fixtureResearchRunsRepository: ResearchRunsRepository = {
  async listActiveRuns(limit = 3): Promise<readonly ResearchRun[]> {
    return FIXTURE_RUNS.slice(0, limit);
  },
};
