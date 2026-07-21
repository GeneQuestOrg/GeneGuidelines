/** Typed clients for the rare-disease index endpoints exposed by
 * ``backend/disease_index/api.py`` — Tier 1 fuzzy autocomplete and
 * Tier 2 Gemma-backed wider search.
 *
 * The shape mirrors :class:`backend.disease_index.contracts` 1:1; field
 * names stay camelCase because the FastAPI DTOs already produce that.
 */

import { ApiRequestError, apiGet, apiPostJson } from "./client";

export type DiseaseCategory =
  | "genetic"
  | "predominantly_genetic"
  | "multifactorial"
  | "infectious"
  | "acquired"
  | "unknown";

export type DiseaseIndexSource = "orphanet" | "mondo" | "gard" | "manual";

export type AliasKind =
  | "canonical"
  | "synonym"
  | "omim"
  | "gene"
  | "orpha"
  | "icd10"
  | "locale_name";

export interface MatchedAlias {
  alias: string;
  kind: AliasKind;
  locale: string | null;
}

export interface DiseaseSuggestion {
  primaryId: string;
  source: DiseaseIndexSource;
  canonicalName: string;
  summary: string;
  omimCodes: string[];
  geneSymbols: string[];
  inheritance: string | null;
  category: DiseaseCategory | null;
  isInScope: boolean;
  localSlug: string | null;
  hasLocalRecord: boolean;
  matchedAlias: MatchedAlias;
  score: number;
  orphaUrl: string | null;
  omimUrl: string | null;
}

export interface SuggestResponse {
  query: string;
  suggestions: DiseaseSuggestion[];
  elapsedMs: number;
}

export interface WiderSearchCandidate {
  canonicalName: string;
  omim: string;
  gene: string;
  inheritance: string;
  summary: string;
  category: DiseaseCategory;
  isInScope: boolean;
  isHardBlocked: boolean;
  scopeLabel: string;
  confidence: number;
  modelUsed: string;
  /** Why this disease matches the query — surfaced to the user. */
  evidence: string;
}

export interface WiderSearchResponse {
  query: string;
  candidates: WiderSearchCandidate[];
  elapsedMs: number;
  /** Human-readable context: what was found / corrected / rejected / unidentified. */
  notes: string;
  /** True when a second, stronger model verified the candidates. */
  judged: boolean;
}

const _SUGGEST_TIMEOUT_MS = 4_000;

/** Tier 1 — local fuzzy lookup. Cheap; safe to call on every keystroke. */
export async function suggestDiseases(
  query: string,
  limit = 7,
): Promise<SuggestResponse> {
  const trimmed = query.trim();
  if (!trimmed) {
    return { query: "", suggestions: [], elapsedMs: 0 };
  }
  const params = new URLSearchParams({
    q: trimmed,
    limit: String(limit),
  });
  return apiGet<SuggestResponse>(
    `/api/disease-index/suggest?${params.toString()}`,
    { timeoutMs: _SUGGEST_TIMEOUT_MS },
  );
}

/** Tier 2 — Gemma-backed lookup. Slow (1–8 s), AI-priced. Triggered only
 * when the user opens the "missing disease" dialog and clicks search. */
export async function widerSearchDisease(
  query: string,
): Promise<WiderSearchResponse> {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    throw new ApiRequestError(400, "Type at least two characters before searching the literature.");
  }
  return apiPostJson<WiderSearchResponse>("/api/disease-index/wider-search", {
    query: trimmed,
  });
}
