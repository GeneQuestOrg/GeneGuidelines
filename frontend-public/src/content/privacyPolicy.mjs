/**
 * The privacy policy page (/privacy, /pl/privacy): the one version date and the small inline markup its text uses.
 *
 * Plain JavaScript on purpose: the React view (src/views/PrivacyView.tsx) and the build-time prerender (prerender/pages.mjs, run by Node without a TypeScript step) both import this file, so the date and the way the text is marked up cannot drift between what a browser shows and what a reader without JavaScript gets. Types live in privacyPolicy.d.mts.
 *
 * The text itself is in src/locales/{pl,en}/privacy.json, copied verbatim from the approved policy (Polish binding, English a translation). Only the publication date is filled in here.
 */

/** The policy's publication date, ISO. Change it here, and only here, when a new version is published. */
export const PRIVACY_POLICY_VERSION = "2026-11-21";

/** The page's in-app path (unprefixed; the Polish page is /pl/privacy). */
export const PRIVACY_PATH = "/privacy";

/** `/privacy` or `/pl/privacy`, optionally pointing at one section (`#clinicians`). */
export function privacyPolicyHref(locale, sectionId) {
  const path = locale === "pl" ? `/pl${PRIVACY_PATH}` : PRIVACY_PATH;
  return sectionId ? `${path}#${sectionId}` : path;
}

/** The version date as a reader of that language writes it: "21 listopada 2026", "21 November 2026". UTC, so no time zone can move it to the day before. */
export function formatPolicyVersion(locale) {
  const date = new Date(`${PRIVACY_POLICY_VERSION}T00:00:00Z`);
  return new Intl.DateTimeFormat(locale === "pl" ? "pl-PL" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** Where the date goes in the policy's "Version: …" line. */
export const VERSION_PLACEHOLDER = "{{date}}";

const INLINE = /\*\*(.+?)\*\*|`([^`]+)`|([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)/g;

/**
 * Split one string of the policy into text, **bold**, `code` (browser storage key names) and email addresses (rendered as mailto links). That is all the markup the approved text uses; anything else stays plain text.
 */
export function inlineTokens(text) {
  const tokens = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > last) {
      tokens.push({ kind: "text", value: text.slice(last, match.index) });
    }
    if (match[1] !== undefined) {
      tokens.push({ kind: "bold", value: match[1] });
    } else if (match[2] !== undefined) {
      tokens.push({ kind: "code", value: match[2] });
    } else {
      tokens.push({ kind: "email", value: match[3] });
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    tokens.push({ kind: "text", value: text.slice(last) });
  }
  return tokens;
}
