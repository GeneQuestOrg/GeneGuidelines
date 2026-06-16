import type { GuidelineSynthesis } from "../types/guidelineSynthesis";

/**
 * Fixture syntheses — ported from draft10 `GUIDELINES` (chat 019). Content
 * language follows the app (English); structure mirrors the prototype.
 *
 * Honesty rules applied vs the prototype:
 *   - Citations reference only the REAL source-shelf PMIDs (Boyce 2019 ·
 *     31196103, Gun/Boyce 2024 · 38010041, Szymczuk/Boyce 2023 · 36849642).
 *     The prototype's per-paragraph PMIDs were placeholders; a citation chip
 *     links to PubMed, so every chip here resolves to a real article. The
 *     GeneReviews-backed claims cite no PMID (Bookshelf) — provenance still
 *     links out via the source mark.
 *   - No reviewer-name attribution anywhere (chat 019 demo mine).
 *   - The parent projection shows the first two paragraphs of each section, so
 *     each section leads with guidance; granular dosing sits in later
 *     paragraphs, for the treating clinician only (wizja 04: the synthesis
 *     stops at patient guidance, not protocol).
 */
const FD_SYNTHESIS: GuidelineSynthesis = {
  slug: "fd",
  kind: "synthesis",
  title: "Fibrous Dysplasia — synthesis of the guidelines",
  version: "Synthesis · 4 sources",
  lastUpdated: "2026-05-10",
  sourceIds: ["boyce2019", "gun2024", "szymczuk2023", "genereviews"],
  basedOn:
    "Combined from 4 source documents (Boyce 2019, Gun/Boyce 2024, Szymczuk/Boyce 2023, GeneReviews).",
  synthDisclaimer:
    "This summary was prepared by AI from 4 source documents — it is not an official guideline and may contain inaccuracies. Every claim links to the document and section it came from; read straight from the source if you prefer.",
  status: "consensus",
  hasFlowchart: true,
  whatToDoNow: [
    {
      lead: "Confirm the diagnosis properly.",
      body: "A DNA test for the GNAS mutation is decisive — histopathology alone is not enough.",
    },
    {
      lead: "Map the extent with imaging.",
      body: "CT or MRI shows how far the lesion reaches. A bone scan is done once at diagnosis, not on a cycle.",
    },
    {
      lead: "Reach a specialist who knows this disease.",
      body: "Not every surgeon or endocrinologist has seen it — check the doctor list on the disease page.",
    },
    {
      lead: "Plan for the long term.",
      body: "Reviews every 6–12 months; treatment is driven by pain and progression, not by the diagnosis alone.",
    },
  ],
  redFlags: {
    title: "When to seek a second opinion",
    items: [
      "A recommendation to excise a child's fibrous dysplasia without a compelling reason (vision loss, severe deformity).",
      "A histopathological diagnosis made without a confirmatory DNA test.",
      "No consultation with an international consortium (FD/MAS Alliance / Leiden).",
    ],
  },
  sections: [
    {
      id: "diagnosis",
      title: "1. Diagnosis",
      intro:
        "Diagnosis rests on the combined picture of radiology, histopathology, and genetic confirmation of a GNAS mutation.",
      paragraphs: [
        {
          id: "dx-ct",
          source: { doc: "szymczuk2023", loc: "§ Imaging" },
          text: "The first imaging study when craniofacial FD is suspected is a non-contrast CT of the facial skeleton in thin slices (≤1 mm). The typical picture is a “ground-glass” appearance with blurring of the boundary between cancellous and cortical bone.",
          citations: ["36849642"],
        },
        {
          id: "dx-mri",
          source: { doc: "szymczuk2023", loc: "§ MRI / optic nerve" },
          text: "Contrast MRI is indicated when compression of soft-tissue structures is suspected (optic nerve, brain, inner-ear structures). MRI does not replace CT — it complements the assessment.",
          citations: ["36849642"],
        },
        {
          id: "dx-scintigraphy",
          source: { doc: "boyce2019", loc: "§ Imaging" },
          text: "A bone scan is done only once at diagnosis, to assess extent (mono- vs polyostotic). Routine repetition is not recommended, given the cumulative radiation dose and low clinical value in follow-up.",
          citations: ["31196103"],
          highlight: true,
        },
      ],
    },
    {
      id: "histopathology",
      title: "2. Histopathology and genetics",
      intro:
        "Histopathology alone is insufficient. Confirmation of a GNAS mutation is required.",
      paragraphs: [
        {
          id: "hp-classic",
          source: { doc: "genereviews", loc: "§ Histopathology" },
          text: "The classic histopathological picture: irregular “Chinese-letter” bony trabeculae in a stroma of proliferating fibroblasts. NOTE: the microscopic appearance of FD can be indistinguishable from juvenile trabecular ossifying fibroma (JTOF), particularly in children.",
        },
        {
          id: "hp-gnas",
          source: { doc: "boyce2019", loc: "§ Genetic confirmation" },
          text: "Molecular testing for a somatic GNAS mutation (most often R201H or R201C in exon 8) is pathognomonic for FD and mandatory on any biopsy suspicious for FD. Absence of the mutation does not exclude FD (mosaicism), but a positive result confirms the diagnosis with 100% specificity.",
          citations: ["31196103"],
        },
        {
          id: "hp-mosaic",
          source: { doc: "genereviews", loc: "§ Molecular testing" },
          text: "In patients with a negative GNAS result in peripheral blood, retesting from lesional tissue should be considered (somatic mosaicism). Droplet digital PCR is more sensitive than classic Sanger sequencing.",
        },
      ],
    },
    {
      id: "therapy",
      title: "3. Therapy",
      intro:
        "Treatment choice depends on pain, lesion progression, and the patient's age. In children, a conservative approach is preferred.",
      paragraphs: [
        {
          id: "tx-observe",
          source: { doc: "boyce2019", loc: "§ Conservative management" },
          update: {
            doc: "gun2024",
            note: "Gun/Boyce 2024 refines observation in children up to skeletal maturity.",
          },
          text: "Observation is the standard for asymptomatic patients until skeletal maturity (typically 16–18 years). It requires periodic clinical review every 6–12 months and imaging (CT/MRI) every 12–24 months.",
          citations: ["31196103"],
        },
        {
          id: "tx-medical-lead",
          source: { doc: "boyce2019", loc: "§ Medical therapy" },
          text: "Medical therapy is an option for bone pain that does not respond to NSAIDs, or for rapid progression — and it is led by a specialist experienced in FD (e.g. an endocrinologist), not started from a web summary. The specific drugs and dosing below are for the treating clinician.",
          citations: ["31196103"],
        },
        {
          id: "tx-bisphos",
          source: { doc: "boyce2019", loc: "§ Bisphosphonates" },
          text: "IV bisphosphonates (pamidronate 1 mg/kg/day × 3 days every 4 months, or zoledronate 0.025 mg/kg once every 6–12 months) are indicated for bone pain refractory to NSAIDs. They require calcium and vitamin-D supplementation and monitoring of renal function.",
          citations: ["31196103"],
        },
        {
          id: "tx-denosumab",
          source: { doc: "gun2024", loc: "§ Denosumab in children" },
          update: {
            doc: "gun2024",
            supersedes: "boyce2019",
            note: "Gun/Boyce 2024 changes the schedule: induction → CTX-guided maintenance, instead of the fixed 4-weekly dosing of the 2019 consensus.",
          },
          text: "Denosumab 60 mg s.c. every 4 weeks for 6 doses (induction phase), then every 12 weeks if CTX < 0.3 ng/mL is maintained. Monitor calcium and 25-OH-D weekly during induction, monthly during maintenance.",
          citations: ["38010041"],
        },
        {
          id: "tx-denosumab-stop",
          source: { doc: "gun2024", loc: "§ Discontinuation" },
          text: "After stopping denosumab there is a risk of rebound hypercalcemia. A tapering plan is required; consider switching to bisphosphonates for 6–12 months.",
          citations: ["38010041"],
        },
        {
          id: "tx-burosumab",
          source: { doc: "boyce2019", loc: "§ FGF23 / burosumab" },
          text: "Burosumab is only for patients with FGF23-driven hypophosphatemia (phosphate < 0.8 mmol/L + FGF23 > 100 RU/mL). Dosing is weight-based, with phosphate monitoring every 2 weeks during titration.",
          citations: ["31196103"],
        },
      ],
    },
    {
      id: "surgery",
      title: "4. Indications for surgery",
      intro:
        "In children, surgery for FD is contraindicated except for strictly defined compelling reasons.",
      paragraphs: [
        {
          id: "sx-no",
          source: { doc: "boyce2019", loc: "§ Surgery in children" },
          text: "FD in children is NOT excised prophylactically. Resection in a child leads to permanent disfigurement and recurrence of the lesion in 30–60% of cases (literature from the 1990s).",
          citations: ["31196103"],
        },
        {
          id: "sx-yes",
          source: { doc: "szymczuk2023", loc: "§ Surgical indications" },
          text: "Absolute indications for surgical intervention (regardless of age): (a) vision loss or progressive visual-field defects, (b) facial-nerve compression with clinical symptoms, (c) deformity threatening airway patency.",
          citations: ["36849642"],
        },
        {
          id: "sx-optic",
          source: { doc: "szymczuk2023", loc: "§ Optic nerve" },
          text: "Pre-symptomatic decompression of the optic canal (on imaging alone) is NOT recommended — the risk of vision loss from surgery outweighs the risk from observation.",
          citations: ["36849642"],
        },
      ],
    },
    {
      id: "monitoring",
      title: "5. Monitoring and follow-up",
      intro:
        "The surveillance schedule depends on type (mono/polyostotic), age, and the presence of endocrinopathy (overlap with MAS).",
      paragraphs: [
        {
          id: "mon-followup",
          source: { doc: "boyce2019", loc: "§ Follow-up" },
          text: "A review visit every 6 months in children, every 12 months in adults. Assess pain (VAS scale), function, growth parameters, and endocrine symptoms.",
          citations: ["31196103"],
        },
        {
          id: "mon-markers",
          source: { doc: "boyce2019", loc: "§ Bone turnover markers" },
          text: "Bone turnover markers: P1NP, CTX every 6 months (or more often on denosumab — see section 3). Calcium, phosphate, 25-OH-D, ALP every 12 months.",
          citations: ["31196103"],
        },
        {
          id: "mon-mas",
          source: { doc: "boyce2019", loc: "§ MAS screening" },
          text: "Endocrine MAS screening in every case of FD (TSH, fT4, IGF-1, GH, cortisol; Tanner-stage assessment of puberty in children).",
          citations: ["31196103"],
        },
      ],
    },
  ],
};

const MAS_SYNTHESIS: GuidelineSynthesis = {
  slug: "mas",
  kind: "synthesis",
  title: "McCune-Albright Syndrome — synthesis of the guidelines",
  version: "Synthesis · 2 sources",
  lastUpdated: "2026-03-02",
  sourceIds: ["boyce2019", "genereviews"],
  basedOn:
    "Combined from the FD/MAS consensus (MAS section) and the GeneReviews reference chapter.",
  synthDisclaimer:
    "This summary was prepared by AI from the source documents — it is not an official guideline and may contain inaccuracies. Show it to your doctor.",
  status: "verified",
  sections: [
    {
      id: "overview",
      title: "1. Diagnosis and screening",
      intro:
        "The classic triad: FD + café-au-lait macules + endocrinopathy. Two of the three are sufficient.",
      paragraphs: [
        {
          id: "mas-dx",
          source: { doc: "boyce2019", loc: "§ MAS" },
          text: "A diagnosis of MAS requires: (a) documented FD (CT + GNAS), (b) café-au-lait macules of the “coast of Maine” type with a border running along the body midline, (c) one of the endocrinopathies: GnRH-independent precocious puberty, hyperthyroidism, GH excess, hypercortisolism, or FGF23-mediated hypophosphatemia.",
          citations: ["31196103"],
        },
      ],
    },
  ],
};

/** Disease slug → synthesis. Absent slugs (e.g. noonan) have no synthesis yet
 *  → the parent view shows the level-(c) "show your doctor" gate. */
export const SYNTHESES: Readonly<Record<string, GuidelineSynthesis>> = {
  fd: FD_SYNTHESIS,
  mas: MAS_SYNTHESIS,
};
