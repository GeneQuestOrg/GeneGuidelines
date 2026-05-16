export interface ResearchRun {
  readonly runId: string;
  readonly diseaseSlug: string | null;
  readonly flowKey: string;
  readonly label: string;
  readonly startedAt: string | null;
  readonly elapsedSec: number | null;
}

export interface ResearchRunsResponse {
  readonly runs: readonly ResearchRun[];
}
