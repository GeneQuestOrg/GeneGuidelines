import type { GuidelineBaseline } from "../types/guidelineBaseline";

/**
 * Fixture baselines — ported from draft10 `BASELINE` (chat 019). Level (c): a
 * disease with no agreed guideline. Placeholder content until the from-scratch
 * workflow generates it; citations use the real Noonan reference (PMID 23303081)
 * so chips resolve. No reviewer names.
 */
const NOONAN_BASELINE: GuidelineBaseline = {
  slug: "noonan",
  title: "Noonan syndrome — AI baseline for expert review",
  builtFrom: "47 PubMed papers (2018–2025) · generated 2026-05-12",
  readState: { read: false, note: "No clinician has read this draft yet." },
  runSteps: [
    { label: "PubMed scan (RAS-MAPK, Noonan)", meta: "47 papers", done: true },
    { label: "Fact extraction & structuring (librarian step)", meta: "Gemma 4", done: true },
    { label: "Evidence-strength scoring + provenance", meta: "in progress", active: true },
    { label: "Draft sections: diagnosis / monitoring / therapy", meta: "queued", done: false },
  ],
  sections: [
    {
      id: "no-dx",
      title: "1. Diagnosis",
      items: [
        {
          id: "no-dx-1",
          text: "Confirm with a genetic test across the RAS-MAPK pathway (PTPN11, SOS1, RAF1, KRAS, RIT1, BRAF). A van der Burgt clinical score > 5 is a strong pre-test indicator.",
          evidence: "strong",
          citations: ["23303081"],
          provenance: "Consistent across 9 of 11 diagnostic-criteria papers.",
          signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
        },
        {
          id: "no-dx-2",
          text: "PTPN11-negative cases with a classic phenotype need a broader RASopathy panel before the diagnosis is excluded.",
          evidence: "moderate",
          citations: [],
          provenance: "Synthesised from 3 cohort studies — no single guideline source.",
          signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
        },
      ],
    },
    {
      id: "no-cardio",
      title: "2. Cardiac monitoring",
      items: [
        {
          id: "no-card-1",
          text: "Baseline ECHO at diagnosis; the commonest defects are pulmonary-valve stenosis and hypertrophic cardiomyopathy. Repeat every 1–2 years, more often with HCM.",
          evidence: "moderate",
          citations: [],
          provenance: "Recurring recommendation; intervals vary across sources (1–3 years).",
          signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
        },
      ],
    },
  ],
};

/** Disease slug → level-(c) baseline. Absent slugs have no baseline. */
export const BASELINES: Readonly<Record<string, GuidelineBaseline>> = {
  noonan: NOONAN_BASELINE,
};
