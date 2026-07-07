import type { UserLocation } from "../router/types";
import type { PublicDoctor } from "../types/doctor";
import { haversineKm } from "./geo";

export interface DoctorWithDistance extends PublicDoctor {
  readonly km: number | null;
}

export function attachDoctorDistances(
  doctors: readonly PublicDoctor[],
  userLoc: UserLocation | null,
): DoctorWithDistance[] {
  return doctors.map((doctor) => ({
    ...doctor,
    km:
      userLoc && doctor.lat != null && doctor.lng != null
        ? haversineKm(userLoc, { lat: doctor.lat, lng: doctor.lng })
        : null,
  }));
}

export function sortDoctorsByDistanceThenScore(
  doctors: readonly DoctorWithDistance[],
): DoctorWithDistance[] {
  return [...doctors].sort((a, b) => {
    if (a.km != null && b.km != null) {
      return a.km - b.km;
    }
    if (a.km != null) {
      return -1;
    }
    if (b.km != null) {
      return 1;
    }
    return b.score - a.score;
  });
}
