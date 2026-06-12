/**
 * Fetch wrapper for backend API (FastAPI).
 * Dev (no VITE_API_URL): relative URLs — Vite proxies `/api` and `/health` → 127.0.0.1:8000 in `vite dev` and `vite preview`.
 * Static / prod: set `VITE_API_URL` to the API origin only (no `/api` suffix); request paths already include `/api/...`.
 */
import type { FlowDefinition, FlowNode, FlowEdge, FlowsMap } from "../types";
import { getAccessToken, getCachedAccessToken } from "./accessToken";

function resolveApiBase(): string {
  const raw = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  if (raw) {
    let base = raw.replace(/\/+$/, "");
    if (base.endsWith("/api")) {
      base = base.slice(0, -4);
    }
    return base.replace(/\/+$/, "");
  }
  return import.meta.env.DEV ? "" : "";
}

export const API_BASE = resolveApiBase();

function getOptionalApiKey(): string | undefined {
  const k = (import.meta.env.VITE_GENEGUIDELINES_API_KEY as string | undefined)?.trim();
  return k || undefined;
}

/** Headers for optional shared-secret auth (must match backend GENEGUIDELINES_API_KEY). */
function apiAuthHeaders(): Record<string, string> {
  const k = getOptionalApiKey();
  if (!k) return {};
  return { Authorization: `Bearer ${k}` };
}

/**
 * Auth headers preferring an Auth0 bearer token (admin superadmin session),
 * falling back to the legacy api-key header. Both credential modes supported.
 */
async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return apiAuthHeaders();
}

/**
 * EventSource cannot set Authorization. Prefer the cached Auth0 token via
 * ``access_token`` (mirrors the backend SSE contract), else fall back to the
 * legacy ``api_key`` query. Synchronous on purpose: SSE URL builders are sync,
 * so the token comes from the cache the auth gate keeps warm.
 */
function appendApiKeyQueryForSse(pathOrUrl: string): string {
  const sep = pathOrUrl.includes("?") ? "&" : "?";
  const token = getCachedAccessToken();
  if (token) {
    return `${pathOrUrl}${sep}access_token=${encodeURIComponent(token)}`;
  }
  const k = getOptionalApiKey();
  if (!k) return pathOrUrl;
  return `${pathOrUrl}${sep}api_key=${encodeURIComponent(k)}`;
}

/** API flow node (backend response) */
export interface ApiFlowNode {
  flow_key: string;
  node_id: string;
  node_type: string;
  label: string;
  description: string | null;
  prompt: string | null;
  loop_policy: string;
  execution_policy: string;
  max_retry: number;
  version: number;
  updated_at: string;
  position_x?: number | null;
  position_y?: number | null;
  python_source?: string | null;
  http_url?: string | null;
  http_method?: string | null;
  http_headers?: string | null;
  http_body?: string | null;
  rag_operation?: string | null;
  rag_body_json?: string | null;
  merge_strategy?: string | null;
  merge_fields?: string | null;
  merge_key_field?: string | null;
  integration_operation?: string | null;
  integration_params_json?: string | null;
  integration_credentials_json?: string | null;
}

/** API flow edge (backend response) */
export interface ApiFlowEdge {
  flow_key: string;
  source_node_id: string;
  target_node_id: string;
  label?: string | null;
}

/** API flow definition (backend response) */
export interface ApiFlowDefinition {
  flow_key: string;
  nodes: ApiFlowNode[];
  edges: ApiFlowEdge[];
}

/** API tool catalog item */
export interface ApiToolCatalogItem {
  id: number;
  name: string;
  category: string;
  execution_mode: string;
  scope: string;
  enabled: number;
}

/** API requested tool */
export interface ApiToolRequest {
  id: number;
  name: string;
  status: string;
  similarity_key: string | null;
  note: string | null;
  ticket_id: number | null;
  builder_agent_id: string | null;
  created_at: string;
  updated_at: string;
}

/** API implemented tool */
export interface ApiToolImplementation {
  id: number;
  name: string;
  status: string;
  pr_number: string | null;
  pr_url: string | null;
  created_at: string;
}

const REQUEST_TIMEOUT_MS = 15000;

type RequestOptions = RequestInit & { timeoutMs?: number };

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const url = `${API_BASE}${path}`;
  const opts = options ?? {};
  const timeoutMs = opts.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const fetchOptions: RequestInit = { ...opts };
  delete (fetchOptions as RequestInit & { timeoutMs?: number }).timeoutMs;
  const hasBody = fetchOptions.body != null;
  const headers: Record<string, string> = {
    ...(await authHeaders()),
    ...(fetchOptions.headers as Record<string, string>),
  };
  if (hasBody && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: fetchOptions.signal ?? controller.signal,
    });
  } catch (e) {
    clearTimeout(timeoutId);
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error(
        `Timeout - backend did not respond within ${timeoutMs / 1000} s. Check whether the server is running (for example http://127.0.0.1:8000/api/tickets).`
      );
    }
    throw e;
  }
  clearTimeout(timeoutId);
  if (!res.ok) {
    const errText = await res.text();
    let msg = errText || `HTTP ${res.status}`;
    try {
      const j = JSON.parse(errText) as { detail?: unknown };
      if (j?.detail != null && j.detail !== "") {
        const d = j.detail;
        if (typeof d === "string") {
          msg = d;
        } else if (Array.isArray(d)) {
          msg = d
            .map((item) => {
              if (item != null && typeof item === "object" && "msg" in item) {
                return String((item as { msg?: unknown }).msg);
              }
              try {
                return JSON.stringify(item);
              } catch {
                return String(item);
              }
            })
            .join("; ");
        } else if (typeof d === "object") {
          try {
            msg = JSON.stringify(d);
          } catch {
            msg = String(d);
          }
        } else {
          msg = String(d);
        }
      }
    } catch {
      // not JSON — keep errText
    }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  const raw = await res.text();
  const trimmed = raw.trimStart();
  if (
    trimmed.startsWith("<!") ||
    trimmed.toLowerCase().startsWith("<html") ||
    contentType.includes("text/html")
  ) {
    throw new Error(
      "Expected JSON from the API but received HTML — start uvicorn on :8000, use `npm run dev` (Vite proxies `/api`), set `VITE_API_URL`, or configure `preview.proxy` in vite.config (same as `server.proxy`).",
    );
  }
  if (raw.trim() === "") {
    throw new Error("Empty response body from API.");
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(
      `Response is not valid JSON. First characters: ${raw.slice(0, 120).trim()}`,
    );
  }
}

// --- Account (Auth0 superadmin gate) ---

export type AccountRole = "parent" | "doctor" | "researcher" | "superadmin";

/** Wire shape of `GET /api/account/me` (snake_case). */
export interface MeResponse {
  id: string;
  email: string;
  display_name: string | null;
  role: AccountRole | null;
  verified: boolean;
  orcid: string | null;
  institution: string | null;
}

/** The signed-in user's account. Used by the admin gate to check for `superadmin`. */
export async function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>("/api/account/me");
}

/** A user as seen in the superadmin Users view (`GET /api/account/users`). */
export interface AdminUser {
  id: string;
  auth0_sub: string;
  email: string;
  display_name: string | null;
  role: AccountRole | null;
  verified: boolean;
  orcid: string | null;
  institution: string | null;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

/** Superadmin: list every user (sorted by email server-side). */
export async function fetchUsers(): Promise<AdminUser[]> {
  return request<AdminUser[]>("/api/account/users");
}

/** Superadmin: patch a user's role and/or verified flag (`PATCH /api/account/users/{id}`). */
export async function patchUser(
  userId: string,
  patch: { role?: AccountRole; verified?: boolean }
): Promise<AdminUser> {
  return request<AdminUser>(`/api/account/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

// --- Flows ---

export async function fetchFlows(): Promise<ApiFlowDefinition[]> {
  try {
    return await request<ApiFlowDefinition[]>("/api/flows");
  } catch {
    return [];
  }
}

export async function fetchFlow(flowKey: string): Promise<ApiFlowDefinition> {
  return request<ApiFlowDefinition>(`/api/flows/${flowKey}?_t=${Date.now()}`, {
    headers: { "Cache-Control": "no-cache" },
  });
}

/** Save a node — same pattern as Tools: single URL, everything in body. */
export async function updateNodePrompt(
  flowKey: string,
  nodeId: string,
  data: Record<string, unknown>
): Promise<ApiFlowNode> {
  return request<ApiFlowNode>("/api/flows/node", {
    method: "PUT",
    body: JSON.stringify({ flow_key: flowKey, node_id: nodeId, ...data }),
  });
}

/** Create a flow node. The backend generates node_id (op-4, bl-10, …). */
export async function createFlowNode(
  flowKey: string,
  data: {
    node_type?: string;
    label?: string;
    description?: string;
    prompt?: string;
    loop_policy?: string;
    execution_policy?: string;
    max_retry?: number;
    python_source?: string;
    http_url?: string;
    http_method?: string;
    http_headers?: string;
    http_body?: string;
    rag_operation?: string;
    rag_body_json?: string;
    merge_strategy?: string;
    merge_fields?: string;
    merge_key_field?: string;
    integration_operation?: string;
    integration_params_json?: string;
    integration_credentials_json?: string;
  }
): Promise<ApiFlowNode> {
  return request<ApiFlowNode>(`/api/flows/${flowKey}/nodes`, {
    method: "POST",
    body: JSON.stringify({
      node_type: data.node_type ?? "action",
      label: data.label ?? "New node",
      description: data.description ?? "",
      prompt: data.prompt ?? "",
      loop_policy: data.loop_policy ?? "none",
      execution_policy: data.execution_policy ?? "auto",
      max_retry: data.max_retry ?? 3,
      python_source: data.python_source ?? "",
      http_url: data.http_url ?? "",
      http_method: data.http_method ?? "GET",
      http_headers: data.http_headers ?? "",
      http_body: data.http_body ?? "",
      rag_operation: data.rag_operation ?? "similar",
      rag_body_json: data.rag_body_json ?? "",
      merge_strategy: data.merge_strategy ?? "append",
      merge_fields: data.merge_fields ?? '["items"]',
      merge_key_field: data.merge_key_field ?? "id",
      integration_operation: data.integration_operation ?? "",
      integration_params_json: data.integration_params_json ?? "{}",
      integration_credentials_json: data.integration_credentials_json ?? "",
    }),
  });
}

/** Delete a node and all edges to/from it. */
export async function deleteFlowNode(
  flowKey: string,
  nodeId: string
): Promise<{ ok: boolean; deleted: string }> {
  return request<{ ok: boolean; deleted: string }>(
    `/api/flows/${flowKey}/nodes/${encodeURIComponent(nodeId)}`,
    { method: "DELETE" }
  );
}

/** Add an edge (connection) between nodes. */
export async function createFlowEdge(
  flowKey: string,
  sourceNodeId: string,
  targetNodeId: string,
  label?: string
): Promise<ApiFlowEdge> {
  return request<ApiFlowEdge>(`/api/flows/${flowKey}/edges`, {
    method: "POST",
    body: JSON.stringify({
      source_node_id: sourceNodeId,
      target_node_id: targetNodeId,
      label: label ?? null,
    }),
  });
}

/** Delete an edge. */
export async function deleteFlowEdge(
  flowKey: string,
  sourceNodeId: string,
  targetNodeId: string
): Promise<{ ok: boolean }> {
  const params = new URLSearchParams({
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
  });
  return request<{ ok: boolean }>(
    `/api/flows/${flowKey}/edges?${params}`,
    { method: "DELETE" }
  );
}

// --- Tools ---

export async function fetchToolCatalog(
  enabledOnly = true
): Promise<ApiToolCatalogItem[]> {
  return request<ApiToolCatalogItem[]>(
    `/api/tools/catalog?enabled_only=${enabledOnly}`
  );
}

export async function updateToolMode(
  toolId: number,
  data: { execution_mode: string }
): Promise<ApiToolCatalogItem> {
  return request<ApiToolCatalogItem>(`/api/tools/catalog/${toolId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function fetchRequestedTools(
  ticketId?: number
): Promise<ApiToolRequest[]> {
  const path =
    ticketId != null
      ? `/api/tools/requested?ticket_id=${ticketId}&_t=${Date.now()}`
      : `/api/tools/requested?_t=${Date.now()}`;
  return request<ApiToolRequest[]>(path, {
    headers: { "Cache-Control": "no-cache" },
  });
}

/** Request for builder — appends an entry to the requested queue (mimics request_missing_tool). */
export async function createToolRequest(data: {
  name: string;
  note?: string;
  ticket_id?: number | null;
}): Promise<ApiToolRequest> {
  return request<ApiToolRequest>("/api/tools/requested", {
    method: "POST",
    body: JSON.stringify({
      name: data.name,
      note: data.note ?? "",
      ticket_id: data.ticket_id ?? null,
    }),
  });
}

export async function fetchImplementedTools(): Promise<ApiToolImplementation[]> {
  return request<ApiToolImplementation[]>("/api/tools/implemented?_t=" + Date.now(), {
    headers: { "Cache-Control": "no-cache" },
  });
}

/** Builder step ("thought") — step name, message, and optional payload. */
export interface BuilderStep {
  step: string;
  msg: string | null;
  [key: string]: unknown;
}

/** Reservation result for Builder: runs the flow and returns its steps. */
export interface ReserveForBuilderResult {
  ok: boolean;
  reason?: string;
  request_id: number;
  steps: BuilderStep[];
  pr_url?: string | null;
  duplicate_of?: string | null;
}

const RESERVE_TIMEOUT_MS = 120000;

/** Reserve a request for Builder, run the flow (implementation, PR) and return its steps ("thoughts"). */
export async function reserveForBuilder(
  requestId: number,
  body?: { builder_agent_id?: string }
): Promise<ReserveForBuilderResult> {
  const url = `${API_BASE}/api/tools/requested/${requestId}/reserve`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), RESERVE_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify(body ?? {}),
      signal: controller.signal,
    });
  } catch (e) {
    clearTimeout(timeoutId);
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error(
        `Timeout - Builder did not respond within ${RESERVE_TIMEOUT_MS / 1000} s. Check the backend.`
      );
    }
    throw e;
  }
  clearTimeout(timeoutId);
  const data = (await res.json()) as ReserveForBuilderResult;
  return data;
}

// --- Tickets (optional usage) ---

export async function fetchTickets(): Promise<unknown[]> {
  try {
    return await request<unknown[]>("/api/tickets");
  } catch {
    return [];
  }
}

export async function fetchTicket(id: number): Promise<unknown> {
  return request<unknown>(`/api/tickets/${id}`);
}

// --- Agent (run + SSE trace) ---

export type ModelProfile = "production" | "test" | "openrouter" | "vllm";

export async function agentRun(
  ticketId: number,
  flowKey?: string,
  profile?: ModelProfile,
): Promise<{ execution_id: string; status: string }> {
  const qs = new URLSearchParams();
  if (flowKey) qs.set("flow_key", flowKey);
  if (profile) qs.set("profile", profile);
  const query = qs.toString();
  const params = query ? `?${query}` : "";
  return request<{ execution_id: string; status: string }>(
    `/api/agent/run/${ticketId}${params}`,
    { method: "POST" }
  );
}

/** EventSource URL for the trace stream (SSE). */
export function agentTraceUrl(executionId: string): string {
  return appendApiKeyQueryForSse(`${API_BASE}/api/agent/trace/${executionId}`);
}

/** One missing-tool request from the agent. */
export interface MissingToolRequest {
  tool_name: string;
  reason: string;
  ticket_id?: number;
}

export interface PubmedQualityEvalSnapshot {
  ok?: boolean;
  issues_found?: boolean;
  quality_summary?: string;
  correction_instructions?: string;
  issues?: unknown[];
  issue_count?: number;
}

export interface PubmedQualitySnapshot {
  pm_eval?: PubmedQualityEvalSnapshot;
  pm_fix?: { applied?: boolean; disease_name?: string };
  targeted_retry?: {
    retried_sections?: string[];
    planned_retry_count?: number;
  };
}

/** Agent run result (AI Summary, Diagnostics, output). */
export interface AgentRunResult {
  contract_version?: string;
  execution_id: string;
  ticket_id: number;
  done: boolean;
  error: string | null;
  output: string | null;
  structured_output?: Record<string, unknown> | null;
  quality_snapshot?: PubmedQualitySnapshot | null;
  ai_summary: { issue: string; work_log_summary: string };
  diagnostics_entries: { tool: string; result: string; detail?: string }[];
  steps_completed_by_ai?: number[];
  missing_tool_requests?: MissingToolRequest[];
}

export async function fetchAgentRunResult(
  executionId: string
): Promise<AgentRunResult> {
  return request<AgentRunResult>(`/api/agent/run/${executionId}`);
}

/** Summary row from GET /api/agent/runs (in-memory server runs). */
export interface AgentRunListItem {
  execution_id: string;
  ticket_id: number;
  flow_key: string;
  profile: string;
  status: string;
  done: boolean;
  error: string | null;
  started_at: string | null;
}

export async function fetchAgentRuns(): Promise<AgentRunListItem[]> {
  try {
    const data = await request<{ runs: AgentRunListItem[] }>("/api/agent/runs");
    return data.runs ?? [];
  } catch {
    return [];
  }
}

export type PipelineKind = "guideline" | "doctor_finder" | "parent_pathway" | "legacy";

export interface PipelineRunItem {
  execution_id: string;
  pipeline: PipelineKind;
  label: string;
  status: string;
  done: boolean;
  error: string | null;
  started_at: string | null;
}

export async function fetchPipelineRuns(): Promise<PipelineRunItem[]> {
  try {
    const data = await request<{ runs: PipelineRunItem[] }>("/api/pipeline/runs");
    return data.runs ?? [];
  } catch {
    return [];
  }
}

/** Disease row from public content API (camelCase). */
export interface GuidelinePromptProfile {
  clinicalFraming: string;
  pubmedRetrieval: string;
  synthesisEmphasis: string;
  homonymsToAvoid: string[];
  preferredTerms: string[];
}

export interface ContentDiseaseOption {
  slug: string;
  name: string;
  nameShort: string;
  gene: string;
  summary: string;
  coverage: "full" | "skeleton";
  guidelinePromptProfile?: GuidelinePromptProfile;
}

export async function fetchDiseaseGuidelinePromptProfile(
  slug: string,
): Promise<GuidelinePromptProfile> {
  const data = await request<{ guidelinePromptProfile: GuidelinePromptProfile }>(
    `/api/pipeline/diseases/${encodeURIComponent(slug)}/guideline-prompt-profile`,
    { timeoutMs: 30_000 },
  );
  return data.guidelinePromptProfile;
}

export async function updateDiseaseGuidelinePromptProfile(
  slug: string,
  profile: GuidelinePromptProfile,
): Promise<GuidelinePromptProfile> {
  const data = await request<{ guidelinePromptProfile: GuidelinePromptProfile }>(
    `/api/pipeline/diseases/${encodeURIComponent(slug)}/guideline-prompt-profile`,
    { method: "PUT", body: JSON.stringify(profile) },
  );
  return data.guidelinePromptProfile;
}

export async function fetchContentDiseases(): Promise<ContentDiseaseOption[]> {
  const rows = await request<ContentDiseaseOption[]>("/api/diseases", {
    timeoutMs: 30_000,
  });
  return rows ?? [];
}

export type GuidelinePrStatus =
  | "pending"
  | "under-review"
  | "verified"
  | "rejected";

export type GuidelinePrReviewAction =
  | "publish"
  | "reject"
  | "request_changes";

export interface GuidelinePrSummary {
  id: string;
  disease: string;
  title: string;
  opened: string;
  status: GuidelinePrStatus;
}

export interface GuidelinePrDiffLine {
  type: "added" | "removed";
  text: string;
}

export interface GuidelinePrPaper {
  pmid: string;
  title: string;
  year: number;
}

export interface GuidelinePrDetail extends GuidelinePrSummary {
  author: string;
  reviewer: string | null;
  summary: string;
  citationsCount: number;
  diff: GuidelinePrDiffLine[];
  papers: GuidelinePrPaper[];
}

export async function fetchGuidelinePrs(
  status?: GuidelinePrStatus,
): Promise<GuidelinePrSummary[]> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const rows = await request<GuidelinePrSummary[]>(
    `/api/guideline-prs${params}`,
    { timeoutMs: 30_000 },
  );
  return rows ?? [];
}

export async function fetchGuidelinePrDetail(
  prId: string,
): Promise<GuidelinePrDetail> {
  return request<GuidelinePrDetail>(
    `/api/guideline-prs/${encodeURIComponent(prId)}`,
    { timeoutMs: 30_000 },
  );
}

export async function reviewGuidelinePr(
  prId: string,
  action: GuidelinePrReviewAction,
  reviewer?: string,
): Promise<GuidelinePrDetail> {
  return request<GuidelinePrDetail>(
    `/api/pipeline/guideline-prs/${encodeURIComponent(prId)}/review`,
    {
      method: "POST",
      body: JSON.stringify({ action, reviewer }),
    },
  );
}

export interface ModelProfileSettings {
  id: ModelProfile;
  label: string;
  simpleModel: string;
  agenticModel: string;
  overflowModel: string | null;
  ready: boolean;
  missingEnvVars: string[];
}

export interface IntegrationSetting {
  id: string;
  label: string;
  envVar: string;
  configured: boolean;
  optional: boolean;
  description: string;
}

export interface RuntimeSettings {
  apiKeyGateEnabled: boolean;
  agentRunTimeoutSec: number;
  mcpEnabled: boolean;
  qualityFirstHardMode: boolean;
}

export interface OperatorSettings {
  defaultModelProfile: ModelProfile;
  singleLlmMode?: boolean;
  singleLlmModel?: string | null;
  modelProfiles: ModelProfileSettings[];
  integrations: IntegrationSetting[];
  runtime: RuntimeSettings;
}

export async function fetchPipelineSettings(): Promise<OperatorSettings> {
  return request<OperatorSettings>("/api/pipeline/settings", {
    timeoutMs: 30_000,
  });
}

export async function startGuidelineRun(
  diseaseSlug: string,
  profile?: ModelProfile,
): Promise<{ execution_id: string; status: string }> {
  return request<{ execution_id: string; status: string }>("/api/pipeline/guideline-run", {
    method: "POST",
    body: JSON.stringify({ disease_slug: diseaseSlug, profile: profile ?? "vllm" }),
  });
}

export async function startPathwayRun(
  diseaseSlug: string,
  profile?: ModelProfile,
  options?: { locale?: string; refreshPubmed?: boolean },
): Promise<{ execution_id: string; status: string }> {
  return request<{ execution_id: string; status: string }>("/api/pipeline/pathway-run", {
    method: "POST",
    body: JSON.stringify({
      disease_slug: diseaseSlug,
      profile: profile ?? "vllm",
      locale: options?.locale ?? "en",
      refresh_pubmed: Boolean(options?.refreshPubmed),
    }),
  });
}

export async function publishParentPathway(
  diseaseSlug: string,
): Promise<{ diseaseSlug: string; version: string }> {
  return request<{ diseaseSlug: string; version: string }>("/api/pipeline/pathway-publish", {
    method: "POST",
    body: JSON.stringify({ disease_slug: diseaseSlug }),
  });
}

/** Whether the agent is waiting for action approval (e.g. server restart). */
export interface ApprovalPending {
  tool_name: string;
  service_name: string;
  server_ip: string;
  reason: string;
}

/** Poll whether the agent is waiting for approval. Never throws — on error/404 returns { pending: null }. */
export async function getApprovalPending(): Promise<{
  pending: ApprovalPending | null;
  execution_id?: string;
}> {
  const url = `${API_BASE}/api/agent/approval-pending`;
  try {
    const res = await fetch(url, { method: "GET", headers: { ...(await authHeaders()) } });
    if (!res.ok) return { pending: null };
    const j = (await res.json()) as { pending?: ApprovalPending | null; execution_id?: string };
    return { pending: j.pending ?? null, execution_id: j.execution_id };
  } catch {
    return { pending: null };
  }
}

export async function postApproval(
  action: "approve" | "reject",
  executionId?: string | null
): Promise<{ status: string; action: string }> {
  const body: { action: string; execution_id?: string } = { action };
  if (executionId) {
    body.execution_id = executionId;
  }
  return request<{ status: string; action: string }>("/api/agent/approval", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Convert API flow definition to app FlowDefinition (labels from fallback if provided). */
export function apiFlowToFlowDefinition(
  api: ApiFlowDefinition,
  fallback?: { label: string; desc: string }
): FlowDefinition {
  const nodes: FlowNode[] = api.nodes.map((n) => ({
    id: n.node_id,
    type: n.node_type as FlowNode["type"],
    label: n.label,
    desc: n.description ?? "",
    prompt: n.prompt ?? "",
    merge_strategy: n.merge_strategy ?? "append",
    merge_fields: n.merge_fields ?? '["items"]',
    merge_key_field: n.merge_key_field ?? "id",
    integration_operation: n.integration_operation ?? "",
    integration_params_json: n.integration_params_json ?? "{}",
    integration_credentials_json: n.integration_credentials_json ?? "",
    python_source: n.python_source ?? "",
    http_url: n.http_url ?? "",
    http_method: n.http_method ?? "GET",
    http_headers: n.http_headers ?? "",
    http_body: n.http_body ?? "",
    rag_operation: n.rag_operation ?? "similar",
    rag_body_json: n.rag_body_json ?? "",
    loop_policy: n.loop_policy ?? "",
    execution_policy: n.execution_policy ?? "",
    max_retry: n.max_retry ?? 3,
    position:
      n.position_x != null && n.position_y != null
        ? { x: n.position_x, y: n.position_y }
        : undefined,
  }));
  const edges: FlowEdge[] = api.edges.map((e) => ({
    source: e.source_node_id,
    target: e.target_node_id,
    ...(e.label ? { label: e.label } : {}),
  }));
  return {
    label: fallback?.label ?? api.flow_key,
    desc: fallback?.desc ?? "",
    nodes,
    edges,
  };
}

// --- Doctor Finder API ---

export async function doctorFinderRun(
  input: import("../types").DoctorFinderInput
): Promise<{ execution_id: string; status: string }> {
  return request<{ execution_id: string; status: string }>(
    "/api/doctor-finder/run",
    { method: "POST", body: JSON.stringify(input) }
  );
}

export function doctorFinderTraceUrl(executionId: string): string {
  return appendApiKeyQueryForSse(`${API_BASE}/api/doctor-finder/trace/${executionId}`);
}

export async function doctorFinderGetResult(
  executionId: string,
  opts?: { timeoutMs?: number }
): Promise<import("../types").DoctorFinderRunResult> {
  return request<import("../types").DoctorFinderRunResult>(`/api/doctor-finder/run/${executionId}`, {
    method: "GET",
    timeoutMs: opts?.timeoutMs ?? 120_000,
  });
}

const DOCTOR_FINDER_LLM_TIMEOUT_MS = 120_000;

export async function doctorFinderSuggestAliases(
  body: import("../types").DoctorFinderAliasSuggestInput
): Promise<{ aliases: string[] }> {
  return request<{ aliases: string[] }>("/api/doctor-finder/suggest-aliases", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: DOCTOR_FINDER_LLM_TIMEOUT_MS,
  });
}

/** Fetch flows from API and convert to FlowsMap; use fallbackLabels for flow labels. */
export async function fetchFlowsMap(
  fallbackLabels: FlowsMap
): Promise<FlowsMap> {
  try {
    const list = await fetchFlows();
    const map: FlowsMap = { ...fallbackLabels };
    for (const def of list) {
      const fallback = fallbackLabels[def.flow_key];
      map[def.flow_key] = apiFlowToFlowDefinition(def, {
        label: fallback?.label ?? def.flow_key,
        desc: fallback?.desc ?? "",
      });
    }
    return map;
  } catch {
    return fallbackLabels;
  }
}
