import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";

export interface GuidelineSynthesisState {
  synthesis: GuidelineSynthesis | null;
  loading: boolean;
  error: string | null;
}

export function useGuidelineSynthesis(diseaseSlug: string): GuidelineSynthesisState {
  const [synthesis, setSynthesis] = useState<GuidelineSynthesis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getSynthesis(diseaseSlug);
        if (!cancelled) {
          setSynthesis(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load the guideline synthesis.",
          );
          setSynthesis(null);
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

  return { synthesis, loading, error };
}
