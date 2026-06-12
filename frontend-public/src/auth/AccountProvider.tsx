import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { isAuth0Configured } from "./authConfig";
import { setAccessTokenGetter } from "./accessToken";
import { AccountContext, type AccountContextValue } from "./accountContext";
import { repositories } from "../repositories";
import type { MeAccount, SelectableRole } from "../types/account";

/**
 * Active account provider, chosen by the env gate:
 * - **auth0** — real Auth0 session, `/me` lookup, role-picker driver.
 * - **disabled** — Auth0 unconfigured: a static signed-out context so the rest
 *   of the app renders exactly as it did before any auth was added.
 */
export function AccountProvider({ children }: { children: ReactNode }) {
  if (isAuth0Configured()) {
    return <Auth0AccountProvider>{children}</Auth0AccountProvider>;
  }
  return <DisabledAccountProvider>{children}</DisabledAccountProvider>;
}

function DisabledAccountProvider({ children }: { children: ReactNode }) {
  const value = useMemo<AccountContextValue>(
    () => ({
      signInAvailable: false,
      loading: false,
      isAuthenticated: false,
      account: null,
      needsRoleSelection: false,
      error: null,
      login: () => undefined,
      logout: () => undefined,
      selectRole: async () => undefined,
      acceptInvite: async () => undefined,
    }),
    [],
  );
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

function Auth0AccountProvider({ children }: { children: ReactNode }) {
  const {
    isAuthenticated,
    isLoading: auth0Loading,
    getAccessTokenSilently,
    loginWithRedirect,
    logout: auth0Logout,
  } = useAuth0();

  const [account, setAccount] = useState<MeAccount | null>(null);
  const [meLoading, setMeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bridge the React-only token getter to the plain API client module.
  useEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenGetter(null);
      return;
    }
    setAccessTokenGetter(() => getAccessTokenSilently());
    return () => setAccessTokenGetter(null);
  }, [isAuthenticated, getAccessTokenSilently]);

  // Load /me once the session is established; clear it on sign-out. All state
  // updates run after an async tick to avoid synchronous setState in the effect.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      if (!isAuthenticated) {
        setAccount(null);
        setError(null);
        return;
      }
      setMeLoading(true);
      setError(null);
      try {
        const me = await repositories().account.me();
        if (!cancelled) {
          setAccount(me);
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load your account.");
        }
      } finally {
        if (!cancelled) {
          setMeLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const login = useCallback(() => {
    void loginWithRedirect();
  }, [loginWithRedirect]);

  const logout = useCallback(() => {
    setAccessTokenGetter(null);
    void auth0Logout({ logoutParams: { returnTo: window.location.origin } });
  }, [auth0Logout]);

  const selectRole = useCallback(async (role: SelectableRole) => {
    const updated = await repositories().account.selectRole(role);
    setAccount(updated);
  }, []);

  const acceptInvite = useCallback(async (token: string) => {
    const updated = await repositories().account.acceptInvite(token);
    setAccount(updated);
  }, []);

  const value = useMemo<AccountContextValue>(
    () => ({
      signInAvailable: true,
      loading: auth0Loading || meLoading,
      isAuthenticated,
      account,
      needsRoleSelection: isAuthenticated && account != null && account.role == null,
      error,
      login,
      logout,
      selectRole,
      acceptInvite,
    }),
    [
      auth0Loading,
      meLoading,
      isAuthenticated,
      account,
      error,
      login,
      logout,
      selectRole,
      acceptInvite,
    ],
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}
