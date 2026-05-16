import { useEffect, useState } from "react";
import type { ContentDiseaseOption } from "../api/client";
import { fetchContentDiseasesCached } from "../api/diseaseCatalogCache";

export function useDiseaseCatalog(): {
  diseases: ContentDiseaseOption[];
  loading: boolean;
  error: string | null;
} {
  const [diseases, setDiseases] = useState<ContentDiseaseOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchContentDiseasesCached()
      .then((rows) => {
        if (!cancelled) {
          setDiseases(rows);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { diseases, loading, error };
}
