/**
 * General-purpose href sanitizer for <a>-rendered buttons / links.
 *
 * Unlike {@link safeBrandHref} — which is deliberately strict because the brand
 * logo must only ever go to an in-app target — this permits the normal set of
 * navigable links a link-button legitimately needs: in-app hash + relative
 * paths, external http(s), and the share schemes `mailto:` / `tel:` / `sms:`.
 * It still rejects the script-injection schemes (`javascript:`, `data:`,
 * `vbscript:`) and protocol-relative (`//host`) URLs, falling back to a safe
 * default.
 */
export function safeAnchorHref(
  href: string | undefined,
  fallback: string,
): string {
  if (href == null) {
    return fallback;
  }
  const trimmed = href.trim();
  if (trimmed.length === 0) {
    return fallback;
  }

  // In-app targets: hash fragments and same-origin absolute paths. Protocol
  // relative ("//host") is explicitly NOT same-origin — reject it below.
  if (trimmed.startsWith("#")) {
    return trimmed;
  }
  if (trimmed.startsWith("//")) {
    return fallback;
  }
  if (trimmed.startsWith("/")) {
    return trimmed;
  }

  // Explicit scheme present → allow only known-safe navigable schemes.
  const schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(trimmed);
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase();
    const allowed = new Set(["http", "https", "mailto", "tel", "sms"]);
    return allowed.has(scheme) ? trimmed : fallback;
  }

  // No scheme and not an in-app anchor: a bare relative reference (e.g.
  // "docs/page"). Safe to navigate.
  return trimmed;
}
