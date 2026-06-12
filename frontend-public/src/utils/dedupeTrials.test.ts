import { describe, expect, it } from "vitest";
import type { Trial } from "../types/trial";
import { dedupeTrials } from "./dedupeTrials";

const trial = (nct: string): Trial => ({
  nct,
  title: `Trial ${nct}`,
  phase: "Phase 2",
  status: "recruiting",
  sponsor: "Sponsor",
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
  diseases: [],
});

describe("dedupeTrials", () => {
  it("returns an empty list for no input lists", () => {
    expect(dedupeTrials([])).toEqual([]);
  });

  it("flattens several lists into one", () => {
    const result = dedupeTrials([[trial("A")], [trial("B"), trial("C")]]);
    expect(result.map((t) => t.nct)).toEqual(["A", "B", "C"]);
  });

  it("keeps the first occurrence of each nct across lists", () => {
    const first = trial("A");
    const dup = { ...trial("A"), title: "later duplicate" };
    const result = dedupeTrials([[first, trial("B")], [dup, trial("C")]]);
    expect(result.map((t) => t.nct)).toEqual(["A", "B", "C"]);
    expect(result[0]).toBe(first);
  });
});
