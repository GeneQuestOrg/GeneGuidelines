import type {
  InviteCreated,
  InvitePreview,
  MeAccount,
  SelectableRole,
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

export const fixtureAccountRepository: AccountRepository = {
  async me(): Promise<MeAccount> {
    return fixtureAccount;
  },
  async selectRole(role: SelectableRole): Promise<MeAccount> {
    // Doctors require approval; everyone else is considered verified.
    fixtureAccount = { ...fixtureAccount, role, verified: role !== "doctor" };
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
};
