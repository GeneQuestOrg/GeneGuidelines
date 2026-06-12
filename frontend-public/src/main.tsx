import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import "@gene-guidelines/ui/styles/tokens.css";
import "@gene-guidelines/ui/styles/base.css";
import "./index.css";
import App from "./App.tsx";
import { getAuth0Config } from "./auth/authConfig";

/**
 * Env-gated Auth0 wiring. When `VITE_AUTH0_DOMAIN` is unset the app renders with
 * no provider — exactly as before — and the sign-in button stays hidden. When a
 * tenant is configured the SPA uses localStorage cache + refresh tokens (Auth0
 * SPA best practice) and redirects back to the page the user was on.
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
        redirect_uri: window.location.origin + window.location.pathname,
        audience: config.audience.length > 0 ? config.audience : undefined,
      }}
      cacheLocation="localstorage"
      useRefreshTokens={true}
    >
      {children}
    </Auth0Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>{withAuth0(<App />)}</StrictMode>,
);
