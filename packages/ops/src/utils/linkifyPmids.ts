import { pubmedArticleUrl } from "./pubmedUrl";

const HTML_CHUNK = /(<[^>]+>)|([^<]+)/g;
const PMID_IN_TEXT = /\b(PMID[:\s]*)(\d{7,9})\b/gi;

function linkifyPlainTextSegment(text: string): string {
  return text.replace(PMID_IN_TEXT, (_match, prefix: string, pmid: string) => {
    const href = pubmedArticleUrl(pmid);
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${prefix}${pmid}</a>`;
  });
}

/** Turn "PMID 31196103" in HTML text nodes into PubMed links (skips existing tags). */
export function linkifyPmidsInHtml(html: string): string {
  return html.replace(HTML_CHUNK, (chunk, tag: string | undefined, text: string | undefined) => {
    if (tag) {
      return tag;
    }
    if (text) {
      return linkifyPlainTextSegment(text);
    }
    return chunk;
  });
}
