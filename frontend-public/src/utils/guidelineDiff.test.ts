import { describe, expect, it } from "vitest";
import type { GuidelineDocument } from "../types/guidelineDocument";
import type { GuidelinePrParagraphMap } from "../types/contentPr";
import {
  buildSectionsForPrPreview,
  isParagraphVisibleInReader,
} from "./guidelineDiff";

const doc: GuidelineDocument = {
  slug: "fd",
  title: "Test",
  version: "v1",
  lastUpdated: "2026-01-01",
  basedOn: "seed",
  status: "consensus",
  statusBy: null,
  sections: [
    {
      id: "therapy",
      title: "Therapy",
      paragraphs: [
        { id: "old", text: "Old dose", prInDiff: { prId: "PR-142", removed: true } },
        { id: "new", text: "New dose", prInDiff: { prId: "PR-142", added: true } },
      ],
    },
    {
      id: "surgery",
      title: "Surgery",
      paragraphs: [{ id: "sx-optic", text: "Optic rule" }],
    },
  ],
};

const insertMap: GuidelinePrParagraphMap = {
  targetSection: "surgery",
  targetParaIds: ["sx-optic", "sx-optic-add"],
  replaceMode: "insert-after",
  insertAfter: "sx-optic",
  addedParagraph: {
    id: "sx-optic-add",
    text: "MRI every 12 months",
    citations: ["37184453"],
  },
};

describe("guidelineDiff", () => {
  it("hides removed paragraphs unless viewing that PR diff", () => {
    expect(isParagraphVisibleInReader(doc.sections[0].paragraphs[0])).toBe(false);
    expect(
      isParagraphVisibleInReader(doc.sections[0].paragraphs[0], { diffPrId: "PR-142" }),
    ).toBe(true);
  });

  it("inserts added paragraph for insert-after PR map", () => {
    const sections = buildSectionsForPrPreview(doc, insertMap, "PR-141");
    const surgery = sections.find((s) => s.id === "surgery");
    expect(surgery?.paragraphs.map((p) => p.id)).toEqual([
      "sx-optic",
      "sx-optic-add",
    ]);
    expect(surgery?.paragraphs[1].prInDiff?.added).toBe(true);
  });
});
