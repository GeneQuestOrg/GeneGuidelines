import { CONTENT_PRS } from "./prs";
import { DISEASES } from "./diseases";
import { DOCTORS } from "./doctors";
import { TRIALS } from "./trials";
import type { CatalogStats } from "../types";

export function computeCatalogStats(): CatalogStats {
  const openPrCount = CONTENT_PRS.filter(
    (pr) => pr.status !== "verified" && pr.status !== "rejected",
  ).length;
  const recruitingTrialCount = TRIALS.filter((t) => t.status === "recruiting").length;

  return {
    diseaseCount: DISEASES.length,
    doctorCount: DOCTORS.length,
    recruitingTrialCount,
    openPrCount,
  };
}
