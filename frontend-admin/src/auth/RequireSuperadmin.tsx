import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  fetchMe,
  setAccessTokenGetter,
  setCachedAccessToken,
  type MeResponse,
} from "@gene-guidelines/ops";
import { isAuth0Configured } from "./authConfig";
import "./require-superadmin.css";

/**
 * Whole-app auth gate. Env-gated:
 * - Auth0 unconfigured → render children unchanged (API-key mode, as today).
 * - Auth0 configured → require login + `role === "superadmin"` from `/me`,
 *   otherwise a clear "no access" screen with sign-out.
 */
export function RequireSuperadmin({ children }: { children: ReactNode }) {
  if (!isAuth0Configured()) {
    return <>{children}</>;
  }
  return <Auth0Gate>{children}</Auth0Gate>;
}

type GateState =
  | { kind: "loading" }
  | { kind: "denied"; reason: string }
  | { kind: "allowed" };

function Auth0Gate({ children }: { children: ReactNode }) {
  const {
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
    loginWithRedirect,
    logout,
  } = useAuth0();
  const [state, setState] = useState<GateState>({ kind: "loading" });

  // Bridge the token to the ops API client (Bearer headers + SSE cache).
  useEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenGetter(null);
      return;
    }
    setAccessTokenGetter(() => getAccessTokenSilently());
    return () => setAccessTokenGetter(null);
  }, [isAuthenticated, getAccessTokenSilently]);

  // Trigger login automatically once Auth0 finishes loading and finds no session.
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      void loginWithRedirect();
    }
  }, [isLoading, isAuthenticated, loginWithRedirect]);

  // Once authenticated, prime the SSE token cache and check the role. All state
  // updates run after an async tick to avoid synchronous setState in the effect.
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      setState({ kind: "loading" });
      try {
        const token = await getAccessTokenSilently();
        setCachedAccessToken(token);
        const me: MeResponse = await fetchMe();
        if (cancelled) {
          return;
        }
        if (me.role === "superadmin") {
          setState({ kind: "allowed" });
        } else {
          setState({
            kind: "denied",
            reason: "Your account does not have operations access.",
          });
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setState({
            kind: "denied",
            reason: e instanceof Error ? e.message : "Could not verify your access.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, getAccessTokenSilently]);

  const signOut = useCallback(() => {
    setAccessTokenGetter(null);
    void logout({ logoutParams: { returnTo: window.location.origin } });
  }, [logout]);

  if (isLoading || !isAuthenticated || state.kind === "loading") {
    return (
      <div className="auth-gate">
        <p className="auth-gate__msg">Checking access…</p>
      </div>
    );
  }

  if (state.kind === "denied") {
    return (
      <div className="auth-gate">
        <div className="auth-gate__card">
          <h1 className="auth-gate__title">No access</h1>
          <p className="auth-gate__reason">{state.reason}</p>
          <p className="auth-gate__hint">
            The admin panel is restricted to operations accounts. If this is a
            mistake, contact a superadmin.
          </p>
          <button type="button" className="auth-gate__signout" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
