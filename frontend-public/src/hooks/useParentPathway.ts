import { useEffect, useState } from "react";
import { fetchParentPathway } from "../repositories/apiParentPathwayRepository";
import type { ParentPathway } from "../types/parentPathway";

export function useParentPathway(slug: string): {
  pathway: ParentPathway | null;
  loading: boolean;
  error: string | null;
} {
  const [pathway, setPathway] = useState<ParentPathway | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchParentPathway(slug);
        if (!cancelled) {
          setPathway(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setPathway(null);
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

  return { pathway, loading, error };
}
