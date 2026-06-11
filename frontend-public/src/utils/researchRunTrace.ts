/**
 * Helpers for the SSE trace stream emitted by the guideline (pubmed)
 * pipeline. Trace lines are JSON envelopes ``{kind, text, done}``; we
 * extract the human-readable text, hide a known list of internal boot
 * noise, and rewrite a handful of recognisable signals into sentences
 * the patient/clinician page can show without leaking jargon.
 *
 * Workstream classification (which card a trace line belongs to) lives
 * in ``researchWorkstreams.ts``. This file only parses + humanises.
 */

export interface ParsedTraceLine {
  readonly kind: string;
  readonly text: string;
}

const SKIP_PATTERNS: readonly RegExp[] = [
  /import flow_engine/i,
  /async task: (start|launching)/i,
  /flow_engine imported/i,
  /entering fork executor/i,
  /^\[done\]$/i,
  /connection interrupted/i,
  /live sse disabled/i,
  /unknown execution_id/i,
  /live stream interrupted/i,
];

/** True when an SSE payload is a terminal error envelope, not a user-facing log line. */
export function isTraceTransportError(raw: string): boolean {
  try {
    const ev = JSON.parse(raw) as Record<string, unknown>;
    const err = typeof ev.error === "string" ? ev.error : "";
    return err.toLowerCase().includes("unknown execution_id");
  } catch {
    return false;
  }
}

export function parseTraceLine(raw: string): ParsedTraceLine {
  try {
    const ev = JSON.parse(raw) as Record<string, unknown>;
    if (ev.done === true) {
      return { kind: "done", text: "[done]" };
    }
    const kind = typeof ev.kind === "string" ? ev.kind : "";
    const text =
      typeof ev.text === "string"
        ? ev.text
        : typeof ev.output === "string"
          ? ev.output
          : JSON.stringify(ev);
    return { kind, text };
  } catch {
    return { kind: "", text: raw };
  }
}

export function humanizeRunError(error: string): string {
  const lower = error.toLowerCase();
  if (
    lower.includes("maximum context length") ||
    lower.includes("context length") ||
    lower.includes("input_tokens")
  ) {
    return (
      "This disease has an unusually large PubMed literature set. " +
      "The pipeline could not fit it into a single model pass. " +
      "We are improving automatic splitting for large jobs — please try again later or contact us."
    );
  }
  if (lower.includes("timeout") || lower.includes("did not respond")) {
    return (
      "The AI model did not respond in time. The job may still be running on the server — " +
      "refresh this page in a minute. If it keeps failing, try again with a narrower disease name."
    );
  }
  if (lower.includes("429") || lower.includes("rate limit")) {
    return "The service is temporarily rate-limited. Please wait a few minutes and try again.";
  }
  if (lower.includes("failed after") && lower.includes("attempt")) {
    return (
      "The pipeline stopped after several retries. " +
      "Our team can inspect the run from the operator console — you can start a new run from Start research."
    );
  }
  return (
    "Research could not finish. You can start a new run from Start research, " +
    "or check back later if a fix is deployed."
  );
}

export function humanizeTraceMessage(text: string): string | null {
  const stripped = text
    .replace(/^\[(?:sys|SYSTEM)\]\s*/i, "")
    .replace(/^\[SYSTEM\]\s*/i, "")
    .trim();
  if (!stripped) {
    return null;
  }
  if (SKIP_PATTERNS.some((re) => re.test(stripped))) {
    return null;
  }

  const pmids = stripped.match(/pmids=(\d+)/i);
  if (pmids) {
    return `PubMed search complete — ${pmids[1]} articles indexed for analysis.`;
  }

  if (/pm-1 executed via deterministic retrieval/i.test(stripped)) {
    return "Started querying PubMed for relevant publications.";
  }

  if (/node pm-1/i.test(stripped) && /pubmed/i.test(stripped)) {
    return "Searching PubMed and fetching abstracts.";
  }

  if (/node pm-2/i.test(stripped)) {
    return "Categorising abstracts and ranking evidence.";
  }

  if (/node pm-3/i.test(stripped)) {
    return "Scoring evidence tier per recommendation.";
  }

  if (/node pm-merge/i.test(stripped) || /merge waves/i.test(stripped)) {
    return "Merging parallel analysis waves into a draft structure.";
  }

  if (/doctor_finder/i.test(stripped)) {
    return "Identifying specialist authors from PubMed.";
  }

  if (/trials_finder|clinicaltrials/i.test(stripped)) {
    return "Looking up recruiting clinical trials.";
  }

  if (/foundations_finder/i.test(stripped)) {
    return "Searching patient foundations and advocacy groups.";
  }

  if (/guidelines_rag|official_guidelines/i.test(stripped)) {
    return "Cross-checking recognised official guidelines.";
  }

  if (/pmid verification|pmid scrubber/i.test(stripped)) {
    return "Verifying PubMed citations in the draft.";
  }

  if (/parallel \(fork\)/i.test(stripped)) {
    return "Pipeline started — fan-out of parallel workstreams running.";
  }

  if (/loaded disease prompt profile/i.test(stripped)) {
    return stripped.replace(/^\[SYSTEM\]\s*/i, "");
  }

  if (/mode:/i.test(stripped) && stripped.length < 120) {
    return null;
  }

  if (/node [a-z0-9_-]+/i.test(stripped)) {
    const nodeMatch = stripped.match(/node ([a-z0-9_-]+)/i);
    const labelMatch = stripped.match(/\(([^)]+)\)/);
    const nodeId = nodeMatch?.[1] ?? "step";
    const label = labelMatch?.[1] ?? nodeId;
    return `Running ${label}…`;
  }

  if (stripped.startsWith("[SYSTEM]")) {
    return stripped.replace(/^\[SYSTEM\]\s*/i, "");
  }

  return stripped.length > 220 ? `${stripped.slice(0, 217)}…` : stripped;
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  if (minutes < 60) {
    return rem === 0 ? `${minutes}m` : `${minutes}m ${rem}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function formatRunDisplayId(executionId: string): string {
  const compact = executionId.replace(/-/g, "").slice(0, 8).toUpperCase();
  return `RUN-${compact.slice(0, 4)}-${compact.slice(4, 8)}`;
}

export function formatActivityTime(elapsedSec: number): string {
  if (elapsedSec < 60) {
    return `${elapsedSec}s`;
  }
  const min = elapsedSec / 60;
  return `${min.toFixed(1)}m`;
}
