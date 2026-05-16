import { describe, expect, it } from "vitest";
import { formatDistanceKm, haversineKm, projectToEuMapPercent } from "./geo";

describe("haversineKm", () => {
  it("returns ~0 for identical points", () => {
    const point = { lat: 52.229, lng: 21.012 };
    expect(haversineKm(point, point)).toBeLessThan(0.01);
  });

  it("returns plausible Warsaw–Poznań distance", () => {
    const warsaw = { lat: 52.229, lng: 21.012 };
    const poznan = { lat: 52.408, lng: 16.934 };
    const km = haversineKm(warsaw, poznan);
    expect(km).toBeGreaterThan(250);
    expect(km).toBeLessThan(320);
  });
});

describe("formatDistanceKm", () => {
  it("formats sub-kilometre distances", () => {
    expect(formatDistanceKm(0.4)).toBe("< 1 km");
  });

  it("rounds medium distances", () => {
    expect(formatDistanceKm(42.6)).toBe("43 km");
  });
});

describe("projectToEuMapPercent", () => {
  it("projects Warsaw inside EU bounds", () => {
    const pos = projectToEuMapPercent(52.229, 21.012);
    expect(pos).not.toBeNull();
    expect(pos!.x).toBeGreaterThan(0);
    expect(pos!.x).toBeLessThan(100);
  });

  it("returns null for coordinates outside EU frame", () => {
    expect(projectToEuMapPercent(37.763, -122.458)).toBeNull();
  });
});
