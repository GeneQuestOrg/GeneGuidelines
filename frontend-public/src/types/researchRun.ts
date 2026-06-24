export interface ResearchRun {
  readonly runId: string;
  readonly diseaseSlug: string | null;
  readonly flowKey: string;
  readonly label: string;
  readonly startedAt: string | null;
  readonly elapsedSec: number | null;
  /**
   * "token_budget" when the worker is paused on the monthly token budget, else
   * null. Lets the "Active research" card show a "Czeka — budżet tokenów" badge.
   */
  readonly blockedReason: string | null;
}

export interface ResearchRunsResponse {
  readonly runs: readonly ResearchRun[];
}
