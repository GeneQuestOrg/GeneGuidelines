import { describe, expect, it } from "vitest";
import type { TrialWithDistance } from "../api/trials";
import type { Trial } from "../types/trial";
import {
  DEFAULT_TRIALS_QUERY,
  filterTrials,
  parseTrialsQuery,
  queryRecordFromHash,
  serializeTrialsQuery,
  sortTrials,
  trialMatchesPhase,
  type TrialsQuery,
} from "./trialsQuery";

describe("queryRecordFromHash", () => {
  it("returns an empty record when there is no query string", () => {
    expect(queryRecordFromHash("#/trials")).toEqual({});
  });

  it("decodes key/value pairs", () => {
    expect(queryRecordFromHash("#/trials?disease=fd&place=Warsaw%2C%20PL")).toEqual({
      disease: "fd",
      place: "Warsaw, PL",
    });
  });
});

describe("parseTrialsQuery", () => {
  it("returns the default query for an empty record", () => {
    expect(parseTrialsQuery({})).toEqual(DEFAULT_TRIALS_QUERY);
  });

  it("defaults status to recruiting and sort to status", () => {
    const q = parseTrialsQuery({});
    expect(q.status).toBe("recruiting");
    expect(q.sort).toBe("status");
  });

  it("parses every facet", () => {
    const q = parseTrialsQuery({
      disease: "FD",
      status: "completed",
      phase: "2",
      loc: "52.2,21.0",
      place: "Warsaw, PL",
      km: "100",
      sort: "nearest",
      page: "3",
    });
    expect(q).toEqual({
      disease: "fd", // normalized lowercase
      status: "completed",
      phase: "2",
      loc: { lat: 52.2, lng: 21.0 },
      locLabel: "Warsaw, PL",
      maxKm: 100,
      sort: "nearest",
      page: 3,
    });
  });

  it("falls back to defaults for invalid facet values", () => {
    const q = parseTrialsQuery({
      status: "myspace",
      phase: "9",
      sort: "vibes",
      km: "42", // not an allowed radius
      page: "0",
      loc: "not-a-coord",
    });
    expect(q.status).toBe("recruiting");
    expect(q.phase).toBeNull();
    expect(q.sort).toBe("status");
    expect(q.maxKm).toBeNull();
    expect(q.page).toBe(1);
    expect(q.loc).toBeNull();
  });

  it("drops maxKm and label when there is no location", () => {
    const q = parseTrialsQuery({ km: "100", place: "Nowhere" });
    expect(q.loc).toBeNull();
    expect(q.maxKm).toBeNull();
    expect(q.locLabel).toBeNull();
  });
});

describe("serializeTrialsQuery", () => {
  it("yields a clean /trials for the default query", () => {
    expect(serializeTrialsQuery(DEFAULT_TRIALS_QUERY)).toBe("/trials");
  });

  it("omits defaults and emits keys in a stable order", () => {
    const q: TrialsQuery = {
      ...DEFAULT_TRIALS_QUERY,
      disease: "fd",
      status: "completed",
      sort: "nearest",
      page: 2,
    };
    expect(serializeTrialsQuery(q)).toBe(
      "/trials?disease=fd&status=completed&sort=nearest&page=2",
    );
  });

  it("does not serialize the default recruiting status or status sort", () => {
    const q: TrialsQuery = { ...DEFAULT_TRIALS_QUERY, disease: "fd" };
    expect(serializeTrialsQuery(q)).toBe("/trials?disease=fd");
  });

  it("round-trips a fully populated query", () => {
    const q: TrialsQuery = {
      disease: "fd",
      status: "completed",
      phase: "3",
      loc: { lat: 52.2, lng: 21 },
      locLabel: "Warsaw, PL",
      maxKm: 100,
      sort: "nearest",
      page: 3,
    };
    expect(parseTrialsQuery(queryRecordFromHash(`#${serializeTrialsQuery(q)}`))).toEqual(q);
  });

  it("never serializes maxKm without a location", () => {
    const q: TrialsQuery = { ...DEFAULT_TRIALS_QUERY, maxKm: 100 };
    expect(serializeTrialsQuery(q)).toBe("/trials");
  });
});

describe("trialMatchesPhase", () => {
  it("matches the phase digit in free-text phase strings", () => {
    expect(trialMatchesPhase("Phase 2", "2")).toBe(true);
    expect(trialMatchesPhase("Phase 1/2", "1")).toBe(true);
    expect(trialMatchesPhase("Phase 1/2", "2")).toBe(true);
    expect(trialMatchesPhase("Phase 2", "3")).toBe(false);
    expect(trialMatchesPhase("Observational", "2")).toBe(false);
  });
});

function makeTrial(
  nct: string,
  overrides: Partial<Trial> & { km?: number | null } = {},
): TrialWithDistance {
  const { km = null, ...rest } = overrides;
  return {
    ...({
      nct,
      title: nct,
      phase: "Phase 2",
      status: "recruiting",
      sponsor: "",
      city: null,
      country: null,
      lat: null,
      lng: null,
      ageRange: null,
      principalInvestigator: null,
      eligibilitySummary: "",
      enrollmentTarget: null,
      enrolled: null,
      contact: null,
      lastSeen: null,
      diseases: ["fd"],
    } satisfies Trial),
    ...rest,
    km,
  };
}

describe("filterTrials", () => {
  const rows: TrialWithDistance[] = [
    makeTrial("a", { status: "recruiting", phase: "Phase 1", diseases: ["fd"], km: 10 }),
    makeTrial("b", { status: "completed", phase: "Phase 2", diseases: ["fd", "mas"], km: 300 }),
    makeTrial("c", { status: "recruiting", phase: "Observational", diseases: ["noonan"], km: null }),
  ];

  it("filters by status", () => {
    expect(filterTrials(rows, { status: "recruiting" }).map((t) => t.nct)).toEqual(["a", "c"]);
  });

  it("filters by phase against the free-text phase string", () => {
    expect(filterTrials(rows, { phase: "2" }).map((t) => t.nct)).toEqual(["b"]);
  });

  it("filters by disease membership", () => {
    expect(filterTrials(rows, { diseaseSlug: "mas" }).map((t) => t.nct)).toEqual(["b"]);
  });

  it("applies the distance cap only to rows with a known distance", () => {
    // km=300 dropped; km=null kept (no location → no distance cut for that row).
    expect(filterTrials(rows, { maxKm: 100 }).map((t) => t.nct)).toEqual(["a", "c"]);
  });

  it("keeps every status when 'all'", () => {
    expect(filterTrials(rows, { status: "all" }).map((t) => t.nct)).toEqual(["a", "b", "c"]);
  });
});

describe("sortTrials", () => {
  const rows: TrialWithDistance[] = [
    makeTrial("c", { status: "completed", lastSeen: "2024-01-01", km: 300 }),
    makeTrial("a", { status: "recruiting", lastSeen: "2026-05-01", km: null }),
    makeTrial("b", { status: "active_not_recruiting", lastSeen: "2025-06-01", km: 10 }),
  ];

  it("sorts by distance (nearest first, unknown last)", () => {
    expect(sortTrials(rows, "nearest").map((t) => t.nct)).toEqual(["b", "c", "a"]);
  });

  it("sorts by status (recruiting → active → completed)", () => {
    expect(sortTrials(rows, "status").map((t) => t.nct)).toEqual(["a", "b", "c"]);
  });

  it("sorts by date (most-recently-seen first)", () => {
    expect(sortTrials(rows, "date").map((t) => t.nct)).toEqual(["a", "b", "c"]);
  });

  it("does not mutate the input", () => {
    const before = rows.map((t) => t.nct);
    sortTrials(rows, "status");
    expect(rows.map((t) => t.nct)).toEqual(before);
  });
});
