/**
 * Trials data helpers for the faceted browser.
 *
 * Types and fetchers shared by {@link TrialsBrowserView}. Kept in a dedicated
 * module (not the shared `api/client.ts`) so trials work merges cleanly while
 * the directory base client evolves elsewhere. Imports from `client.ts` are
 * read-only — this module never modifies it.
 */

import type { UserLocation } from "../router/types";
import type { Trial } from "../types/trial";
import { haversineKm } from "../utils/geo";

/** A trial decorated with its distance to the user (km), or null when unknown. */
export interface TrialWithDistance extends Trial {
  /** Great-circle km to the user location, or null when either point is missing. */
  readonly km: number | null;
}

/** True when the trial carries a usable map coordinate. */
export function trialHasCoords(trial: Trial): boolean {
  return (
    trial.lat != null &&
    trial.lng != null &&
    Number.isFinite(trial.lat) &&
    Number.isFinite(trial.lng)
  );
}

/**
 * Attach each trial's distance to the user. Trials without coordinates (or with
 * no user location) get a null distance, mirroring {@link attachDoctorDistances}.
 */
export function attachTrialDistances(
  trials: readonly Trial[],
  userLoc: UserLocation | null,
): TrialWithDistance[] {
  return trials.map((trial) => ({
    ...trial,
    km:
      userLoc != null && trialHasCoords(trial)
        ? haversineKm(userLoc, { lat: trial.lat as number, lng: trial.lng as number })
        : null,
  }));
}

/** Canonical ClinicalTrials.gov study URL for a registry id. */
export function clinicalTrialsUrl(nct: string): string {
  return `https://clinicaltrials.gov/study/${encodeURIComponent(nct)}`;
}
