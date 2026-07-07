import { useEffect, useState } from "react";
import type { GuidelinePrDetail } from "../types/contentPr";
import { repositories } from "../repositories";

export interface GuidelinePrState {
  pr: GuidelinePrDetail | null;
  loading: boolean;
  error: string | null;
}

export function useGuidelinePr(prId: string | undefined): GuidelinePrState {
  const [pr, setPr] = useState<GuidelinePrDetail | null>(null);
  const [loading, setLoading] = useState(prId != null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (prId == null || prId.trim().length === 0) {
      return undefined;
    }

    const activePrId = prId;
    let cancelled = false;
    const { contentPrs } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const row = await contentPrs.getPrById(activePrId);
        if (!cancelled) {
          setPr(row);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load proposed update.");
          setPr(null);
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
  }, [prId]);

  return { pr, loading, error };
}
