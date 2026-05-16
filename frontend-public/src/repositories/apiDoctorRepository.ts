import { apiGet, ApiRequestError } from "../api/client";
import type { DiseaseDoctorsPayload, PublicDoctor } from "../types/doctor";
import type { DoctorRepository } from "./types";

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
};
