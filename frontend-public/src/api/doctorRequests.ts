import { apiPostJson } from "./client";

export type DoctorRequestKind = "removal" | "correction";
export type DoctorRequestRelation = "self" | "representative";

export interface DoctorRequestPayload {
  kind: DoctorRequestKind;
  relation: DoctorRequestRelation;
  email: string;
  message?: string;
}

/** A clinician's GDPR request about their own directory entry — emailed to the foundation, stored nowhere. */
export async function submitDoctorRequest(
  slug: string,
  payload: DoctorRequestPayload,
): Promise<{ status: string }> {
  return apiPostJson<{ status: string }>(
    `/api/doctors/${encodeURIComponent(slug)}/requests`,
    payload,
  );
}
