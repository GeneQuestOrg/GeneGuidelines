import type { Disease } from "../types";
import type { OfficialGuideline } from "../types/officialGuideline";

/**
 * Whether a page may say an agreed guideline exists for this disease. A disease still marked `pending` can have an official guideline on record (FD: the 2019 FD/MAS consensus, PMID 31196103), and telling that family "there is no agreed guideline" is false, so the recorded pointer counts as much as the status.
 */
export function hasOfficialGuideline(
  disease: Pick<Disease, "status">,
  pointer: OfficialGuideline | null,
): boolean {
  return pointer != null || disease.status !== "pending";
}
