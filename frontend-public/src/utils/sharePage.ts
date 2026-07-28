/**
 * Client-side helpers for sharing the current guideline page with a doctor.
 *
 * These are deliberately pure and locale-agnostic: they only build URLs. The
 * user-facing message / subject / body text is composed in the component via
 * react-i18next so it follows the active locale (EN + PL).
 */

/** Current page URL for sharing (hash-router aware). */
export function getCurrentPageUrl(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.href;
}

/** A WhatsApp "click to chat" share link carrying a pre-filled message. */
export function buildWhatsAppShareUrl(message: string): string {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}

/** A mailto: link with a pre-filled subject and body. */
export function buildEmailShareUrl(subject: string, body: string): string {
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
