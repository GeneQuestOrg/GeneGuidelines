import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelinePoints } from "../types/guidelinePoints";

interface Loaded {
  readonly slug: string;
  readonly points: GuidelinePoints | null;
}

/**
 * One request per disease per page load. The disease page asks twice — the orientation map to know whether there is a block to point step 1 at, the block itself to render it — and the second asker mounts only after the first got its answer, so an in-flight check alone would not stop a second request. A failed request is forgotten, so a later visit tries again.
 */
const requests = new Map<string, Promise<GuidelinePoints | null>>();

function loadPoints(slug: string): Promise<GuidelinePoints | null> {
  const known = requests.get(slug);
  if (known != null) {
    return known;
  }
  const request = repositories()
    .officialGuidelines.getGuidelinePoints(slug)
    .catch(() => {
      requests.delete(slug);
      return null;
    });
  requests.set(slug, request);
  return request;
}

/**
 * The disease's generated diagnosis block, or null while loading, when none is published, or when the request fails (the page then simply shows no block). `enabled: false` (FD, whose page keeps the hand-written block) asks nothing and returns null.
 */
export function useGuidelinePoints(diseaseSlug: string, enabled = true): GuidelinePoints | null {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let cancelled = false;
    void loadPoints(diseaseSlug).then((points) => {
      if (!cancelled) setLoaded({ slug: diseaseSlug, points });
    });
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug, enabled]);

  // A block loaded for another disease is never shown while the next one loads.
  return enabled && loaded && loaded.slug === diseaseSlug ? loaded.points : null;
}
