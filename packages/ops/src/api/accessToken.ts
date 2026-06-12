/**
 * Access-token bridge for the admin API client.
 *
 * Supports both credential modes by design:
 * - **API key** (today): no getter registered → requests fall back to the
 *   `VITE_GENEGUIDELINES_API_KEY` Bearer header / `?api_key=` query.
 * - **Auth0 Bearer**: the admin's auth gate registers an async getter (from
 *   `getAccessTokenSilently`) and keeps a synchronous cached copy. The cache is
 *   needed because SSE URL builders (`agentTraceUrl`, …) are synchronous and
 *   `EventSource` cannot send headers — the token must go in `?access_token=`.
 */

export type AccessTokenGetter = () => Promise<string | null>;

let tokenGetter: AccessTokenGetter | null = null;
let cachedToken: string | null = null;

/** Register the async token source. Pass `null` to clear it (sign-out/unmount). */
export function setAccessTokenGetter(getter: AccessTokenGetter | null): void {
  tokenGetter = getter;
  if (getter == null) {
    cachedToken = null;
  }
}

/** Seed/refresh the synchronous token cache used by SSE URL builders. */
export function setCachedAccessToken(token: string | null): void {
  cachedToken = token;
}

/** Last known token, synchronously. Used where async retrieval is impossible (SSE URLs). */
export function getCachedAccessToken(): string | null {
  return cachedToken;
}

/**
 * Resolve the current access token, refreshing the synchronous cache as a side
 * effect. Returns `null` when no getter is registered (API-key mode) or retrieval
 * fails. Never throws — a missing token degrades to API-key/anonymous behaviour.
 */
export async function getAccessToken(): Promise<string | null> {
  if (tokenGetter == null) {
    return null;
  }
  try {
    const token = await tokenGetter();
    cachedToken = token;
    return token;
  } catch {
    return null;
  }
}
