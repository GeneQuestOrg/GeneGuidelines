import { useEffect, useState } from "react";
import type { ContentPrSummary } from "../types";
import { isOpenPrStatus } from "../utils/guidelineDiff";
import { repositories } from "../repositories";

export interface ContentPrsState {
  prs: readonly ContentPrSummary[];
  openPrs: readonly ContentPrSummary[];
  loading: boolean;
  error: string | null;
}

export function useContentPrs(diseaseSlug: string): ContentPrsState {
  const [prs, setPrs] = useState<readonly ContentPrSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { contentPrs } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const rows = await contentPrs.listPrs({ disease: diseaseSlug });
        if (!cancelled) {
          setPrs(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load proposed updates.");
          setPrs([]);
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

  const openPrs = prs.filter((pr) => isOpenPrStatus(pr.status));

  return { prs, openPrs, loading, error };
}
