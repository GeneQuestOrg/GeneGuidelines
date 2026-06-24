import type { Foundation } from "../types/foundation";
import type { FoundationRepository } from "./types";

const FIXTURE: readonly Foundation[] = [
  {
    name: "FDMAS Alliance",
    scope: "International",
    url: "fibrousdysplasia.org",
    city: "USA / Online",
    country: "US",
    services: ["Doctor Finder", "Patient Registry", "Workshops"],
    diseases: ["fd", "mas"],
  },
  {
    name: "GeneQuest Foundation",
    scope: "Poland",
    url: "genequest.org",
    city: "Zielona Góra",
    country: "PL",
    services: ["Family support (PL)", "Polish doctor catalog"],
    diseases: ["fd", "mas"],
  },
  {
    name: "Noonan Syndrome Foundation",
    scope: "International",
    url: "teamnoonan.org",
    city: "USA",
    country: "US",
    services: ["Community", "Annual conference"],
    diseases: ["noonan"],
  },
];

export const fixtureFoundationRepository: FoundationRepository = {
  async listForDisease(diseaseSlug: string): Promise<readonly Foundation[]> {
    return FIXTURE.filter((f) => f.diseases.includes(diseaseSlug));
  },
};
