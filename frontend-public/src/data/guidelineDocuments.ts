import type { GuidelineDocument } from "../types/guidelineDocument";

export const GUIDELINE_DOCUMENTS: Readonly<Record<string, GuidelineDocument>> = {
  fd: {
    slug: "fd",
    title: "Fibrous dysplasia — clinical guidelines (living document)",
    version: "v3.2",
    lastUpdated: "2026-05-10",
    basedOn:
      "Boyce et al. 2019 (PMID 31196103) plus 23 approved update PRs through April 2026",
    status: "consensus",
    statusBy: "specialist network",
    sections: [
      {
        id: "diagnosis",
        title: "1. Diagnosis",
        intro:
          "FD diagnosis combines imaging, histopathology when biopsy is obtained, and confirmation of a somatic GNAS mutation.",
        paragraphs: [
          {
            id: "dx-imaging-1",
            text: "First-line imaging for suspected craniofacial FD is non-contrast facial CT with thin slices (≤1 mm). The classic pattern is ground-glass bone with loss of corticomedullary distinction.",
            citations: ["31196103", "25719192"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-08-12" },
          },
          {
            id: "dx-imaging-2",
            text: "MRI with contrast is indicated when soft-tissue compression is suspected (optic nerve, brain, inner ear). MRI complements CT; it does not replace it for bone detail.",
            citations: ["31196103", "30176400"],
            lastChange: { type: "verified", by: "specialist network", date: "2024-11-03" },
          },
          {
            id: "dx-imaging-3",
            text: "Bone scintigraphy once at diagnosis may help define extent (monostotic vs polyostotic). Routine repeat scans are not recommended because of cumulative radiation exposure and limited follow-up value.",
            citations: ["2188311", "31196103"],
            lastChange: {
              type: "verified",
              by: "specialist network",
              date: "2026-05-02",
              prId: "PR-140",
            },
            highlight: true,
          },
        ],
      },
      {
        id: "histopathology",
        title: "2. Histopathology and genetics",
        intro: "Histology alone is insufficient. GNAS confirmation is required when FD is suspected.",
        paragraphs: [
          {
            id: "hp-1",
            text: "Classic histology shows irregular trabeculae of woven bone in a fibrous stroma. The pattern may overlap with juvenile trabecular ossifying fibroma, especially in children.",
            citations: ["25719192"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-08-12" },
          },
          {
            id: "hp-2",
            text: "Molecular testing for somatic GNAS (commonly R201H or R201C in exon 8) is pathognomonic when positive. A negative blood test does not exclude mosaic disease — repeat from affected tissue if clinical suspicion remains high.",
            citations: ["25719192", "25719192"],
            lastChange: {
              type: "consensus",
              by: "specialist network",
              date: "2025-08-12",
            },
          },
        ],
      },
      {
        id: "therapy",
        title: "3. Medical therapy",
        intro:
          "Treatment depends on pain, functional impact, and skeletal maturity. Conservative management is preferred in asymptomatic children until growth is complete.",
        paragraphs: [
          {
            id: "tx-observe",
            text: "Observation is standard for asymptomatic patients until skeletal maturity (typically 16–18 years), with clinical review every 6–12 months and imaging every 12–24 months when indicated.",
            citations: ["31196103", "39766409", "12065933"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-12-04" },
          },
          {
            id: "tx-bisphos",
            text: "IV bisphosphonates (pamidronate or zoledronate per weight-based protocols) are considered for pain refractory to NSAIDs, with calcium and vitamin D supplementation and renal monitoring.",
            citations: ["31196103"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-12-04" },
          },
          {
            id: "tx-denosumab-1",
            text: "Denosumab 60 mg subcutaneously every 4 weeks until skeletal maturity.",
            citations: ["31196103"],
            lastChange: { type: "superseded", by: "PR-142", date: "2026-05-08" },
            prInDiff: { prId: "PR-142", removed: true },
          },
          {
            id: "tx-denosumab-2",
            text: "Denosumab 60 mg subcutaneously every 4 weeks for six induction doses, then every 12 weeks if CTX remains below 0.3 ng/mL. Monitor calcium and 25-OH vitamin D weekly during induction, then monthly during maintenance.",
            citations: ["34964677", "34964677", "36755645"],
            lastChange: { type: "pending", by: "PR-142", date: "2026-05-08" },
            prInDiff: { prId: "PR-142", added: true },
          },
          {
            id: "tx-denosumab-3",
            text: "After denosumab discontinuation, rebound hypercalcemia is a risk — plan a taper and consider transition to bisphosphonates for 6–12 months.",
            citations: ["34964677", "34964677"],
            lastChange: { type: "verified", by: "specialist network", date: "2026-02-18" },
          },
          {
            id: "tx-burosumab",
            text: "Burosumab is reserved for FGF23-mediated hypophosphatemia (phosphate <0.8 mmol/L with elevated FGF23). Titrate per weight with phosphate monitoring every two weeks during dose adjustment.",
            citations: ["37184453"],
            lastChange: { type: "verified", by: "specialist network", date: "2024-09-22" },
          },
        ],
      },
      {
        id: "surgery",
        title: "4. Surgery",
        intro:
          "In children, surgery is generally avoided except for strictly defined compelling indications.",
        paragraphs: [
          {
            id: "sx-no",
            text: "Prophylactic resection of FD in children is not recommended. Historical series report high recurrence and permanent deformity after aggressive early surgery.",
            citations: ["31196103", "39766409"],
            lastChange: {
              type: "consensus",
              by: "specialist network",
              date: "2025-12-04",
            },
          },
          {
            id: "sx-yes",
            text: "Absolute indications include threatened or established vision loss, symptomatic cranial nerve compression, or airway compromise from deformity.",
            citations: ["30176400", "31196103"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-08-12" },
          },
          {
            id: "sx-optic",
            text: "Pre-symptomatic optic canal decompression based on imaging alone is not recommended — operative risk may exceed risk from observation in asymptomatic patients.",
            citations: ["37184453", "30176400", "30176400"],
            lastChange: { type: "verified", by: "specialist network", date: "2026-03-11" },
          },
        ],
      },
      {
        id: "monitoring",
        title: "5. Monitoring",
        intro:
          "Follow-up intensity depends on disease extent, age, and whether MAS overlap features are present.",
        paragraphs: [
          {
            id: "mon-1",
            text: "Clinical review every 6 months in children and annually in stable adults, including pain scores, function, growth parameters, and endocrine symptoms when MAS overlap is possible.",
            citations: ["31196103"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-05-20" },
          },
          {
            id: "mon-2",
            text: "Bone turnover markers (P1NP, CTX) every 6 months, or more often on denosumab. Calcium, phosphate, 25-OH vitamin D, and ALP at least annually.",
            citations: ["31196103", "36755645"],
            lastChange: { type: "verified", by: "specialist network", date: "2025-05-20" },
          },
          {
            id: "mon-3",
            text: "Screen for MAS-related endocrinopathy at FD diagnosis: thyroid function, IGF-1/GH axis, cortisol, and pubertal staging in children.",
            citations: ["31196103"],
            lastChange: { type: "consensus", by: "FD/MAS consensus panel", date: "2024-09-22" },
          },
        ],
      },
    ],
  },
  mas: {
    slug: "mas",
    title: "McCune-Albright syndrome — clinical guidelines (skeleton)",
    version: "v2.1",
    lastUpdated: "2026-03-02",
    basedOn: "Boyce et al. 2019 (MAS chapter) plus three update PRs",
    status: "verified",
    statusBy: "specialist network",
    sections: [
      {
        id: "overview",
        title: "1. Diagnosis and screening",
        intro: "Classic triad: fibrous dysplasia, café-au-lait macules, and endocrinopathy — two of three suffice.",
        paragraphs: [
          {
            id: "mas-dx-1",
            text: "Document fibrous dysplasia (CT plus GNAS), coast-of-Maine café-au-lait pigmentation, and at least one endocrinopathy such as precocious puberty, hyperthyroidism, GH excess, or FGF23-mediated hypophosphatemia.",
            citations: ["31196103"],
            lastChange: { type: "verified", by: "specialist network", date: "2026-03-02" },
          },
        ],
      },
    ],
  },
  noonan: {
    slug: "noonan",
    title: "Noonan syndrome — clinical guidelines (skeleton draft)",
    version: "v0.9-draft",
    lastUpdated: "2026-05-12",
    basedOn: "AI draft from 47 PubMed articles (2018–2025) — awaiting specialist review",
    status: "pending",
    statusBy: null,
    sections: [
      {
        id: "intro",
        title: "1. Diagnosis",
        intro:
          "Molecular testing of the RAS-MAPK pathway (PTPN11, SOS1, RAF1, KRAS, RIT1, and others) is required when clinical suspicion is high.",
        paragraphs: [
          {
            id: "no-1",
            text: "Clinical suspicion combines characteristic facies, short stature, congenital heart disease (often pulmonary valve stenosis), and lymphatic or bleeding complications. Use established scoring systems when available.",
            citations: [],
            lastChange: { type: "pending", by: null, date: "2026-05-12" },
          },
        ],
      },
    ],
  },
};
