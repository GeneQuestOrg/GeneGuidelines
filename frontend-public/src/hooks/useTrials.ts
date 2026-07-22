import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { repositories } from "../repositories";
import type { Trial } from "../types/trial";

export interface TrialsState {
  trials: readonly Trial[];
  loading: boolean;
  error: string | null;
}

/**
 * Load the full trial catalog once for the faceted browser. Mirrors {@link useDoctors}: the
 * browser fetches everything and filters/sorts client-side from the URL query, so the map can
 * always show the full filtered set without an extra round trip per facet change.
 */
export function useTrials(): TrialsState {
  const { t } = useTranslation("common");
  const [trials, setTrials] = useState<readonly Trial[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { trials: repo } = repositories();

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const rows = await repo.listAll();
        if (!cancelled) {
          setTrials(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("errors.couldNotLoadTrials"));
          setTrials([]);
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
  }, [t]);

  return { trials, loading, error };
}
