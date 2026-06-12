import { PUBLIC_DOCTORS } from "../data/publicDoctors";
import type {
  DiseaseDoctorsPayload,
  DoctorSubmissionInput,
  DoctorSubmissionResult,
  ParentRecInput,
  ParentRecResult,
  PublicDoctor,
} from "../types/doctor";
import { normalizeDiseaseSlug } from "./slug";
import type { DoctorRepository } from "./types";

/** Offline slugifier mirroring the backend's `slugify_doctor_name`. */
function fixtureSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 64) || "clinician";
}

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

  async submitDoctor(input: DoctorSubmissionInput): Promise<DoctorSubmissionResult> {
    const slug = fixtureSlug(input.name);
    return {
      id: `fixture-${slug}`,
      slug,
      name: input.name.trim(),
      reviewStatus: "pending",
      // Collides when an existing fixture doctor already owns the slug.
      possibleDuplicate: PUBLIC_DOCTORS.some((d) => d.slug === slug),
    };
  },

  async submitParentRec(
    doctorSlug: string,
    input: ParentRecInput,
  ): Promise<ParentRecResult> {
    return {
      id: `fixture-rec-${input.text.length}-${Math.random().toString(36).slice(2, 10)}`,
      doctorSlug: doctorSlug.trim().toLowerCase(),
      reviewStatus: "pending",
    };
  },
};
