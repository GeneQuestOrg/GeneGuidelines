import { apiGet, apiPostJson } from "./client";

/**
 * Optional override for guideline runs. When unset, POST omits `profile` and the
 * backend uses `MODEL_PROFILE` from server `.env` (typically `vllm`).
 */
export const DEFAULT_GUIDELINE_PROFILE: string | undefined =
  typeof import.meta.env.VITE_GUIDELINE_PROFILE === "string" &&
  import.meta.env.VITE_GUIDELINE_PROFILE.trim().length > 0
    ? import.meta.env.VITE_GUIDELINE_PROFILE.trim()
    : undefined;

export interface StartGuidelineRunResponse {
  execution_id: string;
  status: string;
  ticket_id?: number;
}

export interface StartGuidelineRunCatalogInput {
  mode: "catalog";
  diseaseSlug: string;
  profile?: string;
}

export interface StartGuidelineRunCustomInput {
  mode: "custom";
  diseaseName: string;
  diseaseAliases: string[];
  profile?: string;
}

export type StartGuidelineRunInput =
  | StartGuidelineRunCatalogInput
  | StartGuidelineRunCustomInput;

export async function startGuidelineRunPublic(
  input: StartGuidelineRunInput,
): Promise<StartGuidelineRunResponse> {
  const profile = input.profile ?? DEFAULT_GUIDELINE_PROFILE;
  if (input.mode === "catalog") {
    return apiPostJson<StartGuidelineRunResponse>("/api/pipeline/guideline-run", {
      disease_slug: input.diseaseSlug,
      ...(profile != null ? { profile } : {}),
    });
  }
  return apiPostJson<StartGuidelineRunResponse>("/api/pipeline/guideline-run", {
    disease_name: input.diseaseName,
    disease_aliases: input.diseaseAliases,
    ...(profile != null ? { profile } : {}),
  });
}

export interface AgentRunPayloadV1 {
  contract_version: string;
  execution_id: string;
  ticket_id: number;
  done: boolean;
  error: string | null;
  output: string | null;
  structured_output: Record<string, unknown> | null;
  quality_snapshot: Record<string, unknown> | null;
  ai_summary: Record<string, unknown>;
  diagnostics_entries: unknown[];
  steps_completed_by_ai: unknown[];
  missing_tool_requests: unknown[];
  started_at?: string | null;
  current_stage?: string | null;
  /** Fair-share queue (RES-1): "queued" until a worker slot frees up. */
  status?: string | null;
  queue_position?: number | null;
  /**
   * Why a queued run is not yet starting: "token_budget" when the monthly LLM
   * budget is exhausted (the worker paused claiming), else null. Only
   * meaningful while `status === "queued"`.
   */
  blocked_reason?: string | null;
}

/**
 * Status poll while a PubMed/guideline job runs.
 * GET /api/agent/run/{id} is a fast in-memory read; keep this short so quick
 * tunnels (trycloudflare.com) and nginx do not cancel long-lived connections.
 */
const AGENT_RUN_POLL_TIMEOUT_MS = 20_000;

export async function fetchAgentRun(
  executionId: string,
): Promise<AgentRunPayloadV1> {
  return apiGet<AgentRunPayloadV1>(
    `/api/agent/run/${encodeURIComponent(executionId)}`,
    { timeoutMs: AGENT_RUN_POLL_TIMEOUT_MS },
  );
}
