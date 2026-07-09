import type { AccountRole, SelectableRole } from "../types/account";

export interface RoleOption {
  readonly value: SelectableRole;
  readonly label: string;
  readonly description: string;
}

/** The three self-selectable roles, in display order. `superadmin` is excluded. */
export const ROLE_OPTIONS: readonly RoleOption[] = [
  {
    value: "parent",
    label: "Patient / Family",
    description: "Follow a disease and get plain-language guidance for your family.",
  },
  {
    value: "doctor",
    label: "Doctor / Clinician",
    description: "Review and contribute to living clinical guidelines (verification required).",
  },
  {
    value: "researcher",
    label: "Researcher",
    description:
      "Track the evidence base and contribute to research workstreams (verification required).",
  },
] as const;

/**
 * Whether the role picker should be shown: authenticated, account loaded, and
 * no role chosen yet. The one-time selection lives server-side (PATCH 409s on
 * repeat), so this is purely a UI gate.
 */
export function shouldShowRolePicker(
  isAuthenticated: boolean,
  role: AccountRole | null,
): boolean {
  return isAuthenticated && role === null;
}

/** Doctors and researchers await verification (ORCID or admin approval) after picking a role. */
export function isPendingVerification(
  role: AccountRole | null,
  verified: boolean,
): boolean {
  return (role === "doctor" || role === "researcher") && !verified;
}
