import { useMemo } from "react";
import { useDoctors } from "./useDoctors";
import { useTrials } from "./useTrials";
import {
  listedDoctorCount,
  parseDoctorsQuery,
  serializeDoctorsQuery,
} from "../utils/doctorsQuery";
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
 * The number is computed from the data the listing itself loads (`/api/doctors`, `/api/trials`) with the same query and the same filter, because the counts carried on the disease record measure something else: the record's doctor count applies the clinician gate to each disease's own rows, while the directory applies it to a profile merged across diseases (a specialty found under another disease admits the doctor here too), and the record's trial count includes trials that no longer recruit, while the browser opens on recruiting ones.
 */
export function useListingLinks(slug: string): ListingLinks {
  const { doctors, loading: doctorsLoading, error: doctorsError } = useDoctors();
  const { trials, loading: trialsLoading, error: trialsError } = useTrials();

  const doctorsQuery = useMemo(() => parseDoctorsQuery({ disease: slug }), [slug]);
  const trialsQuery = useMemo(() => parseTrialsQuery({ disease: slug }), [slug]);

  const doctorCount = useMemo(
    () =>
      doctorsLoading || doctorsError != null ? null : listedDoctorCount(doctors, doctorsQuery),
    [doctors, doctorsLoading, doctorsError, doctorsQuery],
  );
  const trialCount = useMemo(
    () => (trialsLoading || trialsError != null ? null : listedTrialCount(trials, trialsQuery)),
    [trials, trialsLoading, trialsError, trialsQuery],
  );

  return {
    doctors: { path: serializeDoctorsQuery(doctorsQuery), count: doctorCount },
    trials: { path: serializeTrialsQuery(trialsQuery), count: trialCount },
  };
}
