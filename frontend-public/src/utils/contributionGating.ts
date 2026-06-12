/**
 * Env-gating decisions for the DOC-5 parent write-path, derived from the unified
 * account context. Pulled out of the views so the gate is unit-testable without
 * jsdom/providers (STYLE: derived logic lives in utils).
 *
 * The single switch is `signInAvailable` (true only when VITE_AUTH0_DOMAIN is
 * set). When it is false, the write-path is dormant and the UI behaves exactly
 * as it did before any auth existed (localStorage echo, no sign-in CTA).
 */

export interface ContributionAccountState {
  readonly signInAvailable: boolean;
  readonly isAuthenticated: boolean;
  readonly role: string | null | undefined;
}

/** Roles allowed to contribute through the public UI. */
export function isContributorRole(role: string | null | undefined): boolean {
  return role === "parent" || role === "superadmin";
}

/** What the "Recommend a doctor we're missing" entry should render. */
export type AddDoctorCtaMode = "hidden" | "sign-in" | "open-modal";

export function addDoctorCtaMode(
  account: ContributionAccountState,
): AddDoctorCtaMode {
  if (!account.signInAvailable) {
    return "hidden";
  }
  if (account.isAuthenticated && isContributorRole(account.role)) {
    return "open-modal";
  }
  if (!account.isAuthenticated) {
    return "sign-in";
  }
  // Signed-in but not a contributor role (e.g. researcher): no entry.
  return "hidden";
}

/**
 * AddDoctorModal submit state machine. Kept pure so the transitions are testable
 * without rendering: editing → submitting → (submitted | error), and the error
 * state returns to editing on the next submit.
 */
export type SubmitState =
  | { readonly status: "editing" }
  | { readonly status: "submitting" }
  | { readonly status: "submitted"; readonly possibleDuplicate: boolean }
  | { readonly status: "error"; readonly message: string };

export type SubmitEvent =
  | { readonly type: "submit" }
  | { readonly type: "success"; readonly possibleDuplicate: boolean }
  | { readonly type: "failure"; readonly message: string };

export function submitReducer(state: SubmitState, event: SubmitEvent): SubmitState {
  switch (event.type) {
    case "submit":
      // A new submit from editing/error transitions to submitting; ignore a
      // duplicate submit while already in flight or after success.
      if (state.status === "submitting" || state.status === "submitted") {
        return state;
      }
      return { status: "submitting" };
    case "success":
      if (state.status !== "submitting") {
        return state;
      }
      return { status: "submitted", possibleDuplicate: event.possibleDuplicate };
    case "failure":
      if (state.status !== "submitting") {
        return state;
      }
      return { status: "error", message: event.message };
    default:
      return state;
  }
}

/** What the recommendation form should render. */
export type RecFormMode = "local" | "sign-in" | "not-allowed" | "post";

export function recFormMode(account: ContributionAccountState): RecFormMode {
  // Auth0 unset → today's behaviour: localStorage echo, no sign-in needed.
  if (!account.signInAvailable) {
    return "local";
  }
  if (account.isAuthenticated && isContributorRole(account.role)) {
    return "post";
  }
  if (!account.isAuthenticated) {
    return "sign-in";
  }
  return "not-allowed";
}
