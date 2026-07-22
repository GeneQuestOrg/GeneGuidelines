import { useTranslation } from "react-i18next";
import { type PublicDoctor, isWorkflowDoctorSource } from "../types/doctor";
import {
  doctorLocation,
  pubmedRoleLabel,
  reachabilityLabel,
  recencyBandOf,
  recencyLabel,
  specialtySourceBadge,
  verifiedSpecialties,
  VALID_PUBMED_ROLES,
} from "../utils/doctorLabels";
import { DistancePill } from "./DistancePill";

export interface DoctorCardProps {
  readonly doctor: PublicDoctor;
  readonly km: number | null;
  readonly compact?: boolean;
  readonly onNav: (path: string) => void;
}

export function DoctorCard({ doctor, km, compact = false, onNav }: DoctorCardProps) {
  const { t } = useTranslation("common");
  const roleLabel = t(pubmedRoleLabel(doctor.pubmedRole));
  const safeRoleClass = VALID_PUBMED_ROLES.has(doctor.pubmedRole) ? doctor.pubmedRole : "unknown";
  // Clinical specialty is a SEPARATE axis from the PubMed research role. Prefer verified NUCC
  // specialties (with a source badge); fall back to the deprecated free-text field; else say
  // "not verified" honestly rather than showing a role token.
  const specialties = verifiedSpecialties(doctor);
  const primarySpecialty = specialties[0];
  const specialtyText = primarySpecialty?.labelEn ?? doctor.specialty?.trim();
  const reachText = reachabilityLabel(doctor.reachability ?? "unknown");
  const recencyBand = recencyBandOf(doctor);
  const href = `/doctor/${doctor.slug}`;

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
      {specialtyText ? (
        <div className="doc__spec">
          {specialtyText}
          {primarySpecialty ? (
            <span className={`doc__spec-src doc__spec-src--${primarySpecialty.source}`}>
              {specialtySourceBadge(primarySpecialty.source)}
            </span>
          ) : null}
        </div>
      ) : (
        <div className="doc__spec doc__spec--unverified">Specialty not verified</div>
      )}
      <div className="doc__inst">
        {doctor.institution} · {doctorLocation(doctor, t)}
      </div>
      {!compact && reachText ? (
        <div
          className={`doc__reach doc__reach--${doctor.reachability}`}
        >
          {reachText}
        </div>
      ) : null}
      {!compact ? (
        <>
          <div className="doc__meta">
            <span className={`tag tag--role tag--${safeRoleClass}`}>{roleLabel}</span>
            {recencyBand !== "unknown" ? (
              <span
                className={`tag tag--recency tag--recency-${recencyBand}`}
                title={
                  doctor.lastCentralPaperYear || doctor.lastPaperYear
                    ? `Latest disease-relevant paper: ${doctor.lastCentralPaperYear ?? doctor.lastPaperYear}`
                    : undefined
                }
              >
                {recencyLabel(recencyBand)}
              </span>
            ) : null}
            <span className="tag tag--score">
              PubMed <b>{doctor.score}</b>
              <span className="doc__score-bar">
                <i style={{ width: `${doctor.score}%` }} />
              </span>
            </span>
            {doctor.evidence.guidelineOrConsensusCoauthor ? (
              <span className="tag tag--ok">Guideline author</span>
            ) : doctor.evidence.citesRecentGuidelines ? (
              <span className="tag tag--ok">Cites guidelines</span>
            ) : null}
            {doctor.evidence.activeLast2y ? (
              <span className="tag tag--ok">Active</span>
            ) : null}
            {isWorkflowDoctorSource(doctor.source) ? (
              <span className="tag tag--source">Doctor Finder</span>
            ) : null}
          </div>
        </>
      ) : null}
    </a>
  );
}
