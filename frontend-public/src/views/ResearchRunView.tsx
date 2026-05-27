/**
 * ResearchRunView — live mirror of the six-workstream fan-out a disease
 * bootstrap triggers.
 *
 * The page is intentionally *just a status mirror*: results land directly
 * on ``/diseases/<slug>`` as each finder finishes, and the "Open disease
 * page" CTA is unblocked the moment any of those datasets is non-empty.
 * The old sequential Stage 1 → 2 → 3 → 4 model is gone — see
 * ``researchWorkstreams.ts`` for the new derivation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Section, Status } from "@gene-guidelines/ui";
import {
  ApiRequestError,
  appendApiKeyQueryForSse,
  getApiBaseUrl,
} from "../api/client";
import { type AgentRunPayloadV1, fetchAgentRun } from "../api/guidelineRun";
import { repositories } from "../repositories";
import type { Disease } from "../types/disease";
import { useResearchPartialResults } from "../hooks/useResearchPartialResults";
import {
  formatActivityTime,
  formatElapsed,
  formatRunDisplayId,
  humanizeRunError,
  humanizeTraceMessage,
  parseTraceLine,
} from "../utils/researchRunTrace";
import {
  WORKSTREAM_LABELS,
  activeWorkstreamKeys,
  computeOverallProgress,
  countDone,
  countQueued,
  countRunning,
  deriveWorkstreams,
  tagTraceMessage,
  type WorkstreamKey,
  type WorkstreamState,
} from "../utils/researchWorkstreams";
import "../styles/research.css";

const POLL_MS = 2000;
const MAX_TRACE_LINES = 120;
const MAX_ACTIVITY_ENTRIES = 14;

function shouldUseTraceSse(): boolean {
  if (typeof window === "undefined") return true;
  const host = window.location.hostname.toLowerCase();
  return !host.endsWith(".trycloudflare.com");
}

export interface ResearchRunViewProps {
  readonly executionId: string;
  readonly diseaseSlug?: string;
  readonly diseaseName?: string;
  readonly queryTag?: string;
  readonly onNav: (path: string) => void;
}

interface TaggedActivity {
  readonly elapsedSec: number;
  readonly streamKey: WorkstreamKey | "system";
  readonly message: string;
}

interface TimedTraceLine {
  readonly text: string;
  readonly atMs: number;
}

export function ResearchRunView({
  executionId,
  diseaseSlug,
  diseaseName,
  queryTag,
  onNav,
}: ResearchRunViewProps) {
  // startedAtMs is captured once on mount via a lazy initializer — safe
  // to read during render because it is plain state, not a ref.
  const [startedAtMs] = useState<number>(() => Date.now());
  const [elapsedTick, setElapsedTick] = useState(0);
  const [run, setRun] = useState<AgentRunPayloadV1 | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [rawLines, setRawLines] = useState<TimedTraceLine[]>(() =>
    shouldUseTraceSse()
      ? []
      : [
          {
            text: '{"kind":"sys","text":"Live SSE disabled on quick tunnel — status updates via polling only."}',
            atMs: Date.now(),
          },
        ],
  );
  const [disease, setDisease] = useState<Disease | null>(null);

  const displayName =
    diseaseName?.trim() || queryTag?.trim() || "Research in progress";

  const appendRawLines = useCallback((next: string[]) => {
    setRawLines((prev) => {
      const stamped = next.map<TimedTraceLine>((text) => ({
        text,
        atMs: Date.now(),
      }));
      return [...prev, ...stamped].slice(-MAX_TRACE_LINES);
    });
  }, []);

  // 1-second wall-clock ticker — keeps the "elapsed" string and the
  // sticky-done detection in sync with real time without re-rendering
  // every input change.
  useEffect(() => {
    const id = window.setInterval(() => setElapsedTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Poll the agent-run payload bound to the guideline executionId. This
  // is the only run we have a deterministic handle to; everything else
  // we derive from the active-runs projection and the per-disease
  // endpoints.
  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const payload = await fetchAgentRun(executionId);
        if (!cancelled) {
          setRun(payload);
          setPollError(null);
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiRequestError && e.status === 404) {
          setPollError(
            "Run not found — it may have expired from server memory. Try starting a new job from Start research.",
          );
        } else if (e instanceof ApiRequestError && e.status === 0) {
          setPollError(
            `${e.message} Status below may still update — refresh or wait.`,
          );
        } else if (e instanceof Error) {
          setPollError(e.message);
        } else {
          setPollError("Could not load run status.");
        }
      } finally {
        inFlight = false;
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [executionId]);

  // SSE trace from the guideline pipeline. We feed the raw lines into
  // tagTraceMessage / humanizeTraceMessage to build the per-workstream
  // activity feed.
  useEffect(() => {
    if (!shouldUseTraceSse()) {
      return;
    }
    const base = getApiBaseUrl();
    const path = appendApiKeyQueryForSse(
      `/api/agent/trace/${encodeURIComponent(executionId)}`,
    );
    const url = base ? `${base}${path}` : path;
    const es = new EventSource(url);
    es.onmessage = (event) => {
      appendRawLines([event.data]);
    };
    es.onerror = () => {
      appendRawLines([
        JSON.stringify({
          kind: "sys",
          text: "Live stream interrupted — polling still runs.",
        }),
      ]);
      es.close();
    };
    return () => {
      es.close();
    };
  }, [appendRawLines, executionId]);

  // Load the disease row for the OMIM / gene chips on the hero. The row
  // is created immediately by the bootstrap endpoint, so a 404 here just
  // means the projection has not caught up yet — we silently retry until
  // we get a row, then stop.
  useEffect(() => {
    if (diseaseSlug == null || diseaseSlug === "") return;
    if (disease != null) return;
    let cancelled = false;
    let attempts = 0;
    const repo = repositories().diseases;

    const fetchOnce = async () => {
      try {
        const next = await repo.getDiseaseBySlug(diseaseSlug);
        if (!cancelled && next != null) {
          setDisease(next);
        }
      } catch {
        // ignore — the lede falls back to the queryTag.
      }
    };

    void fetchOnce();
    const id = window.setInterval(() => {
      attempts += 1;
      if (attempts > 30) {
        window.clearInterval(id);
        return;
      }
      void fetchOnce();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [diseaseSlug, disease]);

  const done = run?.done ?? false;
  const runError = run?.error ?? null;
  const failed = done && runError != null && runError.length > 0;
  const succeeded = done && !failed;

  // Partial-results poll: doctors/trials/therapies/foundations counts +
  // official guideline presence + guideline document presence + active
  // runs filtered by diseaseSlug.
  const partial = useResearchPartialResults(diseaseSlug, !succeeded, {
    pollIntervalMs: 2000,
  });

  const previouslyDoneRef = useRef<Set<WorkstreamKey>>(new Set());
  const seenActiveRef = useRef<Set<WorkstreamKey>>(new Set());
  const lastInactiveRef = useRef<Partial<Record<WorkstreamKey, number>>>({});

  // Whether we have seen *any* SSE / agent activity for the guideline
  // pipeline — gates the "running" status of the guideline workstream.
  const guidelineTraceSeen = useMemo(
    () => rawLines.some((line) => parseTraceLine(line.text).text.trim().length > 0),
    [rawLines],
  );

  // elapsedTick is the once-per-second wall-clock counter. Using it as
  // the elapsed seconds value keeps derivation pure (no Date.now() reads
  // during render).
  const elapsedSec = elapsedTick;

  const nowMs = startedAtMs + elapsedSec * 1000;

  const streams = useMemo<readonly WorkstreamState[]>(() => {
    const currentlyActive = new Set(activeWorkstreamKeys(partial.activeRuns));

    for (const key of currentlyActive) {
      seenActiveRef.current.add(key);
    }
    for (const key of seenActiveRef.current) {
      if (!currentlyActive.has(key) && lastInactiveRef.current[key] == null) {
        lastInactiveRef.current[key] = nowMs;
      }
    }
    for (const key of currentlyActive) {
      delete lastInactiveRef.current[key];
    }

    const derived = deriveWorkstreams({
      activeRuns: partial.activeRuns,
      guidelineRunDone: succeeded,
      guidelineRunFailed: failed,
      hasGuidelineDocument: partial.hasGuidelineDocument || succeeded,
      hasOfficialGuideline: partial.hasOfficialGuideline,
      doctorsCount: partial.doctors,
      trialsCount: partial.trials,
      therapiesCount: partial.therapies,
      foundationsCount: partial.foundations,
      elapsedSec,
      previouslyDone: Array.from(previouslyDoneRef.current),
      seenActive: Array.from(seenActiveRef.current),
      lastInactiveAtMs: { ...lastInactiveRef.current },
      nowMs,
      guidelineTraceSeen,
    });
    for (const stream of derived) {
      if (stream.status !== "done") continue;
      const isFinderWithZero =
        stream.key !== "guideline" &&
        stream.key !== "official_guidelines" &&
        (stream.count ?? 0) === 0;
      if (!isFinderWithZero) {
        previouslyDoneRef.current.add(stream.key);
      }
    }
    return derived;
  }, [
    partial.activeRuns,
    partial.doctors,
    partial.trials,
    partial.therapies,
    partial.foundations,
    partial.hasGuidelineDocument,
    partial.hasOfficialGuideline,
    succeeded,
    failed,
    elapsedSec,
    guidelineTraceSeen,
    nowMs,
  ]);

  const overall = computeOverallProgress(streams);
  const doneCount = countDone(streams);
  const runningCount = countRunning(streams);
  const queuedCount = countQueued(streams);
  const everythingDone =
    doneCount === streams.length && !streams.some((s) => s.status === "error");

  // Build the tagged activity feed. Each raw SSE line carries the
  // wall-clock timestamp it arrived at (``atMs``), so timestamps are a
  // pure derivation of state rather than ``Date.now()`` during render.
  const activity = useMemo<TaggedActivity[]>(() => {
    const entries: TaggedActivity[] = [];
    const seen = new Set<string>();
    rawLines.forEach((line) => {
      const { text } = parseTraceLine(line.text);
      const message = humanizeTraceMessage(text);
      if (message == null || seen.has(message)) return;
      seen.add(message);
      const elapsedAt = Math.max(
        0,
        Math.floor((line.atMs - startedAtMs) / 1000),
      );
      entries.push({
        elapsedSec: elapsedAt,
        streamKey: tagTraceMessage(text),
        message,
      });
    });
    return entries.slice(-MAX_ACTIVITY_ENTRIES).reverse();
  }, [rawLines, startedAtMs]);

  const diseasePath =
    diseaseSlug != null && diseaseSlug !== ""
      ? `/diseases/${diseaseSlug}`
      : null;

  const guidelinePath =
    diseaseSlug != null && diseaseSlug !== ""
      ? `/diseases/${diseaseSlug}/guidelines`
      : null;

  const anyResults =
    partial.doctors > 0 ||
    partial.trials > 0 ||
    partial.therapies > 0 ||
    partial.foundations > 0 ||
    partial.hasOfficialGuideline ||
    partial.hasGuidelineDocument;

  const omim = disease?.omim?.trim();
  const gene = disease?.gene?.trim();
  const inheritance = disease?.inheritance?.trim();
  const prevalence = disease?.prevalenceText?.trim();

  return (
    <div className="page page--run">
      <header className="rrun__hero">
        <div className="rrun__hero-meta">
          <Status
            status={failed ? "pending" : everythingDone ? "verified" : "live"}
            compact
          />
          <code className="rrun__id">{formatRunDisplayId(executionId)}</code>
          <span className="rrun__sep">·</span>
          <span className="rrun__elapsed">
            elapsed{" "}
            <span className="rrun__elapsed-num">
              {formatElapsed(elapsedSec)}
            </span>
          </span>
        </div>

        <h1 className="rrun__title">{disease?.name ?? displayName}</h1>

        {(omim || gene || inheritance || prevalence) ? (
          <div className="rrun__chips">
            {gene ? (
              <code className="rrun__chip">{gene.split(",")[0]?.trim()}</code>
            ) : null}
            {omim ? (
              <code className="rrun__chip rrun__chip--dim">OMIM {omim}</code>
            ) : null}
            {inheritance ? (
              <span className="rrun__chip-text">{inheritance}</span>
            ) : null}
            {prevalence ? (
              <span className="rrun__chip-text">prevalence {prevalence}</span>
            ) : null}
          </div>
        ) : null}

        <p className="rrun__lede">
          {failed ? (
            <>Research stopped before completion. Details below.</>
          ) : everythingDone ? (
            <>
              Research complete. <b>{disease?.name ?? displayName}</b> is in
              the catalogue — guidelines, doctors, trials and foundations
              are pending specialist verification.
            </>
          ) : (
            <>
              Six workstreams are running <b>in parallel</b>. Each writes its
              results directly to the disease page as they land — you don't
              need to wait for the long guideline draft to finish.
            </>
          )}
        </p>

        {pollError ? (
          <p className="research__error" role="alert">
            {pollError}
          </p>
        ) : null}

        {failed && runError ? (
          <div className="run__error-banner" role="alert">
            <strong>Could not finish</strong>
            <p>{humanizeRunError(runError)}</p>
          </div>
        ) : null}

        <div className="rrun__overall">
          <div className="rrun__overall-bar">
            <i style={{ width: `${overall}%` }} />
          </div>
          <div className="rrun__overall-counts">
            <span>
              <b>{doneCount}</b> done
            </span>
            <span>
              <b>{runningCount}</b> running
            </span>
            <span>
              <b>{queuedCount}</b> queued
            </span>
            <span className="rrun__overall-pct">{overall}%</span>
          </div>
        </div>

        <div className="rrun__actions">
          {diseasePath ? (
            <Button
              variant="primary"
              type="button"
              disabled={!anyResults}
              onClick={() => onNav(diseasePath)}
            >
              {everythingDone
                ? `Open ${disease?.nameShort ?? "disease page"} →`
                : anyResults
                  ? "See what we have so far →"
                  : "Waiting for first results…"}
            </Button>
          ) : null}
          {succeeded && guidelinePath ? (
            <Button type="button" onClick={() => onNav(guidelinePath)}>
              Open guideline draft
            </Button>
          ) : null}
          <Button type="button" onClick={() => onNav("/start-research")}>
            Start another run
          </Button>
          <Button type="button" onClick={() => onNav("/")}>
            Home
          </Button>
        </div>
      </header>

      <Section
        title="What we're collecting"
        sub={
          <>
            Each card is its own pipeline. Results land directly on the
            disease page — this view is just a status mirror.
          </>
        }
      >
        <div className="rrun__streams">
          {streams.map((stream) => (
            <StreamCard
              key={stream.key}
              stream={stream}
              onOpenDisease={
                diseasePath ? () => onNav(diseasePath) : undefined
              }
            />
          ))}
        </div>
      </Section>

      <Section
        title="Live activity"
        sub="Audit log from the workflow engine — each event tagged with the workstream that emitted it. Newest first."
      >
        {activity.length > 0 ? (
          <div className="rrun__activity">
            {activity.map((entry, index) => (
              <div
                key={`${entry.message}-${index}`}
                className={`rrun__act-line rrun__act-line--${entry.streamKey}`}
              >
                <span className="rrun__act-time">
                  {formatActivityTime(entry.elapsedSec)}
                </span>
                <span
                  className={`rrun__act-tag rrun__act-tag--${entry.streamKey}`}
                >
                  {WORKSTREAM_LABELS[entry.streamKey]}
                </span>
                <span className="rrun__act-msg">{entry.message}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rrun__act-empty">
            Waiting for the workflow engine to report progress…
          </div>
        )}
      </Section>

      {everythingDone && diseasePath ? (
        <section className="rrun__done">
          <div className="rrun__done-inner">
            <div className="rrun__done-icon" aria-hidden="true">
              ✓
            </div>
            <div className="rrun__done-body">
              <h3>Research finished in {formatElapsed(elapsedSec)}.</h3>
              <p>
                <b>{disease?.name ?? displayName}</b> is now in the catalogue.
                Draft guideline, {partial.doctors} doctors, {partial.trials}{" "}
                trials, {partial.therapies} therapies and{" "}
                {partial.foundations} foundations are waiting for specialist
                review — every section is marked <em>pending verification</em>{" "}
                until a clinician signs off.
              </p>
            </div>
            <Button
              variant="primary"
              type="button"
              onClick={() => onNav(diseasePath)}
            >
              Open {disease?.nameShort ?? "disease page"} →
            </Button>
          </div>
        </section>
      ) : null}

      {rawLines.length > 0 ? (
        <details className="run__technical">
          <summary>Technical log (for operators)</summary>
          <div className="research__trace">
            <pre>
              {rawLines
                .map((line) => {
                  const { kind, text } = parseTraceLine(line.text);
                  return kind ? `[${kind}] ${text}` : text;
                })
                .join("\n")}
            </pre>
          </div>
        </details>
      ) : null}
    </div>
  );
}

interface StreamCardProps {
  readonly stream: WorkstreamState;
  readonly onOpenDisease?: () => void;
}

function StreamCard({ stream, onOpenDisease }: StreamCardProps) {
  const showCount =
    stream.count != null && stream.key !== "official_guidelines";
  const officialPresent =
    stream.key === "official_guidelines" && stream.count === 1;

  return (
    <article
      className={`stream stream--${stream.status} ${
        stream.primary ? "stream--primary" : ""
      }`}
    >
      <header className="stream__head">
        <span className="stream__icon" aria-hidden="true">
          <StreamIcon streamKey={stream.key} />
        </span>
        <div className="stream__title">
          <div className="stream__label">{stream.label}</div>
          <div className="stream__sub">{stream.sub}</div>
        </div>
        <StreamPill status={stream.status} />
      </header>

      <div className="stream__metric">
        {showCount ? (
          <>
            <span className="stream__count">{stream.count}</span>
            <span className="stream__count-label">{stream.countLabel}</span>
          </>
        ) : officialPresent ? (
          <span className="stream__count">1</span>
        ) : stream.key === "official_guidelines" ? (
          <span className="stream__count stream__count--ghost">—</span>
        ) : (
          <span className="stream__count stream__count--ghost">—</span>
        )}
      </div>

      {stream.status === "running" ? (
        <div className="stream__bar">
          <i style={{ width: `${stream.progress}%` }} />
        </div>
      ) : null}

      <p className="stream__summary">{stream.resultSummary}</p>

      {stream.status === "done" &&
      (stream.count ?? 0) > 0 &&
      onOpenDisease != null ? (
        <button type="button" className="stream__cta" onClick={onOpenDisease}>
          See on the disease page →
        </button>
      ) : null}
    </article>
  );
}

function StreamPill({ status }: { status: WorkstreamState["status"] }) {
  if (status === "queued") {
    return <span className="stream__pill stream__pill--queued">queued</span>;
  }
  if (status === "done") {
    return <span className="stream__pill stream__pill--done">✓ done</span>;
  }
  if (status === "error") {
    return <span className="stream__pill stream__pill--error">stopped</span>;
  }
  return (
    <span className="stream__pill stream__pill--running">
      <span className="stream__pill-dot" />
      running
    </span>
  );
}

function StreamIcon({ streamKey }: { streamKey: WorkstreamKey }) {
  switch (streamKey) {
    case "guideline":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
          <path d="M14 3v6h6" />
          <path d="M8 13h8M8 17h5" />
        </svg>
      );
    case "doctors":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="8" r="3.4" />
          <path d="M5 21c.6-3.8 3.5-6 7-6s6.4 2.2 7 6" />
        </svg>
      );
    case "trials":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10 4v6.5a4.5 4.5 0 1 0 4 0V4" />
          <path d="M9 4h6" />
        </svg>
      );
    case "therapies":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="3" y="9" width="18" height="6" rx="3" />
          <path d="M12 9v6" />
        </svg>
      );
    case "foundations":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="9" cy="8" r="3" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M3 20c0-3 2.5-5 6-5s6 2 6 5" />
          <path d="M14 20c0-2.2 1.6-4 3.5-4S21 17.8 21 20" />
        </svg>
      );
    case "official_guidelines":
      return (
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 4h16v16H4z" />
          <path d="M9 9h6M9 13h6M9 17h4" />
        </svg>
      );
    default:
      return null;
  }
}
