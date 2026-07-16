import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import "@gene-guidelines/ui/styles/tokens.css";
import "@gene-guidelines/ui/styles/base.css";
import "./index.css";
import App from "./App.tsx";
import { getAuth0Config } from "./auth/authConfig";

/**
 * Legacy hash-link shim. The public app moved from a hash router (``#/diseases/fd``)
 * to a history router (``/diseases/fd``). Rewrite any inbound ``#/…`` URL — old
 * bookmarks, shared links, and already-sent ``#/join/{token}`` invites — to its
 * path equivalent before React mounts, so the history router parses the real path.
 * Runs only at the app root (``/`` with no query) so a real deep path that happens
 * to carry an in-page fragment is never clobbered; in-page anchors (``#section``)
 * are ignored because they do not start with ``#/``.
 */
function redirectLegacyHash(): void {
  const { hash, pathname, search } = window.location;
  if (hash.startsWith("#/") && pathname === "/" && search === "") {
    window.history.replaceState(null, "", hash.slice(1));
  }
}
redirectLegacyHash();

/**
 * Env-gated Auth0 wiring. When `VITE_AUTH0_DOMAIN` is unset the app renders with
 * no provider — exactly as before — and the sign-in button stays hidden. When a
 * tenant is configured the SPA uses localStorage cache + refresh tokens (Auth0
 * SPA best practice).
 *
 * The callback URL is a FIXED `window.location.origin` (already allow-listed in
 * Auth0), and the route the user started from travels in `appState.returnTo`
 * rather than the `redirect_uri` — this avoids the "Callback URL mismatch" class
 * of failures that per-path redirect URIs cause. `onRedirectCallback` restores
 * that route with `history.replaceState` (stripping `?code&state`) and then
 * dispatches a synthetic `popstate` so the custom history router re-parses the
 * restored URL deterministically (`replaceState` fires no `popstate` of its own).
 */
function withAuth0(children: ReactNode): ReactNode {
  const config = getAuth0Config();
  if (config == null) {
    return children;
  }
  return (
    <Auth0Provider
      domain={config.domain}
      clientId={config.clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: config.audience.length > 0 ? config.audience : undefined,
      }}
      cacheLocation="localstorage"
      useRefreshTokens={true}
      onRedirectCallback={(appState) => {
        const to =
          typeof appState?.returnTo === "string" ? appState.returnTo : "/";
        window.history.replaceState(null, "", to);
        window.dispatchEvent(new PopStateEvent("popstate"));
      }}
    >
      {children}
    </Auth0Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>{withAuth0(<App />)}</StrictMode>,
);
