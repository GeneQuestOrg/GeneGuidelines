import type { AgentRunResult } from "./client";

type AgentTraceKind =
  | "sys"
  | "ai_summary"
  | "diagnostic"
  | "ticket_status"
  | "missing_tool_request"
  | "output"
  | "technician_steps";

const AGENT_TRACE_KINDS: ReadonlySet<AgentTraceKind> = new Set([
  "sys",
  "ai_summary",
  "diagnostic",
  "ticket_status",
  "missing_tool_request",
  "output",
  "technician_steps",
]);

export type AgentTraceEvent = {
  kind?: AgentTraceKind;
  done?: boolean;
  text?: string;
  error?: string;
  output?: string;
  issue?: string;
  work_log_summary?: string;
  tool?: string;
  result?: string;
  status?: string;
  ticket_id?: number;
  tool_name?: string;
  reason?: string;
  steps?: string[];
  steps_completed_by_ai?: number[];
  summary?: string;
};

export function parseAgentTraceEvent(raw: unknown): AgentTraceEvent | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const data = raw as Record<string, unknown>;
  const rawKind = typeof data.kind === "string" ? data.kind : undefined;
  const kind = rawKind && AGENT_TRACE_KINDS.has(rawKind as AgentTraceKind)
    ? (rawKind as AgentTraceKind)
    : undefined;
  return {
    kind,
    done: typeof data.done === "boolean" ? data.done : undefined,
    text: typeof data.text === "string" ? data.text : undefined,
    error: typeof data.error === "string" ? data.error : undefined,
    output: typeof data.output === "string" ? data.output : undefined,
    issue: typeof data.issue === "string" ? data.issue : undefined,
    work_log_summary:
      typeof data.work_log_summary === "string" ? data.work_log_summary : undefined,
    tool: typeof data.tool === "string" ? data.tool : undefined,
    result: typeof data.result === "string" ? data.result : undefined,
    status: typeof data.status === "string" ? data.status : undefined,
    ticket_id: typeof data.ticket_id === "number" ? data.ticket_id : undefined,
    tool_name: typeof data.tool_name === "string" ? data.tool_name : undefined,
    reason: typeof data.reason === "string" ? data.reason : undefined,
    steps: Array.isArray(data.steps)
      ? (data.steps.filter((x): x is string => typeof x === "string"))
      : undefined,
    steps_completed_by_ai: Array.isArray(data.steps_completed_by_ai)
      ? (data.steps_completed_by_ai.filter((x): x is number => typeof x === "number"))
      : undefined,
    summary: typeof data.summary === "string" ? data.summary : undefined,
  };
}

export function normalizeAgentRunResult(raw: AgentRunResult): AgentRunResult {
  return {
    ...raw,
    structured_output:
      raw.structured_output && typeof raw.structured_output === "object"
        ? raw.structured_output
        : null,
    ai_summary: raw.ai_summary ?? { issue: "", work_log_summary: "" },
    diagnostics_entries: Array.isArray(raw.diagnostics_entries) ? raw.diagnostics_entries : [],
    missing_tool_requests: Array.isArray(raw.missing_tool_requests) ? raw.missing_tool_requests : [],
    steps_completed_by_ai: Array.isArray(raw.steps_completed_by_ai) ? raw.steps_completed_by_ai : [],
  };
}
