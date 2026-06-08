import type { PubmedRole } from "../types/doctor";

export function pubmedRoleLabel(role: PubmedRole): string {
  switch (role) {
    case "research_leader":
      return "Led research";
    case "research_participant":
      return "Contributed";
    case "case_study_author":
      return "Case studies";
    default:
      return "Local contact";
  }
}
