import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";

describe("fixtureOfficialGuidelineRepository.getSynthSignals", () => {
  it("seeds no signals for any disease", async () => {
    // A signal is a count of real clinician votes. The fixtures used to ship
    // "7 found this useful · 3 verified" plus flag notes signed "Verified
    // reviewer", which is what production ended up serving — see the
    // f4c8d1b6a903 migration.
    for (const slug of ["fd", "mas", "noonan", "unknown"]) {
      expect(await fixtureOfficialGuidelineRepository.getSynthSignals(slug)).toEqual({});
    }
  });
});
