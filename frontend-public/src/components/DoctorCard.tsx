import { type PublicDoctor, isWorkflowDoctorSource } from "../types/doctor";
import { pubmedRoleLabel } from "../utils/doctorLabels";
import { DistancePill } from "./DistancePill";

export interface DoctorCardProps {
  readonly doctor: PublicDoctor;
  readonly km: number | null;
  readonly compact?: boolean;
  readonly onNav: (path: string) => void;
}

export function DoctorCard({ doctor, km, compact = false, onNav }: DoctorCardProps) {
  const roleLabel = pubmedRoleLabel(doctor.pubmedRole);
  const href = `#/doctor/${doctor.slug}`;

  return (
    <a
      href={href}
      className={`doc${compact ? " doc--compact" : ""}`}
      onClick={(e) => {
        e.preventDefault();
        onNav(`/doctor/${doctor.slug}`);
      }}
    >
      <div className="doc__top">
        <div className="doc__name">{doctor.name}</div>
        {km != null ? <DistancePill km={km} /> : null}
      </div>
      <div className="doc__spec">{doctor.specialty}</div>
      <div className="doc__inst">
        {doctor.institution} · {doctor.city}, {doctor.country}
      </div>
      {!compact ? (
        <div className="doc__meta">
          <span className={`tag tag--role tag--${doctor.pubmedRole}`}>{roleLabel}</span>
          <span className="tag tag--score">
            PubMed score <b>{doctor.score}</b>
          </span>
          {doctor.evidence.citesRecentGuidelines ? (
            <span className="tag tag--ok">Cites current guidelines</span>
          ) : (
            <span className="tag tag--warn">No recent guideline citations</span>
          )}
          {isWorkflowDoctorSource(doctor.source) ? (
            <span className="tag tag--source">Doctor Finder</span>
          ) : null}
        </div>
      ) : null}
    </a>
  );
}
