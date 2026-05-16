import type { GuidelinePrDetail } from "../types/contentPr";
import { GUIDELINE_PR_PARA_MAP } from "./guidelinePrParaMap";

export const CONTENT_PR_DETAILS: Readonly<Record<string, GuidelinePrDetail>> = {
  "PR-142": {
    id: "PR-142",
    disease: "fd",
    title: "Update: denosumab dosing schedule for pediatric polyostotic FD",
    opened: "2026-05-08",
    status: "under-review",
    author: "AI Watcher",
    reviewer: "Dr. Appelman-Dijkstra",
    summary:
      "Based on four recent articles (2024–2025): extend maintenance intervals from every 4 weeks to every 12 weeks after induction when CTX response is sustained.",
    citationsCount: 4,
    diff: [
      {
        type: "removed",
        text: "Denosumab 60 mg subcutaneously every 4 weeks until skeletal maturity.",
      },
      {
        type: "added",
        text: "Denosumab 60 mg subcutaneously every 4 weeks for six induction doses, then every 12 weeks if CTX remains below 0.3 ng/mL.",
      },
      {
        type: "added",
        text: "Monitor calcium and 25-OH vitamin D weekly during induction, then monthly during maintenance.",
      },
    ],
    papers: [
      {
        pmid: "37889911",
        title: "Denosumab in fibrous dysplasia — international consensus update",
        year: 2024,
      },
      {
        pmid: "38112233",
        title: "Long-term denosumab outcomes in pediatric FD — Leiden cohort",
        year: 2025,
      },
      {
        pmid: "38223344",
        title: "Rebound hypercalcemia after denosumab discontinuation",
        year: 2024,
      },
      {
        pmid: "38334455",
        title: "CTX-guided denosumab dosing in bone dysplasias",
        year: 2025,
      },
    ],
    paragraphMap: GUIDELINE_PR_PARA_MAP["PR-142"] ?? null,
  },
  "PR-141": {
    id: "PR-141",
    disease: "fd",
    title: "Add: optic canal monitoring protocol for asymptomatic patients",
    opened: "2026-05-05",
    status: "pending",
    author: "AI Watcher",
    reviewer: null,
    summary:
      "Add serial orbital MRI every 12 months for asymptomatic patients with imaging-evident optic canal involvement.",
    citationsCount: 2,
    diff: [
      {
        type: "added",
        text: "For asymptomatic patients with imaging-evident optic canal involvement: MRI orbits with contrast every 12 months.",
      },
    ],
    papers: [
      {
        pmid: "38445566",
        title: "Optic neuropathy in fibrous dysplasia — natural history",
        year: 2025,
      },
      {
        pmid: "38556677",
        title: "Pre-symptomatic decompression vs watchful waiting in FD",
        year: 2024,
      },
    ],
    paragraphMap: GUIDELINE_PR_PARA_MAP["PR-141"] ?? null,
  },
};
