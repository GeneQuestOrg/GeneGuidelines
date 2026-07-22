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

/**
 * `label`/`sub`/`countLabel` below are bare i18n keys, not display text — callers must translate
 * them via `t(`common:${key}`)` (or `t(key)` when already scoped to "common").
 */
export interface WorkstreamDef {
  readonly key: WorkstreamKey;
  readonly label: string;
  readonly sub: string;
  readonly countLabel: string;
  readonly primary?: boolean;
  /** Flow keys reported by ``/api/research-runs`` for this workstream. */
  readonly flowKeys: readonly string[];
}

/**
 * `resultSummary` is a translation descriptor, not display text — callers must render it via
 * `t(`common:${resultSummary.key}`, resultSummary.params)` (drop the "common:" prefix when
 * already scoped to that namespace).
 */
export interface ResultSummary {
  readonly key: string;
  readonly params?: { readonly count: number };
}

export interface WorkstreamState extends WorkstreamDef {
  readonly status: WorkstreamStatus;
  readonly count: number | null;
  readonly resultSummary: ResultSummary;
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
  /** Finders that have appeared in ``activeRuns`` at least once this session. */
  readonly seenActive: ReadonlyArray<WorkstreamKey>;
  /** Wall-clock ms when a finder last dropped off ``activeRuns``. */
  readonly lastInactiveAtMs: Partial<Record<WorkstreamKey, number>>;
  /** Current wall-clock ms — used for post-finder settling window. */
  readonly nowMs: number;
  /** True while we have any trace from the guideline run. */
  readonly guidelineTraceSeen: boolean;
  /** True after the first successful per-disease counts fetch (avoids refresh flash). */
  readonly countsReady: boolean;
}

export const WORKSTREAMS: readonly WorkstreamDef[] = [
  {
    key: "guideline",
    label: "researchWorkstreams.guideline.label",
    sub: "researchWorkstreams.guideline.sub",
    countLabel: "researchWorkstreams.guideline.countLabel",
    primary: true,
    flowKeys: ["pubmed", "guideline"],
  },
  {
    key: "doctors",
    label: "researchWorkstreams.doctors.label",
    sub: "researchWorkstreams.doctors.sub",
    countLabel: "researchWorkstreams.doctors.countLabel",
    flowKeys: ["doctor_finder"],
  },
  {
    key: "trials",
    label: "researchWorkstreams.trials.label",
    sub: "researchWorkstreams.trials.sub",
    countLabel: "researchWorkstreams.trials.countLabel",
    flowKeys: ["trials_finder"],
  },
  {
    key: "therapies",
    label: "researchWorkstreams.therapies.label",
    sub: "researchWorkstreams.therapies.sub",
    countLabel: "researchWorkstreams.therapies.countLabel",
    flowKeys: ["therapies_finder"],
  },
  {
    key: "foundations",
    label: "researchWorkstreams.foundations.label",
    sub: "researchWorkstreams.foundations.sub",
    countLabel: "researchWorkstreams.foundations.countLabel",
    flowKeys: ["foundations_finder"],
  },
  {
    key: "official_guidelines",
    label: "researchWorkstreams.official_guidelines.label",
    sub: "researchWorkstreams.official_guidelines.sub",
    countLabel: "researchWorkstreams.official_guidelines.countLabel",
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
/**
 * After a finder leaves ``activeRuns``, keep the card running while per-disease
 * count polls catch up. Must exceed the count poll interval plus network slack —
 * otherwise the UI flashes ``done / 0`` one poll cycle before rows land.
 */
const RESULTS_SETTLING_MS = 22_000;
/**
 * Only for finders never seen in ``activeRuns``: after this many seconds on the
 * run page, treat as finished with zero results. Must exceed real LLM finder
 * runtime (often 5–15+ min) — a low value falsely showed ``done / 0`` while
 * trials/therapies were still extracting.
 */
const FINDER_MAX_RUNTIME_SEC = 900;

function bootstrapSeen(inputs: WorkstreamInputs): boolean {
  return (
    inputs.guidelineTraceSeen ||
    inputs.activeRuns.length > 0 ||
    inputs.seenActive.length > 0
  );
}

function isSettlingAfterInactive(
  key: WorkstreamKey,
  count: number | null,
  inputs: WorkstreamInputs,
): boolean {
  if (count != null && count > 0) return false;
  if (key === "official_guidelines" || key === "guideline") return false;
  const inactiveAt = inputs.lastInactiveAtMs[key];
  if (inactiveAt == null) return false;
  return inputs.nowMs - inactiveAt < RESULTS_SETTLING_MS;
}

function flowActive(
  activeRuns: readonly ResearchRun[],
  flowKeys: readonly string[],
): boolean {
  return activeRuns.some((run) => flowKeys.includes(run.flowKey));
}

export function activeWorkstreamKeys(
  activeRuns: readonly ResearchRun[],
): readonly WorkstreamKey[] {
  return WORKSTREAMS.filter(
    (def) => def.key !== "guideline" && flowActive(activeRuns, def.flowKeys),
  ).map((def) => def.key);
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

/**
 * Per-workstream summary key roots for the four "generic finder" streams (doctors/trials/
 * therapies/foundations) — the only ones whose summary sentence embeds a counted noun, so each
 * needs its own grammatically-correct translation rather than one generic templated sentence.
 */
const FINDER_SUMMARY_ROOT: Partial<Record<WorkstreamKey, string>> = {
  doctors: "doctors",
  trials: "trials",
  therapies: "therapies",
  foundations: "foundations",
};

function resultSummary(
  def: WorkstreamDef,
  status: WorkstreamStatus,
  count: number | null,
  inputs: WorkstreamInputs,
): ResultSummary {
  if (status === "queued") {
    return { key: "researchWorkstreams.summary.queued" };
  }
  if (status === "error") {
    return { key: "researchWorkstreams.summary.error" };
  }
  if (def.key === "guideline") {
    if (status === "done") {
      return {
        key: inputs.hasGuidelineDocument
          ? "researchWorkstreams.summary.guidelineDonePublished"
          : "researchWorkstreams.summary.guidelineDoneNoDraft",
      };
    }
    return {
      key: inputs.guidelineTraceSeen
        ? "researchWorkstreams.summary.guidelineRunningMining"
        : "researchWorkstreams.summary.guidelineRunningStarting",
    };
  }
  if (def.key === "official_guidelines") {
    if (status === "done") {
      return {
        key: inputs.hasOfficialGuideline
          ? "researchWorkstreams.summary.officialDoneLinked"
          : "researchWorkstreams.summary.officialDoneNotFound",
      };
    }
    return { key: "researchWorkstreams.summary.officialLookingUp" };
  }
  if (
    status === "running" &&
    isSettlingAfterInactive(def.key, count, inputs)
  ) {
    return { key: "researchWorkstreams.summary.settling" };
  }
  if (count == null) {
    return { key: "researchWorkstreams.summary.waitingForResults" };
  }
  // Only the four generic finders reach this point (guideline/official_guidelines already
  // returned above), so `root` is always defined here.
  const root = FINDER_SUMMARY_ROOT[def.key] ?? def.key;
  if (status === "done") {
    if (count === 0) {
      return { key: `researchWorkstreams.summary.${root}DoneZero` };
    }
    return { key: `researchWorkstreams.summary.${root}DoneWithCount`, params: { count } };
  }
  // running
  if (count === 0) {
    return { key: "researchWorkstreams.summary.searchingPublicSources" };
  }
  return { key: `researchWorkstreams.summary.${root}RunningWithCount`, params: { count } };
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
  const seen = new Set(inputs.seenActive);
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

      if (!inputs.countsReady) {
        // Avoid treating unloaded zeros as "still running" after a page refresh.
        status = "queued";
      } else if (active) {
        status = "running";
      } else if (isSettlingAfterInactive(def.key, count, inputs)) {
        status = "running";
      } else if (count != null && count > 0) {
        status = "done";
      } else if (
        sticky.has(def.key) &&
        (count ?? 0) > 0
      ) {
        // Never stick at done/0 — counts often arrive one poll after activeRuns drops.
        status = "done";
      } else if (
        seen.has(def.key) &&
        !isSettlingAfterInactive(def.key, count, inputs) &&
        (count ?? 0) === 0
      ) {
        status = "done";
      } else if (inputs.elapsedSec < BOOTSTRAP_GRACE_SEC) {
        status = "queued";
      } else if (
        !seen.has(def.key) &&
        !active &&
        bootstrapSeen(inputs) &&
        !isSettlingAfterInactive(def.key, count, inputs) &&
        inputs.elapsedSec >= FINDER_MAX_RUNTIME_SEC
      ) {
        // Never appeared in active-runs poll but fan-out started long ago.
        status = "done";
      } else if (bootstrapSeen(inputs)) {
        status = "running";
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

/**
 * Bare i18n keys, not display text — callers must translate via `t(`common:${key}`)` (or
 * `t(key)` when already scoped to "common").
 */
export const WORKSTREAM_LABELS: Record<
  WorkstreamKey | "system",
  string
> = {
  guideline: "researchWorkstreams.labels.guideline",
  doctors: "researchWorkstreams.labels.doctors",
  trials: "researchWorkstreams.labels.trials",
  therapies: "researchWorkstreams.labels.therapies",
  foundations: "researchWorkstreams.labels.foundations",
  official_guidelines: "researchWorkstreams.labels.official_guidelines",
  system: "researchWorkstreams.labels.system",
};
