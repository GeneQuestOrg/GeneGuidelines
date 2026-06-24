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
    blockedReason: null,
  };
}

function baseInputs(overrides: Partial<WorkstreamInputs> = {}): WorkstreamInputs {
  const nowMs = overrides.nowMs ?? Date.now();
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
    seenActive: [],
    lastInactiveAtMs: {},
    nowMs,
    guidelineTraceSeen: false,
    countsReady: true,
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
    // Other finders stay running once bootstrap has started — never jump to
    // done with zero counts just because their flow_key is not in this poll.
    expect(byKey.therapies.status).toBe("running");
  });

  it("keeps a finder running while counts settle after it leaves active runs", () => {
    const nowMs = 1_000_000;
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 20,
        seenActive: ["foundations"],
        lastInactiveAtMs: { foundations: nowMs - 5_000 },
        nowMs,
        foundationsCount: 0,
        activeRuns: [],
      }),
    );
    const foundations = streams.find((s) => s.key === "foundations");
    expect(foundations?.status).toBe("running");
    expect(foundations?.resultSummary).toMatch(/saving results/i);
  });

  it("marks done as soon as counts arrive, even inside the settling window", () => {
    const nowMs = 1_000_000;
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 20,
        seenActive: ["foundations"],
        lastInactiveAtMs: { foundations: nowMs - 5_000 },
        nowMs,
        foundationsCount: 2,
        activeRuns: [],
      }),
    );
    const foundations = streams.find((s) => s.key === "foundations");
    expect(foundations?.status).toBe("done");
    expect(foundations?.count).toBe(2);
  });

  it("marks a seen finder done with zero only after settling window expires", () => {
    const nowMs = 1_000_000;
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 40,
        seenActive: ["trials"],
        lastInactiveAtMs: { trials: nowMs - 25_000 },
        nowMs,
        trialsCount: 0,
        activeRuns: [makeRun("pubmed")],
      }),
    );
    const trials = streams.find((s) => s.key === "trials");
    expect(trials?.status).toBe("done");
    expect(trials?.resultSummary).toMatch(/no trials matched/i);
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
        doctorsCount: 8,
        activeRuns: [],
      }),
    );
    const doctors = streams.find((s) => s.key === "doctors");
    expect(doctors?.status).toBe("done");
  });

  it("reports a useful summary for finders that complete with zero results", () => {
    const nowMs = 1_000_000;
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        activeRuns: [makeRun("pubmed")],
        seenActive: ["trials"],
        lastInactiveAtMs: { trials: nowMs - 25_000 },
        nowMs,
        trialsCount: 0,
      }),
    );
    const trials = streams.find((s) => s.key === "trials");
    expect(trials?.status).toBe("done");
    expect(trials?.resultSummary).toMatch(/no trials matched/i);
  });

  it("keeps finders queued until disease counts have loaded once", () => {
    const streams = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        countsReady: false,
        doctorsCount: 20,
        activeRuns: [],
      }),
    );
    expect(streams.find((s) => s.key === "doctors")?.status).toBe("queued");
    const hydrated = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        countsReady: true,
        doctorsCount: 20,
        activeRuns: [],
      }),
    );
    expect(hydrated.find((s) => s.key === "doctors")?.status).toBe("done");
  });

  it("marks a never-seen zero-result finder done once the fan-out window elapses", () => {
    // Fast finder that finished with zero results and was never caught in a
    // 2 s active-runs poll: it must not stay stuck on "running" forever.
    const stuckWindow = deriveWorkstreams(
      baseInputs({
        elapsedSec: 30,
        countsReady: true,
        guidelineTraceSeen: true,
        foundationsCount: 0,
        activeRuns: [],
      }),
    );
    expect(
      stuckWindow.find((s) => s.key === "foundations")?.status,
    ).toBe("running");

    const settled = deriveWorkstreams(
      baseInputs({
        elapsedSec: 900,
        countsReady: true,
        guidelineTraceSeen: true,
        foundationsCount: 0,
        activeRuns: [],
      }),
    );
    expect(settled.find((s) => s.key === "foundations")?.status).toBe("done");
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
