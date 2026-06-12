import type { AddedVia, PubmedRole } from "../types/doctor";
import type { DoctorWithDistance } from "./doctorSort";

/** Provenance of a directory entry. The backend defaults missing rows to PubMed mining. */
export function addedViaOf(doctor: { addedVia?: AddedVia }): AddedVia {
  return doctor.addedVia ?? "pubmed";
}

export type SourceFilter = "all" | "pubmed" | "parent" | "consortium";

export interface DoctorFilterCriteria {
  /** Disease slug to filter by, or null/undefined to show every doctor. */
  readonly diseaseSlug?: string | null;
  /** PubMed role to filter by, or null/undefined for all roles. */
  readonly role?: PubmedRole | null;
  /** Provenance source to filter by; "all" (or null/undefined) keeps every source. */
  readonly source?: SourceFilter | null;
  /** When true, keep only doctors with a parent recommendation or parent provenance. */
  readonly parentOnly?: boolean;
  /** Distance cap in km; only applies when set AND the row has a known distance. */
  readonly maxKm?: number | null;
}

/** True when the doctor carries a parent signal (a family recommendation or parent provenance). */
export function hasParentSignal(
  doctor: { readonly parentRecs?: readonly unknown[]; readonly addedVia?: AddedVia },
): boolean {
  return (doctor.parentRecs?.length ?? 0) > 0 || addedViaOf(doctor) === "parent";
}

/**
 * Pure directory filter. Order-preserving; the caller sorts separately. Distance filtering only
 * applies when ``maxKm`` is set AND the row has a non-null ``km`` (no location → no distance cut).
 */
export function filterDoctors(
  rows: readonly DoctorWithDistance[],
  criteria: DoctorFilterCriteria,
): DoctorWithDistance[] {
  const { diseaseSlug, role, source, parentOnly, maxKm } = criteria;
  return rows.filter((doctor) => {
    if (diseaseSlug && !doctor.diseases.includes(diseaseSlug)) {
      return false;
    }
    if (role && doctor.pubmedRole !== role) {
      return false;
    }
    if (source && source !== "all" && addedViaOf(doctor) !== source) {
      return false;
    }
    if (parentOnly && !hasParentSignal(doctor)) {
      return false;
    }
    if (maxKm != null && doctor.km != null && doctor.km > maxKm) {
      return false;
    }
    return true;
  });
}
