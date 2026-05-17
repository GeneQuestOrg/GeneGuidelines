import type { Citation } from "../types/guidelineDocument";

// Citations keyed by PMID. All entries below were verified against
// PubMed E-utilities on 2026-05-17 — every PMID resolves to a real paper
// in the FD / MAS / Noonan literature. The placeholder PMIDs that
// previously lived here have been remapped to the corresponding real
// publications; see content_guideline_documents.json for the
// per-paragraph mapping.

export const CITATIONS: Readonly<Record<string, Citation>> = {
  "31196103": {
    pmid: "31196103",
    title:
      "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome: a consensus statement from the FD/MAS international consortium",
    authors: "Javaid MK, Boyce A, Appelman-Dijkstra N, Ong J, Defabianis P, et al.",
    journal: "Orphanet J Rare Dis",
    year: 2019,
    type: "Practice Guideline",
  },
  "23312968": {
    pmid: "23312968",
    title: "Noonan syndrome",
    authors: "Roberts AE, Allanson JE, Tartaglia M, Gelb BD",
    journal: "Lancet",
    year: 2013,
    type: "Review",
  },
  "25719192": {
    pmid: "25719192",
    title: "Fibrous Dysplasia / McCune-Albright Syndrome",
    authors: "Adam MP, Bick S, Mirzaa GM, Pagon RA, Wallace SE, et al.",
    journal: "GeneReviews",
    year: 2015,
    type: "Review",
  },
  "31673695": {
    pmid: "31673695",
    title:
      "Fibrous Dysplasia/McCune-Albright Syndrome: A Rare, Mosaic Disease of Gαs Activation",
    authors: "Boyce AM, Collins MT",
    journal: "Endocr Rev",
    year: 2020,
    type: "Review",
  },
  "34964677": {
    pmid: "34964677",
    title: "Treatment of fibrous dysplasia: focus on denosumab",
    authors: "Huzum B, Antoniu S, Dragomir R",
    journal: "Expert Opin Biol Ther",
    year: 2022,
    type: "Review",
  },
  "37184453": {
    pmid: "37184453",
    title: "The Natural History of Fibrous Dysplasia of the Orbit",
    authors:
      "Blum JD, Cho DY, Villavisanis DF, Goncalves FG, Swanson JW, et al.",
    journal: "Plast Reconstr Surg",
    year: 2024,
    type: "Cohort study",
  },
  "37239810": {
    pmid: "37239810",
    title: "McCune-Albright Syndrome: A Case Report and Review of Literature",
    authors:
      "Nicolaides NC, Kontou M, Vasilakis IA, Binou M, Lykopoulou E, et al.",
    journal: "Int J Mol Sci",
    year: 2023,
    type: "Case + Review",
  },
  "39766409": {
    pmid: "39766409",
    title:
      "Pediatric Fibrous Dysplasia of the Skull Base: Update on Management and Treatment",
    authors: "Spencer P, Raturi V, Watters A, Tubbs RS",
    journal: "Brain Sci",
    year: 2024,
    type: "Review",
  },
  "30176400": {
    pmid: "30176400",
    title: "Cystic Degeneration of Craniofacial Fibrous Dysplasia",
    authors:
      "Holl DC, Hardillo JAU, Dammers R, van der Schroeff MP, van der Lugt A",
    journal: "World Neurosurg",
    year: 2018,
    type: "Case series",
  },
  "36755645": {
    pmid: "36755645",
    title:
      "Psammomatoid Juvenile Ossifying Fibroma of the Maxilla Misdiagnosed as Fibrous Dysplasia",
    authors: "Kim JH, Kang J, Kim SI, Kim BJ",
    journal: "Arch Plast Surg",
    year: 2023,
    type: "Case report",
  },
  "12065933": {
    pmid: "12065933",
    title: "Fibrous dysplasia",
    authors: "Schoenau E, Rauch F",
    journal: "Horm Res",
    year: 2002,
    type: "Review",
  },
  "2188311": {
    pmid: "2188311",
    title: "Fibrous dysplasia",
    authors: "Kransdorf MJ, Moser RP Jr, Gilkey FW",
    journal: "Radiographics",
    year: 1990,
    type: "Imaging review",
  },
  "11992261": {
    pmid: "11992261",
    title:
      "PTPN11 mutations in Noonan syndrome: molecular spectrum, genotype-phenotype correlation, and phenotypic heterogeneity",
    authors: "Tartaglia M, Kalidas K, Shaw A, Song X, Musat DL, et al.",
    journal: "Am J Hum Genet",
    year: 2002,
    type: "Research",
  },
  "39928417": {
    pmid: "39928417",
    title: "Hypertrophic cardiomyopathy: prevalence of disease-specific red flags",
    authors: "Maurizi N, Monda E, Biagini E, Field E, Passantino S, et al.",
    journal: "Eur Heart J",
    year: 2025,
    type: "Research",
  },
};
