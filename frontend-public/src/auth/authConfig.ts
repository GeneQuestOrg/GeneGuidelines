/**
 * Auth0 configuration, read from `VITE_AUTH0_*` env vars.
 *
 * Env-gating contract: when `VITE_AUTH0_DOMAIN` is unset the public app runs
 * exactly as before — no `Auth0Provider`, no sign-in button — falling back to
 * the localStorage account stub. Auth0 is only wired in once a tenant exists.
 */

export interface Auth0Config {
  readonly domain: string;
  readonly clientId: string;
  /** Audience identifying the backend API (must match AUTH0_AUDIENCE). */
  readonly audience: string;
}

function readTrimmed(value: string | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Resolved Auth0 config, or `null` when `VITE_AUTH0_DOMAIN` is unset (the gate).
 * `clientId`/`audience` are read alongside but the domain is the single switch.
 */
export function getAuth0Config(): Auth0Config | null {
  const domain = readTrimmed(import.meta.env.VITE_AUTH0_DOMAIN);
  if (domain.length === 0) {
    return null;
  }
  return {
    domain,
    clientId: readTrimmed(import.meta.env.VITE_AUTH0_CLIENT_ID),
    audience: readTrimmed(import.meta.env.VITE_AUTH0_AUDIENCE),
  };
}

/** True when an Auth0 tenant is configured for this build. */
export function isAuth0Configured(): boolean {
  return getAuth0Config() != null;
}
