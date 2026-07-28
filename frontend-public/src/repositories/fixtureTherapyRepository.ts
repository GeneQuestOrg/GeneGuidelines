import type { Therapy } from "../types/therapy";
import type { TherapyRepository } from "./types";

// Offline/dev fixture — mirrors the real serve contract: `status` follows
// PMID-presence ("sourced" when >=1 PMID, else "unverified"). One row carries a
// real PMID so the "source-backed" label + PubMed link render without a backend.
const FIXTURE: Readonly<Record<string, readonly Therapy[]>> = {
  fd: [
    {
      name: "Observation (children — standard of care)",
      status: "unverified",
      note: "Monitor until skeletal maturity if no pain or functional impairment.",
      pmids: [],
    },
    {
      name: "Denosumab",
      status: "sourced",
      note: "For rapidly progressive lesions; strict calcium monitoring.",
      pmids: ["22422767"],
    },
  ],
  mas: [
    {
      name: "Endocrine treatment (per endocrinopathy)",
      status: "unverified",
      note: "Letrozole for precocious puberty; somatostatin analogues for GH excess.",
      pmids: [],
    },
  ],
  noonan: [
    {
      name: "Recombinant growth hormone",
      status: "unverified",
      note: "FDA-approved for Noonan short stature; higher dose than in GH deficiency.",
      pmids: [],
    },
  ],
};

export const fixtureTherapyRepository: TherapyRepository = {
  async listForDisease(diseaseSlug: string): Promise<readonly Therapy[]> {
    return FIXTURE[diseaseSlug] ?? [];
  },
};
