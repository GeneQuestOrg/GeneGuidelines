import { apiGet, apiPatchJson } from "../api/client";
import type { AccountRole, MeAccount, SelectableRole } from "../types/account";
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

export const apiAccountRepository: AccountRepository = {
  async me(): Promise<MeAccount> {
    const row = await apiGet<MeResponse>("/api/account/me");
    return meFromResponse(row);
  },
  async selectRole(role: SelectableRole): Promise<MeAccount> {
    const row = await apiPatchJson<MeResponse>("/api/account/me", { role });
    return meFromResponse(row);
  },
};
