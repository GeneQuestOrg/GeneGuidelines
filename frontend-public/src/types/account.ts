/** Account domain types mirroring the backend `/api/account/me` contract. */

/** Roles a user can hold. `superadmin` is granted server-side, never self-selected. */
export type AccountRole = "parent" | "doctor" | "researcher" | "superadmin";

/** Roles a user may pick once after first login. */
export type SelectableRole = "parent" | "doctor" | "researcher";

/**
 * The signed-in user's own account (payload of `GET /api/account/me`).
 * `role` is `null` until the one-time role selection is made.
 */
export interface MeAccount {
  readonly id: string;
  readonly email: string;
  readonly displayName: string | null;
  readonly role: AccountRole | null;
  readonly verified: boolean;
  readonly orcid: string | null;
  readonly institution: string | null;
}

/** Result of minting a doctor invite (`POST /api/account/invites`). */
export interface InviteCreated {
  readonly token: string;
  /** Frontend landing path (history-router form), e.g. `/join/{token}`. */
  readonly urlPath: string;
  readonly expiresAt: string;
}

/** Public preview of an invite (`GET /api/account/invites/{token}`), no PII. */
export interface InvitePreview {
  readonly intendedRole: AccountRole;
  /** Display name or masked email of who sent the invite. */
  readonly inviterDisplay: string;
  readonly doctorSlug: string | null;
  readonly expired: boolean;
  readonly used: boolean;
}
