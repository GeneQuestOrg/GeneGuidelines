import { apiGet, apiPostJson } from "./client";

/** Server profile for guideline runs + alias suggest. Use `production` (OpenAI) or `vllm`. */
export const DEFAULT_GUIDELINE_PROFILE = "production";

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
      profile,
    });
  }
  return apiPostJson<StartGuidelineRunResponse>("/api/pipeline/guideline-run", {
    disease_name: input.diseaseName,
    disease_aliases: input.diseaseAliases,
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

/** Status poll while a PubMed/guideline job runs — backend may be busy for minutes. */
const AGENT_RUN_POLL_TIMEOUT_MS = 120_000;

export async function fetchAgentRun(
  executionId: string,
): Promise<AgentRunPayloadV1> {
  return apiGet<AgentRunPayloadV1>(
    `/api/agent/run/${encodeURIComponent(executionId)}`,
    { timeoutMs: AGENT_RUN_POLL_TIMEOUT_MS },
  );
}
