import type { ResearchRun } from "../types/researchRun";

/**
 * One disease's research, aggregated from its individual workstream runs.
 *
 * A single "run research" fans out into several backend runs (guideline +
 * doctor / trials / therapies / foundations finders). The home "Active
 * research" section must show ONE card per disease, not one per worker —
 * otherwise the same disease appears as 3-5 near-identical tiles.
 */
export interface ActiveResearchGroup {
  readonly key: string;
  readonly diseaseSlug: string | null;
  readonly label: string;
  readonly runs: readonly ResearchRun[];
  /** Longest-running workstream = how long the whole research has been going. */
  readonly elapsedSec: number | null;
  /** Set when any workstream is blocked (e.g. token budget). */
  readonly blockedReason: string | null;
  /** Best target for "Watch live" — the guideline (pubmed) run when present. */
  readonly primaryRun: ResearchRun;
  readonly workstreamCount: number;
}

/**
 * Collapse per-workstream runs into one group per disease, preserving arrival
 * order. Runs without a disease slug stay separate (keyed by run id) so nothing
 * is silently merged.
 */
export function groupActiveResearchRuns(
  runs: readonly ResearchRun[],
): ActiveResearchGroup[] {
  const order: string[] = [];
  const byKey = new Map<string, ResearchRun[]>();
  for (const run of runs) {
    const slug = run.diseaseSlug?.trim() ?? "";
    const key = slug !== "" ? `slug:${slug.toLowerCase()}` : `run:${run.runId}`;
    const bucket = byKey.get(key);
    if (bucket) {
      bucket.push(run);
    } else {
      byKey.set(key, [run]);
      order.push(key);
    }
  }
  return order.map((key) => {
    const members = byKey.get(key) as ResearchRun[];
    const primaryRun =
      members.find((r) => r.flowKey === "pubmed") ?? members[0];
    const elapsedSec = members.reduce<number | null>((max, r) => {
      if (r.elapsedSec == null) return max;
      return max == null ? r.elapsedSec : Math.max(max, r.elapsedSec);
    }, null);
    const blocked = members.find((r) => r.blockedReason != null);
    const labelled = members.find((r) => r.label.trim() !== "");
    return {
      key,
      diseaseSlug: primaryRun.diseaseSlug,
      label: (labelled ?? primaryRun).label,
      runs: members,
      elapsedSec,
      blockedReason: blocked?.blockedReason ?? null,
      primaryRun,
      workstreamCount: members.length,
    };
  });
}
