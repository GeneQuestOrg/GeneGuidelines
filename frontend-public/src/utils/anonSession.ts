/**
 * Anonymous research session id (RES-1, fair-share queue).
 *
 * The backend caps how many unfinished bootstrap jobs one anonymous browser
 * may hold. To identify "the same browser" without accounts, we mint a uuid
 * once and keep it in localStorage, then send it as the `X-Anon-Session`
 * header on bootstrap calls. Signed-in users send a Bearer token instead and
 * are not capped, so this is only consulted for anonymous traffic.
 *
 * A missing/blocked localStorage (private mode, SSR) degrades to a fresh
 * per-call id rather than throwing — the backend treats unknown ids as their
 * own bucket, which is the safe default.
 */

const STORAGE_KEY = "gg-anon-session";

/** RFC-4122-ish v4 uuid; prefers crypto.randomUUID, falls back for old browsers. */
function generateUuid(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  // Fallback: not cryptographically strong, but only used as a bucket key.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Return the stable anonymous session id for this browser, creating and
 * persisting one on first use. Never throws.
 */
export function getAnonSessionId(): string {
  try {
    if (typeof localStorage === "undefined") {
      return generateUuid();
    }
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing != null && existing.trim().length > 0) {
      return existing;
    }
    const fresh = generateUuid();
    localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    // localStorage blocked (private mode / SSR) — degrade to a transient id.
    return generateUuid();
  }
}

export const ANON_SESSION_STORAGE_KEY = STORAGE_KEY;
