export interface ResearchRun {
  readonly runId: string;
  readonly diseaseSlug: string | null;
  readonly flowKey: string;
  readonly pipeline?: string;
  readonly label: string;
  readonly startedAt: string | null;
  readonly elapsedSec: number | null;
  readonly progressPct?: number;
  readonly activity?: string;
}

export interface ResearchRunsResponse {
  readonly runs: readonly ResearchRun[];
}

export interface ResearchRunHistoryItem {
  readonly runId: string;
  readonly diseaseSlug: string | null;
  readonly flowKey: string;
  readonly label: string;
  readonly status: "running" | "completed" | "failed";
  readonly startedAt: string | null;
  readonly finishedAt: string | null;
  readonly errorSnippet: string | null;
}

export interface ResearchRunHistoryResponse {
  readonly runs: readonly ResearchRunHistoryItem[];
}
