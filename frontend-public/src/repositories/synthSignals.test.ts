import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";

describe("fixtureOfficialGuidelineRepository.getSynthSignals", () => {
  it("returns per-section signals for FD with flag notes and no names", async () => {
    const signals = await fixtureOfficialGuidelineRepository.getSynthSignals("fd");
    expect(Object.keys(signals)).toEqual([
      "diagnosis",
      "histopathology",
      "therapy",
      "surgery",
      "monitoring",
    ]);
    expect(signals.diagnosis.up).toBe(7);
    // Asymmetric: histopathology + therapy carry an open flag with a QA note.
    expect(signals.histopathology.flags).toBe(1);
    expect(signals.histopathology.flagNotes?.[0].who).toBe("Verified reviewer");
    expect(JSON.stringify(signals)).not.toMatch(/Riminucci|Hsiao|Dijkstra/);
  });

  it("returns MAS signals and an empty map for diseases without any", async () => {
    expect(Object.keys(await fixtureOfficialGuidelineRepository.getSynthSignals("mas"))).toEqual([
      "overview",
    ]);
    expect(await fixtureOfficialGuidelineRepository.getSynthSignals("noonan")).toEqual({});
    expect(await fixtureOfficialGuidelineRepository.getSynthSignals("unknown")).toEqual({});
  });
});
