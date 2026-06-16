import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";

export interface GuidelineSuggestionsState {
  suggestions: readonly GuidelineSuggestion[];
  loading: boolean;
  error: string | null;
}

export function useGuidelineSuggestions(diseaseSlug: string): GuidelineSuggestionsState {
  const [suggestions, setSuggestions] = useState<readonly GuidelineSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getSuggestions(diseaseSlug);
        if (!cancelled) {
          setSuggestions(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load AI suggestions.",
          );
          setSuggestions([]);
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

  return { suggestions, loading, error };
}
