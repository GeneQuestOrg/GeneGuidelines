import type { Trial } from "../types/trial";
import type { TrialRepository } from "./types";

// Fixture mode only (VITE_DATA_SOURCE=fixture). The studies are invented, so nothing here may name a real institution, person or address: an invented trial under a real investigator's name is a false statement about that person.
const FIXTURE_TRIALS: readonly Trial[] = [
  {
    nct: "NCT99990001",
    title: "Example phase 2 study in fibrous dysplasia (fixture)",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Example University Hospital",
    city: "Utrecht",
    country: "NL",
    lat: 52.166,
    lng: 4.49,
    ageRange: "6-17",
    principalInvestigator: "Example Investigator",
    eligibilitySummary:
      "Patients 6-17 with polyostotic FD confirmed by GNAS, ≥2 pain episodes in the last 12 months.",
    enrollmentTarget: 60,
    enrolled: 23,
    contact: "trials@example.org",
    lastSeen: "2026-05-12",
    diseases: ["fd"],
  },
  {
    nct: "NCT99990002",
    title: "Example phase 3 study in FD/MAS (fixture)",
    phase: "Phase 3",
    status: "recruiting",
    sponsor: "Example Pharma",
    city: "Berlin",
    country: "DE",
    lat: 52.52,
    lng: 13.405,
    ageRange: "12+",
    principalInvestigator: "Example Investigator",
    eligibilitySummary:
      "FGF23 > 100 RU/mL, serum phosphate < 0.8 mmol/L, no prior burosumab exposure.",
    enrollmentTarget: 120,
    enrolled: 89,
    contact: "trials@example.org",
    lastSeen: "2026-05-10",
    diseases: ["fd", "mas"],
  },
  {
    nct: "NCT99990003",
    title: "Example phase 2 study in Noonan syndrome (fixture)",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Example Medical Center",
    city: "Rotterdam",
    country: "NL",
    lat: 51.923,
    lng: 4.469,
    ageRange: "5-17",
    principalInvestigator: "Example Investigator",
    eligibilitySummary:
      "Noonan syndrome with hypertrophic cardiomyopathy and PTPN11 or RIT1 mutation.",
    enrollmentTarget: 40,
    enrolled: 12,
    contact: "trials@example.org",
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
