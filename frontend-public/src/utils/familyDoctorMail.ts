import type { SourceDoc } from "../types/sourceDoc";
import { sourceDocUrl } from "../types/sourceDoc";

function shortAuthors(authors: string, etAl: string): string {
  const names = authors.split(",").map((name) => name.trim()).filter(Boolean);
  if (names.length <= 2) {
    return names.join(", ");
  }
  return `${names[0]} ${etAl}`;
}

/** One citation line, the same on paper and in the e-mail: authors (year). Title. Journal. URL — and title (year). when the shelf has no authors (the NCBI compendia). */
export function citationLine(doc: SourceDoc, etAl: string): string {
  const title = doc.title.trim();
  const titleStop = /[.?!]$/.test(title) ? title : `${title}.`;
  const authors = shortAuthors(doc.authors, etAl);
  const lead = authors
    ? `${authors} (${doc.year}). ${titleStop}`
    : `${title.replace(/[.]$/, "")} (${doc.year}).`;
  const journal = doc.journal.trim() ? ` ${doc.journal.trim()}.` : "";
  return `${lead}${journal} ${sourceDocUrl(doc)}`;
}

/** A plain mailto the parent sends from their own mail program: we receive nothing and store nothing. */
export function familyDoctorMailto(
  docs: readonly SourceDoc[],
  subject: string,
  intro: string,
  etAl: string,
): string {
  const body = [intro, ...docs.map((doc) => `- ${citationLine(doc, etAl)}`)].join("\n\n");
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
