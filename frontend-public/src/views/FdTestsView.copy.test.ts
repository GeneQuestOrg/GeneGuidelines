import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import enTests from "../locales/en/fd-tests.json";
import plTests from "../locales/pl/fd-tests.json";

/**
 * The printable list is an artefact a parent hands to a clinician, so it is held
 * to the same rules as the parent map (components/ParentDiseaseMap.copy.test.ts):
 *
 *   - a row is published only with the verbatim guideline sentence behind it
 *     (the evidence gate, ADR 005), and that sentence is quoted, so it is
 *     identical in every language — translating it would stop it being a quotation;
 *   - the sheet describes what the guideline lists; it never tells a parent to do,
 *     ask for, start or stop anything;
 *   - the withdrawn phrasings (2026-09-08) are a closed list and stay out;
 *   - the sheet always says who wrote it and that nobody signed it off.
 */
const source = readFileSync(
  fileURLToPath(new URL("../components/FdTestsSheet.tsx", import.meta.url)),
  "utf8",
);

interface Row {
  readonly name: string;
  readonly why: string;
  readonly quote: string;
  readonly when: string;
  readonly whenQuote?: string;
}

const locales = {
  en: enTests as unknown as { rows: Record<string, Row> },
  pl: plTests as unknown as { rows: Record<string, Row> },
};

/** The row ids the view actually renders, read out of ROW_IDS in print order. */
const rowIds = (source.match(/const ROW_IDS = \[([\s\S]*?)\] as const;/)?.[1] ?? "")
  .split(",")
  .map((entry) => entry.trim().replace(/^"|"$/g, ""))
  .filter((entry) => entry.length > 0);

describe("printable FD test list copy", () => {
  it("renders rows", () => {
    expect(rowIds.length).toBeGreaterThan(0);
  });

  it("carries no row the view does not render, and renders no row without copy", () => {
    for (const [lang, map] of Object.entries(locales)) {
      expect(Object.keys(map.rows).sort(), lang).toEqual([...rowIds].sort());
    }
  });

  it.each(rowIds)("%s is published with its source sentence", (id) => {
    for (const [lang, map] of Object.entries(locales)) {
      const row = map.rows[id];
      expect(row, `${lang}:${id}`).toBeTruthy();
      expect(row.name, `${lang}:${id}.name`).toBeTruthy();
      expect(row.why, `${lang}:${id}.why`).toBeTruthy();
      expect(row.when, `${lang}:${id}.when`).toBeTruthy();
      // No quote, no row.
      expect(row.quote, `${lang}:${id}.quote`).toBeTruthy();
    }
    // A quotation is the same text in every language or it is not a quotation.
    expect(locales.pl.rows[id].quote).toBe(locales.en.rows[id].quote);
    expect(locales.pl.rows[id].whenQuote ?? "").toBe(locales.en.rows[id].whenQuote ?? "");
  });

  it.each(["kiedy szukać drugiej opinii", "sygnały ostrzegawcze", "histopatologia"])(
    "keeps the withdrawn phrase %s out of the Polish sheet",
    (phrase) => {
      expect(JSON.stringify(plTests).toLowerCase()).not.toContain(phrase.toLowerCase());
    },
  );

  it.each(["second opinion", "red flag", "histopathology can be wrong"])(
    "keeps the withdrawn phrase %s out of the English sheet",
    (phrase) => {
      expect(JSON.stringify(enTests).toLowerCase()).not.toContain(phrase.toLowerCase());
    },
  );

  /**
   * The guideline's own sentences say "should be performed" — that is the guideline
   * talking to a clinician, quoted and attributed. Our own words must not instruct
   * the parent, so only the fields we wrote are checked.
   */
  const ourWords = (lang: "pl" | "en") =>
    rowIds
      .flatMap((id) => {
        const row = locales[lang].rows[id];
        return [row.name, row.why, row.when];
      })
      .join(" ")
      .toLowerCase();

  it.each(["poproś", "zapytaj o skierowanie", "powinieneś", "powinnaś", "musisz", "należy"])(
    "does not tell a parent to act: %s",
    (phrase) => {
      expect(ourWords("pl")).not.toContain(phrase);
    },
  );

  it.each(["ask for", "you should", "make sure you", "request a"])(
    "does not tell a parent to act: %s",
    (phrase) => {
      expect(ourWords("en")).not.toContain(phrase);
    },
  );

  it("names its source and says nobody signed it off", () => {
    expect(plTests.sourceLine).toContain("31196103");
    expect(enTests.sourceLine).toContain("31196103");
    expect(plTests.authorshipLine).toContain("nie przeglądali");
    expect(enTests.authorshipLine).toContain("have not reviewed");
  });
});
