/**
 * What this browser remembers about its own disease subscriptions: a random reference per disease, nothing else.
 *
 * The backend stores only the reference's hash and answers "pending / confirmed" to whoever holds it — never to someone who merely knows an email address (until 2026-11-20 the status endpoint took `?email=`, so anyone could check any address). Browsers that still hold the old `gg-sub-email-<slug>` key have it deleted the first time they read their status.
 */
const REF_KEY_PREFIX = "gg-sub-ref-";
const LEGACY_EMAIL_KEY_PREFIX = "gg-sub-email-";

function forgetLegacyEmail(slug: string): void {
  try {
    localStorage.removeItem(`${LEGACY_EMAIL_KEY_PREFIX}${slug}`);
  } catch {
    // Storage unavailable (private mode): nothing stored, nothing to forget.
  }
}

export function readStoredSubscriptionRef(slug: string): string | null {
  forgetLegacyEmail(slug);
  try {
    const raw = localStorage.getItem(`${REF_KEY_PREFIX}${slug}`);
    return raw && raw.trim() !== "" ? raw : null;
  } catch {
    return null;
  }
}

/** The reference to send with a new subscription: the stored one, or a fresh random one that is stored now. */
export function ensureSubscriptionRef(slug: string): string {
  const existing = readStoredSubscriptionRef(slug);
  if (existing != null) return existing;
  const ref = crypto.randomUUID().replaceAll("-", "");
  try {
    localStorage.setItem(`${REF_KEY_PREFIX}${slug}`, ref);
  } catch {
    // Without storage the subscription still works; this browser just cannot show its status later.
  }
  return ref;
}

export function clearStoredSubscriptionRef(slug: string): void {
  forgetLegacyEmail(slug);
  try {
    localStorage.removeItem(`${REF_KEY_PREFIX}${slug}`);
  } catch {
    // Nothing stored.
  }
}

export type SubscriptionUiStatus = "none" | "pending" | "confirmed";

export function subscriptionUiFromApiStatus(
  status: "pending" | "confirmed" | null | undefined,
): SubscriptionUiStatus {
  if (status === "confirmed") return "confirmed";
  if (status === "pending") return "pending";
  return "none";
}
