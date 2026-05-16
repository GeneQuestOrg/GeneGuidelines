import type { Therapy } from "../types/therapy";
import type { TherapyRepository } from "./types";

const FIXTURE: Readonly<Record<string, readonly Therapy[]>> = {
  fd: [
    {
      name: "Observation (children — standard of care)",
      status: "consensus",
      note: "Monitor until skeletal maturity if no pain or functional impairment.",
    },
    {
      name: "Denosumab",
      status: "verified",
      note: "For rapidly progressive lesions; strict calcium monitoring.",
    },
  ],
  mas: [
    {
      name: "Endocrine treatment (per endocrinopathy)",
      status: "consensus",
      note: "Letrozole for precocious puberty; somatostatin analogues for GH excess.",
    },
  ],
  noonan: [
    {
      name: "Recombinant growth hormone",
      status: "consensus",
      note: "FDA-approved for Noonan short stature; higher dose than in GH deficiency.",
    },
  ],
};

export const fixtureTherapyRepository: TherapyRepository = {
  async listForDisease(diseaseSlug: string): Promise<readonly Therapy[]> {
    return FIXTURE[diseaseSlug] ?? [];
  },
};
