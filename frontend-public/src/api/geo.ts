import { getApiBaseUrl } from "./client";

export interface GeoResult {
  lat: number;
  lng: number;
  displayName: string;
}

export async function searchGeo(q: string, signal?: AbortSignal): Promise<GeoResult[]> {
  const url = `${getApiBaseUrl()}/api/geo/search?q=${encodeURIComponent(q)}`;
  const res = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Geo search failed: ${res.status}`);
  return res.json() as Promise<GeoResult[]>;
}
