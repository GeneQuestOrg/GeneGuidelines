import type { Trial } from "../types/trial";

/** Flatten per-disease trial lists into one list, keeping the first occurrence of each nct. */
export function dedupeTrials(lists: readonly (readonly Trial[])[]): readonly Trial[] {
  const seen = new Set<string>();
  const out: Trial[] = [];
  for (const list of lists) {
    for (const trial of list) {
      if (seen.has(trial.nct)) {
        continue;
      }
      seen.add(trial.nct);
      out.push(trial);
    }
  }
  return out;
}
