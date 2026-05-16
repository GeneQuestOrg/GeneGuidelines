import type { GuidelinePrParagraphMap } from "../types/contentPr";
import type {
  GuidelineDocument,
  GuidelineParagraph,
  GuidelineSection,
} from "../types/guidelineDocument";

export interface GuidelineReaderOptions {
  readonly diffPrId?: string;
}

/** Whether a paragraph appears in the published reader (non-diff). */
export function isParagraphVisibleInReader(
  para: GuidelineParagraph,
  options?: GuidelineReaderOptions,
): boolean {
  if (para.prInDiff?.removed === true) {
    if (options?.diffPrId != null && para.prInDiff.prId === options.diffPrId) {
      return true;
    }
    return false;
  }
  return true;
}

export function filterDocumentForReader(
  doc: GuidelineDocument,
  options?: GuidelineReaderOptions,
): GuidelineDocument {
  return {
    ...doc,
    sections: doc.sections.map((sec) => ({
      ...sec,
      paragraphs: sec.paragraphs.filter((p) =>
        isParagraphVisibleInReader(p, options),
      ),
    })),
  };
}

export function buildSectionsForPrPreview(
  doc: GuidelineDocument,
  paraMap: GuidelinePrParagraphMap | null,
  prId: string,
): readonly GuidelineSection[] {
  const base = filterDocumentForReader(doc, { diffPrId: prId });

  return base.sections.map((sec) => {
    let paragraphs = [...sec.paragraphs];
    if (
      paraMap != null &&
      paraMap.targetSection === sec.id &&
      paraMap.replaceMode === "insert-after" &&
      paraMap.addedParagraph != null &&
      paraMap.insertAfter != null
    ) {
      const hasAdded = paragraphs.some((p) => p.id === paraMap.addedParagraph?.id);
      if (!hasAdded) {
        const idx = paragraphs.findIndex((p) => p.id === paraMap.insertAfter);
        if (idx >= 0) {
          const added: GuidelineParagraph = {
            ...paraMap.addedParagraph,
            prInDiff: { prId, added: true },
          };
          paragraphs = [
            ...paragraphs.slice(0, idx + 1),
            added,
            ...paragraphs.slice(idx + 1),
          ];
        }
      }
    }
    return { ...sec, paragraphs };
  });
}

export function isParagraphInPrTarget(
  paraId: string,
  paraMap: GuidelinePrParagraphMap | null,
): boolean {
  if (paraMap == null) {
    return false;
  }
  return paraMap.targetParaIds.includes(paraId);
}

export function isOpenPrStatus(status: string): boolean {
  return status !== "verified" && status !== "rejected";
}
