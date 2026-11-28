import { useMemo } from "react";
import type { Disease } from "../types";
import { useTrials } from "./useTrials";
import { parseDoctorsQuery, serializeDoctorsQuery } from "../utils/doctorsQuery";
import {
  listedTrialCount,
  parseTrialsQuery,
  serializeTrialsQuery,
} from "../utils/trialsQuery";

export interface ListingLink {
  /** Unprefixed in-app path of the listing, filtered to the disease. */
  readonly path: string;
  /** How many rows that listing opens with; null while it loads or when it failed. */
  readonly count: number | null;
}

export interface ListingLinks {
  readonly doctors: ListingLink;
  readonly trials: ListingLink;
}

/**
 * The doctors directory and the trials browser, as a disease page links to them: the address, and the number of rows that address opens with.
 *
 * The doctor number is the disease record's `doctorsCount`, which the backend defines as the directory entries listed under the disease (backend/doctor_catalog.py, `public_doctors_for_disease`) — the rows `/doctors?disease=<slug>` opens with, without loading the whole directory here. The trial number is computed from the data the browser itself loads (`/api/trials`) with the same query and filter, because the record's trial count includes trials that no longer recruit, while the browser opens on recruiting ones.
 */
export function useListingLinks(disease: Pick<Disease, "slug" | "doctorsCount">): ListingLinks {
  const { slug, doctorsCount } = disease;
  const { trials, loading: trialsLoading, error: trialsError } = useTrials();

  const doctorsQuery = useMemo(() => parseDoctorsQuery({ disease: slug }), [slug]);
  const trialsQuery = useMemo(() => parseTrialsQuery({ disease: slug }), [slug]);

  const trialCount = useMemo(
    () => (trialsLoading || trialsError != null ? null : listedTrialCount(trials, trialsQuery)),
    [trials, trialsLoading, trialsError, trialsQuery],
  );

  return {
    doctors: { path: serializeDoctorsQuery(doctorsQuery), count: doctorsCount },
    trials: { path: serializeTrialsQuery(trialsQuery), count: trialCount },
  };
}
