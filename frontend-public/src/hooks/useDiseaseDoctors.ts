import { useEffect, useState } from "react";
import type { DiseaseDoctorsPayload } from "../types/doctor";
import { repositories } from "../repositories";

export interface DiseaseDoctorsState {
  payload: DiseaseDoctorsPayload | null;
  loading: boolean;
  error: string | null;
}

export function useDiseaseDoctors(diseaseSlug: string): DiseaseDoctorsState {
  const [payload, setPayload] = useState<DiseaseDoctorsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { doctors: repo } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const row = await repo.getDoctorsForDisease(diseaseSlug);
        if (!cancelled) {
          setPayload(row);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load specialists.");
          setPayload(null);
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

  return { payload, loading, error };
}
