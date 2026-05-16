const DEV_ADMIN_ORIGIN = "http://localhost:5174";
const DEV_LEGACY_OPS_ORIGIN = "http://localhost:5175";

function trimOrigin(value: string): string {
  return value.trim().replace(/\/$/, "");
}

/** Base URL of the admin Vite app (separate origin in dev and on admin subdomain in prod). */
export function getAdminAppUrl(): string | null {
  const configured = import.meta.env.VITE_ADMIN_URL;
  if (typeof configured === "string" && configured.trim().length > 0) {
    return trimOrigin(configured);
  }
  if (import.meta.env.DEV) {
    return DEV_ADMIN_ORIGIN;
  }
  return null;
}

/** Legacy panel — Doctor Finder and other views not yet on admin (dev only). */
export function getLegacyOpsUrl(): string | null {
  const configured = import.meta.env.VITE_LEGACY_OPS_URL;
  if (typeof configured === "string" && configured.trim().length > 0) {
    return trimOrigin(configured);
  }
  if (import.meta.env.DEV) {
    return DEV_LEGACY_OPS_ORIGIN;
  }
  return null;
}

export function isAdminLinkVisible(): boolean {
  return getAdminAppUrl() != null;
}

export function isLegacyOpsLinkVisible(): boolean {
  return import.meta.env.DEV && getLegacyOpsUrl() != null;
}
