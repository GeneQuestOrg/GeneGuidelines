import DOMPurify from "dompurify";

import { linkifyPmidsInHtml } from "./linkifyPmids";

export type PubmedOutput = {
  disease_name?: string;
  guideline_html?: string;
  key_updates?: string;
  confidence_level?: string;
  evidence_score?: number;
  article_count?: number;
  source_links_html?: string;
};

export function parsePubmedOutput(output: string | null | undefined): PubmedOutput | null {
  if (!output) return null;
  try {
    const parsed = JSON.parse(output) as PubmedOutput;
    if (!parsed || typeof parsed !== "object") return null;
    if (!parsed.disease_name && !parsed.guideline_html && !parsed.key_updates) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function sanitizeGeneratedHtml(html: string | undefined): string {
  if (!html) return "";
  const linked = linkifyPmidsInHtml(html);
  return DOMPurify.sanitize(linked, {
    ALLOWED_TAGS: [
      "p", "br", "b", "strong", "i", "em", "u", "s",
      "h1", "h2", "h3", "h4", "h5", "h6",
      "ul", "ol", "li", "dl", "dt", "dd",
      "table", "thead", "tbody", "tr", "th", "td",
      "a", "span", "div", "blockquote", "pre", "code", "hr", "sup", "sub",
    ],
    ALLOWED_ATTR: ["href", "target", "rel", "class", "id"],
    FORCE_BODY: true,
  });
}
