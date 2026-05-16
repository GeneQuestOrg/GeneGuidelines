/** Single node in a flow (trigger, prompt, action, etc.) */
export interface FlowNode {
  id: string;
  type: NodeType;
  label: string;
  desc: string;
  prompt: string;
  python_source?: string;
  http_url?: string;
  http_method?: string;
  http_headers?: string;
  http_body?: string;
  rag_operation?: string;
  rag_body_json?: string;
  /** Merge: strategy for combining predecessor outputs. */
  merge_strategy?: "append" | "zip" | "combine_by_key" | string;
  /** Merge: JSON list of keys/fields to merge, e.g. ["items","rows"]. */
  merge_fields?: string;
  /** Merge: key field used for combine_by_key, e.g. "id". */
  merge_key_field?: string;
  /** Integration: which provider operation to run (e.g. message/invite/create/update/send). */
  integration_operation?: string;
  /** Integration: JSON string with operation parameters. */
  integration_params_json?: string;
  /** Integration: JSON string with credentials/tokens (stored server-side). */
  integration_credentials_json?: string;
  /** Optional schema preset key for prompt/action output (e.g. ai_summary). */
  output_schema_key?: string;
  /** Optional custom JSON schema string for prompt/action output. */
  output_schema?: string;
  loop_policy?: string;
  execution_policy?: string;
  max_retry?: number;
  /** Position on canvas (saved when user drags). */
  position?: { x: number; y: number };
}

export interface FlowEdgeObject {
  source: string;
  target: string;
  label?: string;
}

export type FlowEdge = FlowEdgeObject | [string, string];

export type NodeType =
  | "trigger"
  | "prompt"
  | "action"
  | "decision"
  | "loop"
  | "approval"
  | "code"
  | "http_request"
  | "rag"
  | "merge"
  | "slack"
  | "jira"
  | "entra"
  | "email"
  | "output"
  | "end"
  | "guidelines_rag"
  | "pmid_verify"
  | "pmid_scrub"
  | "evaluation_check"
  | "pubmed_authors_fetch"
  | "doctor_finder_step"
  | "doctor_finder_ai_justification";

/** Flow definition: label, description, nodes, edges */
export interface FlowDefinition {
  label: string;
  desc: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

/** Map of flow key to definition */
export type FlowsMap = Record<string, FlowDefinition>;

/** Node style (colors, label for type) */
export interface NodeStyle {
  color: string;
  bg: string;
  border: string;
  dot: string;
  label: string;
  /** Short description of the node role (UI / docs panel). */
  description?: string;
}

/** Tool in catalog (execution_mode = auto | approval); id from API for updates */
export interface Tool {
  id?: number;
  name: string;
  category: string;
  auto: boolean;
  scope: "operational" | "builder";
}

/** Requested tool in queue */
export interface RequestedTool {
  id?: number;
  name: string;
  status: "requested" | "in_progress" | "pr_created" | "merged";
  sim: string | null;
  note: string;
}

/** Implemented tool (PR) */
export interface ImplementedTool {
  name: string;
  status: "pr_created" | "merged";
  pr: string;
  url: string;
}

/** Governance rule card */
export interface GovernanceRule {
  title: string;
  desc: string;
  v: "enabled" | "strict";
}

// --- Doctor Finder types ---

export interface DoctorFinderInput {
  disease_name: string;
  disease_aliases?: string[];
  country?: string | null;
  continent?: string | null;
  max_results?: number;
  top_n_authors?: number;
  ai_justification?: boolean;
  ai_justification_threshold?: number;
  /** Backend LLM profile: production | test | openrouter */
  model_profile?: string;
  /** e.g. openai:gpt-4o-mini — overrides profile simple model for LLM steps */
  llm_model_override?: string | null;
  /** When true, backend merges AI-suggested aliases before PubMed */
  ai_generate_aliases?: boolean;
}

/** POST /api/doctor-finder/suggest-aliases */
export interface DoctorFinderAliasSuggestInput {
  disease_name: string;
  model_profile?: string;
  llm_model_override?: string | null;
}

export interface AuthorFlags {
  guideline_author: boolean;
  cites_current_guidelines: boolean;
  active_last_2y: boolean;
  runs_clinical_trial: boolean;
  international_collab: boolean;
}

export interface KeyPaper {
  pmid: string;
  title: string;
  year: number | null;
  pubmed_url: string;
  article_type: string;
}

export interface EvidenceSummary {
  guideline_papers: number;
  review_papers: number;
  original_papers: number;
  case_reports: number;
}

export interface DoctorEntry {
  rank: number;
  author_key: string;
  display_name: string;
  affiliation: string | null;
  country: string | null;
  continent: string | null;
  role: string;
  score: number;
  flags: AuthorFlags;
  key_papers: KeyPaper[];
  evidence_summary: EvidenceSummary;
  ai_justification: string | null;
}

export interface DoctorReport {
  disease_name: string;
  query_text: string;
  total_papers_scanned: number;
  total_authors_found: number;
  top_authors: DoctorEntry[];
  markdown: string;
}

export interface DoctorFinderRunResult {
  execution_id: string;
  disease_name: string;
  done: boolean;
  error: string | null;
  doctor_report: DoctorReport | null;
}
