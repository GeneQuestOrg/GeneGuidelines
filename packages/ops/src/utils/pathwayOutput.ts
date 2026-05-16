import type { AgentRunResult } from "../api/client";

export interface PathwayRunOutputView {
  pathway: Record<string, unknown> | null;
  rawOutput: string | null;
}

export function extractPathwayRunOutput(
  raw: AgentRunResult | null | undefined,
  fallbackOutput?: string | null,
): PathwayRunOutputView {
  const outputText = raw?.output ?? fallbackOutput ?? null;
  if (!outputText?.trim()) {
    return { pathway: null, rawOutput: outputText };
  }
  try {
    const parsed = JSON.parse(outputText) as Record<string, unknown>;
    let pathway =
      (parsed.pathway as Record<string, unknown> | undefined) ??
      (parsed.ok ? (parsed as Record<string, unknown>) : null);
    if (pathway && typeof pathway.pathway === "object" && pathway.pathway !== null) {
      const inner = pathway.pathway as Record<string, unknown>;
      if (inner.tree != null) {
        pathway = inner;
      }
    }
    if (pathway && typeof pathway === "object") {
      return { pathway, rawOutput: outputText };
    }
  } catch {
    // not JSON
  }
  return { pathway: null, rawOutput: outputText };
}
