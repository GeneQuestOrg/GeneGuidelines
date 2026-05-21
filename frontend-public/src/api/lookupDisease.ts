import { apiPostJson } from "./client";

/** Single user query: disease name, HGNC gene symbol, or OMIM phenotype id. */
export interface LookupDiseaseMetadataRequest {
  name: string;
}

export interface LookupDiseaseMetadataResponse {
  canonical_name: string;
  omim: string;
  gene: string;
  inheritance: string;
  summary: string;
  model_used: string;
}

export async function lookupDiseaseMetadata(
  body: LookupDiseaseMetadataRequest,
): Promise<LookupDiseaseMetadataResponse> {
  return apiPostJson<LookupDiseaseMetadataResponse>(
    "/api/pipeline/lookup-disease-metadata",
    body,
  );
}
