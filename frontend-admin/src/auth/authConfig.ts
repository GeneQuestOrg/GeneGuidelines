/**
 * Auth0 configuration for the admin app, read from `VITE_AUTH0_*`.
 *
 * Env-gating contract: when `VITE_AUTH0_DOMAIN` is unset the admin app keeps its
 * current behaviour (API-key mode via `VITE_GENEGUIDELINES_API_KEY`) and renders
 * no auth gate. When configured, the whole app sits behind `RequireSuperadmin`.
 */

export interface Auth0Config {
  readonly domain: string;
  readonly clientId: string;
  readonly audience: string;
}

function readTrimmed(value: string | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Resolved Auth0 config, or `null` when `VITE_AUTH0_DOMAIN` is unset (the gate). */
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

export function isAuth0Configured(): boolean {
  return getAuth0Config() != null;
}
