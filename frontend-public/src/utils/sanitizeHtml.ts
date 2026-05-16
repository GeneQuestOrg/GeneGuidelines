import createDOMPurify, { type DOMPurify } from "dompurify";

const ALLOWED_TAGS = [
  "p",
  "br",
  "b",
  "strong",
  "i",
  "em",
  "u",
  "h2",
  "h3",
  "h4",
  "ul",
  "ol",
  "li",
  "a",
  "span",
  "blockquote",
  "code",
  "hr",
] as const;

const ALLOWED_ATTR = ["href", "target", "rel", "class", "id"] as const;

let purify: DOMPurify | null = null;

function getPurify(): DOMPurify {
  if (purify == null) {
    purify = createDOMPurify(window);
  }
  return purify;
}

/** Sanitize optional HTML blocks (e.g. future guideline HTML sections). */
export function sanitizeGuidelineHtml(html: string | undefined): string {
  if (html == null || html.trim().length === 0) {
    return "";
  }
  return getPurify().sanitize(html, {
    ALLOWED_TAGS: [...ALLOWED_TAGS],
    ALLOWED_ATTR: [...ALLOWED_ATTR],
    FORCE_BODY: true,
  });
}
