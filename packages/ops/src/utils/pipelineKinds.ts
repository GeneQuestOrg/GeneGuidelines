/** Finder workflows started by POST /api/pipeline/bootstrap-disease. */
export const DISEASE_BOOTSTRAP_PIPELINES = [
  "official_guidelines_finder",
  "trials_finder",
  "therapies_finder",
  "foundations_finder",
] as const;

export type DiseaseBootstrapPipeline = (typeof DISEASE_BOOTSTRAP_PIPELINES)[number];

export function isDiseaseBootstrapPipeline(pipeline: string): pipeline is DiseaseBootstrapPipeline {
  return (DISEASE_BOOTSTRAP_PIPELINES as readonly string[]).includes(pipeline);
}

export const DISEASE_BOOTSTRAP_PIPELINE_LABEL: Record<DiseaseBootstrapPipeline, string> = {
  official_guidelines_finder: "Official guidelines",
  trials_finder: "Clinical trials",
  therapies_finder: "Therapies",
  foundations_finder: "Foundations",
};
