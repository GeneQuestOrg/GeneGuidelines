/**
 * Restrict logo links to safe in-app targets (hash or same-origin relative paths).
 * Rejects javascript:, data:, protocol-relative, and absolute external URLs.
 */
export function safeBrandHref(
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

  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("data:") ||
    lower.startsWith("vbscript:")
  ) {
    return fallback;
  }

  if (trimmed.startsWith("#")) {
    return trimmed;
  }

  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
    return trimmed;
  }

  return fallback;
}
