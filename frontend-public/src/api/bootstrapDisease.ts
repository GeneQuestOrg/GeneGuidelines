import { apiPostJson } from "./client";

export interface BootstrapDiseaseRequest {
  slug: string;
  name: string;
  name_short?: string;
  gene?: string;
  omim?: string;
  inheritance?: string;
  summary?: string;
  prevalence_text?: string;
  profile?: string;
}

export interface BootstrapDiseaseResponse {
  disease_slug: string;
  created: boolean;
  status: "running";
  execution_ids: {
    official_guidelines: string;
    trials: string;
    therapies: string;
    foundations: string;
    doctor_finder: string;
    guideline: string;
  };
}

export async function bootstrapDisease(
  body: BootstrapDiseaseRequest,
): Promise<BootstrapDiseaseResponse> {
  return apiPostJson<BootstrapDiseaseResponse>(
    "/api/pipeline/bootstrap-disease",
    body,
  );
}
