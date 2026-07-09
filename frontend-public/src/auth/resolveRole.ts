import type { AudienceView } from "../router/types";
import type { MeAccount } from "../types/account";
import type { ViewAsRole } from "./viewAs";

/**
 * The viewer's effective role, resolved from the signed-in account — not a
 * free toggle. Anonymous visitors get the parent projection; the clinician /
 * researcher surfaces live behind authentication (chat 019: a public toggle
 * leaked clinician machinery to everyone).
 */
export type ViewRole =
  | "anon"
  | "parent"
  | "doctor"
  | "doctor-unverified"
  | "researcher"
  | "researcher-unverified";

/** Dev/demo override (Tweaks panel only). `"auto"` = resolve from auth. */
export type PreviewRole = "auto" | ViewRole;

export const PREVIEW_ROLES: readonly PreviewRole[] = [
  "auto",
  "anon",
  "parent",
  "doctor",
  "doctor-unverified",
  "researcher",
  "researcher-unverified",
] as const;

export function isPreviewRole(value: unknown): value is PreviewRole {
  return typeof value === "string" && (PREVIEW_ROLES as readonly string[]).includes(value);
}

/**
 * Resolve the viewing role. In dev, a non-`"auto"` `previewRole` overrides the
 * account (Tweaks panel, dev-only); in production builds the override is
 * ignored and the role comes strictly from the authenticated account.
 */
export function resolveRole(
  account: MeAccount | null,
  previewRole: PreviewRole,
  isAuthenticated: boolean,
  viewAsRole: ViewAsRole = "auto",
): ViewRole {
  if (account?.role === "superadmin" && viewAsRole !== "auto") {
    return viewAsRole;
  }
  if (import.meta.env.DEV && previewRole !== "auto") {
    return previewRole;
  }
  if (!isAuthenticated || account == null) {
    return "anon";
  }
  switch (account.role) {
    case "doctor":
      return account.verified ? "doctor" : "doctor-unverified";
    case "researcher":
      return account.verified ? "researcher" : "researcher-unverified";
    case "superadmin":
      return "researcher";
    case "parent":
    default:
      // includes role === null (pre role-selection): treat as parent projection
      return "parent";
  }
}

/** Clinician-facing surfaces (full text, suggestions, source trail). Only VERIFIED
 *  clinicians qualify — an unverified doctor/researcher stays on the parent projection
 *  until an admin (or ORCID) verifies them, so they cannot see or rate the expert layer. */
export function isClinicianView(role: ViewRole): boolean {
  return role === "doctor" || role === "researcher";
}

export function isParentSide(role: ViewRole): boolean {
  // Everything that is not a verified-clinician surface renders the parent projection —
  // anon, parent, and unverified doctor/researcher.
  return !isClinicianView(role);
}

/** Only verified clinicians produce ranking signal (D5); unverified can read. */
export function canRate(role: ViewRole): boolean {
  return role === "doctor" || role === "researcher";
}

/** Map the role onto the two-value audience the copy/layout machinery expects. */
export function audienceForRole(role: ViewRole): AudienceView {
  return isClinicianView(role) ? "doctor" : "parent";
}
