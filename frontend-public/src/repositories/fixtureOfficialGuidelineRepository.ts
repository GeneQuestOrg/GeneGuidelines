import type { OfficialGuideline } from "../types/officialGuideline";
import type { OfficialGuidelineRepository } from "./types";

const FIXTURE: Readonly<Record<string, OfficialGuideline>> = {
  fd: {
    diseaseSlug: "fd",
    title:
      "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome",
    authors: "Javaid, Boyce, Appelman-Dijkstra, et al.",
    year: 2019,
    journal: "Orphanet Journal of Rare Diseases",
    pmid: "31196103",
    url: "https://link.springer.com/article/10.1186/s13023-019-1102-9",
    summary:
      "International consensus for FD/MAS — diagnosis, imaging, medical and surgical management, surveillance.",
    confirmedBy: "GeneQuest reviewer panel",
    confirmedAt: "2026-05-17",
    source: "seed",
  },
  mas: {
    diseaseSlug: "mas",
    title:
      "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome",
    authors: "Javaid, Boyce, Appelman-Dijkstra, et al.",
    year: 2019,
    journal: "Orphanet Journal of Rare Diseases",
    pmid: "31196103",
    url: "https://link.springer.com/article/10.1186/s13023-019-1102-9",
    summary:
      "Same international consensus — endocrine sections specific to MAS.",
    confirmedBy: "GeneQuest reviewer panel",
    confirmedAt: "2026-05-17",
    source: "seed",
  },
  noonan: {
    diseaseSlug: "noonan",
    title:
      "Noonan syndrome: clinical aspects and molecular pathogenesis (European clinical guideline)",
    authors: "Roberts AE, Allanson JE, Tartaglia M, Gelb BD",
    year: 2013,
    journal: "Lancet",
    pmid: "23303081",
    url: "https://pubmed.ncbi.nlm.nih.gov/23303081/",
    summary:
      "Foundational clinical review — diagnostic criteria, RAS-MAPK molecular pathogenesis, cardiology surveillance.",
    confirmedBy: "GeneQuest reviewer panel",
    confirmedAt: "2026-05-17",
    source: "seed",
  },
};

export const fixtureOfficialGuidelineRepository: OfficialGuidelineRepository = {
  async getForDisease(diseaseSlug: string): Promise<OfficialGuideline | null> {
    return FIXTURE[diseaseSlug] ?? null;
  },
};
