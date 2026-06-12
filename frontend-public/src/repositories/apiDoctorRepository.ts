import { apiGet, apiPostJson, ApiRequestError } from "../api/client";
import type {
  ContributionReviewStatus,
  DiseaseDoctorsPayload,
  DoctorSubmissionInput,
  DoctorSubmissionResult,
  ParentRecInput,
  ParentRecResult,
  PublicDoctor,
} from "../types/doctor";
import type { DoctorRepository } from "./types";

/** Wire shape of `POST /api/doctors/submissions` (snake_case, backend canon). */
interface DoctorSubmissionResponse {
  id: string;
  slug: string;
  name: string;
  review_status: ContributionReviewStatus;
  possible_duplicate: boolean;
}

/** Wire shape of `POST /api/doctors/{slug}/parent-recs`. */
interface ParentRecResponse {
  id: string;
  doctor_slug: string;
  review_status: ContributionReviewStatus;
}

export const apiDoctorRepository: DoctorRepository = {
  async listAllDoctors(): Promise<readonly PublicDoctor[]> {
    return apiGet<readonly PublicDoctor[]>("/api/doctors");
  },

  async getDoctorBySlug(slug: string): Promise<PublicDoctor | null> {
    const trimmed = slug.trim();
    if (!trimmed) {
      return null;
    }
    try {
      return await apiGet<PublicDoctor>(`/api/doctors/${encodeURIComponent(trimmed)}`);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  async getDoctorsForDisease(diseaseSlug: string): Promise<DiseaseDoctorsPayload> {
    const trimmed = diseaseSlug.trim();
    return apiGet<DiseaseDoctorsPayload>(
      `/api/diseases/${encodeURIComponent(trimmed)}/doctors`,
    );
  },

  async submitDoctor(input: DoctorSubmissionInput): Promise<DoctorSubmissionResult> {
    const row = await apiPostJson<DoctorSubmissionResponse>(
      "/api/doctors/submissions",
      {
        name: input.name,
        specialty: input.specialty ?? "",
        institution: input.institution ?? "",
        city: input.city ?? "",
        country: input.country ?? "",
        disease_slug: input.diseaseSlug ?? "",
        note: input.note ?? "",
      },
    );
    return {
      id: row.id,
      slug: row.slug,
      name: row.name,
      reviewStatus: row.review_status,
      possibleDuplicate: row.possible_duplicate,
    };
  },

  async submitParentRec(
    doctorSlug: string,
    input: ParentRecInput,
  ): Promise<ParentRecResult> {
    const row = await apiPostJson<ParentRecResponse>(
      `/api/doctors/${encodeURIComponent(doctorSlug.trim())}/parent-recs`,
      {
        text: input.text,
        region: input.region ?? null,
        relation: input.relation ?? "parent",
      },
    );
    return {
      id: row.id,
      doctorSlug: row.doctor_slug,
      reviewStatus: row.review_status,
    };
  },
};
