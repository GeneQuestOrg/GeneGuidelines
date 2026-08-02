/** Where the "support the project" affordances point.
 *
 * A Stripe Payment Link (``VITE_STRIPE_DONATE_URL``) sends people straight to
 * checkout, which is one click instead of three. When it is not configured the
 * link falls back to the foundation's donate page, which always exists and also
 * explains bank transfer and the tax route — so the CTA is never dead.
 */

const DONATE_PAGE_BY_LOCALE: Record<string, string> = {
  pl: "https://genequest.org/donacje",
  en: "https://genequest.org/en/donacje",
};

const DEFAULT_DONATE_PAGE = DONATE_PAGE_BY_LOCALE.en;

/** Foundation donate page for a locale (unknown locales get the English page). */
export function getDonatePageUrl(locale: string): string {
  return DONATE_PAGE_BY_LOCALE[locale] ?? DEFAULT_DONATE_PAGE;
}

/** Stripe Payment Link when configured, otherwise the foundation donate page. */
export function getSupportUrl(locale: string): string {
  const configured = import.meta.env.VITE_STRIPE_DONATE_URL;
  if (typeof configured === "string" && configured.trim().length > 0) {
    return configured.trim();
  }
  return getDonatePageUrl(locale);
}

/** True when support goes straight to card checkout rather than the donate page. */
export function isDirectCheckout(): boolean {
  const configured = import.meta.env.VITE_STRIPE_DONATE_URL;
  return typeof configured === "string" && configured.trim().length > 0;
}
