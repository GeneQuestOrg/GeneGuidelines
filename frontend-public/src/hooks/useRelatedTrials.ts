import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { repositories } from "../repositories";
import type { Trial } from "../types/trial";
import { dedupeTrials } from "../utils/dedupeTrials";

export interface RelatedTrialsState {
  trials: readonly Trial[];
  loading: boolean;
  error: string | null;
}

/**
 * Trials across several diseases in a single effect — one Promise.all over the trials repo, flattened
 * and deduped by nct. Do NOT call useDiseaseTrials in a loop; this keeps a single hook/effect.
 */
export function useRelatedTrials(slugs: readonly string[]): RelatedTrialsState {
  const { t } = useTranslation("common");
  const [trials, setTrials] = useState<readonly Trial[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stable dependency so re-renders with an equivalent slug array do not refetch.
  const slugKey = slugs.join(",");

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().trials;
    const slugList = slugKey ? slugKey.split(",") : [];

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const lists = await Promise.all(slugList.map((slug) => repo.listForDisease(slug)));
        if (!cancelled) {
          setTrials(dedupeTrials(lists));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("errors.failedToLoadTrials"));
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
  }, [slugKey, t]);

  return { trials, loading, error };
}
