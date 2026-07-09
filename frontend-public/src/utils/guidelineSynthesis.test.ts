import { describe, expect, it } from "vitest";
import type { SynthesisParagraph } from "../types/guidelineSynthesis";
import { hasParaphrases, paraphrasesForPmid } from "./guidelineSynthesis";

function para(overrides: Partial<SynthesisParagraph> = {}): SynthesisParagraph {
  return {
    id: "p1",
    text: "A synthesised claim.",
    source: { doc: "boyce2019", loc: "§ X" },
    citations: ["31196103", "38010041"],
    ...overrides,
  };
}

describe("paraphrasesForPmid", () => {
  it("returns nothing when the paragraph carries no quotes (older synthesis)", () => {
    expect(paraphrasesForPmid(para(), "31196103")).toEqual([]);
    expect(hasParaphrases(para())).toBe(false);
  });

  it("returns only the paraphrases matching the requested PMID", () => {
    const p = para({
      quotes: [
        { pmid: "31196103", paraphrase: "Backs the diagnostic claim." },
        { pmid: "38010041", paraphrase: "Backs the therapy claim." },
      ],
    });
    expect(paraphrasesForPmid(p, "31196103")).toEqual([
      { pmid: "31196103", paraphrase: "Backs the diagnostic claim." },
    ]);
    expect(paraphrasesForPmid(p, "38010041")).toEqual([
      { pmid: "38010041", paraphrase: "Backs the therapy claim." },
    ]);
    expect(hasParaphrases(p)).toBe(true);
  });

  it("keeps multiple paraphrases for the same PMID in order", () => {
    const p = para({
      quotes: [
        { pmid: "31196103", paraphrase: "First backing passage." },
        { pmid: "31196103", paraphrase: "Second backing passage." },
      ],
    });
    expect(paraphrasesForPmid(p, "31196103").map((q) => q.paraphrase)).toEqual([
      "First backing passage.",
      "Second backing passage.",
    ]);
  });

  it("ignores blank/whitespace-only paraphrases (defensive)", () => {
    const p = para({
      quotes: [
        { pmid: "31196103", paraphrase: "   " },
        { pmid: "31196103", paraphrase: "" },
      ],
    });
    expect(paraphrasesForPmid(p, "31196103")).toEqual([]);
    expect(hasParaphrases(p)).toBe(false);
  });

  it("does not return a paraphrase for an unrelated PMID", () => {
    const p = para({
      quotes: [{ pmid: "31196103", paraphrase: "Backs the claim." }],
    });
    expect(paraphrasesForPmid(p, "99999999")).toEqual([]);
  });
});
