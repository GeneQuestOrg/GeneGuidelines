import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { OfficialGuideline } from "../types/officialGuideline";

export interface OfficialGuidelineState {
  pointer: OfficialGuideline | null;
  loading: boolean;
  error: string | null;
}

export function useOfficialGuideline(diseaseSlug: string): OfficialGuidelineState {
  const [pointer, setPointer] = useState<OfficialGuideline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getForDisease(
          diseaseSlug,
        );
        if (!cancelled) {
          setPointer(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load official guideline pointer.",
          );
          setPointer(null);
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

  return { pointer, loading, error };
}
