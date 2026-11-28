import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { GuidelinePoints } from "../types/guidelinePoints";

interface Loaded {
  readonly slug: string;
  readonly points: GuidelinePoints | null;
}

/**
 * One request per disease per page load. A page that asks again after the first answer (a remount, a language switch) gets the same promise rather than a second request. A failed request is forgotten, so a later visit tries again.
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

export interface GuidelinePointsState {
  /** The published block; null while loading, when none is published, or when the request failed. */
  readonly points: GuidelinePoints | null;
  /** True until the answer for this disease is in, so the page can hold the block's place instead of moving when it arrives. */
  readonly loading: boolean;
}

/**
 * The disease's generated diagnosis block, and whether the answer is still on its way. When none is published or the request fails the page simply shows no block. `enabled: false` (FD, whose page keeps the hand-written block) asks nothing: no block, not loading.
 */
export function useGuidelinePoints(diseaseSlug: string, enabled = true): GuidelinePointsState {
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
  const current = enabled && loaded != null && loaded.slug === diseaseSlug;
  return { points: current ? loaded.points : null, loading: enabled && !current };
}
