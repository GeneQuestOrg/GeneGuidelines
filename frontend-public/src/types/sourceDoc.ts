/**
 * One real document on a disease's source shelf. There is rarely a single
 * "official guideline" — we show a curated set of real papers, each linking to
 * its original. The AI synthesis (GL-2) summarizes them together. Mirrors the
 * draft10 `SOURCE_DOCS` shape.
 */
export interface SourceDoc {
  readonly id: string;
  /** Short role on the shelf, e.g. "Base consensus", "Children — update". */
  readonly role: string;
  readonly pmid?: string;
  /** NCBI Bookshelf id (e.g. GeneReviews), when there is no PMID. */
  readonly bookshelf?: string;
  readonly title: string;
  readonly authors: string;
  readonly journal: string;
  /** Number, or a label like "continuously updated" (GeneReviews). */
  readonly year: number | string;
  readonly scope: string;
  readonly covers: readonly string[];
  readonly freeFullText?: boolean;
  readonly isNew?: boolean;
  /** "Updates the X recommendation from the Y consensus" — newer-supersedes-older marker. */
  readonly updatesNote?: string;
}

/** Link to the original document (PubMed for PMIDs, NCBI Bookshelf otherwise). */
export function sourceDocUrl(doc: SourceDoc): string {
  if (doc.pmid) {
    return `https://pubmed.ncbi.nlm.nih.gov/${doc.pmid}/`;
  }
  if (doc.bookshelf) {
    return `https://www.ncbi.nlm.nih.gov/books/${doc.bookshelf}/`;
  }
  return "#";
}
