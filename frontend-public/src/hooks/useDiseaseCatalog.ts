import { useEffect, useState } from "react";
import type { CatalogStats, Disease } from "../types";
import { repositories } from "../repositories";

export interface DiseaseCatalogState {
  diseases: readonly Disease[];
  stats: CatalogStats | null;
  loading: boolean;
  error: string | null;
}

export function useDiseaseCatalog(searchQuery = ""): DiseaseCatalogState {
  const [diseases, setDiseases] = useState<readonly Disease[]>([]);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().diseases;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [list, catalogStats] = await Promise.all([
          searchQuery.trim()
            ? repo.searchDiseases(searchQuery)
            : repo.listDiseases(),
          repo.getCatalogStats(),
        ]);
        if (!cancelled) {
          setDiseases(list);
          setStats(catalogStats);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load disease catalog.",
          );
          setDiseases([]);
          setStats(null);
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
  }, [searchQuery]);

  return { diseases, stats, loading, error };
}
