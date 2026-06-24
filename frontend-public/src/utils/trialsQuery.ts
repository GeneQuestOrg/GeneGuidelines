import type { UserLocation } from "../router/types";
import type { TrialWithDistance } from "../api/trials";
import { normalizeDiseaseSlug } from "../router/slug";

/**
 * The full faceted state of the trials browser as one typed object, serialized to the URL hash so
 * every view is deep-linkable, shareable, and restored by the browser back button. This is the
 * single source of truth — {@link TrialsBrowserView} derives its render from a parsed query and
 * mutates only by navigating to a new serialized query. Mirrors {@link DoctorsQuery}.
 */
export interface TrialsQuery {
  /** Disease slug filter, or null for every disease. */
  readonly disease: string | null;
  /** Recruitment status filter; defaults to "recruiting" (the actionable set for families). */
  readonly status: TrialStatusFilter;
  /** Trial phase filter (1–4), or null for any phase. */
  readonly phase: TrialPhase | null;
  /** User location for distance sort/filter, or null. */
  readonly loc: UserLocation | null;
  /** Human label for {@link loc} (e.g. "Warsaw, PL"); null when loc is null. */
  readonly locLabel: string | null;
  /** Distance cap in km (25 | 100 | 500), or null for no limit. */
  readonly maxKm: number | null;
  /** Active sort order. */
  readonly sort: TrialSort;
  /** 1-based page number for the list (the map always shows the full filtered set). */
  readonly page: number;
}

/** Recruitment status facet. "all" keeps every status. */
export type TrialStatusFilter = "all" | "recruiting" | "active_not_recruiting" | "completed";

/** Phase facet. Matched against the free-text ``Trial.phase`` ("Phase 2", "Phase 1/2", …). */
export type TrialPhase = "1" | "2" | "3" | "4";

/** Sort order. "date" orders by ``lastSeen`` (most-recently-seen first). */
export type TrialSort = "nearest" | "status" | "date";

/** Trial cards per list page. The map is never paginated. */
export const PAGE_SIZE = 12;

const SORTS: readonly TrialSort[] = ["nearest", "status", "date"];
const STATUSES: readonly TrialStatusFilter[] = [
  "all",
  "recruiting",
  "active_not_recruiting",
  "completed",
];
const PHASES: readonly TrialPhase[] = ["1", "2", "3", "4"];
const RADII: readonly number[] = [25, 100, 500];

/**
 * Status ordering for the "status" sort: recruiting is the most actionable, then active,
 * then completed, then anything else (unknown / withdrawn). Lower rank sorts first.
 */
const STATUS_RANK: Readonly<Record<string, number>> = {
  recruiting: 0,
  active_not_recruiting: 1,
  completed: 2,
};

function statusRank(status: string): number {
  return STATUS_RANK[status] ?? 3;
}

export const DEFAULT_TRIALS_QUERY: TrialsQuery = {
  disease: null,
  status: "recruiting",
  phase: null,
  loc: null,
  locLabel: null,
  maxKm: null,
  sort: "status",
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
 * Parse a query record (from {@link queryRecordFromHash}) into a validated {@link TrialsQuery}.
 * Every field falls back to its default when missing or invalid, so a hand-edited or stale URL can
 * never throw or produce an out-of-range facet.
 */
export function parseTrialsQuery(q: Record<string, string>): TrialsQuery {
  const loc = parseLoc(q.loc);
  const status = STATUSES.includes(q.status as TrialStatusFilter)
    ? (q.status as TrialStatusFilter)
    : "recruiting";
  const phase = PHASES.includes(q.phase as TrialPhase) ? (q.phase as TrialPhase) : null;
  const sort = SORTS.includes(q.sort as TrialSort) ? (q.sort as TrialSort) : "status";
  const kmNum = Number(q.km);
  const maxKm = loc != null && RADII.includes(kmNum) ? kmNum : null;
  const pageNum = Math.trunc(Number(q.page));
  const page = Number.isFinite(pageNum) && pageNum > 1 ? pageNum : 1;
  return {
    disease: q.disease ? normalizeDiseaseSlug(q.disease) : null,
    status,
    phase,
    loc,
    locLabel: loc != null && q.place ? q.place : null,
    maxKm,
    sort,
    page,
  };
}

/**
 * Serialize a {@link TrialsQuery} back to a `/trials?…` hash path, omitting every default so the
 * canonical empty view stays a clean `/trials`. Keys are emitted in a stable order so the same
 * state always yields the same URL (shareable, cache-friendly, back-button-stable).
 */
export function serializeTrialsQuery(query: TrialsQuery): string {
  const params: string[] = [];
  const add = (key: string, value: string) =>
    params.push(`${key}=${encodeURIComponent(value)}`);

  if (query.disease) add("disease", query.disease);
  if (query.status !== "recruiting") add("status", query.status);
  if (query.phase) add("phase", query.phase);
  if (query.loc) {
    add("loc", `${query.loc.lat},${query.loc.lng}`);
    if (query.locLabel) add("place", query.locLabel);
    if (query.maxKm != null) add("km", String(query.maxKm));
  }
  if (query.sort !== "status") add("sort", query.sort);
  if (query.page > 1) add("page", String(query.page));

  return params.length > 0 ? `/trials?${params.join("&")}` : "/trials";
}

/** True when the trial's free-text phase string names the given phase number. */
export function trialMatchesPhase(phaseText: string, phase: TrialPhase): boolean {
  // Match the bare digit but not a longer number (so "Phase 1" matches "1" but
  // "Phase 12" — were it ever to exist — would not match "1").
  return new RegExp(`(?<!\\d)${phase}(?!\\d)`).test(phaseText);
}

export interface TrialFilterCriteria {
  readonly diseaseSlug?: string | null;
  readonly status?: TrialStatusFilter | null;
  readonly phase?: TrialPhase | null;
  /** Distance cap in km; only applies when set AND the row has a known distance. */
  readonly maxKm?: number | null;
}

/**
 * Pure trials filter. Order-preserving; the caller sorts separately. Distance filtering only
 * applies when ``maxKm`` is set AND the row has a non-null ``km`` (no location → no distance cut).
 */
export function filterTrials(
  rows: readonly TrialWithDistance[],
  criteria: TrialFilterCriteria,
): TrialWithDistance[] {
  const { diseaseSlug, status, phase, maxKm } = criteria;
  return rows.filter((trial) => {
    if (diseaseSlug && !trial.diseases.includes(diseaseSlug)) {
      return false;
    }
    if (status && status !== "all" && trial.status !== status) {
      return false;
    }
    if (phase && !trialMatchesPhase(trial.phase, phase)) {
      return false;
    }
    if (maxKm != null && trial.km != null && trial.km > maxKm) {
      return false;
    }
    return true;
  });
}

function byTitleAsc(a: TrialWithDistance, b: TrialWithDistance): number {
  return a.title.localeCompare(b.title);
}

function byStatusThenTitle(a: TrialWithDistance, b: TrialWithDistance): number {
  const r = statusRank(a.status) - statusRank(b.status);
  if (r !== 0) return r;
  return byTitleAsc(a, b);
}

function byDateDesc(a: TrialWithDistance, b: TrialWithDistance): number {
  const da = a.lastSeen ?? "";
  const db = b.lastSeen ?? "";
  if (da !== db) return db.localeCompare(da); // most recent first; "" sorts last
  return byStatusThenTitle(a, b);
}

function byDistanceAsc(a: TrialWithDistance, b: TrialWithDistance): number {
  if (a.km != null && b.km != null && a.km !== b.km) return a.km - b.km;
  if (a.km != null && b.km == null) return -1;
  if (a.km == null && b.km != null) return 1;
  return byStatusThenTitle(a, b);
}

/** Pure, stable sort of the filtered rows for the chosen order. Never mutates the input. */
export function sortTrials(
  rows: readonly TrialWithDistance[],
  sort: TrialSort,
): TrialWithDistance[] {
  switch (sort) {
    case "nearest":
      return [...rows].sort(byDistanceAsc);
    case "date":
      return [...rows].sort(byDateDesc);
    case "status":
    default:
      return [...rows].sort(byStatusThenTitle);
  }
}
