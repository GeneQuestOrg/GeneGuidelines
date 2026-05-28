import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { ResearchRun } from "../types/researchRun";

const POLL_INTERVAL_MS = 8_000;

export interface ActiveResearchState {
  runs: readonly ResearchRun[];
  error: string | null;
}

/**
 * Polls the active-research projection endpoint and keeps the home view's
 * "Active research" section in sync with what the workflow engine is
 * currently executing. A poll every 10 s is plenty for a section that
 * disappears as soon as the runs finish — a heavier SSE channel would be
 * unjustified here.
 */
export function useActiveResearchRuns(limit = 3): ActiveResearchState {
  const [runs, setRuns] = useState<readonly ResearchRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().researchRuns;

    async function load(): Promise<void> {
      try {
        const next = await repo.listActiveRuns(limit);
        if (!cancelled) {
          setRuns(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load runs.");
        }
      }
    }

    void load();
    const id = setInterval(() => {
      void load();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [limit]);

  return { runs, error };
}
