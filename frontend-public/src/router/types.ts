export type AudienceView = "parent" | "doctor";

export type Route =
  | { name: "home" }
  | { name: "devComponents" }
  | { name: "diseaseIndex"; query?: string }
  | { name: "disease"; slug: string; alert?: string }
  | { name: "diseaseMap"; slug: string }
  | { name: "myCase"; slug: string }
  | { name: "flowchart"; slug: string }
  | { name: "guidelines"; slug: string; prId?: string; srcParaId?: string }
  | { name: "bibliography"; slug: string }
  | { name: "doctors"; disease?: string }
  | { name: "doctor"; slug: string }
  | { name: "startResearch"; diseaseSlug?: string }
  | { name: "about" }
  | { name: "account" }
  | { name: "join"; token: string }
  | {
      name: "researchRun";
      id: string;
      query?: string;
      diseaseSlug?: string;
      diseaseName?: string;
    }
  | { name: "trials"; disease?: string };

export interface UserLocation {
  lat: number;
  lng: number;
}
