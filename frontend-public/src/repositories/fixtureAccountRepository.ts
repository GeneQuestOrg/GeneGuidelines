import { ApiRequestError } from "../api/client";
import type {
  InviteCreated,
  InvitePreview,
  MeAccount,
  SelectableRole,
  SubmitVerificationInput,
  VerificationRequest,
} from "../types/account";
import type { AccountRepository } from "./types";

/**
 * Offline twin of {@link apiAccountRepository}. Holds a single in-memory account
 * so fixture/Storybook mode can exercise the role-picker, invite, and account-menu
 * flows without a backend. `role` starts `null` to mimic a freshly provisioned user.
 */
let fixtureAccount: MeAccount = {
  id: "fixture-user",
  email: "demo@example.org",
  displayName: "Demo User",
  role: null,
  verified: false,
  orcid: null,
  institution: null,
};

/** In-memory invite store keyed by token, so accept/preview round-trip in fixtures. */
const fixtureInvites = new Map<string, InvitePreview>();

/** In-memory verification requests for the fixture account (newest first). */
let fixtureVerificationRequests: VerificationRequest[] = [];

/** Roles that carry verification — mirrors the backend `VERIFIABLE_ROLES`. */
const VERIFIABLE_ROLES = new Set(["doctor", "researcher"]);

function cleanField(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed != null && trimmed.length > 0 ? trimmed : null;
}

export const fixtureAccountRepository: AccountRepository = {
  async me(): Promise<MeAccount> {
    return fixtureAccount;
  },
  async selectRole(role: SelectableRole): Promise<MeAccount> {
    // Doctors and researchers require verification; a parent needs none, so it
    // is treated as verified for the fixture's pending-state gate.
    fixtureAccount = { ...fixtureAccount, role, verified: role === "parent" };
    fixtureVerificationRequests = [];
    return fixtureAccount;
  },
  async createInvite(input): Promise<InviteCreated> {
    const token = `fixture-${Math.random().toString(36).slice(2, 10)}`;
    fixtureInvites.set(token, {
      intendedRole: "doctor",
      inviterDisplay: fixtureAccount.displayName ?? "A GeneGuidelines member",
      doctorSlug: input?.doctorSlug ?? null,
      expired: false,
      used: false,
    });
    const expiresAt = new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString();
    return { token, urlPath: `/join/${token}`, expiresAt };
  },
  async getInvitePreview(token: string): Promise<InvitePreview> {
    return (
      fixtureInvites.get(token) ?? {
        intendedRole: "doctor",
        inviterDisplay: "A GeneGuidelines member",
        doctorSlug: null,
        expired: false,
        used: false,
      }
    );
  },
  async acceptInvite(token: string): Promise<MeAccount> {
    const preview = fixtureInvites.get(token);
    if (preview != null) {
      fixtureInvites.set(token, { ...preview, used: true });
    }
    fixtureAccount = { ...fixtureAccount, role: "doctor", verified: false };
    return fixtureAccount;
  },
  async orcidEnabled(): Promise<boolean> {
    return false;
  },
  async orcidLoginUrl(): Promise<string> {
    return "https://orcid.org/oauth/authorize";
  },
  async submitVerificationRequest(
    input: SubmitVerificationInput,
  ): Promise<VerificationRequest> {
    // Mirror the backend guards so the offline panel behaves like production.
    if (fixtureAccount.role == null || !VERIFIABLE_ROLES.has(fixtureAccount.role)) {
      throw new ApiRequestError(
        403,
        "Verification is for doctor and researcher accounts.",
      );
    }
    if (fixtureAccount.verified) {
      throw new ApiRequestError(409, "Your account is already verified.");
    }
    if (fixtureVerificationRequests.some((r) => r.status === "pending")) {
      throw new ApiRequestError(
        409,
        "You already have a verification request under review.",
      );
    }
    const orcid = cleanField(input.orcid);
    const licenseNo = cleanField(input.licenseNo);
    const institution = cleanField(input.institution);
    const note = cleanField(input.note);
    if (orcid == null && licenseNo == null && institution == null && note == null) {
      throw new ApiRequestError(
        400,
        "Provide at least one of: ORCID, licence number, institution, or a note.",
      );
    }
    const now = new Date().toISOString();
    const request: VerificationRequest = {
      id: `fixture-vr-${Math.random().toString(36).slice(2, 10)}`,
      userId: fixtureAccount.id,
      role: fixtureAccount.role,
      orcid,
      licenseNo,
      institution,
      note,
      status: "pending",
      createdAt: now,
      updatedAt: now,
      reviewedBy: null,
      reviewedAt: null,
      userEmail: null,
    };
    fixtureVerificationRequests = [request, ...fixtureVerificationRequests];
    return request;
  },
  async myVerificationRequests(): Promise<readonly VerificationRequest[]> {
    return fixtureVerificationRequests;
  },
};
