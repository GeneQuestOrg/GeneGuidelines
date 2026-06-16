import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";
import { weightedSuggestionScore } from "../types/guidelineSuggestion";

describe("fixtureOfficialGuidelineRepository.getSuggestions", () => {
  it("returns the FD suggestions (3) with the expected gates and shapes", async () => {
    const suggestions = await fixtureOfficialGuidelineRepository.getSuggestions("fd");
    expect(suggestions).toHaveLength(3);
    const byId = Object.fromEntries(suggestions.map((s) => [s.id, s]));
    expect(byId["sg-oct"].gate).toBe("promoted");
    expect(byId["sg-oct"].parentText).toBeTruthy();
    // The modification carries a unified diff vs the source doc.
    expect(byId["sg-deno"].kind).toBe("modification");
    expect(byId["sg-deno"].diff?.lines.some((l) => l.t === "del")).toBe(true);
    expect(byId["sg-deno"].diff?.lines.some((l) => l.t === "add")).toBe(true);
    expect(byId["sg-deno"].regenSeed).toBeTruthy();
    // Additions have no diff.
    expect(byId["sg-gnas"].kind).toBe("addition");
    expect(byId["sg-gnas"].diff).toBeUndefined();
  });

  it("cites only real shelf PMIDs and carries no reviewer names", async () => {
    const suggestions = await fixtureOfficialGuidelineRepository.getSuggestions("fd");
    const realPmids = new Set(["31196103", "38010041", "36849642"]);
    for (const s of suggestions) {
      for (const pmid of s.citations) {
        expect(realPmids.has(pmid)).toBe(true);
      }
    }
    const serialized = JSON.stringify(suggestions);
    expect(serialized).not.toMatch(/Riminucci|Hsiao|Dijkstra|Dowgierd|Boyce|Gun|Szymczuk/);
  });

  it("returns MAS suggestions and empty for diseases without any", async () => {
    expect(await fixtureOfficialGuidelineRepository.getSuggestions("mas")).toHaveLength(1);
    expect(await fixtureOfficialGuidelineRepository.getSuggestions("noonan")).toHaveLength(0);
    expect(await fixtureOfficialGuidelineRepository.getSuggestions("unknown")).toHaveLength(0);
  });
});

describe("weightedSuggestionScore", () => {
  it("weights verified specialists up and 'wrong' down", () => {
    const base = { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 };
    expect(weightedSuggestionScore({ ...base, useful: 1 })).toBe(2);
    expect(weightedSuggestionScore({ ...base, verified: 1 })).toBe(3);
    expect(weightedSuggestionScore({ ...base, not: 1 })).toBe(-1);
    expect(weightedSuggestionScore({ ...base, wrong: 1 })).toBe(-4);
    // sg-deno (5 useful, 0 not, 1 wrong, 3 verified) ranks above sg-oct (3,1,0,2).
    const deno = weightedSuggestionScore({ useful: 5, not: 0, wrong: 1, ratings: 6, verified: 3 });
    const oct = weightedSuggestionScore({ useful: 3, not: 1, wrong: 0, ratings: 4, verified: 2 });
    expect(deno).toBeGreaterThan(oct);
  });
});
