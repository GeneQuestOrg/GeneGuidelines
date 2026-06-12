import type { DoctorTier, PublicDoctor, PubmedRole } from "../types/doctor";

export const VALID_PUBMED_ROLES = new Set<string>([
  "research_leader",
  "research_participant",
  "case_study_author",
  "unknown",
]);

/**
 * Per-disease experience tier with a global-role fallback: experienceByDisease keys can
 * legitimately be a subset of diseases[] (curated rows without the map, merged rows).
 */
export function tierForDisease(doctor: PublicDoctor, diseaseSlug: string): DoctorTier {
  return doctor.experienceByDisease?.[diseaseSlug] ?? doctor.pubmedRole;
}

export function pubmedRoleLabel(role: PubmedRole): string {
  switch (role) {
    case "research_leader":
      return "Led research";
    case "research_participant":
      return "Contributed";
    case "case_study_author":
      return "Case studies";
    default:
      return "Unknown";
  }
}
