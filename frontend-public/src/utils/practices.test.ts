import { describe, expect, it } from "vitest";
import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type { PublicDoctor } from "../types/doctor";
import { nearestPractice, practiceList, practicesOf } from "./practices";

const bySlug = (slug: string): PublicDoctor => {
  const doctor = PUBLIC_DOCTORS.find((d) => d.slug === slug);
  if (!doctor) {
    throw new Error(`fixture doctor not found: ${slug}`);
  }
  return doctor;
};

describe("practicesOf", () => {
  it("returns every listed practice for a multi-venue doctor", () => {
    const practices = practicesOf(bySlug("dowgierd"));
    expect(practices).toHaveLength(2);
    expect(practices.map((p) => p.type)).toEqual(["hospital", "clinic"]);
  });

  it("falls back to a single primary practice from the affiliation", () => {
    const allecou = bySlug("allecou");
    expect(allecou.practices).toBeUndefined();
    const practices = practicesOf(allecou);
    expect(practices).toHaveLength(1);
    expect(practices[0]).toMatchObject({
      type: "primary",
      name: allecou.institution,
      city: allecou.city,
      lat: allecou.lat,
      lng: allecou.lng,
    });
  });
});

describe("practiceList", () => {
  it("sorts nearest-first and flags the closest when a location is known", () => {
    // Sit the user right on the Dowgierd Clinic venue so it must sort ahead of the hospital.
    const list = practiceList(bySlug("dowgierd"), { lat: 53.7705, lng: 20.4901 });
    expect(list[0].practice.type).toBe("clinic");
    expect(list[0].nearest).toBe(true);
    expect(list[0].km).toBeLessThan((list[1].km ?? Infinity));
    expect(list[1].nearest).toBe(false);
  });

  it("leaves distance null and flags nothing without a user location", () => {
    const list = practiceList(bySlug("dowgierd"), null);
    expect(list).toHaveLength(2);
    expect(list.every((entry) => entry.km === null)).toBe(true);
    expect(list.some((entry) => entry.nearest)).toBe(false);
  });
});

describe("nearestPractice", () => {
  it("returns the closest practice to the user", () => {
    const practice = nearestPractice(bySlug("dowgierd"), { lat: 53.778, lng: 20.48 });
    expect(practice.type).toBe("hospital");
  });
});
