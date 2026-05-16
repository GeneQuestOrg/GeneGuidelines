import type { GuidelineDocument } from "../types/guidelineDocument";
import {
  filterDocumentForReader,
  isParagraphVisibleInReader,
  type GuidelineReaderOptions,
} from "./guidelineDiff";

export { filterDocumentForReader, isParagraphVisibleInReader };
export type { GuidelineReaderOptions };

export function collectCitationPmids(
  doc: GuidelineDocument,
  options?: GuidelineReaderOptions,
): readonly string[] {
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const sec of doc.sections) {
    for (const para of sec.paragraphs) {
      if (!isParagraphVisibleInReader(para, options)) {
        continue;
      }
      for (const pmid of para.citations ?? []) {
        if (!seen.has(pmid)) {
          seen.add(pmid);
          ordered.push(pmid);
        }
      }
    }
  }
  return ordered;
}

export function citationDisplayIndex(
  orderedPmids: readonly string[],
  pmid: string,
): number | null {
  const idx = orderedPmids.indexOf(pmid);
  return idx >= 0 ? idx + 1 : null;
}
