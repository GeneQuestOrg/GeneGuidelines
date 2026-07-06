import type { AddedVia, PubmedRole, RecencyBand } from "../types/doctor";
import {
  recencyBandOf,
  specialtyGroupsOf,
  workTypesOf,
  type WorkType,
} from "./doctorLabels";
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
  /**
   * Keep only doctors carrying ALL of these disease-relevant work types (AND semantics — each
   * added facet narrows the set). Empty/undefined keeps every work type.
   */
  readonly workTypes?: readonly WorkType[];
  /**
   * Minimum recency: "active_2y" keeps only ≤2y; "active_5y" keeps ≤5y; null/undefined keeps all.
   * "unknown"-band rows are dropped when a recency floor is set (we can't prove they're current).
   */
  readonly recency?: RecencyBand | null;
  /** Keep only doctors with a verified clinical specialty in this NUCC group. */
  readonly specialtyGroup?: string | null;
  /** Keep only doctors practising in this ISO2 country. */
  readonly country?: string | null;
  /**
   * Keep only doctors who see patients — BUT never drop an ``expert_reachable`` profile (the
   * "Mara" case: a scientist who answers consults must stay visible). So this keeps
   * ``sees_patients`` OR ``expert_reachable``.
   */
  readonly seesPatientsOnly?: boolean;
}

const RECENCY_RANK: Record<RecencyBand, number> = {
  active_2y: 3,
  active_5y: 2,
  older: 1,
  unknown: 0,
};

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
  const {
    diseaseSlug, role, source, parentOnly, maxKm, workTypes, recency,
    specialtyGroup, country, seesPatientsOnly,
  } = criteria;
  const recencyFloor = recency && recency !== "unknown" ? RECENCY_RANK[recency] : 0;
  const wantCountry = (country || "").trim().toUpperCase();
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
    if (workTypes && workTypes.length > 0) {
      const have = workTypesOf(doctor);
      if (!workTypes.every((w) => have.has(w))) {
        return false;
      }
    }
    if (recencyFloor > 0 && RECENCY_RANK[recencyBandOf(doctor)] < recencyFloor) {
      return false;
    }
    if (specialtyGroup && !specialtyGroupsOf(doctor).has(specialtyGroup)) {
      return false;
    }
    if (wantCountry && (doctor.country || "").trim().toUpperCase() !== wantCountry) {
      return false;
    }
    if (seesPatientsOnly) {
      const r = doctor.reachability ?? "unknown";
      // Never hide a reachable expert (the "Mara" rule).
      if (r !== "sees_patients" && r !== "expert_reachable") {
        return false;
      }
    }
    return true;
  });
}
