import { getDataSource } from "../config/dataSource";
import { apiDiseaseRepository } from "./apiDiseaseRepository";
import { apiContentPrRepository } from "./apiContentPrRepository";
import { apiDoctorRepository } from "./apiDoctorRepository";
import { apiGuidelineRepository } from "./apiGuidelineRepository";
import { apiResearchRunsRepository } from "./apiResearchRunsRepository";
import { apiFoundationRepository } from "./apiFoundationRepository";
import { apiOfficialGuidelineRepository } from "./apiOfficialGuidelineRepository";
import { apiPrivateContextRepository } from "./apiPrivateContextRepository";
import { apiTherapyRepository } from "./apiTherapyRepository";
import { apiTrialRepository } from "./apiTrialRepository";
import { fixtureContentPrRepository } from "./fixtureContentPrRepository";
import { fixtureDoctorRepository } from "./fixtureDoctorRepository";
import { fixtureDiseaseRepository } from "./fixtureDiseaseRepository";
import { fixtureFoundationRepository } from "./fixtureFoundationRepository";
import { fixtureGuidelineRepository } from "./fixtureGuidelineRepository";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";
import { fixturePrivateContextRepository } from "./fixturePrivateContextRepository";
import { fixtureResearchRunsRepository } from "./fixtureResearchRunsRepository";
import { fixtureTherapyRepository } from "./fixtureTherapyRepository";
import { fixtureTrialRepository } from "./fixtureTrialRepository";
import type {
  ContentPrRepository,
  DoctorRepository,
  DiseaseRepository,
  FoundationRepository,
  GuidelineRepository,
  OfficialGuidelineRepository,
  PrivateContextRepository,
  ResearchRunsRepository,
  TherapyRepository,
  TrialRepository,
} from "./types";

export type {
  ContentPrRepository,
  DoctorRepository,
  DiseaseRepository,
  FoundationRepository,
  GuidelineRepository,
  OfficialGuidelineRepository,
  PrivateContextRepository,
  ResearchRunsRepository,
  TherapyRepository,
  TrialRepository,
} from "./types";
export { ApiRepositoryNotReadyError } from "./errors";
export { isValidDiseaseSlug, normalizeDiseaseSlug, DISEASE_SLUG_PATTERN } from "../router/slug";

export interface Repositories {
  diseases: DiseaseRepository;
  guidelines: GuidelineRepository;
  contentPrs: ContentPrRepository;
  doctors: DoctorRepository;
  researchRuns: ResearchRunsRepository;
  trials: TrialRepository;
  therapies: TherapyRepository;
  foundations: FoundationRepository;
  privateContexts: PrivateContextRepository;
  officialGuidelines: OfficialGuidelineRepository;
}

export function getRepositories(): Repositories {
  const source = getDataSource();
  if (source === "api") {
    return {
      diseases: apiDiseaseRepository,
      guidelines: apiGuidelineRepository,
      contentPrs: apiContentPrRepository,
      doctors: apiDoctorRepository,
      researchRuns: apiResearchRunsRepository,
      trials: apiTrialRepository,
      therapies: apiTherapyRepository,
      foundations: apiFoundationRepository,
      privateContexts: apiPrivateContextRepository,
      officialGuidelines: apiOfficialGuidelineRepository,
    };
  }
  return {
    diseases: fixtureDiseaseRepository,
    guidelines: fixtureGuidelineRepository,
    contentPrs: fixtureContentPrRepository,
    doctors: fixtureDoctorRepository,
    researchRuns: fixtureResearchRunsRepository,
    trials: fixtureTrialRepository,
    therapies: fixtureTherapyRepository,
    foundations: fixtureFoundationRepository,
    privateContexts: fixturePrivateContextRepository,
    officialGuidelines: fixtureOfficialGuidelineRepository,
  };
}

/** Singleton for app lifetime — fixture data is static. */
let cached: Repositories | null = null;

export function repositories(): Repositories {
  if (cached == null) {
    cached = getRepositories();
  }
  return cached;
}
