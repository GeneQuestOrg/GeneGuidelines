import type { Trial } from "../types/trial";
import type { TrialRepository } from "./types";

const FIXTURE_TRIALS: readonly Trial[] = [
  {
    nct: "NCT05882211",
    title: "Denosumab in progressive polyostotic FD in children",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Leiden University Medical Center",
    city: "Leiden",
    country: "NL",
    lat: 52.166,
    lng: 4.49,
    ageRange: "6-17",
    principalInvestigator: "Dr. Appelman-Dijkstra",
    eligibilitySummary:
      "Patients 6-17 with polyostotic FD confirmed by GNAS, ≥2 pain episodes in the last 12 months.",
    enrollmentTarget: 60,
    enrolled: 23,
    contact: "fdmas-trials@lumc.nl",
    lastSeen: "2026-05-12",
    diseases: ["fd"],
  },
  {
    nct: "NCT06112233",
    title: "Burosumab in FD/MAS with FGF23-dependent hypophosphataemia",
    phase: "Phase 3",
    status: "recruiting",
    sponsor: "Kyowa Kirin",
    city: "Berlin",
    country: "DE",
    lat: 52.52,
    lng: 13.405,
    ageRange: "12+",
    principalInvestigator: "Prof. T. Schwarz",
    eligibilitySummary:
      "FGF23 > 100 RU/mL, serum phosphate < 0.8 mmol/L, no prior burosumab exposure.",
    enrollmentTarget: 120,
    enrolled: 89,
    contact: "trials@kyowa-kirin.eu",
    lastSeen: "2026-05-10",
    diseases: ["fd", "mas"],
  },
  {
    nct: "NCT06334455",
    title: "MEK inhibitor in cardiovascular complications of Noonan syndrome",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Erasmus MC",
    city: "Rotterdam",
    country: "NL",
    lat: 51.923,
    lng: 4.469,
    ageRange: "5-17",
    principalInvestigator: "Prof. de Graaf-Schoenmakers",
    eligibilitySummary:
      "Noonan syndrome with hypertrophic cardiomyopathy and PTPN11 or RIT1 mutation.",
    enrollmentTarget: 40,
    enrolled: 12,
    contact: "noonan-trials@erasmusmc.nl",
    lastSeen: "2026-05-09",
    diseases: ["noonan"],
  },
];

export const fixtureTrialRepository: TrialRepository = {
  async listAll(): Promise<readonly Trial[]> {
    return FIXTURE_TRIALS;
  },

  async listForDisease(diseaseSlug: string): Promise<readonly Trial[]> {
    return FIXTURE_TRIALS.filter((t) => t.diseases.includes(diseaseSlug));
  },
};
