import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";

export interface GuidelineSuggestionsState {
  suggestions: readonly GuidelineSuggestion[];
  loading: boolean;
  error: string | null;
}

/**
 * @param authKey  Changes when the signed-in account resolves (e.g. its id).
 *   Passed as an effect dep so the rail refetches once auth is ready — the first
 *   fetch on a fresh load runs before the token getter registers, so without this
 *   each suggestion's `myVote` would stay null until the next navigation.
 */
export function useGuidelineSuggestions(
  diseaseSlug: string,
  authKey?: string | null,
): GuidelineSuggestionsState {
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
  }, [diseaseSlug, authKey]);

  return { suggestions, loading, error };
}
