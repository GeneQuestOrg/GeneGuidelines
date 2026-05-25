/**
 * Derivation of the six parallel workstreams that a disease bootstrap fans
 * out into. The run page used to lie to users — it rendered a sequential
 * "Stage 1 → 2 → 3 → 4" model on top of fan-out execution. This module
 * mirrors what the backend actually does: ``disease_bootstrap.py`` starts
 * the official-guideline finder, trials finder, therapies finder,
 * foundations finder, doctor finder and the long-running pubmed/guideline
 * pipeline **in parallel** as soon as the disease row exists.
 *
 * The state of each workstream is derived from a few signals:
 *
 * - **active runs** filtered by ``diseaseSlug`` (``/api/research-runs``).
 *   The finder's ``flow_key`` is present while the worker is busy and
 *   disappears as soon as ``finished_at`` is written.
 * - **per-disease counts** (doctors, trials, therapies, foundations) and
 *   presence flags (official guideline pointer, guideline document) —
 *   polled from the public per-disease endpoints already exposed by the
 *   FastAPI app.
 * - the guideline run's own ``done`` / ``error`` flags from
 *   ``GET /api/agent/run/{id}``, since that workstream is bound to the
 *   ``executionId`` the user is watching.
 *
 * Once a workstream has reached ``done`` we never let it slip back to
 * ``running``: the active-runs poll lags slightly behind reality and
 * flipping cards backwards would be confusing.
 */

import type { ResearchRun } from "../types/researchRun";

export type WorkstreamKey =
  | "guideline"
  | "doctors"
  | "trials"
  | "therapies"
  | "foundations"
  | "official_guidelines";

export type WorkstreamStatus = "queued" | "running" | "done" | "error";

export interface WorkstreamDef {
  readonly key: WorkstreamKey;
  readonly label: string;
  readonly sub: string;
  readonly countLabel: string;
  readonly primary?: boolean;
  /** Flow keys reported by ``/api/research-runs`` for this workstream. */
  readonly flowKeys: readonly string[];
}

export interface WorkstreamState extends WorkstreamDef {
  readonly status: WorkstreamStatus;
  readonly count: number | null;
  readonly resultSummary: string;
  readonly progress: number;
}

export interface WorkstreamInputs {
  readonly activeRuns: readonly ResearchRun[];
  readonly guidelineRunDone: boolean;
  readonly guidelineRunFailed: boolean;
  readonly hasGuidelineDocument: boolean;
  readonly hasOfficialGuideline: boolean;
  readonly doctorsCount: number;
  readonly trialsCount: number;
  readonly therapiesCount: number;
  readonly foundationsCount: number;
  readonly elapsedSec: number;
  /** Workstream keys that should be sticky-done from prior renders. */
  readonly previouslyDone: ReadonlyArray<WorkstreamKey>;
  /** True while we have any trace from the guideline run. */
  readonly guidelineTraceSeen: boolean;
}

export const WORKSTREAMS: readonly WorkstreamDef[] = [
  {
    key: "guideline",
    label: "Guideline draft",
    sub: "PubMed retrieval → therapy + diagnostic extraction → assembly with citations",
    countLabel: "sections",
    primary: true,
    flowKeys: ["pubmed", "guideline"],
  },
  {
    key: "doctors",
    label: "Specialist doctors",
    sub: "PubMed author scoring · institution + geo enrichment",
    countLabel: "candidates",
    flowKeys: ["doctor_finder"],
  },
  {
    key: "trials",
    label: "Clinical trials",
    sub: "ClinicalTrials.gov · status: recruiting",
    countLabel: "trials",
    flowKeys: ["trials_finder"],
  },
  {
    key: "therapies",
    label: "Therapies",
    sub: "Standard + experimental · 4-state evidence tier",
    countLabel: "lines",
    flowKeys: ["therapies_finder"],
  },
  {
    key: "foundations",
    label: "Patient foundations",
    sub: "Orphanet partners + grassroots support groups",
    countLabel: "orgs",
    flowKeys: ["foundations_finder"],
  },
  {
    key: "official_guidelines",
    label: "Official guideline",
    sub: "Recognised consensus paper (e.g. Boyce 2019 for FD)",
    countLabel: "pointer",
    flowKeys: ["official_guidelines_finder"],
  },
];

/**
 * If the active-runs response has not surfaced a finder within this grace
 * window we assume the user hit the page before the bootstrap fan-out
 * managed to register itself, and we keep the workstream in ``queued``
 * instead of jumping to ``done``.
 */
const BOOTSTRAP_GRACE_SEC = 8;

function flowActive(
  activeRuns: readonly ResearchRun[],
  flowKeys: readonly string[],
): boolean {
  return activeRuns.some((run) => flowKeys.includes(run.flowKey));
}

function countForKey(
  key: WorkstreamKey,
  inputs: WorkstreamInputs,
): number | null {
  switch (key) {
    case "doctors":
      return inputs.doctorsCount;
    case "trials":
      return inputs.trialsCount;
    case "therapies":
      return inputs.therapiesCount;
    case "foundations":
      return inputs.foundationsCount;
    case "official_guidelines":
      return inputs.hasOfficialGuideline ? 1 : 0;
    case "guideline":
      return inputs.hasGuidelineDocument ? 1 : null;
    default:
      return null;
  }
}

function resultSummary(
  def: WorkstreamDef,
  status: WorkstreamStatus,
  count: number | null,
  inputs: WorkstreamInputs,
): string {
  if (status === "queued") {
    return "Waiting for the worker to pick up this job.";
  }
  if (status === "error") {
    return "The job stopped before it could finish.";
  }
  if (def.key === "guideline") {
    if (status === "done") {
      return inputs.hasGuidelineDocument
        ? "Draft published — pending specialist verification."
        : "Pipeline finished without publishing a draft.";
    }
    return inputs.guidelineTraceSeen
      ? "Mining PubMed, scoring evidence, drafting sections."
      : "Starting up — connecting to the workflow engine.";
  }
  if (def.key === "official_guidelines") {
    if (status === "done") {
      return inputs.hasOfficialGuideline
        ? "Linked to the recognised consensus paper."
        : "No consensus guideline found in PubMed.";
    }
    return "Looking up the recognised guideline document.";
  }
  if (count == null) {
    return "Waiting for results.";
  }
  const noun = def.countLabel;
  if (status === "done") {
    if (count === 0) {
      return `Run complete — no ${noun} matched.`;
    }
    return `Run complete — ${count} ${noun} stored on the disease page.`;
  }
  // running
  if (count === 0) {
    return "Searching public sources — results land on the disease page as they come in.";
  }
  return `${count} ${noun} so far · more may still land.`;
}

function progressForRunningStream(
  def: WorkstreamDef,
  count: number | null,
  inputs: WorkstreamInputs,
): number {
  if (def.key === "guideline") {
    if (inputs.hasGuidelineDocument) return 95;
    if (inputs.guidelineTraceSeen) {
      // Slow up to 75% over ~10 minutes of elapsed wall time — purely a
      // visual ramp; the real progress comes from the trace signals.
      const ramp = Math.min(75, 5 + Math.floor(inputs.elapsedSec / 8));
      return ramp;
    }
    return 5;
  }
  // For the small finders, scale by count up to 70% then ease towards
  // 90% as time passes — keeps the bar moving even while waiting on the
  // network.
  if (count != null && count > 0) {
    const scaled = Math.min(70, count * 12);
    const timeBoost = Math.min(20, Math.floor(inputs.elapsedSec / 6));
    return Math.min(90, scaled + timeBoost);
  }
  return Math.min(45, 10 + Math.floor(inputs.elapsedSec / 4));
}

export function deriveWorkstreams(
  inputs: WorkstreamInputs,
): readonly WorkstreamState[] {
  const sticky = new Set(inputs.previouslyDone);
  return WORKSTREAMS.map((def) => {
    const count = countForKey(def.key, inputs);

    let status: WorkstreamStatus;
    if (def.key === "guideline") {
      if (inputs.guidelineRunFailed) {
        status = "error";
      } else if (inputs.guidelineRunDone) {
        status = "done";
      } else if (inputs.guidelineTraceSeen) {
        status = "running";
      } else if (inputs.elapsedSec < BOOTSTRAP_GRACE_SEC) {
        status = "queued";
      } else {
        status = "running";
      }
    } else {
      const active = flowActive(inputs.activeRuns, def.flowKeys);
      if (active) {
        status = "running";
      } else if (sticky.has(def.key)) {
        status = "done";
      } else if (count != null && count > 0) {
        status = "done";
      } else if (inputs.elapsedSec < BOOTSTRAP_GRACE_SEC) {
        status = "queued";
      } else if (inputs.activeRuns.length > 0) {
        // We have seen *some* runs but not this one — the finder either
        // returned empty quickly or already finished.
        status = "done";
      } else {
        status = "queued";
      }
    }

    let progress = 0;
    if (status === "done") progress = 100;
    else if (status === "running")
      progress = progressForRunningStream(def, count, inputs);
    else if (status === "error") progress = 0;

    return {
      ...def,
      status,
      count,
      progress,
      resultSummary: resultSummary(def, status, count, inputs),
    };
  });
}

export function computeOverallProgress(
  streams: readonly WorkstreamState[],
): number {
  if (streams.length === 0) return 0;
  const sum = streams.reduce((acc, s) => acc + s.progress, 0);
  return Math.min(100, Math.round(sum / streams.length));
}

export function countDone(streams: readonly WorkstreamState[]): number {
  return streams.filter((s) => s.status === "done").length;
}

export function countRunning(streams: readonly WorkstreamState[]): number {
  return streams.filter((s) => s.status === "running").length;
}

export function countQueued(streams: readonly WorkstreamState[]): number {
  return streams.filter((s) => s.status === "queued").length;
}

export interface TaggedActivityEntry {
  readonly elapsedSec: number;
  readonly streamKey: WorkstreamKey | "system";
  readonly streamLabel: string;
  readonly message: string;
}

/**
 * Tag a raw guideline-trace message with the workstream it belongs to.
 * Pubmed retrieval lives inside the guideline pipeline but is reported
 * as the dedicated ``literature`` phase of the ``guideline`` workstream,
 * so we collapse them. Finder telemetry rarely shows up on this SSE
 * channel — we synthesise activity for those workstreams from changes
 * in the active-runs projection.
 */
export function tagTraceMessage(rawMessage: string): WorkstreamKey | "system" {
  const lower = rawMessage.toLowerCase();
  if (/doctor_finder/.test(lower)) return "doctors";
  if (/trials_finder|clinicaltrials/.test(lower)) return "trials";
  if (/therapies_finder/.test(lower)) return "therapies";
  if (/foundations_finder/.test(lower)) return "foundations";
  if (/official_guidelines_finder|guidelines_rag/.test(lower))
    return "official_guidelines";
  if (
    /pm-\d|pubmed|pmids=|merge waves|pmid verification|pmid scrubber/.test(
      lower,
    )
  )
    return "guideline";
  if (/parallel \(fork\)|loaded disease prompt profile/.test(lower))
    return "guideline";
  return "system";
}

export const WORKSTREAM_LABELS: Record<
  WorkstreamKey | "system",
  string
> = {
  guideline: "Guideline",
  doctors: "Doctors",
  trials: "Trials",
  therapies: "Therapies",
  foundations: "Foundations",
  official_guidelines: "Official",
  system: "System",
};
