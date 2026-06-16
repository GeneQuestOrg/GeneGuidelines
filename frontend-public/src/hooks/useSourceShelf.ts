import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { SourceDoc } from "../types/sourceDoc";

export interface SourceShelfState {
  docs: readonly SourceDoc[];
  loading: boolean;
  error: string | null;
}

export function useSourceShelf(diseaseSlug: string): SourceShelfState {
  const [docs, setDocs] = useState<readonly SourceDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getShelf(diseaseSlug);
        if (!cancelled) {
          setDocs(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load the source shelf.",
          );
          setDocs([]);
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

  return { docs, loading, error };
}
