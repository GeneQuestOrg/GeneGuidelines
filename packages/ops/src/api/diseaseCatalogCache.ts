import { fetchContentDiseases, type ContentDiseaseOption } from "./client";

let cached: ContentDiseaseOption[] | null = null;
let inflight: Promise<ContentDiseaseOption[]> | null = null;

/** Single shared request for disease list (avoids duplicate /api/diseases calls on Runs page). */
export function fetchContentDiseasesCached(): Promise<ContentDiseaseOption[]> {
  if (cached) {
    return Promise.resolve(cached);
  }
  if (!inflight) {
    inflight = fetchContentDiseases()
      .then((rows) => {
        cached = rows;
        return rows;
      })
      .catch((err) => {
        inflight = null;
        throw err;
      });
  }
  return inflight;
}

export function invalidateContentDiseasesCache(): void {
  cached = null;
  inflight = null;
}
