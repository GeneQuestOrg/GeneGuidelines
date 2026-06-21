import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelineBaseline } from "../types/guidelineBaseline";

export interface GuidelineBaselineState {
  baseline: GuidelineBaseline | null;
  loading: boolean;
  error: string | null;
}

/**
 * Level-(c) AI baseline. `enabled` gates the fetch: a disease that already has
 * an official guideline has no baseline, so callers pass `false` to skip the
 * request entirely (the backend has no `guideline-baseline` route, so an
 * ungated call 404s on every disease and just spams the console).
 */
export function useGuidelineBaseline(
  diseaseSlug: string,
  enabled = true,
): GuidelineBaselineState {
  const [baseline, setBaseline] = useState<GuidelineBaseline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Disabled (an official guideline exists): skip the fetch. No setState here
    // — the derived return below reports an idle state instead.
    if (!enabled) {
      return;
    }
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
  }, [diseaseSlug, enabled]);

  if (!enabled) {
    return { baseline: null, loading: false, error: null };
  }
  return { baseline, loading, error };
}
