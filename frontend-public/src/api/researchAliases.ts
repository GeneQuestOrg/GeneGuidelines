import { apiPostJson } from "./client";
import { DEFAULT_GUIDELINE_PROFILE } from "./guidelineRun";

export interface SuggestDiseaseAliasesResponse {
  aliases: string[];
}

export async function suggestDiseaseAliases(
  diseaseName: string,
  profile?: string,
): Promise<SuggestDiseaseAliasesResponse> {
  const resolved = profile ?? DEFAULT_GUIDELINE_PROFILE;
  return apiPostJson<SuggestDiseaseAliasesResponse>(
    "/api/doctor-finder/suggest-aliases",
    {
      disease_name: diseaseName.trim(),
      ...(resolved != null ? { model_profile: resolved } : {}),
    },
  );
}

export function parseAliasesRaw(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of raw.split(/[,\n]/)) {
    const s = part.trim();
    if (!s) continue;
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

export function mergeAliasesRaw(existing: string, added: string[]): string {
  const merged = [...parseAliasesRaw(existing)];
  const seen = new Set(merged.map((s) => s.toLowerCase()));
  for (const a of added) {
    const t = a.trim();
    if (!t) continue;
    const key = t.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(t);
  }
  return merged.join(", ");
}
