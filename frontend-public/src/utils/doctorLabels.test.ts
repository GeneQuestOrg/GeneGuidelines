import { describe, expect, it } from "vitest";
import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type { PublicDoctor } from "../types/doctor";
import { doctorLocation, pubmedRoleLabel, tierForDisease } from "./doctorLabels";

const bySlug = (slug: string): PublicDoctor => {
  const doctor = PUBLIC_DOCTORS.find((d) => d.slug === slug);
  if (!doctor) {
    throw new Error(`fixture doctor not found: ${slug}`);
  }
  return doctor;
};

describe("tierForDisease", () => {
  it("returns the per-disease tier when the experience map has the slug", () => {
    const dowgierd = bySlug("dowgierd");
    expect(dowgierd.experienceByDisease).toMatchObject({ mas: "research_participant" });
    expect(tierForDisease(dowgierd, "mas")).toBe("research_participant");
    expect(tierForDisease(dowgierd, "fd")).toBe("research_leader");
  });

  it("falls back to the global pubmedRole when the slug is absent from the map", () => {
    const dowgierd = bySlug("dowgierd");
    // "xyz" is not in experienceByDisease → fall back to pubmedRole.
    expect(tierForDisease(dowgierd, "xyz")).toBe(dowgierd.pubmedRole);
  });

  it("falls back to the global pubmedRole when the disease is absent from the experience map", () => {
    const allecou = bySlug("allecou");
    // allecou is FD-only, so "mas" is not in experienceByDisease → fall back to pubmedRole.
    expect(allecou.experienceByDisease?.mas).toBeUndefined();
    expect(tierForDisease(allecou, "mas")).toBe(allecou.pubmedRole);
  });
});

describe("pubmedRoleLabel", () => {
  it("maps each role to a human label and unknown to Unknown", () => {
    expect(pubmedRoleLabel("research_leader")).toBe("Led research");
    expect(pubmedRoleLabel("research_participant")).toBe("Contributed");
    expect(pubmedRoleLabel("case_study_author")).toBe("Case studies");
    expect(pubmedRoleLabel("unknown")).toBe("Unknown");
  });
});

describe("doctorLocation", () => {
  const base = PUBLIC_DOCTORS[0] as PublicDoctor;

  it("prefers a real NPPES practice (City, ST) over the noisy top-level fields", () => {
    const d: PublicDoctor = {
      ...base, city: "WASHINGTON", country: "MD",
      practices: [{ type: "primary", name: "NIH", city: "Washington", state: "DC",
        country: "US", lat: 0, lng: 0, source: "nppes", confidence: "high" }],
    };
    expect(doctorLocation(d)).toBe("Washington, DC");
  });

  it("drops a US-state-abbrev mis-stored as country and renders City, ST", () => {
    const d: PublicDoctor = { ...base, city: "Bethesda", country: "MD", practices: [] };
    expect(doctorLocation(d)).toBe("Bethesda, MD");
  });

  it("collapses City, City duplication ('MD, MD' → 'MD')", () => {
    const d: PublicDoctor = { ...base, city: "MD", country: "MD", practices: [] };
    expect(doctorLocation(d)).toBe("MD");
  });

  it("keeps a real ISO country distinct from the city", () => {
    const d: PublicDoctor = { ...base, city: "Rome", country: "IT", practices: [] };
    expect(doctorLocation(d)).toBe("Rome, IT");
  });

  it("says location not listed when nothing usable is present", () => {
    const d: PublicDoctor = { ...base, city: "—", country: "—", practices: [] };
    expect(doctorLocation(d)).toBe("Location not listed");
  });
});
