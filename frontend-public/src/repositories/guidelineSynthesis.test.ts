import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";
import {
  citationIndex,
  orderedSynthesisPmids,
  shortDocLabel,
} from "../utils/guidelineSynthesis";

describe("fixtureOfficialGuidelineRepository.getSynthesis", () => {
  it("returns the FD synthesis (5 sections, paragraphs with source + citations)", async () => {
    const synthesis = await fixtureOfficialGuidelineRepository.getSynthesis("fd");
    expect(synthesis).not.toBeNull();
    expect(synthesis?.kind).toBe("synthesis");
    expect(synthesis?.sections).toHaveLength(5);
    expect(synthesis?.sourceIds).toEqual([
      "boyce2019",
      "gun2024",
      "szymczuk2023",
      "genereviews",
    ]);

    const everyParagraph = synthesis!.sections.flatMap((s) => s.paragraphs);
    // Every paragraph carries provenance.
    expect(everyParagraph.every((p) => p.source != null)).toBe(true);
    // Citations only reference real shelf PMIDs (no fabricated ids).
    const realPmids = new Set(["31196103", "38010041", "36849642"]);
    for (const para of everyParagraph) {
      for (const pmid of para.citations ?? []) {
        expect(realPmids.has(pmid)).toBe(true);
      }
    }
  });

  it("drives the parent projection: first two paragraphs of therapy stay guidance-level", async () => {
    const synthesis = await fixtureOfficialGuidelineRepository.getSynthesis("fd");
    const therapy = synthesis!.sections.find((s) => s.id === "therapy");
    const parentVisible = therapy!.paragraphs.slice(0, 2).map((p) => p.id);
    // Granular dosing (bisphosphonates, denosumab) sits past the parent fold.
    expect(parentVisible).not.toContain("tx-bisphos");
    expect(parentVisible).not.toContain("tx-denosumab");
  });

  it("carries no reviewer-name attribution (chat 019 demo mine)", async () => {
    const synthesis = await fixtureOfficialGuidelineRepository.getSynthesis("fd");
    const serialized = JSON.stringify(synthesis);
    expect(serialized).not.toMatch(/Riminucci|Hsiao|Dijkstra|Dowgierd/);
    expect(serialized).not.toMatch(/statusBy/);
  });

  it("returns the MAS synthesis and null for diseases without one", async () => {
    expect(await fixtureOfficialGuidelineRepository.getSynthesis("mas")).not.toBeNull();
    expect(await fixtureOfficialGuidelineRepository.getSynthesis("noonan")).toBeNull();
    expect(await fixtureOfficialGuidelineRepository.getSynthesis("unknown")).toBeNull();
  });
});

describe("synthesis citation + provenance helpers", () => {
  it("numbers citations by document order", async () => {
    const synthesis = await fixtureOfficialGuidelineRepository.getSynthesis("fd");
    const ordered = orderedSynthesisPmids(synthesis!);
    // First cited PMID in the FD doc is Szymczuk 2023 (diagnosis → CT).
    expect(ordered[0]).toBe("36849642");
    expect(citationIndex(ordered, "36849642")).toBe(1);
    expect(citationIndex(ordered, "31196103")).toBeGreaterThan(0);
  });

  it("labels shelf documents and falls back for unknown ids", async () => {
    const docs = await fixtureOfficialGuidelineRepository.getShelf("fd");
    expect(shortDocLabel(docs, "boyce2019")).toBe("Javaid 2019");
    expect(shortDocLabel(docs, "gun2024")).toBe("Gun 2024");
    expect(shortDocLabel(docs, "genereviews")).toBe("GeneReviews");
    expect(shortDocLabel(docs, "99999999")).toBe("PMID 99999999");
  });
});
