/** Wall-clock helpers for research run pages (server start vs page mount). */

export function earliestResearchStartedAtIso(
  sources: ReadonlyArray<string | null | undefined>,
): string | null {
  let bestMs: number | null = null;
  let bestIso: string | null = null;
  for (const raw of sources) {
    if (typeof raw !== "string" || !raw.trim()) {
      continue;
    }
    const ms = Date.parse(raw);
    if (Number.isNaN(ms)) {
      continue;
    }
    if (bestMs == null || ms < bestMs) {
      bestMs = ms;
      bestIso = raw;
    }
  }
  return bestIso;
}

export function researchElapsedSecFromStartedAt(
  startedAtIso: string | null | undefined,
  nowMs: number,
  fallbackSec: number,
): number {
  if (typeof startedAtIso === "string" && startedAtIso.trim()) {
    const started = Date.parse(startedAtIso);
    if (!Number.isNaN(started)) {
      return Math.max(0, Math.floor((nowMs - started) / 1000));
    }
  }
  return Math.max(0, fallbackSec);
}
