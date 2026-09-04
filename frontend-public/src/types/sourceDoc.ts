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
  /** PMC id when the article is open access — lets us link the readable full text. */
  readonly pmcid?: string;
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

/**
 * Link to the original document, preferring what a reader can actually read.
 *
 * PMC first: when the article is open access, the abstract page is a detour. For
 * the FD/MAS consensus in particular the abstract is the one part that never
 * mentions biopsy, imaging or histopathology — the whole point of following the
 * link. Falls back to PubMed, then NCBI Bookshelf.
 */
export function sourceDocUrl(doc: SourceDoc): string {
  if (doc.pmcid) {
    return `https://pmc.ncbi.nlm.nih.gov/articles/${doc.pmcid}/`;
  }
  if (doc.pmid) {
    return `https://pubmed.ncbi.nlm.nih.gov/${doc.pmid}/`;
  }
  if (doc.bookshelf) {
    return `https://www.ncbi.nlm.nih.gov/books/${doc.bookshelf}/`;
  }
  return "#";
}
