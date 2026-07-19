/**
 * Locale helpers for the history router. The site defaults to English (the
 * canonical, unprefixed URL space); Polish is the opt-in alternate served under a
 * ``/pl/`` path prefix. The URL is the single source of truth for the active
 * locale — one URL maps to exactly one language, which keeps prerender/SEO clean
 * and avoids client-side language drift.
 */

export const LOCALES = ["en", "pl"] as const;
export type Locale = (typeof LOCALES)[number];

/** English is the default/fallback and lives at the unprefixed root. */
export const DEFAULT_LOCALE: Locale = "en";

function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

/**
 * Split an optional leading locale segment off a pathname.
 *
 *   "/pl/diseases/fd" → { locale: "pl", pathname: "/diseases/fd" }
 *   "/en/diseases/fd" → { locale: "en", pathname: "/diseases/fd" }  (explicit en canonicalizes away)
 *   "/diseases/fd"    → { locale: "en", pathname: "/diseases/fd" }  (no prefix = English canon)
 *   "/pl"             → { locale: "pl", pathname: "/" }
 */
export function splitLocale(pathname: string): { locale: Locale; pathname: string } {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length > 0 && isLocale(parts[0])) {
    const rest = parts.slice(1).join("/");
    return { locale: parts[0], pathname: rest.length > 0 ? `/${rest}` : "/" };
  }
  return { locale: DEFAULT_LOCALE, pathname: pathname || "/" };
}

/**
 * Prepend the active locale prefix to an unprefixed in-app path. English is the
 * canonical space and gets no prefix; Polish is served under ``/pl``.
 *
 *   ("/diseases/fd", "pl") → "/pl/diseases/fd"
 *   ("/", "pl")            → "/pl"
 *   ("/diseases/fd", "en") → "/diseases/fd"
 */
export function withLocalePrefix(pathname: string, locale: Locale): string {
  const bare = pathname.startsWith("/") ? pathname : `/${pathname}`;
  if (locale === DEFAULT_LOCALE) {
    return bare;
  }
  return bare === "/" ? `/${locale}` : `/${locale}${bare}`;
}

/** Read the active locale from the browser URL (source of truth). Safe on the server (defaults). */
export function readLocaleFromLocation(): Locale {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }
  return splitLocale(window.location.pathname).locale;
}
