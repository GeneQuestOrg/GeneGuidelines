import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type { DiseaseDoctorsPayload, PublicDoctor } from "../types/doctor";
import { normalizeDiseaseSlug } from "./slug";
import type { DoctorRepository } from "./types";

export const fixtureDoctorRepository: DoctorRepository = {
  async listAllDoctors(): Promise<readonly PublicDoctor[]> {
    return PUBLIC_DOCTORS;
  },

  async getDoctorBySlug(slug: string): Promise<PublicDoctor | null> {
    const trimmed = slug.trim().toLowerCase();
    return PUBLIC_DOCTORS.find((d) => d.slug === trimmed) ?? null;
  },

  async getDoctorsForDisease(diseaseSlug: string): Promise<DiseaseDoctorsPayload> {
    const slug = normalizeDiseaseSlug(diseaseSlug);
    if (slug == null) {
      return { diseaseSlug: diseaseSlug.trim().toLowerCase(), source: "none", doctors: [] };
    }
    const doctors = PUBLIC_DOCTORS.filter((d) => d.diseases.includes(slug));
    return {
      diseaseSlug: slug,
      source: doctors.length > 0 ? "content_seed" : "none",
      doctors,
    };
  },
};
