import type { AgentRunResult } from "../api/client";
import { parsePubmedOutput, type PubmedOutput } from "./pubmedOutput";

export interface GuidelineRunOutputView {
  pubmed: PubmedOutput | null;
  rawOutput: string | null;
}

function pubmedFromStructured(
  structured: Record<string, unknown> | null | undefined,
): PubmedOutput | null {
  if (!structured || typeof structured !== "object") {
    return null;
  }
  const candidate = structured as PubmedOutput;
  if (
    candidate.disease_name ||
    candidate.guideline_html ||
    candidate.key_updates
  ) {
    return candidate;
  }
  return null;
}

/** Resolve guideline HTML/JSON from API result, SSE output, or local snapshot. */
export function extractGuidelineRunOutput(
  raw: AgentRunResult | null | undefined,
  fallbackOutput?: string | null,
): GuidelineRunOutputView {
  const outputText = raw?.output ?? fallbackOutput ?? null;
  const fromOutput = parsePubmedOutput(outputText);
  if (fromOutput) {
    return { pubmed: fromOutput, rawOutput: outputText };
  }

  const fromStructured = pubmedFromStructured(
    raw?.structured_output as Record<string, unknown> | undefined,
  );
  if (fromStructured) {
    return { pubmed: fromStructured, rawOutput: outputText };
  }

  if (outputText?.trim()) {
    return { pubmed: null, rawOutput: outputText };
  }

  return { pubmed: null, rawOutput: null };
}

export interface RunSnapshotPayload {
  pubmed?: PubmedOutput | null;
  rawOutput?: string | null;
  error?: string | null;
}

export function snapshotToGuidelineView(
  snapshot: RunSnapshotPayload | null,
): GuidelineRunOutputView {
  if (!snapshot) {
    return { pubmed: null, rawOutput: null };
  }
  if (snapshot.pubmed) {
    return { pubmed: snapshot.pubmed, rawOutput: snapshot.rawOutput ?? null };
  }
  return extractGuidelineRunOutput(
    {
      contract_version: "v1",
      execution_id: "",
      ticket_id: 0,
      done: true,
      error: snapshot.error ?? null,
      output: snapshot.rawOutput ?? null,
      ai_summary: { issue: "", work_log_summary: "" },
      diagnostics_entries: [],
    },
    snapshot.rawOutput,
  );
}
