import { describe, expect, it } from "vitest";
import {
  WORKSTREAMS,
  computeOverallProgress,
  countDone,
  countRunning,
  deriveWorkstreams,
  tagTraceMessage,
  type WorkstreamInputs,
} from "./researchWorkstreams";
import type { ResearchRun } from "../types/researchRun";

function makeRun(flowKey: string, slug = "alport"): ResearchRun {
  return {
    runId: `run-${flowKey}`,
    diseaseSlug: slug,
    flowKey,
    label: flowKey,
    startedAt: null,
    elapsedSec: 0,
  };
}

function baseInputs(overrides: Partial<WorkstreamInputs> = {}): WorkstreamInputs {
  return {
    activeRuns: [],
    guidelineRunDone: false,
    guidelineRunFailed: false,
    hasGuidelineDocument: false,
    hasOfficialGuideline: false,
    doctorsCount: 0,
    trialsCount: 0,
    therapiesCount: 0,
    foundationsCount: 0,
    elapsedSec: 30,
    previouslyDone: [],
    guidelineTraceSeen: false,
    ...overrides,
  };
}

describe("researchWorkstreams", () => {
  it("exposes the six fan-out workstreams in a stable order", () => {
    expect(WORKSTREAMS.map((w) => w.key)).toEqual([
      "guideline",
      "doctors",
      "trials",
      "therapies",
      "foundations",
      "official_guidelines",
    ]);
  });

  it("shows everything queued in the first seconds before bootstrap registers", () => {
    const streams = deriveWorkstreams(baseInputs({ elapsedSec: 1 }));
    expect(streams.every((s) => s.status === "queued")).toBe(true);
    expect(computeOverallProgress(streams)).toBe(0);
  });

  it("flips finders to running while their flow_key is in active runs", () => {
    const streams = deriveWorkstreams(
      baseInputs({
        activeRuns: [makeRun("doctor_finder"), makeRun("trials_finder")],
        elapsedSec: 12,
      }),
    );
    const byKey = Object.fromEntries(streams.map((s) => [s.key, s]));
    expect(byKey.doctors.status).toBe("running");
    expect(byKey.trials.status).toBe("running");
    // Therapies finder is not in active runs yet — still queued during grace
    // window, but elapsed > grace so it falls through to "done" once we have
    // *any* active runs. That intentional fallback keeps the UI honest when
    // a finder finishes faster than the first 5 s poll cycle.
    expect(byKey.therapies.status).toBe("done");
  });

  it("treats the guideline workstream as bound to the agent run flag", () => {
    const running = deriveWorkstreams(
      baseInputs({ guidelineTraceSeen: true }),
    );
    expect(running[0]?.key).toBe("guideline");
    expect(running[0]?.status).toBe("running");

    const done = deriveWorkstreams(
      baseInputs({ guidelineRunDone: true, hasGuidelineDocument: true }),
    );
    expect(done[0]?.status).toBe("done");
    expect(done[0]?.progress).toBe(100);

    const failed = deriveWorkstreams(
      baseInputs({ guidelineRunFailed: true }),
    );
    expect(failed[0]?.status).toBe("error");
  });

  it("respects the sticky-done set so workstreams never flip backwards", () => {
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        previouslyDone: ["doctors"],
        doctorsCount: 0,
        activeRuns: [],
      }),
    );
    const doctors = streams.find((s) => s.key === "doctors");
    expect(doctors?.status).toBe("done");
  });

  it("reports a useful summary for finders that complete with zero results", () => {
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        activeRuns: [makeRun("pubmed")],
        trialsCount: 0,
      }),
    );
    const trials = streams.find((s) => s.key === "trials");
    expect(trials?.status).toBe("done");
    expect(trials?.resultSummary).toMatch(/no trials matched/i);
  });

  it("counts done / running / queued streams for the overall bar", () => {
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        activeRuns: [makeRun("doctor_finder"), makeRun("pubmed")],
        trialsCount: 3,
        guidelineTraceSeen: true,
      }),
    );
    expect(countRunning(streams)).toBeGreaterThan(0);
    expect(countDone(streams)).toBeGreaterThan(0);
  });

  it("tags pubmed messages as the guideline stream and finder logs separately", () => {
    expect(tagTraceMessage("Node pm-1 (Agentic PubMed Retrieval)")).toBe(
      "guideline",
    );
    expect(tagTraceMessage("doctor_finder spawn")).toBe("doctors");
    expect(tagTraceMessage("trials_finder match score")).toBe("trials");
    expect(tagTraceMessage("Random system noise")).toBe("system");
  });
});
