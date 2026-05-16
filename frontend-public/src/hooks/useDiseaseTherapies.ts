import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { Therapy } from "../types/therapy";

export interface DiseaseTherapiesState {
  therapies: readonly Therapy[];
  loading: boolean;
  error: string | null;
}

export function useDiseaseTherapies(diseaseSlug: string): DiseaseTherapiesState {
  const [therapies, setTherapies] = useState<readonly Therapy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().therapies;

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const list = await repo.listForDisease(diseaseSlug);
        if (!cancelled) {
          setTherapies(list);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load therapies.");
          setTherapies([]);
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
  }, [diseaseSlug]);

  return { therapies, loading, error };
}
