import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import enMap from "../locales/en/disease-map.json";
import plMap from "../locales/pl/disease-map.json";

/**
 * The parent map offers questions, never advice. That line was decided on 2026-09-08
 * (wizja/02-rodzic.md, "Granica: orientacja, nie porada") and it has drifted back
 * twice: the step-3 lede promised "red flags" and "when to seek a second opinion"
 * long after both were withdrawn, because nothing failed when the copy said so.
 *
 * Two rules, both mechanical:
 *   - a question is published only with the verbatim guideline sentence behind it
 *     (the evidence gate, ADR 005), and that sentence is quoted, so it is identical
 *     in every language — translating it would stop it being a quotation;
 *   - the withdrawn phrasings are a closed list and stay out of the copy.
 */
const source = readFileSync(
  fileURLToPath(new URL("./DiseaseMapView.tsx", import.meta.url)),
  "utf8",
);

const locales = { en: enMap as Record<string, string>, pl: plMap as Record<string, string> };

/** The [question, guideline-sentence] pairs the view actually renders. */
const pairs = [...source.matchAll(/\["(askQ\d+)",\s*"(askS\d+)"\]/g)].map(
  ([, question, quote]) => [question, quote] as const,
);

describe("parent map copy", () => {
  it("renders at least one question", () => {
    expect(pairs.length).toBeGreaterThan(0);
  });

  it.each(pairs)("%s is published with its source sentence %s", (question, quote) => {
    for (const [lang, map] of Object.entries(locales)) {
      expect(map[question], `${lang}:${question}`).toBeTruthy();
      expect(map[quote], `${lang}:${quote}`).toBeTruthy();
    }
    // A quotation is the same text in every language or it is not a quotation.
    expect(locales.pl[quote]).toBe(locales.en[quote]);
  });

  it.each(["kiedy szukać drugiej opinii", "sygnały ostrzegawcze", "histopatologia"])(
    "keeps the withdrawn phrase %s out of the Polish map",
    (phrase) => {
      const copy = JSON.stringify(plMap).toLowerCase();
      expect(copy).not.toContain(phrase.toLowerCase());
    },
  );

  it.each(["second opinion", "red flag", "histopathology can be wrong"])(
    "keeps the withdrawn phrase %s out of the English map",
    (phrase) => {
      const copy = JSON.stringify(enMap).toLowerCase();
      expect(copy).not.toContain(phrase.toLowerCase());
    },
  );
});
