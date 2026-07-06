import { describe, expect, it } from "vitest";
import type { PublicDoctor } from "../types/doctor";
import type { DoctorWithDistance } from "./doctorSort";
import {
  DEFAULT_DOCTORS_QUERY,
  parseDoctorsQuery,
  queryRecordFromHash,
  serializeDoctorsQuery,
  sortDoctors,
  type DoctorsQuery,
} from "./doctorsQuery";

describe("queryRecordFromHash", () => {
  it("returns an empty record when there is no query string", () => {
    expect(queryRecordFromHash("#/doctors")).toEqual({});
  });

  it("decodes key/value pairs", () => {
    expect(queryRecordFromHash("#/doctors?disease=fd&place=Warsaw%2C%20PL")).toEqual({
      disease: "fd",
      place: "Warsaw, PL",
    });
  });
});

describe("parseDoctorsQuery", () => {
  it("returns the default query for an empty record", () => {
    expect(parseDoctorsQuery({})).toEqual(DEFAULT_DOCTORS_QUERY);
  });

  it("parses every facet", () => {
    const q = parseDoctorsQuery({
      disease: "FD",
      role: "research_leader",
      source: "parent",
      parent: "1",
      loc: "52.2,21.0",
      place: "Warsaw, PL",
      km: "100",
      work: "guideline,original",
      recency: "active_2y",
      sort: "distance",
      page: "3",
    });
    expect(q).toEqual({
      disease: "fd", // normalized lowercase
      role: "research_leader",
      source: "parent",
      parentOnly: true,
      loc: { lat: 52.2, lng: 21.0 },
      locLabel: "Warsaw, PL",
      maxKm: 100,
      workTypes: ["guideline", "original"],
      recency: "active_2y",
      sort: "distance",
      page: 3,
    });
  });

  it("drops unknown work types and invalid recency floors", () => {
    const q = parseDoctorsQuery({ work: "guideline,wizardry", recency: "older" });
    expect(q.workTypes).toEqual(["guideline"]);
    expect(q.recency).toBeNull(); // "older" is not a selectable floor
  });

  it("falls back to defaults for invalid facet values", () => {
    const q = parseDoctorsQuery({
      role: "wizard",
      source: "myspace",
      sort: "vibes",
      km: "42", // not an allowed radius
      page: "0",
      loc: "not-a-coord",
    });
    expect(q.role).toBeNull();
    expect(q.source).toBe("all");
    expect(q.sort).toBe("best");
    expect(q.maxKm).toBeNull();
    expect(q.page).toBe(1);
    expect(q.loc).toBeNull();
  });

  it("accepts the extended long-range radii (2500 / 5000 km)", () => {
    const base = { loc: "52.2,21.0", place: "Warsaw, PL" };
    expect(parseDoctorsQuery({ ...base, km: "2500" }).maxKm).toBe(2500);
    expect(parseDoctorsQuery({ ...base, km: "5000" }).maxKm).toBe(5000);
  });

  it("drops maxKm and label when there is no location", () => {
    const q = parseDoctorsQuery({ km: "100", place: "Nowhere" });
    expect(q.loc).toBeNull();
    expect(q.maxKm).toBeNull();
    expect(q.locLabel).toBeNull();
  });
});

describe("serializeDoctorsQuery", () => {
  it("yields a clean /doctors for the default query", () => {
    expect(serializeDoctorsQuery(DEFAULT_DOCTORS_QUERY)).toBe("/doctors");
  });

  it("omits defaults and emits keys in a stable order", () => {
    const q: DoctorsQuery = {
      ...DEFAULT_DOCTORS_QUERY,
      disease: "fd",
      source: "parent",
      sort: "distance",
      page: 2,
    };
    expect(serializeDoctorsQuery(q)).toBe(
      "/doctors?disease=fd&source=parent&sort=distance&page=2",
    );
  });

  it("round-trips a fully populated query", () => {
    const q: DoctorsQuery = {
      disease: "fd",
      role: "research_leader",
      source: "parent",
      parentOnly: true,
      loc: { lat: 52.2, lng: 21 },
      locLabel: "Warsaw, PL",
      maxKm: 100,
      workTypes: ["guideline", "original"],
      recency: "active_2y",
      sort: "distance",
      page: 3,
    };
    expect(parseDoctorsQuery(queryRecordFromHash(`#${serializeDoctorsQuery(q)}`))).toEqual(q);
  });

  it("serializes work types in canonical order regardless of input order", () => {
    const q: DoctorsQuery = {
      ...DEFAULT_DOCTORS_QUERY,
      workTypes: ["original", "guideline"],
    };
    // WORK_TYPE_ORDER puts guideline before original; the comma is URL-encoded (%2C).
    expect(serializeDoctorsQuery(q)).toBe("/doctors?work=guideline%2Coriginal");
  });

  it("never serializes maxKm without a location", () => {
    const q: DoctorsQuery = { ...DEFAULT_DOCTORS_QUERY, maxKm: 100 };
    expect(serializeDoctorsQuery(q)).toBe("/doctors");
  });
});

function makeDoctor(
  slug: string,
  name: string,
  score: number,
  km: number | null,
): DoctorWithDistance {
  return {
    ...({
      slug,
      name,
      specialty: "",
      role: "",
      institution: "",
      city: "",
      country: "",
      lat: 0,
      lng: 0,
      diseases: [],
      pubmedRole: "research_leader",
      score,
      evidence: {
        firstOrLastAuthorPapers: 0,
        reviewPapers: 0,
        citesRecentGuidelines: false,
        activeLast2y: false,
        guidelineOrConsensusCoauthor: false,
      },
      publications: [],
      bio: "",
      publicSource: "",
      endorsements: [],
      contact: "",
    } satisfies PublicDoctor),
    km,
  };
}

describe("sortDoctors", () => {
  const rows: DoctorWithDistance[] = [
    makeDoctor("c", "Carol", 50, 300),
    makeDoctor("a", "Alice", 90, null),
    makeDoctor("b", "Bob", 70, 10),
  ];

  it("sorts by distance (nearest first, unknown last)", () => {
    expect(sortDoctors(rows, "distance").map((d) => d.slug)).toEqual(["b", "c", "a"]);
  });

  it("sorts by score (high to low)", () => {
    expect(sortDoctors(rows, "score").map((d) => d.slug)).toEqual(["a", "b", "c"]);
  });

  it("sorts by name (A–Z)", () => {
    expect(sortDoctors(rows, "name").map((d) => d.slug)).toEqual(["a", "b", "c"]);
  });

  it("'best' is distance-then-score and does not mutate the input", () => {
    const before = rows.map((d) => d.slug);
    expect(sortDoctors(rows, "best").map((d) => d.slug)).toEqual(["b", "c", "a"]);
    expect(rows.map((d) => d.slug)).toEqual(before);
  });

  it("sorts by recency (newest disease-relevant year first, unknown last)", () => {
    const recencyRows: DoctorWithDistance[] = [
      { ...makeDoctor("old", "Old", 90, null), lastCentralPaperYear: 2012 },
      { ...makeDoctor("new", "New", 10, null), lastCentralPaperYear: 2025 },
      { ...makeDoctor("none", "None", 50, null) }, // no year → last
    ];
    expect(sortDoctors(recencyRows, "recency").map((d) => d.slug)).toEqual([
      "new",
      "old",
      "none",
    ]);
  });
});
