import type { TrialSummary } from "../types";

export const TRIALS: readonly TrialSummary[] = [
  {
    nct: "NCT05882211",
    title: "Denosumab in progressive polyostotic FD in children",
    phase: "Phase 2",
    status: "recruiting",
    sponsor: "Leiden University Medical Center",
    city: "Leiden",
    country: "NL",
    diseases: ["fd"],
  },
  {
    nct: "NCT06112233",
    title: "Burosumab in FD/MAS with FGF23-related hypophosphatemia",
    phase: "Phase 3",
    status: "recruiting",
    sponsor: "Kyowa Kirin",
    city: "Berlin",
    country: "DE",
    diseases: ["fd", "mas"],
  },
  {
    nct: "NCT06223344",
    title: "Natural history study — adult craniofacial FD",
    phase: "Observational",
    status: "active",
    sponsor: "FD/MAS Alliance",
    city: "Boston",
    country: "US",
    diseases: ["fd"],
  },
  {
    nct: "NCT06334455",
    title: "MEK inhibitor in Noonan syndrome — pilot",
    phase: "Phase 1",
    status: "recruiting",
    sponsor: "Children's Hospital of Philadelphia",
    city: "Philadelphia",
    country: "US",
    diseases: ["noonan"],
  },
] as const;
