import type { AudienceCopy } from "./types";

export const doctorCopy: AudienceCopy = {
  home: {
    eyebrow: "GeneQuest Foundation · Living guidelines",
    titleLine1: "Evidence-based guidelines for",
    titleEmphasis: "rare genetic disease.",
    subtitle:
      "Specialist-reviewed pathways, literature, and PR workflows — built for clinical practice.",
    searchPlaceholder: "Search diseases, genes, OMIM, or phenotype…",
    aboutLinkLabel: "Why we built this",
    browseCta: "Browse diseases",
    researchCta: "Start research",
    newDiseaseTitle: "Add a new disease",
    newDiseaseSub:
      "Launch the PubMed pipeline to draft sections, surface experts, and open PRs for consortium review.",
    newDiseaseCta: "Start research →",
    diseasesSectionTitle: "Disease catalog",
  },
  disease: {
    personaLabel: "You are reading as",
    parentPersonaTitle: "Patient / caregiver",
    parentPersonaSub: "Plain-language pathway and family resources.",
    doctorPersonaTitle: "Clinician",
    doctorPersonaSub:
      "Full guideline text, diagnostic algorithms, dosing, literature trace, and PR queue.",
    skeletonNoticeTitle: "Skeleton coverage.",
    skeletonNoticeBody:
      "Minimal sections only — run the full pipeline before citing in clinical decisions.",
    relatedTitle: "Related phenotypes",
    tabs: {
      overview: "Overview",
      doctors: "Experts",
      trials: "Trials",
      guidelines: "Guideline",
    },
    pathwayTitle: "Diagnostic algorithm (summary)",
    pathwaySub: "High-level next steps in plain language.",
    pathwaySteps: [
      {
        title: "Genetic confirmation.",
        body: "Document the pathogenic variant; note mosaicism when relevant.",
      },
      {
        title: "Baseline imaging and labs.",
        body: "Establish extent and endocrine involvement before therapy.",
      },
      {
        title: "Multidisciplinary review.",
        body: "Orthopedics, endocrinology, genetics — coordinated plan.",
      },
      {
        title: "Therapy and surveillance.",
        body: "Follow consensus dosing; document deviation with rationale.",
      },
    ],
    redFlagsTitle: "Documentation red flags",
    redFlags: [
      { text: "Guideline citation without checking open PRs for superseding text." },
      { text: "Off-label therapy without published evidence in this disease." },
    ],
    doctorsTitle: "PubMed-ranked experts",
    doctorsSub: (count) => `${count} authors with scored relevance to this disease.`,
    doctorsEmpty: "Run Doctor Finder to populate experts.",
    trialsTitle: "Recruiting trials",
    trialsSub: (count) => `${count} trials with recruitment status tracked.`,
    trialsEmpty: "No trials indexed.",
    guidelinesTitle: "Living guideline document",
    guidelinesSub: "Section-level provenance, citations, and in-context PR diffs.",
    guidelinesCta: "Open full document",
    myCaseCta: "🔒 My case",
    notifyCta: "🔔 Notify me",
    notifyPendingCta: "🔔 Pending confirmation",
    notifySubscribedCta: "🔔 Subscribed",
    synthesisCta: "📄 Synthesis + sources",
    openPrsTitle: "Open pull requests",
    openPrsSub: (count) =>
      count === 0 ? "No drafts pending review." : `${count} drafts awaiting reviewer sign-off.`,
    officialGuidelineTitle: "Current consensus guideline",
    officialGuidelineSub: "Reference document — AI evidence watch, specialist-approved updates.",
  },
};
