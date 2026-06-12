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
