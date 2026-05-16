import type { UserLocation } from "../router/types";

const EARTH_RADIUS_KM = 6371;

/** Great-circle distance in kilometres between two WGS84 points. */
export function haversineKm(a: UserLocation, b: UserLocation): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function formatDistanceKm(km: number): string {
  if (km < 1) {
    return "< 1 km";
  }
  if (km < 100) {
    return `${Math.round(km)} km`;
  }
  return `${Math.round(km).toLocaleString()} km`;
}

/** EU bounding box for static map placeholder pins. */
export const EU_MAP_BOUNDS = {
  minLat: 41,
  maxLat: 60,
  minLng: -5,
  maxLng: 25,
} as const;

export function projectToEuMapPercent(
  lat: number,
  lng: number,
): { x: number; y: number } | null {
  const { minLat, maxLat, minLng, maxLng } = EU_MAP_BOUNDS;
  const x = ((lng - minLng) / (maxLng - minLng)) * 100;
  const y = (1 - (lat - minLat) / (maxLat - minLat)) * 100;
  if (x < 0 || x > 100 || y < 0 || y > 100) {
    return null;
  }
  return { x, y };
}
