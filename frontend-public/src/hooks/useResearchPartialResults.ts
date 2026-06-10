import { useEffect, useRef, useState } from "react";
import { ApiRequestError } from "../api/client";
import { repositories } from "../repositories";
import type { ResearchRun } from "../types/researchRun";

export interface ResearchPartialResults {
  readonly doctors: number;
  readonly trials: number;
  readonly therapies: number;
  readonly foundations: number;
  readonly hasOfficialGuideline: boolean;
  readonly hasGuidelineDocument: boolean;
  readonly activeRuns: readonly ResearchRun[];
  readonly loading: boolean;
  /** True after the first successful per-disease counts fetch. */
  readonly countsReady: boolean;
}

const DEFAULT_POLL_MS = 5000;

export interface ResearchPartialResultsOptions {
  /** Count + active-run poll interval while the research page is live. */
  readonly pollIntervalMs?: number;
}

interface DiseaseCounts {
  readonly doctors: number;
  readonly trials: number;
  readonly therapies: number;
  readonly foundations: number;
  readonly hasOfficialGuideline: boolean;
  readonly hasGuidelineDocument: boolean;
}

const EMPTY_COUNTS: DiseaseCounts = {
  doctors: 0,
  trials: 0,
  therapies: 0,
  foundations: 0,
  hasOfficialGuideline: false,
  hasGuidelineDocument: false,
};

async function fetchDiseaseCounts(slug: string): Promise<DiseaseCounts> {
  const repos = repositories();
  const [doctorsPayload, trials, therapies, foundations, officialGuideline, guidelineDocument] =
    await Promise.all([
      repos.doctors.getDoctorsForDisease(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return { doctors: [] as const };
        }
        throw err;
      }),
      repos.trials.listForDisease(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return [] as const;
        }
        throw err;
      }),
      repos.therapies.listForDisease(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return [] as const;
        }
        throw err;
      }),
      repos.foundations.listForDisease(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return [] as const;
        }
        throw err;
      }),
      repos.officialGuidelines.getForDisease(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return null;
        }
        throw err;
      }),
      repos.guidelines.getGuidelineDocument(slug).catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return null;
        }
        throw err;
      }),
    ]);

  return {
    doctors: doctorsPayload.doctors.length,
    trials: trials.length,
    therapies: therapies.length,
    foundations: foundations.length,
    hasOfficialGuideline: officialGuideline != null,
    hasGuidelineDocument: guidelineDocument != null,
  };
}

export function useResearchPartialResults(
  diseaseSlug: string | undefined,
  enabled: boolean,
  options: ResearchPartialResultsOptions = {},
): ResearchPartialResults {
  // We split the two polls into independent pieces of state so that each
  // effect has a single responsibility — keeps the React 19 strict
  // effect rules happy and makes the "disabled" path a pure derivation
  // of the return value rather than a setState-from-an-effect.
  const [counts, setCounts] = useState<DiseaseCounts>(EMPTY_COUNTS);
  const [countsReady, setCountsReady] = useState(false);
  const [activeRuns, setActiveRuns] = useState<readonly ResearchRun[]>([]);
  const pollCountsRef = useRef<(() => Promise<void>) | null>(null);

  const slug = diseaseSlug?.trim() ?? "";
  const active = enabled && slug !== "";
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;

  useEffect(() => {
    if (!active) {
      return;
    }
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await fetchDiseaseCounts(slug);
        if (cancelled) return;
        setCounts(next);
        setCountsReady(true);
      } catch {
        // Quiet — the next poll will retry. Holding the previous counts
        // is better than blanking the dashboard on a single 5xx blip.
      }
    };

    pollCountsRef.current = poll;
    void poll();
    const id = window.setInterval(() => void poll(), pollIntervalMs);
    return () => {
      cancelled = true;
      pollCountsRef.current = null;
      window.clearInterval(id);
      setCountsReady(false);
    };
  }, [slug, active, pollIntervalMs]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const repo = repositories().researchRuns;
    let previousRunIds = new Set<string>();

    const poll = async () => {
      try {
        const runs = await repo.listActiveRuns(10);
        if (cancelled) return;
        const filtered = runs.filter((r) => r.diseaseSlug === slug);
        const nextIds = new Set(filtered.map((r) => r.runId));
        const finderFinished =
          previousRunIds.size > nextIds.size &&
          [...previousRunIds].some((id) => !nextIds.has(id));
        previousRunIds = nextIds;
        setActiveRuns(filtered);
        if (finderFinished) {
          void pollCountsRef.current?.();
        }
      } catch {
        // Quiet — counts poll surfaces the bigger picture.
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [slug, active, pollIntervalMs]);

  if (!active) {
    return {
      ...counts,
      activeRuns,
      loading: false,
      countsReady,
    };
  }
  return {
    ...counts,
    activeRuns,
    loading: false,
    countsReady,
  };
}
