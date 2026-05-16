const PUBMED_ARTICLE_BASE = "https://pubmed.ncbi.nlm.nih.gov";

/** Build a PubMed article URL from a numeric PMID string. */
export function pubmedArticleUrl(pmid: string): string {
  const digits = pmid.replace(/\D/g, "");
  if (digits.length === 0) {
    return PUBMED_ARTICLE_BASE;
  }
  return `${PUBMED_ARTICLE_BASE}/${digits}/`;
}
