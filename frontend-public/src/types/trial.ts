export interface Trial {
  readonly nct: string;
  readonly title: string;
  readonly phase: string;
  readonly status: string;
  readonly sponsor: string;
  readonly city: string | null;
  readonly country: string | null;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly ageRange: string | null;
  readonly principalInvestigator: string | null;
  readonly eligibilitySummary: string;
  readonly enrollmentTarget: number | null;
  readonly enrolled: number | null;
  readonly contact: string | null;
  readonly lastSeen: string | null;
  readonly diseases: readonly string[];
}
