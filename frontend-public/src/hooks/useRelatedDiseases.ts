import { useEffect, useState } from "react";
import type { Disease } from "../types";
import { repositories } from "../repositories";

export function useRelatedDiseases(relatedSlugs: readonly string[]): {
  related: readonly Disease[];
  loading: boolean;
} {
  const slugKey = relatedSlugs.join(",");
  const hasRelated = relatedSlugs.length > 0;
  const [related, setRelated] = useState<readonly Disease[]>([]);
  const [loading, setLoading] = useState(hasRelated);

  useEffect(() => {
    if (!hasRelated) {
      return;
    }

    let cancelled = false;
    const { diseases } = repositories();

    async function load() {
      setLoading(true);
      try {
        const results = await Promise.all(
          relatedSlugs.map((slug) => diseases.getDiseaseBySlug(slug)),
        );
        if (!cancelled) {
          setRelated(results.filter((d): d is Disease => d != null));
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
  }, [slugKey, hasRelated, relatedSlugs]);

  if (!hasRelated) {
    return { related: [], loading: false };
  }

  return { related, loading };
}
