import type { UserLocation } from "../router/types";

export const CITY_COORDS: Record<string, UserLocation> = {
  "Zielona Góra": { lat: 51.935, lng: 15.506 },
  Warsaw: { lat: 52.229, lng: 21.012 },
  Poznań: { lat: 52.408, lng: 16.934 },
  Kraków: { lat: 50.064, lng: 19.945 },
  Gdańsk: { lat: 54.352, lng: 18.646 },
  Berlin: { lat: 52.52, lng: 13.405 },
  Leiden: { lat: 52.166, lng: 4.49 },
  Rome: { lat: 41.902, lng: 12.496 },
};

export const CITY_NAMES = Object.keys(CITY_COORDS);

export const DEFAULT_CITY = "Warsaw";

export function userLocationFromCity(city: string): UserLocation | null {
  return CITY_COORDS[city] ?? null;
}
