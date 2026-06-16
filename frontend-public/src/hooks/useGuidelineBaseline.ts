import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelineBaseline } from "../types/guidelineBaseline";

export interface GuidelineBaselineState {
  baseline: GuidelineBaseline | null;
  loading: boolean;
  error: string | null;
}

export function useGuidelineBaseline(diseaseSlug: string): GuidelineBaselineState {
  const [baseline, setBaseline] = useState<GuidelineBaseline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getBaseline(diseaseSlug);
        if (!cancelled) {
          setBaseline(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load the AI baseline.",
          );
          setBaseline(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug]);

  return { baseline, loading, error };
}
