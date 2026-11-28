import { describe, expect, it } from "vitest";

import { TRIALS } from "../data/trials";
import { fixtureTrialRepository } from "./fixtureTrialRepository";

/** Fixture trials are invented. An invented study under a real investigator's name, at a real hospital, with a contact address, is a false statement about real people; production once served two such rows from the backend seed (2026-11-28). */
describe("fixture trials name nobody real", () => {
  it("uses identifiers the registry cannot hold, and example addresses only", async () => {
    const trials = await fixtureTrialRepository.listAll();
    expect(trials.length).toBeGreaterThan(0);
    for (const trial of trials) {
      expect(trial.nct).toMatch(/^NCT9999\d{4}$/);
      expect(trial.sponsor).toMatch(/^Example /);
      expect(trial.principalInvestigator ?? "Example Investigator").toBe("Example Investigator");
      expect(trial.contact ?? "trials@example.org").toBe("trials@example.org");
    }
  });

  it("keeps the summary fixtures to the same rule", () => {
    for (const trial of TRIALS) {
      expect(trial.nct).toMatch(/^NCT9999\d{4}$/);
      expect(trial.sponsor).toMatch(/^Example /);
    }
  });
});
