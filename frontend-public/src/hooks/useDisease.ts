import { useEffect, useState } from "react";
import type { Disease, GuidelineMeta } from "../types";
import { repositories } from "../repositories";

export interface DiseaseDetailState {
  disease: Disease | null;
  guideline: GuidelineMeta | null;
  loading: boolean;
  error: string | null;
}

export function useDisease(slug: string): DiseaseDetailState {
  const [disease, setDisease] = useState<Disease | null>(null);
  const [guideline, setGuideline] = useState<GuidelineMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { diseases, guidelines } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [d, g] = await Promise.all([
          diseases.getDiseaseBySlug(slug),
          guidelines.getGuidelineMeta(slug),
        ]);
        if (!cancelled) {
          setDisease(d);
          setGuideline(g);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load disease.");
          setDisease(null);
          setGuideline(null);
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

  return { disease, guideline, loading, error };
}
