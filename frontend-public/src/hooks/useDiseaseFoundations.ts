import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import { useContentLocale } from "./useContentLocale";
import type { Foundation } from "../types/foundation";

export interface DiseaseFoundationsState {
  foundations: readonly Foundation[];
  loading: boolean;
  error: string | null;
}

export function useDiseaseFoundations(
  diseaseSlug: string,
): DiseaseFoundationsState {
  const [foundations, setFoundations] = useState<readonly Foundation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Re-fetch when the language changes; see useContentLocale.
  const contentLocale = useContentLocale();

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().foundations;

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const list = await repo.listForDisease(diseaseSlug);
        if (!cancelled) {
          setFoundations(list);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load supporting foundations.",
          );
          setFoundations([]);
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

  return { foundations, loading, error };
}
