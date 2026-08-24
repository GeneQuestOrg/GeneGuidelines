import type { GuidelineSuggestion } from "../types/guidelineSuggestion";

/**
 * Fixture suggestions — ported from draft10 `SUGGESTIONS` (chat 019). Content
 * is placeholder until the research workflow generates real deltas (GL-4); the
 * value here is the structure / rating loop / diff, not the clinical text.
 * Citations use only the real source-shelf PMIDs so every chip resolves; comments
 * carry no reviewer names ("Verified reviewer · …").
 */
const FD_SUGGESTIONS: readonly GuidelineSuggestion[] = [
  {
    id: "sg-oct",
    kind: "addition",
    targetSection: "surgery",
    sectionLabel: "4. Indications for surgery",
    title:
      "Add OCT + visual-field monitoring for asymptomatic optic-canal involvement",
    summary:
      "For patients with radiological optic-canal involvement but no symptoms: add OCT (optical coherence tomography) and a formal visual field every 6 months, alongside the existing MRI every 12 months.",
    rationale:
      "OCT is an optical scan (light, no ionising radiation) — at worst a low-risk redundant scan, at best early detection of compression before vision is lost. Low risk / high benefit — a candidate to surface to the parent as a question for their doctor.",
    evidence: "moderate",
    citations: ["36849642"],
    gate: "promoted",
    parentText:
      "Newer work suggests that if imaging shows optic-canal involvement — even without symptoms — a periodic OCT (a light-based scan, no radiation) plus a visual-field test can catch a problem early.",
    signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
    comments: [],
  },
  {
    id: "sg-deno",
    kind: "modification",
    targetSection: "therapy",
    sectionLabel: "3. Therapy · denosumab dosing",
    title:
      "Change denosumab dosing: induction, then a CTX-guided maintenance taper",
    summary:
      "Replace fixed 4-weekly dosing with a 6-dose induction, then maintenance every 12 weeks gated on CTX < 0.3 ng/mL, with a defined monitoring schedule.",
    rationale:
      "Four 2024–2025 papers converge on a post-induction taper and warn of rebound hypercalcemia after abrupt discontinuation. This changes a dosing line — a real downside if misapplied — so it stays clinician-only.",
    evidence: "strong",
    citations: ["38010041", "31196103"],
    gate: "expert",
    signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
    comments: [],
    diff: {
      file: "guidelines/fd.md · §3 Therapy",
      hunk: "@@ -142,4 +142,8 @@ Denosumab",
      lines: [
        { t: "ctx", o: "141", n: "141", tx: "Bisphosphonates remain first line for bone pain refractory to NSAIDs." },
        { t: "del", o: "142", tx: "Denosumab 60 mg s.c. every 4 weeks until skeletal maturity." },
        { t: "add", n: "142", tx: "Denosumab 60 mg s.c. every 4 weeks for 6 doses (induction phase)," },
        { t: "add", n: "143", tx: "then every 12 weeks if a CTX < 0.3 ng/mL response is maintained." },
        { t: "add", n: "144", tx: "Monitor calcium and 25-OH-D weekly during induction, monthly during maintenance." },
        { t: "add", n: "145", tx: "On discontinuation: plan a taper — risk of rebound hypercalcemia (consider bisphosphonate cover for 6–12 months)." },
        { t: "ctx", o: "143", n: "146", tx: "Burosumab is reserved for FGF23-driven hypophosphatemia." },
      ],
    },
    regenSeed: {
      version: "draft v2",
      basedOn: "the reviewer note about age-dependent maintenance",
      note: "Adds an age qualifier to the maintenance interval and a sub-note for patients under 10. New, explicitly versioned — nothing was overwritten.",
    },
  },
  {
    id: "sg-gnas",
    kind: "addition",
    targetSection: "histopathology",
    sectionLabel: "2. Histopathology and genetics",
    title: "Note ddPCR over Sanger when peripheral-blood GNAS is negative",
    summary:
      "When peripheral-blood GNAS is negative but FD is clinically suspected, note droplet-digital PCR from lesional tissue as a higher-sensitivity confirmatory test.",
    rationale:
      "Reinforces the existing paragraph, does not change a decision. A diagnostic-sensitivity improvement with no patient risk — a candidate for the parent view as a question to ask.",
    evidence: "moderate",
    citations: ["31196103"],
    gate: "promoted",
    parentText:
      "If a blood test for the GNAS gene comes back negative but doctors still suspect FD, a more sensitive lab test (ddPCR from the affected tissue) can help confirm it — worth asking about.",
    signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
    comments: [],
  },
];

const MAS_SUGGESTIONS: readonly GuidelineSuggestion[] = [
  {
    id: "sg-tanner",
    kind: "modification",
    targetSection: "overview",
    sectionLabel: "1. Diagnosis and screening",
    title: "Shorten the Tanner-staging interval in MAS girls aged 2–7",
    summary:
      "Shorten Tanner staging from 12 to 6 months in girls aged 2–7 — the peak-risk window for GnRH-independent precocious puberty.",
    rationale:
      "A screening-interval change with a monitoring downside (not therapy); stays clinician-only until it gathers more signal.",
    evidence: "moderate",
    citations: ["31196103"],
    gate: "expert",
    signal: { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
    comments: [],
    diff: {
      file: "guidelines/mas.md · §1 Screening",
      hunk: "@@ -22,1 +22,1 @@ Endocrine screening",
      lines: [
        { t: "del", o: "22", tx: "Annual Tanner staging in MAS girls aged 2–8." },
        { t: "add", n: "22", tx: "Tanner staging every 6 months in MAS girls aged 2–7 (peak-risk window for GnRH-independent precocious puberty)." },
      ],
    },
  },
];

/** Disease slug → suggestions hanging beside its synthesis. */
export const SUGGESTIONS: Readonly<Record<string, readonly GuidelineSuggestion[]>> = {
  fd: FD_SUGGESTIONS,
  mas: MAS_SUGGESTIONS,
};
