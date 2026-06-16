import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";

describe("fixtureOfficialGuidelineRepository.getBaseline", () => {
  it("returns the noonan level-(c) baseline with run steps and items", async () => {
    const baseline = await fixtureOfficialGuidelineRepository.getBaseline("noonan");
    expect(baseline).not.toBeNull();
    expect(baseline?.slug).toBe("noonan");
    expect(baseline?.readState.read).toBe(false);
    expect(baseline?.runSteps.some((s) => s.active)).toBe(true);
    expect(baseline?.sections.map((s) => s.id)).toEqual(["no-dx", "no-cardio"]);
    // The diagnosis item cites the real Noonan reference (PMID 23303081).
    const dx = baseline!.sections[0].items[0];
    expect(dx.evidence).toBe("strong");
    expect(dx.citations).toContain("23303081");
  });

  it("returns null for diseases that have a guideline or no baseline", async () => {
    // fd has a synthesis (level a) → no baseline.
    expect(await fixtureOfficialGuidelineRepository.getBaseline("fd")).toBeNull();
    expect(await fixtureOfficialGuidelineRepository.getBaseline("unknown")).toBeNull();
  });

  it("carries no reviewer names", async () => {
    const baseline = await fixtureOfficialGuidelineRepository.getBaseline("noonan");
    expect(JSON.stringify(baseline)).not.toMatch(/Riminucci|Hsiao|Dijkstra|Boyce/);
  });
});
