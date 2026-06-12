import { describe, expect, it } from "vitest";
import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type { PublicDoctor } from "../types/doctor";
import { pubmedRoleLabel, tierForDisease } from "./doctorLabels";

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

  it("falls back to the global pubmedRole when there is no experience map", () => {
    const allecou = bySlug("allecou");
    expect(allecou.experienceByDisease).toBeUndefined();
    expect(tierForDisease(allecou, "fd")).toBe(allecou.pubmedRole);
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
