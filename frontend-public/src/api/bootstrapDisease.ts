import { apiPostJson } from "./client";
import { getAnonSessionId } from "../utils/anonSession";

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

/**
 * Admission response (RES-1). The fan-out no longer fires synchronously: the
 * job is admitted to a fair-share queue and `execution_id` is the guideline
 * run the frontend polls/navigates to. New diseases come back `listed: false`
 * (unlisted-until-approve).
 */
export interface BootstrapDiseaseResponse {
  disease_slug: string;
  created: boolean;
  listed: boolean;
  status: "queued";
  execution_id: string;
  queue_position: number | null;
}

export async function bootstrapDisease(
  body: BootstrapDiseaseRequest,
): Promise<BootstrapDiseaseResponse> {
  // Anonymous callers identify their browser so the backend can enforce the
  // per-session pending cap; signed-in callers send a Bearer token (added by
  // the client) and are not capped, but the header is harmless either way.
  return apiPostJson<BootstrapDiseaseResponse>(
    "/api/pipeline/bootstrap-disease",
    body,
    { "X-Anon-Session": getAnonSessionId() },
  );
}
