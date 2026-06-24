/**
 * Fair-share queue state helpers (RES-1).
 *
 * Pure derivations used by ResearchRunView so the "Queued — position N"
 * messaging is unit-testable without rendering the component.
 */

import type { AgentRunPayloadV1 } from "../api/guidelineRun";

/** True when the run is admitted but waiting for a worker slot. */
export function isQueued(run: Pick<AgentRunPayloadV1, "done" | "status"> | null): boolean {
  if (run == null) {
    return false;
  }
  return !run.done && run.status === "queued";
}

/** Human-readable queue notice; position is shown only when known and positive. */
export function queuedLabel(position: number | null | undefined): string {
  if (position != null && position > 0) {
    return `Queued — position ${position}. Your run will start as soon as a slot frees up.`;
  }
  return "Queued — your run will start as soon as a slot frees up.";
}

/** True when a queued run is held back by the monthly token budget. */
export function isTokenBudgetBlocked(
  blockedReason: string | null | undefined,
): boolean {
  return blockedReason === "token_budget";
}

/** Short badge text for a token-budget-blocked run (Polish, per draft10 copy). */
export function blockedBadgeLabel(
  blockedReason: string | null | undefined,
): string | null {
  if (isTokenBudgetBlocked(blockedReason)) {
    return "Czeka — budżet tokenów";
  }
  return null;
}
