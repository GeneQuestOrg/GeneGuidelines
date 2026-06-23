import type { UserLocation } from "../router/types";
import type { PubmedRole } from "../types/doctor";
import { normalizeDiseaseSlug } from "../router/slug";
import type { SourceFilter } from "./doctorFilters";
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
  /** Distance cap in km (25 | 100 | 500), or null for no limit. */
  readonly maxKm: number | null;
  /** Active sort order. */
  readonly sort: DoctorSort;
  /** 1-based page number for the list (the map always shows the full filtered set). */
  readonly page: number;
}

export type DoctorSort = "best" | "distance" | "score" | "name";

/** Doctor cards per list page. The map is never paginated. */
export const PAGE_SIZE = 12;

const SORTS: readonly DoctorSort[] = ["best", "distance", "score", "name"];
const SOURCES: readonly SourceFilter[] = ["all", "pubmed", "parent", "consortium"];
const ROLES: readonly PubmedRole[] = [
  "research_leader",
  "research_participant",
  "case_study_author",
];
const RADII: readonly number[] = [25, 100, 500];

export const DEFAULT_DOCTORS_QUERY: DoctorsQuery = {
  disease: null,
  role: null,
  source: "all",
  parentOnly: false,
  loc: null,
  locLabel: null,
  maxKm: null,
  sort: "best",
  page: 1,
};

/** Split the query string of a hash route into a decoded key→value record. */
export function queryRecordFromHash(hash: string): Record<string, string> {
  const q = hash.indexOf("?");
  const record: Record<string, string> = {};
  if (q === -1) {
    return record;
  }
  for (const part of hash.slice(q + 1).split("&")) {
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
 * Parse a query record (from {@link queryRecordFromHash}) into a validated {@link DoctorsQuery}.
 * Every field falls back to its default when missing or invalid, so a hand-edited or stale URL
 * can never throw or produce an out-of-range facet.
 */
export function parseDoctorsQuery(q: Record<string, string>): DoctorsQuery {
  const loc = parseLoc(q.loc);
  const role = ROLES.includes(q.role as PubmedRole) ? (q.role as PubmedRole) : null;
  const source = SOURCES.includes(q.source as SourceFilter)
    ? (q.source as SourceFilter)
    : "all";
  const sort = SORTS.includes(q.sort as DoctorSort) ? (q.sort as DoctorSort) : "best";
  const kmNum = Number(q.km);
  const maxKm = loc != null && RADII.includes(kmNum) ? kmNum : null;
  const pageNum = Math.trunc(Number(q.page));
  const page = Number.isFinite(pageNum) && pageNum > 1 ? pageNum : 1;
  return {
    disease: q.disease ? normalizeDiseaseSlug(q.disease) : null,
    role,
    source,
    parentOnly: q.parent === "1",
    loc,
    locLabel: loc != null && q.place ? q.place : null,
    maxKm,
    sort,
    page,
  };
}

/**
 * Serialize a {@link DoctorsQuery} back to a `/doctors?…` hash path, omitting every default so
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
  if (query.loc) {
    add("loc", `${query.loc.lat},${query.loc.lng}`);
    if (query.locLabel) add("place", query.locLabel);
    if (query.maxKm != null) add("km", String(query.maxKm));
  }
  if (query.sort !== "best") add("sort", query.sort);
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
    case "best":
    default:
      return sortDoctorsByDistanceThenScore(rows);
  }
}
