const EMAIL_KEY_PREFIX = "gg-sub-email-";

export function readStoredSubscriptionEmail(slug: string): string | null {
  try {
    const raw = localStorage.getItem(`${EMAIL_KEY_PREFIX}${slug}`);
    return raw && raw.trim() !== "" ? raw : null;
  } catch {
    return null;
  }
}

export function writeStoredSubscriptionEmail(slug: string, email: string): void {
  localStorage.setItem(`${EMAIL_KEY_PREFIX}${slug}`, email.trim().toLowerCase());
}

export function clearStoredSubscriptionEmail(slug: string): void {
  localStorage.removeItem(`${EMAIL_KEY_PREFIX}${slug}`);
}

export type SubscriptionUiStatus = "none" | "pending" | "confirmed";

export function subscriptionUiFromApiStatus(
  status: "pending" | "confirmed" | null | undefined,
): SubscriptionUiStatus {
  if (status === "confirmed") return "confirmed";
  if (status === "pending") return "pending";
  return "none";
}
