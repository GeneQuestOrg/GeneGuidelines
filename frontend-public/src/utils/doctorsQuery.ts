import type { UserLocation } from "../router/types";
import type { PubmedRole, RecencyBand } from "../types/doctor";
import { normalizeDiseaseSlug } from "../router/slug";
import type { SourceFilter } from "./doctorFilters";
import { WORK_TYPE_ORDER, type WorkType } from "./doctorLabels";
import {
  sortDoctorsByDistanceThenScore,
  type DoctorWithDistance,
} from "./doctorSort";

/**
 * The full faceted state of the doctors directory as one typed object, serialized to the URL
 * hash so every view is deep-linkable, shareable, and restored by the browser back button. This
 * is the single source of truth — {@link DoctorsView} derives its render from a parsed query and
 * mutates only by navigating to a new serialized query.
 */
export interface DoctorsQuery {
  /** Disease slug filter, or null for every disease. */
  readonly disease: string | null;
  /** PubMed role filter, or null for all roles. */
  readonly role: PubmedRole | null;
  /** Provenance source filter ("all" keeps every source). */
  readonly source: SourceFilter;
  /** Keep only doctors carrying a parent signal. */
  readonly parentOnly: boolean;
  /** User location for distance sort/filter, or null. */
  readonly loc: UserLocation | null;
  /** Human label for {@link loc} (e.g. "Warsaw, PL"); null when loc is null. */
  readonly locLabel: string | null;
  /** Distance cap in km (25 | 100 | 500 | 2500 | 5000), or null for no limit. */
  readonly maxKm: number | null;
  /** Disease-relevant work types the doctor must have (AND). Empty keeps all. */
  readonly workTypes: readonly WorkType[];
  /** Minimum recency floor ("active_2y" | "active_5y"), or null for any recency. */
  readonly recency: RecencyBand | null;
  /** Verified clinical-specialty group (NUCC classification) filter, or null for all. */
  readonly specialtyGroup: string | null;
  /** Practice-country (ISO2) filter, or null for all. */
  readonly country: string | null;
  /** Keep only doctors who see patients (expert-reachable are always kept too). */
  readonly seesPatients: boolean;
  /** Active sort order. */
  readonly sort: DoctorSort;
  /** 1-based page number for the list (the map always shows the full filtered set). */
  readonly page: number;
}

export type DoctorSort = "best" | "distance" | "score" | "name" | "recency";

/** Doctor cards per list page. The map is never paginated. */
export const PAGE_SIZE = 12;

const SORTS: readonly DoctorSort[] = ["best", "distance", "score", "name", "recency"];
const SOURCES: readonly SourceFilter[] = ["all", "pubmed", "parent", "consortium"];
const ROLES: readonly PubmedRole[] = [
  "research_leader",
  "research_participant",
  "case_study_author",
];
const RADII: readonly number[] = [25, 100, 500, 2500, 5000];
const WORK_TYPE_SET = new Set<string>(WORK_TYPE_ORDER);
const RECENCY_FLOORS = new Set<string>(["active_2y", "active_5y"]);

export const DEFAULT_DOCTORS_QUERY: DoctorsQuery = {
  disease: null,
  role: null,
  source: "all",
  parentOnly: false,
  loc: null,
  locLabel: null,
  maxKm: null,
  workTypes: [],
  recency: null,
  specialtyGroup: null,
  country: null,
  seesPatients: false,
  sort: "best",
  page: 1,
};

/**
 * Ready-made filter bundles that "step into the parent's shoes" — one click composes a sensible
 * set of facets so a family that doesn't know how to filter still lands on the right people.
 * Each preset is a partial query merged onto the current disease/location.
 *
 * `label` is a bare i18n key, not display text — callers must translate it via
 * `t(`common:${preset.label}`)` (or `t(preset.label)` when already scoped to "common").
 */
export type DoctorPresetId = "on_top" | "surgeon_near" | "consult" | "anyone_near";

export const DOCTOR_PRESETS: readonly {
  readonly id: DoctorPresetId;
  readonly label: string;
  readonly patch: Partial<DoctorsQuery>;
  /** When set, the preset only makes sense once a specialty group is picked (needs clinical data). */
  readonly needsSpecialty?: boolean;
}[] = [
  {
    id: "on_top",
    label: "doctorsQuery.presets.onTop",
    // Core case (son's story): a currently-active expert, not merely a titled one.
    patch: { recency: "active_2y", workTypes: [], role: null, sort: "recency", parentOnly: false },
  },
  {
    id: "surgeon_near",
    label: "doctorsQuery.presets.surgeonNear",
    // Detroit case: a practising surgeon with disease experience, closest first. Only surfaced
    // when the specialty axis has data (data-density gate in the view).
    patch: {
      specialtyGroup: "Surgery",
      seesPatients: true,
      sort: "distance",
      recency: null,
      workTypes: [],
      parentOnly: false,
    },
    needsSpecialty: true,
  },
  {
    id: "consult",
    label: "doctorsQuery.presets.consult",
    // The "Mara" case: reachable expertise regardless of geography (guideline-level authors).
    patch: { workTypes: ["guideline"], recency: null, maxKm: null, sort: "best", parentOnly: false },
  },
  {
    id: "anyone_near",
    label: "doctorsQuery.presets.anyoneNear",
    // First step for a lost parent: geography first, any disease experience.
    patch: { workTypes: [], recency: null, role: null, sort: "distance", parentOnly: false },
  },
];

/** Split a `location.search` string (with or without a leading `?`) into a decoded key→value record. */
export function queryRecordFromSearch(search: string): Record<string, string> {
  const q = search.indexOf("?");
  const record: Record<string, string> = {};
  const raw = q === -1 ? search : search.slice(q + 1);
  if (!raw) {
    return record;
  }
  for (const part of raw.split("&")) {
    if (!part) continue;
    const [key, value] = part.split("=");
    if (key) {
      record[key] = decodeURIComponent(value ?? "");
    }
  }
  return record;
}

function parseLoc(raw: string | undefined): UserLocation | null {
  if (!raw) return null;
  const [latRaw, lngRaw] = raw.split(",");
  const lat = Number(latRaw);
  const lng = Number(lngRaw);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat, lng };
}

/**
 * Parse a query record (from {@link queryRecordFromSearch}) into a validated {@link DoctorsQuery}.
 * Every field falls back to its default when missing or invalid, so a hand-edited or stale URL
 * can never throw or produce an out-of-range facet.
 */
export function parseDoctorsQuery(q: Record<string, string>): DoctorsQuery {
  const loc = parseLoc(q.loc);
  const role = ROLES.includes(q.role as PubmedRole) ? (q.role as PubmedRole) : null;
  const source = SOURCES.includes(q.source as SourceFilter)
    ? (q.source as SourceFilter)
    : "all";
  // Default sort: once a location is set, rank Nearest-first (the point of picking a location) —
  // a soft ordering, not a hard radius cut, so a sparse rare-disease result never zeroes out.
  // An explicit ?sort= always wins (user override).
  const sort = SORTS.includes(q.sort as DoctorSort)
    ? (q.sort as DoctorSort)
    : loc != null
      ? "distance"
      : "best";
  const kmNum = Number(q.km);
  const maxKm = loc != null && RADII.includes(kmNum) ? kmNum : null;
  const pageNum = Math.trunc(Number(q.page));
  const page = Number.isFinite(pageNum) && pageNum > 1 ? pageNum : 1;
  const workTypes = (q.work ? q.work.split(",") : [])
    .filter((w) => WORK_TYPE_SET.has(w)) as WorkType[];
  const recency = RECENCY_FLOORS.has(q.recency) ? (q.recency as RecencyBand) : null;
  const specialtyGroup = q.spec ? q.spec : null;
  const countryRaw = (q.country || "").trim().toUpperCase();
  const country = /^[A-Z]{2}$/.test(countryRaw) ? countryRaw : null;
  return {
    disease: q.disease ? normalizeDiseaseSlug(q.disease) : null,
    role,
    source,
    parentOnly: q.parent === "1",
    loc,
    locLabel: loc != null && q.place ? q.place : null,
    maxKm,
    workTypes,
    recency,
    specialtyGroup,
    country,
    seesPatients: q.seespt === "1",
    sort,
    page,
  };
}

/**
 * Serialize a {@link DoctorsQuery} back to a `/doctors?…` path, omitting every default so
 * the canonical empty view stays a clean `/doctors`. Keys are emitted in a stable order so the
 * same state always yields the same URL (shareable, cache-friendly, back-button-stable).
 */
export function serializeDoctorsQuery(query: DoctorsQuery): string {
  const params: string[] = [];
  const add = (key: string, value: string) =>
    params.push(`${key}=${encodeURIComponent(value)}`);

  if (query.disease) add("disease", query.disease);
  if (query.role) add("role", query.role);
  if (query.source !== "all") add("source", query.source);
  if (query.parentOnly) add("parent", "1");
  if (query.workTypes.length > 0) {
    // Stable, canonical order so the same facet set always yields the same URL.
    add("work", WORK_TYPE_ORDER.filter((w) => query.workTypes.includes(w)).join(","));
  }
  if (query.recency) add("recency", query.recency);
  if (query.specialtyGroup) add("spec", query.specialtyGroup);
  if (query.country) add("country", query.country);
  if (query.seesPatients) add("seespt", "1");
  if (query.loc) {
    add("loc", `${query.loc.lat},${query.loc.lng}`);
    if (query.locLabel) add("place", query.locLabel);
    if (query.maxKm != null) add("km", String(query.maxKm));
  }
  // Emit sort unless it matches the location-aware default (no loc → "best"; loc set → "distance"),
  // so the canonical URL stays clean AND the user can still pin "best" while a location is set.
  const defaultSort: DoctorSort = query.loc != null ? "distance" : "best";
  if (query.sort !== defaultSort) add("sort", query.sort);
  if (query.page > 1) add("page", String(query.page));

  return params.length > 0 ? `/doctors?${params.join("&")}` : "/doctors";
}

function byNameAsc(a: DoctorWithDistance, b: DoctorWithDistance): number {
  return a.name.localeCompare(b.name);
}

function byScoreDesc(a: DoctorWithDistance, b: DoctorWithDistance): number {
  if (b.score !== a.score) return b.score - a.score;
  return byNameAsc(a, b);
}

function byDistanceAsc(a: DoctorWithDistance, b: DoctorWithDistance): number {
  if (a.km != null && b.km != null && a.km !== b.km) return a.km - b.km;
  if (a.km != null && b.km == null) return -1;
  if (a.km == null && b.km != null) return 1;
  return byScoreDesc(a, b);
}

/** Most-recently-active first (newest central/any paper year), then PubMed score as tiebreak. */
function byRecencyDesc(a: DoctorWithDistance, b: DoctorWithDistance): number {
  const ay = a.lastCentralPaperYear ?? a.lastPaperYear ?? -1;
  const by = b.lastCentralPaperYear ?? b.lastPaperYear ?? -1;
  if (by !== ay) return by - ay;
  return byScoreDesc(a, b);
}

/** Pure, stable sort of the filtered rows for the chosen order. Never mutates the input. */
export function sortDoctors(
  rows: readonly DoctorWithDistance[],
  sort: DoctorSort,
): DoctorWithDistance[] {
  switch (sort) {
    case "distance":
      return [...rows].sort(byDistanceAsc);
    case "score":
      return [...rows].sort(byScoreDesc);
    case "name":
      return [...rows].sort(byNameAsc);
    case "recency":
      return [...rows].sort(byRecencyDesc);
    case "best":
    default:
      return sortDoctorsByDistanceThenScore(rows);
  }
}
