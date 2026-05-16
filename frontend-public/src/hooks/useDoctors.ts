import { useEffect, useState } from "react";
import type { PublicDoctor } from "../types/doctor";
import { repositories } from "../repositories";

export interface DoctorsState {
  doctors: readonly PublicDoctor[];
  loading: boolean;
  error: string | null;
}

export function useDoctors(): DoctorsState {
  const [doctors, setDoctors] = useState<readonly PublicDoctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { doctors: repo } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const rows = await repo.listAllDoctors();
        if (!cancelled) {
          setDoctors(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load specialists.");
          setDoctors([]);
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
  }, []);

  return { doctors, loading, error };
}
