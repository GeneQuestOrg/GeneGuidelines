import { Badge, Button, Section } from "@gene-guidelines/ui";
import type { UserLocation } from "../router/types";
import { DistancePill } from "../components/DistancePill";
import { SpecialistDisclaimer } from "../components/SpecialistDisclaimer";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useDoctor } from "../hooks/useDoctor";
import { haversineKm } from "../utils/geo";
import { pubmedRoleLabel } from "../utils/doctorLabels";
import { pubmedArticleUrl } from "../utils/pubmedUrl";
import { PlaceholderView } from "./PlaceholderView";
import { isWorkflowDoctorSource } from "../types/doctor";
import "../styles/doctors.css";

export interface DoctorProfileViewProps {
  readonly slug: string;
  readonly userLoc: UserLocation | null;
  readonly onNav: (path: string) => void;
}

export function DoctorProfileView({ slug, userLoc, onNav }: DoctorProfileViewProps) {
  const { doctor, loading, error } = useDoctor(slug);
  const { diseases } = useDiseaseCatalog();

  if (loading) {
    return (
      <section className="page page--doctor">
        <p className="page__loading">Loading profile…</p>
      </section>
    );
  }

  if (error != null) {
    return (
      <PlaceholderView
        title="Could not load profile"
        description={error}
        primaryAction={{ label: "All specialists", path: "/doctors" }}
        onNav={onNav}
      />
    );
  }

  if (doctor == null) {
    return (
      <PlaceholderView
        title="Specialist not found"
        description={`No profile for “${slug}”. Browse the directory or pick another disease.`}
        primaryAction={{ label: "All specialists", path: "/doctors" }}
        onNav={onNav}
      />
    );
  }

  const km =
    userLoc != null ? haversineKm(userLoc, { lat: doctor.lat, lng: doctor.lng }) : null;
  const roleLabel = pubmedRoleLabel(doctor.pubmedRole);
  const evidence = doctor.evidence;

  return (
    <section className="page page--doctor">
      <SpecialistDisclaimer />
      <div className="dprofile__hero">
        <div className="dprofile__hero-top">
          <div>
            {doctor.role ? <div className="dprofile__role">{doctor.role}</div> : null}
            <h1 className="dprofile__name">{doctor.name}</h1>
            <div className="dprofile__spec">{doctor.specialty}</div>
            <div className="dprofile__inst">
              {doctor.institution} · {doctor.city}, {doctor.country}
            </div>
          </div>
          {km != null ? <DistancePill km={km} /> : null}
        </div>

        {doctor.bio ? <p className="dprofile__bio">{doctor.bio}</p> : null}

        <div className="dprofile__score-row">
          <div className="dprofile__score">
            <div className="dprofile__score-label">PubMed score</div>
            <div className="dprofile__score-num">
              {doctor.score}
              <span>/100</span>
            </div>
            <div className="dprofile__score-meter" aria-hidden>
              <i style={{ width: `${doctor.score}%` }} />
            </div>
          </div>
          <div className="dprofile__role-tag">
            <div className="dprofile__score-label">Classification</div>
            <span className={`tag tag--role tag--${doctor.pubmedRole} tag--lg`}>{roleLabel}</span>
            {isWorkflowDoctorSource(doctor.source) ? (
              <Badge variant="ok">Doctor Finder</Badge>
            ) : null}
          </div>
        </div>

        <div className="dprofile__evidence">
          <div className="dprofile__label">Evidence</div>
          <div className="ev-grid">
            <div className="ev">
              <span>First / last author papers</span>
              <b>{evidence.firstOrLastAuthorPapers}</b>
            </div>
            <div className="ev">
              <span>Review papers</span>
              <b>{evidence.reviewPapers}</b>
            </div>
            <div className={`ev${evidence.citesRecentGuidelines ? " ev--ok" : " ev--warn"}`}>
              <span>Cites current guidelines</span>
              <b>{evidence.citesRecentGuidelines ? "Yes" : "No"}</b>
            </div>
            <div className={`ev${evidence.activeLast2y ? " ev--ok" : " ev--warn"}`}>
              <span>Active in last 2 years</span>
              <b>{evidence.activeLast2y ? "Yes" : "No"}</b>
            </div>
            <div className={`ev${evidence.guidelineOrConsensusCoauthor ? " ev--ok" : ""}`}>
              <span>Guideline / consensus co-author</span>
              <b>{evidence.guidelineOrConsensusCoauthor ? "Yes" : "—"}</b>
            </div>
          </div>
        </div>
      </div>

      <Section title="Diseases" sub="Areas of expertise supported by publications.">
        <div className="chip-row">
          {doctor.diseases.map((diseaseSlug) => {
            const disease = diseases.find((d) => d.slug === diseaseSlug);
            return (
              <button
                key={diseaseSlug}
                type="button"
                className="chip chip--btn"
                onClick={() => onNav(`/diseases/${diseaseSlug}`)}
              >
                {disease?.nameShort ?? diseaseSlug}
              </button>
            );
          })}
        </div>
      </Section>

      <Section
        title="Selected publications"
        count={doctor.publications.length}
        divider
      >
        {doctor.publications.length === 0 ? (
          <p className="d-panel-empty">
            No indexed publications for this profile in the catalog seed.
          </p>
        ) : (
          <ul className="pubs">
            {doctor.publications.map((pub) => (
              <li key={pub.pmid} className="pub">
                <div className="pub__pos">{pub.position}</div>
                <div className="pub__body">
                  <div className="pub__title">{pub.title}</div>
                  <div className="pub__meta">
                    <em>{pub.journal}</em>
                    {pub.year != null ? ` · ${pub.year}` : ""}
                    {pub.pmid ? (
                      <>
                        {" · "}
                        <a href={pubmedArticleUrl(pub.pmid)} target="_blank" rel="noreferrer">
                          PMID {pub.pmid}
                        </a>
                      </>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Endorsements" divider>
        {doctor.endorsements.length === 0 ? (
          <p className="d-panel-empty">No consortium endorsements listed.</p>
        ) : (
          <div className="chip-row">
            {doctor.endorsements.map((label) => (
              <span key={label} className="chip chip--ok">
                {label}
              </span>
            ))}
          </div>
        )}
      </Section>

      <div className="dprofile__contact">
        <div>
          <h2>Contact</h2>
          <p>
            Request contact through GeneQuest — we protect direct email and include family
            context in the introduction.
          </p>
          <p className="dprofile__source">
            Public data source: {doctor.publicSource || "—"}
            {isWorkflowDoctorSource(doctor.source) && doctor.executionId
              ? ` · Doctor Finder run ${doctor.executionId}`
              : ""}
          </p>
        </div>
        <Button type="button" variant="ghost" onClick={() => onNav("/about")}>
          About GeneQuest & contact
        </Button>
      </div>
    </section>
  );
}
