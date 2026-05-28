export function getClerkPublishableKey(): string | undefined {
  const raw = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
  if (typeof raw === "string" && raw.trim().length > 0) {
    return raw.trim();
  }
  return undefined;
}

export function isClerkEnabled(): boolean {
  return getClerkPublishableKey() != null;
}
