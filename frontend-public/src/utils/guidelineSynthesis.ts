import type { SourceDoc } from "../types/sourceDoc";
import type {
  GuidelineSynthesis,
  SourceQuote,
  SynthesisParagraph,
} from "../types/guidelineSynthesis";

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
 * The Feature-4 grounded paraphrases attached to a paragraph for one PMID.
 * Empty when the claim was not judged "supported" against that abstract (the
 * backend drops quotes for unsupported/uncertain claims), or on older syntheses
 * that predate the quote-extraction node. A paragraph may carry more than one
 * paraphrase for the same PMID, so this returns a list in emission order.
 */
export function paraphrasesForPmid(
  para: SynthesisParagraph,
  pmid: string,
): readonly SourceQuote[] {
  return (para.quotes ?? []).filter(
    (q) => q.pmid === pmid && q.paraphrase.trim() !== "",
  );
}

/** Whether a paragraph carries at least one grounded paraphrase (Feature 4). */
export function hasParaphrases(para: SynthesisParagraph): boolean {
  return (para.quotes ?? []).some((q) => q.paraphrase.trim() !== "");
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
