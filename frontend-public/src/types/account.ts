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
  /** Frontend landing path; rendered as `#${urlPath}` → `#/join/{token}`. */
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

/** Lifecycle of a manual verification request (mirrors the backend enum). */
export type VerificationStatus = "pending" | "approved" | "rejected";

/**
 * Evidence a doctor / researcher submits for manual review
 * (`POST /api/account/verification-requests`). Every field is optional, but the
 * backend rejects a wholly empty body (400): at least one piece of evidence is
 * required. `verified` is deliberately absent — the client can never set it.
 */
export interface SubmitVerificationInput {
  readonly orcid?: string;
  readonly licenseNo?: string;
  readonly institution?: string;
  readonly note?: string;
}

/**
 * A manual verification request as seen by its owner
 * (`GET /api/account/verification-requests/mine`). `reviewedBy` / `reviewedAt`
 * are set once a superadmin has decided; `userEmail` is only filled on the
 * superadmin queue and stays `null` on the self-serve path.
 */
export interface VerificationRequest {
  readonly id: string;
  readonly userId: string;
  readonly role: AccountRole;
  readonly orcid: string | null;
  readonly licenseNo: string | null;
  readonly institution: string | null;
  readonly note: string | null;
  readonly status: VerificationStatus;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly reviewedBy: string | null;
  readonly reviewedAt: string | null;
  readonly userEmail: string | null;
}
