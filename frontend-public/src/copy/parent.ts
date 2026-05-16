import type { AudienceCopy } from "./types";

export const parentCopy: AudienceCopy = {
  home: {
    eyebrow: "GeneQuest Foundation · Living guidelines",
    titleLine1: "Clear answers for families",
    titleEmphasis: "navigating rare genetic disease.",
    subtitle:
      "Living guidelines, specialists, and trials in one place — every change reviewed by experts.",
    searchPlaceholder: "Search diseases, genes, or symptoms…",
    aboutLinkLabel: "Why we built this",
    browseCta: "Browse all diseases",
    researchCta: "Start research",
    newDiseaseTitle: "Don't see your condition?",
    newDiseaseSub:
      "Start an AI research run — we scan PubMed, surface specialists and trials, and draft a first guideline for review.",
    newDiseaseCta: "Start research →",
    diseasesSectionTitle: "Diseases",
  },
  disease: {
    personaLabel: "You are reading as",
    parentPersonaTitle: "Patient / caregiver",
    parentPersonaSub:
      "Plain language. What to do now, which questions to ask, and where to find help.",
    doctorPersonaTitle: "Clinician",
    doctorPersonaSub:
      "Full pathways, literature, dosing detail, and open PRs for review.",
    skeletonNoticeTitle: "Skeleton coverage.",
    skeletonNoticeBody:
      "Sections exist but content is still minimal — a full AI guideline pipeline will follow in a later release.",
    relatedTitle: "Related conditions",
    tabs: {
      overview: "Overview",
      doctors: "Specialists",
      trials: "Clinical trials",
      guidelines: "Guidelines",
    },
    pathwayTitle: "Patient chart",
    pathwaySub:
      "Plain-language next steps: confirm the diagnosis, map involvement, find the right support, and plan follow-up.",
    pathwaySteps: [
      {
        title: "Confirm the diagnosis.",
        body: "Use the recommended genetic test for this condition — histology alone is often insufficient.",
      },
      {
        title: "Map disease extent.",
        body: "Imaging shows where the disease is active. Repeat only when symptoms change, not on a fixed calendar.",
      },
      {
        title: "See a condition-experienced specialist.",
        body: "Not every local specialist has seen this disease — use the specialist list in the Doctors tab.",
      },
      {
        title: "Plan long-term follow-up.",
        body: "Monitoring every 6–12 months; treatment depends on pain, function, and progression.",
      },
      {
        title: "Check clinical trials.",
        body: "For rare diseases, trial participation may be the best available therapeutic option.",
      },
    ],
    redFlagsTitle: "Red flags — when to seek a second opinion",
    redFlags: [
      { text: "Aggressive surgery is recommended without a compelling indication." },
      { text: "Diagnosis is based on histology alone without genetic confirmation." },
      { text: "No referral to an international expert network or patient registry." },
    ],
    doctorsTitle: "Specialists",
    doctorsSub: (count) =>
      `${count} specialists linked to this condition in our catalog. Filter by location on the full directory.`,
    doctorsEmpty: "No specialists listed yet for this condition.",
    trialsTitle: "Clinical trials",
    trialsSub: (count) =>
      `${count} active or recruiting trials associated with this disease.`,
    trialsEmpty: "No recruiting trials listed yet.",
    guidelinesTitle: "Living guideline",
    guidelinesSub:
      "Patient-friendly summary of the current consensus document — full citations in the reader.",
    guidelinesCta: "Read the guideline",
    researchRunCta: "Suggest evidence scan (AI job)",
    openPrsTitle: "Updates in review",
    openPrsSub: (count) =>
      count === 0
        ? "No open pull requests — the published guideline is current."
        : `${count} proposed updates await specialist review.`,
    officialGuidelineTitle: "Official guideline (ground truth)",
    officialGuidelineSub: "Consensus document approved by the specialist network.",
  },
};
