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
  doctorEvidenceLine,
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
  // How much publication evidence sits behind this listing. The heading above the
  // list says "Specialists", which for someone who co-signed a single 2017 case
  // report claims far more than the record holds — and the weight was already in the
  // payload, just never shown. A reader can now weigh the name against it.
  const evidenceLine = doctorEvidenceLine(doctor, t);
  const hasMeasuredPapers = (doctor.publications?.length ?? 0) > 0;
  // The question a family actually has is "is this the person for MY child's
  // presentation", which is narrower than "has this doctor seen the disease".
  const scope = doctor.scope ?? [];
  // Some of the people a family most needs never publish. The surgeon who actually
  // operates on paediatric craniofacial FD can have zero PubMed records, and the
  // role vocabulary here is entirely PubMed-derived, so he was being shown as
  // "research leader" — a claim about a man with no papers. Where there is no
  // publication record, the card shows what we can actually stand behind instead:
  // the official clinical position and who vouches for him.
  const ernCentres = doctor.ernCentres ?? [];
  // The hospital's own paediatric capability, from the EU register. Kept to the
  // paediatric list on purpose: "has a maxillofacial ward" and "has one for children"
  // are different answers, and only the second one helps a parent.
  const paediatricWards = doctor.facility?.paediatricCapabilities ?? [];
  const clinicalSignals = hasMeasuredPapers
    ? []
    : [doctor.role, ...(doctor.endorsements ?? [])].filter(
        (value): value is string => typeof value === "string" && value.trim().length > 0,
      );
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
        <div className="doc__spec doc__spec--unverified">{t("doctorCard.specialtyNotVerified")}</div>
      )}
      {paediatricWards.length > 0 ? (
        <div className="doc__facility" title={t("doctorCard.facilityTooltip", {
          facility: doctor.facility?.name ?? "",
          release: doctor.facility?.release ?? "",
        })}>
          {t("doctorCard.facilityWards", {
            wards: paediatricWards.map((key) => t(`doctorCard.scope.${key}`)).join(" · "),
          })}
        </div>
      ) : null}
      {ernCentres.map((centre) => (
        <a
          key={`${centre.ern}-${centre.centre}`}
          className="doc__ern"
          href={centre.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          title={t("doctorCard.ernTooltip", {
            ern: centre.ern,
            centre: centre.centre,
            role: centre.roleDetail,
            date: centre.verifiedOn,
          })}
        >
          {t("doctorCard.ernCentre", { ern: centre.ern })}
        </a>
      ))}
      {scope.length > 0 ? (
        <div className="doc__scope">
          {scope.map((tag) => (
            <span key={tag.key} className={`chip chip--scope chip--scope-${tag.key}`} title={tag.basis}>
              {t(`doctorCard.scope.${tag.key}`)}
            </span>
          ))}
        </div>
      ) : null}
      <div className="doc__inst">
        {doctor.institution} · {doctorLocation(doctor, t)}
      </div>
      {/* What kind of contact this doctor has had with the disease. Nobody is cut
          from the list for having only co-signed a case report — that person may
          still be the nearest one who has seen it — but the reader gets to see the
          calibre next to the name instead of inferring it from the "Specialists"
          heading. Shown in compact mode too: the per-disease list is exactly where
          the choice gets made, and it was the one place hiding this. */}
      {hasMeasuredPapers ? (
        <div className="doc__evidence">
          <span className={`tag tag--role tag--${safeRoleClass}`}>{roleLabel}</span>
          {evidenceLine ? <span className="doc__evidence-detail">{evidenceLine}</span> : null}
        </div>
      ) : clinicalSignals.length > 0 ? (
        <div className="doc__evidence">
          {clinicalSignals.map((signal) => (
            <span key={signal} className="tag tag--clinical">
              {signal}
            </span>
          ))}
        </div>
      ) : null}
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
            {/* No "Cites guidelines" badge: the pipeline hardcodes that flag to
                false (flows/doctor_finder/role_classifier.py), so it only ever
                appeared on the six hand-written fixture doctors. */}
            {doctor.evidence?.guidelineOrConsensusCoauthor ? (
              <span className="tag tag--ok">Guideline author</span>
            ) : null}
            {doctor.evidence?.activeLast2y ? (
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
