import { useEffect, useState } from "react";
import type { GuidelineDocument } from "../types/guidelineDocument";
import { repositories } from "../repositories";

export interface GuidelineDocumentState {
  document: GuidelineDocument | null;
  loading: boolean;
  error: string | null;
}

export function useGuidelineDocument(slug: string): GuidelineDocumentState {
  const [document, setDocument] = useState<GuidelineDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const { guidelines } = repositories();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const doc = await guidelines.getGuidelineDocument(slug);
        if (!cancelled) {
          setDocument(doc);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load guideline document.",
          );
          setDocument(null);
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

  return { document, loading, error };
}
