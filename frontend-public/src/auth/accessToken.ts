/**
 * Module-level Auth0 access-token bridge.
 *
 * `getAccessTokenSilently` lives inside React (the `useAuth0` hook), but the API
 * client is a plain module. The `AccountProvider` registers a token getter here
 * on mount; the client awaits it before each request. When Auth0 is not
 * configured (or the user is signed out) no getter is registered and requests
 * carry no bearer token — preserving the unauthenticated public path.
 */

export type AccessTokenGetter = () => Promise<string | null>;

let tokenGetter: AccessTokenGetter | null = null;

/** Register the active token source. Pass `null` to clear it (sign-out/unmount). */
export function setAccessTokenGetter(getter: AccessTokenGetter | null): void {
  tokenGetter = getter;
}

/**
 * Resolve the current Auth0 access token, or `null` when none is available
 * (Auth0 unconfigured, signed out, or token retrieval failed). Never throws —
 * a missing token must degrade to an unauthenticated request, not an error.
 */
export async function getAccessToken(): Promise<string | null> {
  if (tokenGetter == null) {
    return null;
  }
  try {
    return await tokenGetter();
  } catch {
    return null;
  }
}
