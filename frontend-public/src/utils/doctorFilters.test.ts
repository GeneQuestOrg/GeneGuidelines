import { describe, expect, it } from "vitest";
import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type { PublicDoctor } from "../types/doctor";
import { addedViaOf, filterDoctors } from "./doctorFilters";
import { attachDoctorDistances, type DoctorWithDistance } from "./doctorSort";

const rows: readonly DoctorWithDistance[] = attachDoctorDistances(PUBLIC_DOCTORS, null);

const slugs = (result: readonly DoctorWithDistance[]): string[] =>
  result.map((d) => d.slug);

describe("addedViaOf", () => {
  it("returns the explicit provenance when present", () => {
    expect(addedViaOf({ addedVia: "parent" })).toBe("parent");
  });

  it("falls back to pubmed when addedVia is missing", () => {
    expect(addedViaOf({})).toBe("pubmed");
  });
});

describe("filterDoctors", () => {
  it("returns every doctor when no disease is set", () => {
    const result = filterDoctors(rows, {});
    expect(result).toHaveLength(PUBLIC_DOCTORS.length);
  });

  it("filters to the subset matching a disease slug", () => {
    const all = filterDoctors(rows, {});
    const result = filterDoctors(rows, { diseaseSlug: "mas" });
    expect(result.length).toBeLessThan(all.length);
    expect(result.every((d) => d.diseases.includes("mas"))).toBe(true);
    // allecou/podstawski are fd-only, so they must drop out.
    expect(slugs(result)).not.toContain("allecou");
  });

  it("filters by source, treating missing addedVia as pubmed", () => {
    // dowgierd has addedVia: "pubmed" explicitly; allecou has none (fallback → pubmed).
    const pubmed = filterDoctors(rows, { source: "pubmed" });
    expect(slugs(pubmed)).toContain("dowgierd");
    expect(slugs(pubmed)).toContain("allecou");
    // No fixture is parent-added, so the parent source yields nothing.
    expect(filterDoctors(rows, { source: "parent" })).toHaveLength(0);
  });

  it("keeps only doctors with a parent signal when parentOnly is set", () => {
    const result = filterDoctors(rows, { parentOnly: true });
    // dowgierd is the only fixture with a parentRec.
    expect(slugs(result)).toEqual(["dowgierd"]);
  });

  it("ignores maxKm for rows without a known distance", () => {
    // No user location → every km is null → distance filter is a no-op.
    const result = filterDoctors(rows, { maxKm: 25 });
    expect(result).toHaveLength(PUBLIC_DOCTORS.length);
  });

  it("applies maxKm only when a row has a known distance", () => {
    const near: DoctorWithDistance = { ...(PUBLIC_DOCTORS[0] as PublicDoctor), km: 10 };
    const far: DoctorWithDistance = { ...(PUBLIC_DOCTORS[1] as PublicDoctor), km: 800 };
    const unknown: DoctorWithDistance = { ...(PUBLIC_DOCTORS[2] as PublicDoctor), km: null };
    const result = filterDoctors([near, far, unknown], { maxKm: 100 });
    expect(slugs(result)).toEqual([near.slug, unknown.slug]);
  });
});
