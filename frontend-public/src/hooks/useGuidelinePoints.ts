import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelinePoints } from "../types/guidelinePoints";

interface Loaded {
  readonly slug: string;
  readonly points: GuidelinePoints | null;
}

/** The disease's generated diagnosis block, or null while loading, when none is published, or when the request fails (the page then simply shows no block). */
export function useGuidelinePoints(diseaseSlug: string): GuidelinePoints | null {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      let points: GuidelinePoints | null = null;
      try {
        points = await repositories().officialGuidelines.getGuidelinePoints(diseaseSlug);
      } catch {
        points = null;
      }
      if (!cancelled) setLoaded({ slug: diseaseSlug, points });
    })();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug]);

  // A block loaded for another disease is never shown while the next one loads.
  return loaded && loaded.slug === diseaseSlug ? loaded.points : null;
}
