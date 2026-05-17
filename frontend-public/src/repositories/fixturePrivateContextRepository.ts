import type { PrivateContext } from "../types/privateContext";
import type { PrivateContextRepository } from "./types";

// Fixture mode is offline-only. Uploads return a canned redaction example so
// the UI can be developed without a backend.
const FIXTURE_BREAKDOWN = {
  names: 3,
  government_ids: 1,
  absolute_dates: 4,
  addresses: 1,
  document_numbers: 0,
};

const FIXTURE: PrivateContext = {
  id: 1,
  diseaseSlug: "fd",
  originalFilename: "demo_discharge.txt",
  originalChars: 940,
  originalSha256: "d2c468f05d0b5e05ccb2dcd6ba9517f4463a105c7699cfd1fb7d46e31ed3d6ea",
  uploadedAt: new Date().toISOString(),
  redacted: {
    clinical_findings: [
      { text: "right-sided maxillary mass observed in a child", category: "finding" },
      { text: "ground-glass lesion on facial CT", category: "imaging" },
    ],
    interventions: ["observation until skeletal maturity"],
    mutations: ["GNAS c.601C>T"],
    outcomes: ["stable, no functional impairment"],
    evidence_quality: "discharge_summary",
    pii_breakdown: FIXTURE_BREAKDOWN,
  },
  piiBreakdown: FIXTURE_BREAKDOWN,
  piiTokensRemoved: 9,
  clinicalFactsExtracted: 5,
  modelUsed: "openrouter:google/gemma-4-31b-it:free",
  status: "ready",
  error: null,
};

export const fixturePrivateContextRepository: PrivateContextRepository = {
  async upload(diseaseSlug: string): Promise<PrivateContext | null> {
    if (diseaseSlug !== "fd" && diseaseSlug !== "mas" && diseaseSlug !== "noonan") {
      return null;
    }
    return { ...FIXTURE, diseaseSlug };
  },

  async listForDisease(diseaseSlug: string): Promise<readonly PrivateContext[]> {
    if (diseaseSlug === "fd") {
      return [FIXTURE];
    }
    return [];
  },
};
