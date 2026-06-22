import type { GuidelineBaseline } from "../types/guidelineBaseline";
import type { AnalyzedPaper } from "../types/analyzedPaper";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";
import type { GuidelineSynthesis, SynthSectionSignal } from "../types/guidelineSynthesis";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { SourceDoc } from "../types/sourceDoc";
import { BIBLIOGRAPHY } from "./guidelineBibliographyFixtures";
import { BASELINES } from "./guidelineBaselineFixtures";
import { SUGGESTIONS } from "./guidelineSuggestionsFixtures";
import { SYNTHESES } from "./guidelineSynthesisFixtures";
import { SYNTH_SIGNALS } from "./guidelineSynthSignalsFixtures";
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

// Curated source shelf — "there is rarely one document" (draft10 SOURCE_DOCS).
// Content language follows the app (English); structure mirrors the prototype.
const SHELF: Readonly<Record<string, readonly SourceDoc[]>> = {
  fd: [
    {
      id: "boyce2019",
      role: "Base consensus",
      pmid: "31196103",
      title:
        "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome: a consensus statement from the FD/MAS international consortium",
      authors: "Javaid MK, Boyce A, Appelman-Dijkstra N, et al.",
      journal: "Orphanet Journal of Rare Diseases",
      year: 2019,
      scope:
        "Whole-disease FD/MAS management — the consortium's first systematized consensus.",
      covers: ["Diagnosis", "Genetics", "Therapy", "Surgery", "Monitoring"],
      freeFullText: true,
    },
    {
      id: "gun2024",
      role: "Children — update",
      pmid: "38010041",
      title: "Fibrous dysplasia in children and its management",
      authors: "Gun ZH, Arif A, Boyce AM",
      journal: "Curr Opin Endocrinol Diabetes Obes",
      year: 2024,
      scope:
        "Most recent pediatric compendium: skeletal growth and newer therapies (denosumab).",
      covers: ["Therapy (children)", "Denosumab", "Monitoring"],
      updatesNote: "Updates the denosumab recommendation from the 2019 consensus.",
      isNew: true,
    },
    {
      id: "szymczuk2023",
      role: "Craniofacial",
      pmid: "36849642",
      title: "Craniofacial Fibrous Dysplasia: Clinical and Therapeutic Implications",
      authors: "Szymczuk V, Taylor J, Boyce AM",
      journal: "Curr Osteoporos Rep",
      year: 2023,
      scope:
        "Strictly the craniofacial region — including optic-nerve compression management.",
      covers: ["Imaging", "Optic nerve", "Craniofacial surgery"],
    },
    {
      id: "genereviews",
      role: "Reference compendium",
      bookshelf: "NBK274564",
      title: "Fibrous Dysplasia / McCune-Albright Syndrome",
      authors: "Boyce AM, Collins MT, et al.",
      journal: "GeneReviews® · NCBI Bookshelf",
      year: "continuously updated",
      scope:
        "Continuously updated NIH reference chapter — de facto textbook guidance.",
      covers: ["Diagnosis", "Histopathology", "Genetics", "Full review"],
    },
  ],
  mas: [
    {
      id: "boyce2019",
      role: "Base consensus",
      pmid: "31196103",
      title:
        "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome (MAS section)",
      authors: "Javaid MK, Boyce A, Appelman-Dijkstra N, et al.",
      journal: "Orphanet Journal of Rare Diseases",
      year: 2019,
      scope:
        "MAS section of the consortium consensus — the triad and endocrine screening.",
      covers: ["Diagnosis", "Endocrine screening"],
      freeFullText: true,
    },
    {
      id: "genereviews",
      role: "Reference compendium",
      bookshelf: "NBK274564",
      title: "Fibrous Dysplasia / McCune-Albright Syndrome",
      authors: "Boyce AM, Collins MT, et al.",
      journal: "GeneReviews® · NCBI Bookshelf",
      year: "continuously updated",
      scope: "NIH reference chapter covering the FD/MAS spectrum.",
      covers: ["Full review"],
    },
  ],
  // noonan: no source shelf yet → AI-built guideline only (GL-5/6).
};

export const fixtureOfficialGuidelineRepository: OfficialGuidelineRepository = {
  async getForDisease(diseaseSlug: string): Promise<OfficialGuideline | null> {
    return FIXTURE[diseaseSlug] ?? null;
  },
  async getShelf(diseaseSlug: string): Promise<readonly SourceDoc[]> {
    return SHELF[diseaseSlug] ?? [];
  },
  async getSynthesis(diseaseSlug: string): Promise<GuidelineSynthesis | null> {
    return SYNTHESES[diseaseSlug] ?? null;
  },
  async getSuggestions(diseaseSlug: string): Promise<readonly GuidelineSuggestion[]> {
    return SUGGESTIONS[diseaseSlug] ?? [];
  },
  // Fixtures are static: echo back the current aggregate + the optimistic verdict
  // so the offline/test repo satisfies the interface without persistence.
  async rateSuggestion(diseaseSlug, suggestionId, verdict) {
    const found = (SUGGESTIONS[diseaseSlug] ?? []).find((s) => s.id === suggestionId);
    return {
      signal: found?.signal ?? { useful: 0, not: 0, wrong: 0, ratings: 0, verified: 0 },
      myVote: verdict,
    };
  },
  async getSynthSignals(
    diseaseSlug: string,
  ): Promise<Readonly<Record<string, SynthSectionSignal>>> {
    return SYNTH_SIGNALS[diseaseSlug] ?? {};
  },
  async getBaseline(diseaseSlug: string): Promise<GuidelineBaseline | null> {
    return BASELINES[diseaseSlug] ?? null;
  },
  async getBibliography(diseaseSlug: string): Promise<readonly AnalyzedPaper[]> {
    return BIBLIOGRAPHY[diseaseSlug] ?? [];
  },
};
