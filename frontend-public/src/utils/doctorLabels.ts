import type { PubmedRole } from "../types/doctor";

export const VALID_PUBMED_ROLES = new Set<string>([
  "research_leader",
  "research_participant",
  "case_study_author",
  "unknown",
]);

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
