import type { TrialSummary } from "../types";

export const TRIALS: readonly TrialSummary[] = [
  {
    nct: "NCT99990001",
    title: "Example phase 2 study in fibrous dysplasia (fixture)",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Example University Hospital",
    city: "Utrecht",
    country: "NL",
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
    diseases: ["fd", "mas"],
  },
  {
    nct: "NCT99990004",
    title: "Example natural history study in fibrous dysplasia (fixture)",
    phase: "Observational",
    status: "active",
    sponsor: "Example Patient Organisation",
    city: "Boston",
    country: "US",
    diseases: ["fd"],
  },
  {
    nct: "NCT99990003",
    title: "Example phase 1 study in Noonan syndrome (fixture)",
    phase: "Phase 1",
    status: "recruiting",
    sponsor: "Example Children's Hospital",
    city: "Philadelphia",
    country: "US",
    diseases: ["noonan"],
  },
] as const;
