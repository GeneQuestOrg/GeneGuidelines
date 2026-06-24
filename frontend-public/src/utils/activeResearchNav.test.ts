import { describe, expect, it } from "vitest";
import { RESEARCH_LIVE_EXECUTION_ID, hrefForActiveResearchRun } from "./activeResearchNav";
import type { ResearchRun } from "../types/researchRun";

function run(partial: Partial<ResearchRun> & Pick<ResearchRun, "runId" | "flowKey">): ResearchRun {
  return {
    diseaseSlug: null,
    label: "Test run",
    startedAt: null,
    elapsedSec: 0,
    blockedReason: null,
    ...partial,
  };
}

describe("hrefForActiveResearchRun", () => {
  it("links pubmed runs to the guideline trace page", () => {
    expect(
      hrefForActiveResearchRun(
        run({
          runId: "abc-guideline",
          flowKey: "pubmed",
          diseaseSlug: "fd",
          label: "FD synthesis",
        }),
      ),
    ).toBe("/research/abc-guideline?disease=fd&name=FD+synthesis");
  });

  it("links other in-flight finders to the disease-scoped live mirror", () => {
    expect(
      hrefForActiveResearchRun(
        run({
          runId: "df-uuid",
          flowKey: "doctor_finder",
          diseaseSlug: "spinal-muscular-atrophy",
          label: "SMA specialists",
        }),
      ),
    ).toBe(
      `/research/${RESEARCH_LIVE_EXECUTION_ID}?disease=spinal-muscular-atrophy&name=SMA+specialists`,
    );
  });

  it("falls back to start research when slug is missing", () => {
    expect(
      hrefForActiveResearchRun(run({ runId: "x", flowKey: "trials_finder" })),
    ).toBe("/start-research");
  });
});
