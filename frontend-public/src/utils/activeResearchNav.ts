import type { ResearchRun } from "../types/researchRun";

/** Sentinel execution id for disease-scoped progress when no pubmed run id is on the card. */
export const RESEARCH_LIVE_EXECUTION_ID = "live";

/** Hash path for an active-research card ("Watch live"). */
export function hrefForActiveResearchRun(run: ResearchRun): string {
  const slug = run.diseaseSlug?.trim() ?? "";
  const params = new URLSearchParams();
  if (slug) {
    params.set("disease", slug);
  }
  const label = run.label.trim();
  if (label) {
    params.set("name", label);
  }
  const qs = params.toString() ? `?${params.toString()}` : "";

  if (run.flowKey === "pubmed") {
    return `/research/${encodeURIComponent(run.runId)}${qs}`;
  }
  if (slug) {
    return `/research/${RESEARCH_LIVE_EXECUTION_ID}${qs}`;
  }
  return "/start-research";
}
