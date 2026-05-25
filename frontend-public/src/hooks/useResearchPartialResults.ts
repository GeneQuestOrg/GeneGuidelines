import { useEffect, useState } from "react";
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
}

const POLL_MS = 5000;

const EMPTY: ResearchPartialResults = {
  doctors: 0,
  trials: 0,
  therapies: 0,
  foundations: 0,
  hasOfficialGuideline: false,
  hasGuidelineDocument: false,
  activeRuns: [],
  loading: false,
};

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

export function useResearchPartialResults(
  diseaseSlug: string | undefined,
  enabled: boolean,
): ResearchPartialResults {
  // We split the two polls into independent pieces of state so that each
  // effect has a single responsibility — keeps the React 19 strict
  // effect rules happy and makes the "disabled" path a pure derivation
  // of the return value rather than a setState-from-an-effect.
  const [counts, setCounts] = useState<DiseaseCounts>(EMPTY_COUNTS);
  const [activeRuns, setActiveRuns] = useState<readonly ResearchRun[]>([]);

  const slug = diseaseSlug?.trim() ?? "";
  const active = enabled && slug !== "";

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const repos = repositories();

    const poll = async () => {
      try {
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

        if (cancelled) return;
        setCounts({
          doctors: doctorsPayload.doctors.length,
          trials: trials.length,
          therapies: therapies.length,
          foundations: foundations.length,
          hasOfficialGuideline: officialGuideline != null,
          hasGuidelineDocument: guidelineDocument != null,
        });
      } catch {
        // Quiet — the next poll will retry. Holding the previous counts
        // is better than blanking the dashboard on a single 5xx blip.
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [slug, active]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const repo = repositories().researchRuns;

    const poll = async () => {
      try {
        const runs = await repo.listActiveRuns(20);
        if (cancelled) return;
        setActiveRuns(runs.filter((r) => r.diseaseSlug === slug));
      } catch {
        // Quiet — counts poll surfaces the bigger picture.
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [slug, active]);

  if (!active) {
    return EMPTY;
  }
  return {
    ...counts,
    activeRuns,
    loading: false,
  };
}
