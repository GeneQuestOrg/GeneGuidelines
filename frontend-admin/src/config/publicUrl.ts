const DEV_PUBLIC_ORIGIN = "http://localhost:5173";

function trimOrigin(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export function getPublicAppUrl(): string | null {
  const configured = import.meta.env.VITE_PUBLIC_URL;
  if (typeof configured === "string" && configured.trim().length > 0) {
    return trimOrigin(configured);
  }
  if (import.meta.env.DEV) {
    return DEV_PUBLIC_ORIGIN;
  }
  return null;
}

export function isPublicLinkVisible(): boolean {
  return getPublicAppUrl() != null;
}
