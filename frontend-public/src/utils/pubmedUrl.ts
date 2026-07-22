const PUBMED_ARTICLE_BASE = "https://pubmed.ncbi.nlm.nih.gov";

/** Build a PubMed article URL from a numeric PMID string. */
export function pubmedArticleUrl(pmid: string): string {
  const digits = pmid.replace(/\D/g, "");
  if (digits.length === 0) {
    return PUBMED_ARTICLE_BASE;
  }
  return `${PUBMED_ARTICLE_BASE}/${digits}/`;
}

/** A link to a doctor's full publication record (the "whole shelf" we don't mirror). */
export interface PublicationRecordLink {
  readonly url: string;
  readonly label: string;
}

/**
 * Resolve the most authoritative external "whole shelf" for an author.
 * ORCID-identified doctors (slug `orcid:<id>`) get their canonical ORCID works
 * record; everyone else gets a PubMed author-name search (clearly labelled, so
 * the name-disambiguation caveat is implicit).
 *
 * `label` is a bare i18n key, not display text — callers must translate it via
 * `t(`common:${recordLink.label}`)` (or `t(recordLink.label)` when already scoped to "common").
 */
export function publicationRecordLink(slug: string, name: string): PublicationRecordLink | null {
  const orcidMatch = /^orcid:([0-9x-]{9,})$/i.exec(slug.trim());
  if (orcidMatch) {
    return {
      url: `https://orcid.org/${orcidMatch[1].toUpperCase()}`,
      label: "pubmedUrl.orcidRecordLabel",
    };
  }
  const cleanName = name.replace(/\b(prof|professor|dr|doctor|md|phd|msc|mgr)\.?\s+/gi, "").trim();
  if (cleanName.length === 0) {
    return null;
  }
  return {
    url: `${PUBMED_ARTICLE_BASE}/?term=${encodeURIComponent(`${cleanName}[Author]`)}`,
    label: "pubmedUrl.searchAuthorLabel",
  };
}
