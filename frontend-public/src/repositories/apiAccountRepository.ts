import { apiGet, apiPatchJson, apiPostJson } from "../api/client";
import type {
  AccountRole,
  InviteCreated,
  InvitePreview,
  MeAccount,
  SelectableRole,
  SubmitVerificationInput,
  VerificationRequest,
  VerificationStatus,
} from "../types/account";
import type { AccountRepository } from "./types";

/** Wire shape of `GET /api/account/me` (snake_case, per backend canon). */
interface MeResponse {
  id: string;
  email: string;
  display_name: string | null;
  role: AccountRole | null;
  verified: boolean;
  orcid: string | null;
  institution: string | null;
}

function meFromResponse(row: MeResponse): MeAccount {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    role: row.role,
    verified: row.verified,
    orcid: row.orcid,
    institution: row.institution,
  };
}

/** Wire shape of `POST /api/account/invites`. */
interface InviteCreatedResponse {
  token: string;
  url_path: string;
  expires_at: string;
}

/** Wire shape of `GET /api/account/invites/{token}`. */
interface InvitePreviewResponse {
  intended_role: AccountRole;
  inviter_display: string;
  doctor_slug: string | null;
  expired: boolean;
  used: boolean;
}

/** Wire shape of a verification request (snake_case, per backend canon). */
interface VerificationRequestResponse {
  id: string;
  user_id: string;
  role: AccountRole;
  orcid: string | null;
  license_no: string | null;
  institution: string | null;
  note: string | null;
  status: VerificationStatus;
  created_at: string;
  updated_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  user_email: string | null;
}

function verificationRequestFromResponse(
  row: VerificationRequestResponse,
): VerificationRequest {
  return {
    id: row.id,
    userId: row.user_id,
    role: row.role,
    orcid: row.orcid,
    licenseNo: row.license_no,
    institution: row.institution,
    note: row.note,
    status: row.status,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    reviewedBy: row.reviewed_by,
    reviewedAt: row.reviewed_at,
    userEmail: row.user_email,
  };
}

export const apiAccountRepository: AccountRepository = {
  async me(): Promise<MeAccount> {
    const row = await apiGet<MeResponse>("/api/account/me");
    return meFromResponse(row);
  },
  async selectRole(role: SelectableRole): Promise<MeAccount> {
    const row = await apiPatchJson<MeResponse>("/api/account/me", { role });
    return meFromResponse(row);
  },
  async createInvite(input): Promise<InviteCreated> {
    const row = await apiPostJson<InviteCreatedResponse>("/api/account/invites", {
      email: input?.email ?? null,
      doctor_slug: input?.doctorSlug ?? null,
    });
    return { token: row.token, urlPath: row.url_path, expiresAt: row.expires_at };
  },
  async getInvitePreview(token: string): Promise<InvitePreview> {
    const row = await apiGet<InvitePreviewResponse>(
      `/api/account/invites/${encodeURIComponent(token)}`,
    );
    return {
      intendedRole: row.intended_role,
      inviterDisplay: row.inviter_display,
      doctorSlug: row.doctor_slug,
      expired: row.expired,
      used: row.used,
    };
  },
  async acceptInvite(token: string): Promise<MeAccount> {
    const row = await apiPostJson<MeResponse>(
      `/api/account/invites/${encodeURIComponent(token)}/accept`,
      {},
    );
    return meFromResponse(row);
  },
  async orcidEnabled(): Promise<boolean> {
    const row = await apiGet<{ enabled: boolean }>("/api/account/orcid/status");
    return row.enabled;
  },
  async orcidLoginUrl(): Promise<string> {
    const row = await apiGet<{ authorize_url: string }>("/api/account/orcid/login");
    return row.authorize_url;
  },
  async submitVerificationRequest(
    input: SubmitVerificationInput,
  ): Promise<VerificationRequest> {
    // Send only the four evidence fields (the DTO forbids extra keys); absent
    // fields go as null so the backend applies its own "at least one" rule.
    const row = await apiPostJson<VerificationRequestResponse>(
      "/api/account/verification-requests",
      {
        orcid: input.orcid ?? null,
        license_no: input.licenseNo ?? null,
        institution: input.institution ?? null,
        note: input.note ?? null,
      },
    );
    return verificationRequestFromResponse(row);
  },
  async myVerificationRequests(): Promise<readonly VerificationRequest[]> {
    const rows = await apiGet<VerificationRequestResponse[]>(
      "/api/account/verification-requests/mine",
    );
    return rows.map(verificationRequestFromResponse);
  },
};
