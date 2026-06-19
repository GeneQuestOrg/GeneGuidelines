import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { AnalyzedPaper } from "../types/analyzedPaper";

export interface BibliographyState {
  papers: readonly AnalyzedPaper[];
  loading: boolean;
  error: string | null;
}

export function useBibliography(diseaseSlug: string): BibliographyState {
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
          setError(err instanceof Error ? err.message : "Failed to load analyzed bibliography.");
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
  }, [diseaseSlug]);

  return { papers, loading, error };
}
