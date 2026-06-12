import { createContext, useContext } from "react";
import type { MeAccount, SelectableRole } from "../types/account";

/**
 * Unified account context value. Two runtime modes, decided once by the
 * `VITE_AUTH0_DOMAIN` gate (see {@link ../auth/AccountProvider}):
 * Auth0 (real session) and disabled (anonymous, as today).
 */
export interface AccountContextValue {
  /** Whether an Auth0 tenant is configured (controls the sign-in button). */
  readonly signInAvailable: boolean;
  /** True while Auth0 resolves the session or `/me` is loading. */
  readonly loading: boolean;
  readonly isAuthenticated: boolean;
  readonly account: MeAccount | null;
  /** True when authenticated but no role chosen yet — show the RolePicker. */
  readonly needsRoleSelection: boolean;
  readonly error: string | null;
  login: () => void;
  logout: () => void;
  selectRole: (role: SelectableRole) => Promise<void>;
}

export const AccountContext = createContext<AccountContextValue | null>(null);

export function useAccountContext(): AccountContextValue {
  const ctx = useContext(AccountContext);
  if (ctx == null) {
    throw new Error("useAccountContext must be used within an AccountProvider");
  }
  return ctx;
}
