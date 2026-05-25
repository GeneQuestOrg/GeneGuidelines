import { useEffect, useRef, useState } from "react";
import type { CatalogStats, Disease } from "../types";
import { repositories } from "../repositories";

const _DEBOUNCE_MS = 300;

export interface DiseaseCatalogState {
  diseases: readonly Disease[];
  stats: CatalogStats | null;
  loading: boolean;
  error: string | null;
}

export function useDiseaseCatalog(searchQuery = ""): DiseaseCatalogState {
  const [debouncedQuery, setDebouncedQuery] = useState(searchQuery);
  const [diseases, setDiseases] = useState<readonly Disease[]>([]);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasListRef = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(searchQuery), _DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    let cancelled = false;
    const repo = repositories().diseases;

    async function load() {
      if (!hasListRef.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const [list, catalogStats] = await Promise.all([
          debouncedQuery.trim()
            ? repo.searchDiseases(debouncedQuery)
            : repo.listDiseases(),
          repo.getCatalogStats(),
        ]);
        if (!cancelled) {
          setDiseases(list);
          setStats(catalogStats);
          if (list.length > 0) {
            hasListRef.current = true;
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load disease catalog.",
          );
          if (!hasListRef.current) {
            setDiseases([]);
            setStats(null);
          }
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
  }, [debouncedQuery]);

  return { diseases, stats, loading, error };
}
