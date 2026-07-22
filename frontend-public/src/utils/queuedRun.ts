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

/** A translation descriptor — render via `t(`common:${d.key}`, d.params)`. */
export interface QueuedLabel {
  readonly key: string;
  readonly params?: { readonly position: number };
}

/** Human-readable queue notice; position is shown only when known and positive. */
export function queuedLabel(position: number | null | undefined): QueuedLabel {
  if (position != null && position > 0) {
    return { key: "queuedRun.queuedWithPosition", params: { position } };
  }
  return { key: "queuedRun.queuedNoPosition" };
}

/** True when a queued run is held back by the monthly token budget. */
export function isTokenBudgetBlocked(
  blockedReason: string | null | undefined,
): boolean {
  return blockedReason === "token_budget";
}

/**
 * Short badge descriptor for a token-budget-blocked run — render via `t(`common:${d.key}`)`.
 * (Previously hardcoded Polish text regardless of locale; now goes through the same EN/PL
 * translation path as everything else.)
 */
export function blockedBadgeLabel(
  blockedReason: string | null | undefined,
): { readonly key: string } | null {
  if (isTokenBudgetBlocked(blockedReason)) {
    return { key: "queuedRun.tokenBudgetBlocked" };
  }
  return null;
}
