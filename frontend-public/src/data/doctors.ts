import type { DoctorSummary } from "../types";
import { PUBLIC_DOCTORS } from "./publicDoctors";

export const DOCTORS: readonly DoctorSummary[] = PUBLIC_DOCTORS.map((doctor) => ({
  slug: doctor.slug,
  name: doctor.name,
  specialty: doctor.specialty,
  institution: doctor.institution,
  city: doctor.city,
  country: doctor.country,
  diseases: doctor.diseases,
}));
