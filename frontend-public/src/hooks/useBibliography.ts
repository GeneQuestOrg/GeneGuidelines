import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { repositories } from "../repositories";
import type { AnalyzedPaper } from "../types/analyzedPaper";

export interface BibliographyState {
  papers: readonly AnalyzedPaper[];
  loading: boolean;
  error: string | null;
}

export function useBibliography(diseaseSlug: string): BibliographyState {
  const { t } = useTranslation("common");
  const [papers, setPapers] = useState<readonly AnalyzedPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getBibliography(diseaseSlug);
        if (!cancelled) {
          setPapers(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("errors.failedToLoadBibliography"));
          setPapers([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug, t]);

  return { papers, loading, error };
}
