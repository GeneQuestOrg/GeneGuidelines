import { apiGet, apiPostJson } from "./client";

export const DEFAULT_GUIDELINE_PROFILE = "production";

export interface StartGuidelineRunResponse {
  execution_id: string;
  status: string;
  ticket_id?: number;
}

export async function startGuidelineRunPublic(
  diseaseSlug: string,
  profile: string = DEFAULT_GUIDELINE_PROFILE,
): Promise<StartGuidelineRunResponse> {
  return apiPostJson<StartGuidelineRunResponse>("/api/pipeline/guideline-run", {
    disease_slug: diseaseSlug,
    profile,
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
}

export async function fetchAgentRun(
  executionId: string,
): Promise<AgentRunPayloadV1> {
  return apiGet<AgentRunPayloadV1>(
    `/api/agent/run/${encodeURIComponent(executionId)}`,
  );
}
