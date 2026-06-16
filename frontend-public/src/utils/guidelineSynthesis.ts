import type { SourceDoc } from "../types/sourceDoc";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";

/** Unique cited PMIDs across the whole synthesis, in document order. */
export function orderedSynthesisPmids(synthesis: GuidelineSynthesis): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const section of synthesis.sections) {
    for (const para of section.paragraphs) {
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

/** 1-based citation number for a PMID (its position in `orderedSynthesisPmids`). */
export function citationIndex(orderedPmids: readonly string[], pmid: string): number {
  return orderedPmids.indexOf(pmid) + 1;
}

export function pubmedUrl(pmid: string): string {
  return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
}

/**
 * Short label for a provenance source ("Boyce 2019", "Gun 2024", "GeneReviews").
 * Looks the id up on the disease's source shelf; falls back to a PMID label.
 */
export function shortDocLabel(docs: readonly SourceDoc[], docId: string): string {
  const doc = docs.find((d) => d.id === docId);
  if (doc) {
    if (doc.bookshelf) {
      return "GeneReviews";
    }
    const firstAuthor = doc.authors.split(" ")[0]?.replace(/,$/, "") ?? doc.id;
    return `${firstAuthor} ${doc.year}`;
  }
  if (/^\d{6,}$/.test(docId)) {
    return `PMID ${docId}`;
  }
  return docId;
}
