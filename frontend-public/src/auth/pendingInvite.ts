/**
 * Bridge for an invite token across the Auth0 redirect round-trip.
 *
 * A visitor on `#/join/{token}` who is not signed in clicks "Accept" → we stash
 * the token here, kick off `loginWithRedirect`, and Auth0 navigates away and
 * back. On return the JoinView reads the token and auto-accepts it. The global
 * RolePicker is suppressed while a token is pending so an invited doctor is not
 * asked to pick a role they are about to receive from the invite.
 *
 * sessionStorage (not localStorage): the intent is scoped to this browser tab /
 * session and must not leak into unrelated future visits.
 */

const KEY = "gg.pendingInviteToken";

export function setPendingInviteToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // Private-mode / storage-disabled: the in-page flow still works without it.
  }
}

export function getPendingInviteToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearPendingInviteToken(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
