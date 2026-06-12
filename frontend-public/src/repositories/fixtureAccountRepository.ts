import type { MeAccount, SelectableRole } from "../types/account";
import type { AccountRepository } from "./types";

/**
 * Offline twin of {@link apiAccountRepository}. Holds a single in-memory account
 * so fixture/Storybook mode can exercise the role-picker and account-menu flows
 * without a backend. `role` starts `null` to mimic a freshly provisioned user.
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

export const fixtureAccountRepository: AccountRepository = {
  async me(): Promise<MeAccount> {
    return fixtureAccount;
  },
  async selectRole(role: SelectableRole): Promise<MeAccount> {
    // Doctors require approval; everyone else is considered verified.
    fixtureAccount = { ...fixtureAccount, role, verified: role !== "doctor" };
    return fixtureAccount;
  },
};
