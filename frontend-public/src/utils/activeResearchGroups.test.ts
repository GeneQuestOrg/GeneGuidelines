import { describe, expect, it } from "vitest";
import { groupActiveResearchRuns } from "./activeResearchGroups";
import type { ResearchRun } from "../types/researchRun";

function run(partial: Partial<ResearchRun> & { runId: string }): ResearchRun {
  return {
    runId: partial.runId,
    diseaseSlug: partial.diseaseSlug ?? null,
    flowKey: partial.flowKey ?? "pubmed",
    label: partial.label ?? "Some disease",
    startedAt: partial.startedAt ?? null,
    elapsedSec: partial.elapsedSec ?? null,
    blockedReason: partial.blockedReason ?? null,
  };
}

describe("groupActiveResearchRuns", () => {
  it("collapses a fan-out into one group per disease", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "gl-1", diseaseSlug: "stargardt", flowKey: "pubmed", label: "Stargardt", elapsedSec: 120 }),
      run({ runId: "df-1", diseaseSlug: "stargardt", flowKey: "doctor_finder", label: "Stargardt", elapsedSec: 300 }),
      run({ runId: "tf-1", diseaseSlug: "stargardt", flowKey: "trials_finder", label: "Stargardt", elapsedSec: 60 }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].workstreamCount).toBe(3);
    expect(groups[0].label).toBe("Stargardt");
    expect(groups[0].elapsedSec).toBe(300); // longest workstream
    expect(groups[0].primaryRun.flowKey).toBe("pubmed"); // guideline preferred for "Watch live"
  });

  it("keeps distinct diseases as separate groups, in arrival order", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "a", diseaseSlug: "fop", flowKey: "doctor_finder" }),
      run({ runId: "b", diseaseSlug: "stargardt", flowKey: "pubmed" }),
    ]);
    expect(groups.map((g) => g.diseaseSlug)).toEqual(["fop", "stargardt"]);
  });

  it("groups case-insensitively by slug", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "a", diseaseSlug: "FOP" }),
      run({ runId: "b", diseaseSlug: "fop" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].workstreamCount).toBe(2);
  });

  it("does not merge runs that have no disease slug", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "x", diseaseSlug: null }),
      run({ runId: "y", diseaseSlug: null }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("surfaces a blocked reason from any workstream", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "gl", diseaseSlug: "fop", flowKey: "pubmed", blockedReason: null }),
      run({ runId: "df", diseaseSlug: "fop", flowKey: "doctor_finder", blockedReason: "token_budget" }),
    ]);
    expect(groups[0].blockedReason).toBe("token_budget");
  });

  it("falls back to the first run when there is no pubmed workstream", () => {
    const groups = groupActiveResearchRuns([
      run({ runId: "df", diseaseSlug: "fop", flowKey: "doctor_finder" }),
      run({ runId: "tf", diseaseSlug: "fop", flowKey: "trials_finder" }),
    ]);
    expect(groups[0].primaryRun.runId).toBe("df");
  });
});
