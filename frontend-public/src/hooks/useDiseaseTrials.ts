import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import { useContentLocale } from "./useContentLocale";
import type { Trial } from "../types/trial";

export interface DiseaseTrialsState {
  trials: readonly Trial[];
  loading: boolean;
  error: string | null;
}

export function useDiseaseTrials(diseaseSlug: string): DiseaseTrialsState {
  const [trials, setTrials] = useState<readonly Trial[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Re-fetch when the language changes; see useContentLocale.
  const contentLocale = useContentLocale();

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().trials;

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const list = await repo.listForDisease(diseaseSlug);
        if (!cancelled) {
          setTrials(list);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load trials.");
          setTrials([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug, contentLocale]);

  return { trials, loading, error };
}
