/* State machine for the Kaggle juror banner.
   Three states:
     • ribbon    — full-width single line above the header (default).
     • expanded  — full juror panel (snapshot, video, writeup, repo, 3-step guide).
     • pill      — small floating badge in the top-right corner.

   Resolution order on mount:
     1. An explicit user action stored in localStorage wins over everything —
        it is a deliberate choice and must outlast the ?from=kaggle link.
     2. Otherwise, if judges arrived via ?from=kaggle (this visit, or remembered
        for the session) → expanded.
     3. Otherwise → ribbon.

   Kept as a pure module so the machine can be unit-tested without React/DOM. */

export type BannerState = "ribbon" | "expanded" | "pill";

/** localStorage key. Bumped to v3: the state set changed (ribbon is new). */
export const JB_STATE_KEY = "gg-judges-banner-state-v3";

/** sessionStorage key: remembers a ?from=kaggle expansion for the session so
    plain hash navigation does not collapse the panel back to the ribbon. */
export const JB_SESSION_FROM_KAGGLE_KEY = "gg-judges-banner-from-kaggle";

export function isBannerState(value: unknown): value is BannerState {
  return value === "ribbon" || value === "expanded" || value === "pill";
}

export interface ResolveInitialStateInput {
  /** Persisted explicit user action, if any (localStorage). */
  stored: string | null;
  /** `?from=kaggle` present on this visit. */
  fromKaggle: boolean;
  /** A ?from=kaggle expansion was remembered earlier this session. */
  sessionFromKaggle: boolean;
}

/** Whether a fresh ?from=kaggle arrival should be remembered for the session.
    Only when no explicit user action is already stored — a stored action wins,
    so there is no point remembering the param it would override anyway. */
export function shouldRememberKaggleSession(stored: string | null, fromKaggle: boolean): boolean {
  return fromKaggle && !isBannerState(stored);
}

/** Pure resolver for the banner's initial state. */
export function resolveInitialState({
  stored,
  fromKaggle,
  sessionFromKaggle,
}: ResolveInitialStateInput): BannerState {
  /* User actions persist and take precedence over the link param. */
  if (isBannerState(stored)) {
    return stored;
  }
  if (fromKaggle || sessionFromKaggle) {
    return "expanded";
  }
  return "ribbon";
}
