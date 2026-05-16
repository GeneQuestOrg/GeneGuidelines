import { useEffect, useState } from "react";
import type { PublicDoctor } from "../types/doctor";
import { repositories } from "../repositories";

export interface DoctorState {
  doctor: PublicDoctor | null;
  loading: boolean;
  error: string | null;
}

export function useDoctor(slug: string): DoctorState {
  const [doctor, setDoctor] = useState<PublicDoctor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { doctors: repo } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const row = await repo.getDoctorBySlug(slug);
        if (!cancelled) {
          setDoctor(row);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load specialist profile.");
          setDoctor(null);
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
  }, [slug]);

  return { doctor, loading, error };
}
