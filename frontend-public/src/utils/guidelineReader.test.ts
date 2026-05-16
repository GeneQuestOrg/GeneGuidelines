import { describe, expect, it } from "vitest";
import type { GuidelineDocument } from "../types/guidelineDocument";
import {
  citationDisplayIndex,
  collectCitationPmids,
  filterDocumentForReader,
  isParagraphVisibleInReader,
} from "./guidelineReader";

const sampleDoc: GuidelineDocument = {
  slug: "fd",
  title: "Test",
  version: "v1",
  lastUpdated: "2026-01-01",
  basedOn: "seed",
  status: "consensus",
  statusBy: null,
  sections: [
    {
      id: "s1",
      title: "Section",
      paragraphs: [
        {
          id: "p1",
          text: "Visible",
          citations: ["111", "222"],
        },
        {
          id: "p2",
          text: "Removed",
          prInDiff: { prId: "PR-1", removed: true },
          citations: ["333"],
        },
      ],
    },
  ],
};

describe("guidelineReader", () => {
  it("hides paragraphs marked removed in PR diff", () => {
    expect(isParagraphVisibleInReader(sampleDoc.sections[0].paragraphs[1])).toBe(
      false,
    );
  });

  it("filters document for reader", () => {
    const filtered = filterDocumentForReader(sampleDoc);
    expect(filtered.sections[0].paragraphs).toHaveLength(1);
    expect(filtered.sections[0].paragraphs[0].id).toBe("p1");
  });

  it("collects citation PMIDs in document order", () => {
    expect(collectCitationPmids(sampleDoc)).toEqual(["111", "222"]);
  });

  it("maps PMID to display index", () => {
    const ordered = collectCitationPmids(sampleDoc);
    expect(citationDisplayIndex(ordered, "222")).toBe(2);
    expect(citationDisplayIndex(ordered, "999")).toBeNull();
  });
});
