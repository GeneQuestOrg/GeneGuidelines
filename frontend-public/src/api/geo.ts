import { apiGet } from "./client";

export interface GeoResult {
  lat: number;
  lng: number;
  displayName: string;
}

export async function searchGeo(q: string): Promise<GeoResult[]> {
  return apiGet<GeoResult[]>(`/api/geo/search?q=${encodeURIComponent(q)}`);
}
