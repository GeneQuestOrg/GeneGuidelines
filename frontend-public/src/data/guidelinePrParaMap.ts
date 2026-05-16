import type { GuidelinePrParagraphMap } from "../types/contentPr";

export const GUIDELINE_PR_PARA_MAP: Readonly<
  Record<string, GuidelinePrParagraphMap>
> = {
  "PR-142": {
    targetSection: "therapy",
    targetParaIds: ["tx-denosumab-1", "tx-denosumab-2"],
    replaceMode: "replace",
  },
  "PR-141": {
    targetSection: "surgery",
    targetParaIds: ["sx-optic", "sx-optic-add"],
    replaceMode: "insert-after",
    insertAfter: "sx-optic",
    addedParagraph: {
      id: "sx-optic-add",
      text: "For asymptomatic patients with radiologically confirmed optic canal involvement: orbital MRI with contrast every 12 months. Clinically: visual fields and OCT every 6 months.",
      citations: ["38445566", "38556677"],
      lastChange: { type: "pending", by: "PR-141", date: "2026-05-05" },
    },
  },
  "PR-140": {
    targetSection: "diagnosis",
    targetParaIds: ["dx-imaging-3"],
    replaceMode: "already-applied",
  },
};
