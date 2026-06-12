import type { UserLocation } from "../router/types";
import type { Practice, PublicDoctor } from "../types/doctor";
import { haversineKm } from "./geo";

/** Every doctor has at least one practice; fall back to the primary affiliation. */
export function practicesOf(doctor: PublicDoctor): readonly Practice[] {
  if (doctor.practices && doctor.practices.length > 0) {
    return doctor.practices;
  }
  return [
    {
      type: "primary",
      name: doctor.institution,
      city: doctor.city,
      lat: doctor.lat,
      lng: doctor.lng,
    },
  ];
}

export interface PracticeWithDistance {
  readonly practice: Practice;
  /** Distance to the user in km, or null when no user location is known. */
  readonly km: number | null;
  /** True for the closest practice when a user location is known. */
  readonly nearest: boolean;
}

/** Practices sorted nearest-first when a user location is known; flags the closest one. */
export function practiceList(
  doctor: PublicDoctor,
  userLoc: UserLocation | null,
): readonly PracticeWithDistance[] {
  const withKm = practicesOf(doctor).map((practice) => ({
    practice,
    km: userLoc ? haversineKm(userLoc, { lat: practice.lat, lng: practice.lng }) : null,
  }));
  if (userLoc) {
    withKm.sort((a, b) => (a.km ?? Infinity) - (b.km ?? Infinity));
  }
  return withKm.map((entry, index) => ({
    ...entry,
    nearest: userLoc != null && index === 0,
  }));
}

/** Closest practice to the user (or the primary one when no location is known). */
export function nearestPractice(doctor: PublicDoctor, userLoc: UserLocation | null): Practice {
  return practiceList(doctor, userLoc)[0].practice;
}

/** One map-ready (doctor, practice) pair. */
export interface PracticePin<D extends PublicDoctor = PublicDoctor> {
  readonly doctor: D;
  readonly practice: Practice;
}

/**
 * Flatten doctors into one pin per (doctor, practice) pair via {@link practicesOf}. Pairs whose
 * coordinates are not finite are skipped so the map never plots a marker at NaN/Infinity.
 */
export function practicePins<D extends PublicDoctor>(
  doctors: readonly D[],
): readonly PracticePin<D>[] {
  const pins: PracticePin<D>[] = [];
  for (const doctor of doctors) {
    for (const practice of practicesOf(doctor)) {
      if (Number.isFinite(practice.lat) && Number.isFinite(practice.lng)) {
        pins.push({ doctor, practice });
      }
    }
  }
  return pins;
}
