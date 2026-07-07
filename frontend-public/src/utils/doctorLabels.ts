import type {
  ClinicalSpecialty,
  DoctorTier,
  PublicDoctor,
  PubmedRole,
  Reachability,
  RecencyBand,
  SpecialtySource,
} from "../types/doctor";

export const VALID_PUBMED_ROLES = new Set<string>([
  "research_leader",
  "research_participant",
  "case_study_author",
  "unknown",
]);

/**
 * Per-disease experience tier with a global-role fallback: experienceByDisease keys can
 * legitimately be a subset of diseases[] (curated rows without the map, merged rows).
 */
export function tierForDisease(doctor: PublicDoctor, diseaseSlug: string): DoctorTier {
  return doctor.experienceByDisease?.[diseaseSlug] ?? doctor.pubmedRole;
}

export function pubmedRoleLabel(role: PubmedRole): string {
  switch (role) {
    case "research_leader":
      return "Led research";
    case "research_participant":
      return "Contributed";
    case "case_study_author":
      return "Case studies";
    default:
      return "Unknown";
  }
}

/** Recency band with a fallback derived from the newest publication year on the profile. */
export function recencyBandOf(doctor: PublicDoctor): RecencyBand {
  if (doctor.recencyBand) return doctor.recencyBand;
  const year = doctor.lastCentralPaperYear ?? doctor.lastPaperYear ?? null;
  if (year == null) return "unknown";
  const delta = new Date().getFullYear() - year;
  if (delta <= 2) return "active_2y";
  if (delta <= 5) return "active_5y";
  return "older";
}

/** Short human label for the recency band, e.g. shown on a card next to disease experience. */
export function recencyLabel(band: RecencyBand): string {
  switch (band) {
    case "active_2y":
      return "On top of it (≤2y)";
    case "active_5y":
      return "Recent (≤5y)";
    case "older":
      return "Earlier work";
    default:
      return "Recency unknown";
  }
}

/**
 * The types of disease-relevant work a profile carries, derived from existing evidence flags —
 * no new data source. Powers the "type of work" facet (multi-select).
 */
export type WorkType =
  | "guideline"
  | "original"
  | "review"
  | "trial"
  | "case_report";

export const WORK_TYPE_ORDER: readonly WorkType[] = [
  "guideline",
  "original",
  "review",
  "trial",
  "case_report",
];

export function workTypeLabel(t: WorkType): string {
  switch (t) {
    case "guideline":
      return "Guideline / consensus author";
    case "original":
      return "Original research";
    case "review":
      return "Review articles";
    case "trial":
      return "Runs a clinical trial";
    case "case_report":
      return "Case reports";
  }
}

/** Which work types a doctor has, from already-computed evidence (never fabricated). */
export function workTypesOf(doctor: PublicDoctor): Set<WorkType> {
  const out = new Set<WorkType>();
  const ev = doctor.evidence;
  if (ev.guidelineOrConsensusCoauthor) out.add("guideline");
  if (ev.firstOrLastAuthorPapers > 0) out.add("original");
  if (ev.reviewPapers > 0) out.add("review");
  if (ev.runsClinicalTrial) out.add("trial");
  if (doctor.pubmedRole === "case_study_author") out.add("case_report");
  return out;
}

// --- Phase 1 clinical axis -----------------------------------------------------------------

/** Verified clinical specialties (confidence high|medium). Empty when nothing is verified yet. */
export function verifiedSpecialties(doctor: PublicDoctor): readonly ClinicalSpecialty[] {
  return (doctor.clinicalSpecialties ?? []).filter(
    (s) => s.confidence === "high" || s.confidence === "medium",
  );
}

/** The distinct NUCC classification groups a doctor's verified specialties fall under. */
export function specialtyGroupsOf(doctor: PublicDoctor): Set<string> {
  const out = new Set<string>();
  for (const s of verifiedSpecialties(doctor)) {
    const g = (s.group || s.labelEn || "").trim();
    if (g) out.add(g);
  }
  return out;
}

/** Short honest badge for how a specialty was sourced. */
export function specialtySourceBadge(source: SpecialtySource): string {
  switch (source) {
    case "nppes":
      return "NPPES-verified";
    case "nil":
      return "NIL-verified";
    case "curated":
      return "curated";
    case "consortium":
      return "consortium";
    case "clinic_llm":
      return "from clinic page";
    case "orcid":
      return "from ORCID";
    case "inferred":
      return "inferred — unverified";
  }
}

export function reachabilityLabel(r: Reachability): string {
  switch (r) {
    case "sees_patients":
      return "Sees patients";
    case "expert_reachable":
      return "Expert — reachable for consult";
    default:
      return "";
  }
}

// US state / territory abbreviations the finder's geo step sometimes mis-stores as a country.
const US_STATE_ABBREVS = new Set([
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
  "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
  "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
  "VA", "WA", "WV", "WI", "WY", "DC",
]);

/**
 * Honest, clean "where they practise" label. Prefers a real NPPES practice (City, ST) over the
 * noisy PubMed-affiliation guess, and scrubs the classic artifacts: a US state abbrev parsed as a
 * country ("Washington, MD" → "Washington, DC"), and "City, City" duplication ("MD, MD" → "MD").
 */
export function doctorLocation(doctor: PublicDoctor): string {
  const nppes = (doctor.practices ?? []).find((p) => p.source === "nppes" && p.city);
  if (nppes) {
    const st = (nppes.state || "").trim().toUpperCase();
    if (st) return `${nppes.city}, ${st}`;
    return nppes.country ? `${nppes.city}, ${nppes.country}` : nppes.city;
  }
  const city = (doctor.city || "").trim();
  const country = (doctor.country || "").trim();
  const cityUP = city.toUpperCase();
  const countryUP = country.toUpperCase();
  const parts: string[] = [];
  if (city && city !== "—") parts.push(city);
  if (
    country &&
    country !== "—" &&
    countryUP !== cityUP &&
    !US_STATE_ABBREVS.has(countryUP)
  ) {
    // A real country/ISO token distinct from the city.
    parts.push(country);
  } else if (US_STATE_ABBREVS.has(countryUP) && !US_STATE_ABBREVS.has(cityUP)) {
    // The "country" is actually a US state → render "City, ST".
    parts.push(countryUP);
  }
  return parts.length > 0 ? parts.join(", ") : "Location not listed";
}
