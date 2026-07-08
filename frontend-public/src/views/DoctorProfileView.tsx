import { useState } from "react";
import { Badge, Button, Section } from "@gene-guidelines/ui";
import type { UserLocation } from "../router/types";
import { useAccountContext } from "../auth/accountContext";
import { recFormMode } from "../utils/contributionGating";
import { repositories } from "../repositories";
import { ApiRequestError } from "../api/client";
import { DistancePill } from "../components/DistancePill";
import { SpecialistDisclaimer } from "../components/SpecialistDisclaimer";
import { TrialsList } from "../components/TrialsList";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useDoctor } from "../hooks/useDoctor";
import { useRelatedTrials } from "../hooks/useRelatedTrials";
import { addedViaOf } from "../utils/doctorFilters";
import { doctorLocation, pubmedRoleLabel, tierForDisease } from "../utils/doctorLabels";
import { haversineKm } from "../utils/geo";
import {
  type LocalParentRec,
  type LocalRecRelation,
  useLocalParentRecs,
} from "../utils/localParentRecs";
import { nearestPractice, practiceList } from "../utils/practices";
import { publicationRecordLink, pubmedArticleUrl } from "../utils/pubmedUrl";
import { PlaceholderView } from "./PlaceholderView";
import type { AddedVia } from "../types/doctor";
import { isWorkflowDoctorSource } from "../types/doctor";
import "../styles/doctors.css";

const PROVENANCE_LABEL: Record<AddedVia, string | null> = {
  pubmed: "PubMed",
  parent: "Parent-added",
  consortium: "Consortium",
  nil: null,
};

const MIN_REC_CHARS = 20;

/** How many publications to show before the reader opts into the full shelf. */
const TOP_PUBLICATIONS = 3;

interface IdentityBadge {
  readonly label: string;
  readonly title: string;
  readonly ok: boolean;
}

/**
 * Honest identity-confidence label for the hero. We only badge the two ends of
 * the scale that carry a signal: a verified identity (positive) and a name-only
 * match (caution). "medium" stays unbadged to avoid clutter.
 */
function identityBadge(
  confidence: "high" | "medium" | "low" | null | undefined,
): IdentityBadge | null {
  if (confidence === "high") {
    return {
      label: "Verified identity",
      title:
        "Identified by ORCID or a curated match — this profile is one specific person.",
      ok: true,
    };
  }
  if (confidence === "low") {
    return {
      label: "Name-matched only",
      title:
        "Matched by name from PubMed without an ORCID — distinct people with similar names may be merged, so treat the counts with caution.",
      ok: false,
    };
  }
  return null;
}

export interface DoctorProfileViewProps {
  readonly slug: string;
  readonly userLoc: UserLocation | null;
  readonly onNav: (path: string) => void;
}

export function DoctorProfileView({ slug, userLoc, onNav }: DoctorProfileViewProps) {
  const { doctor, loading, error } = useDoctor(slug);
  const { diseases } = useDiseaseCatalog();
  const { recs: localRecs, addRec } = useLocalParentRecs(slug);
  const relatedTrials = useRelatedTrials(doctor?.diseases ?? []);
  const account = useAccountContext();
  const [showAllPubs, setShowAllPubs] = useState(false);

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

  const nearest = nearestPractice(doctor, userLoc);
  const km =
    userLoc != null && nearest.lat != null && nearest.lng != null
      ? haversineKm(userLoc, { lat: nearest.lat, lng: nearest.lng })
      : null;
  const roleLabel = pubmedRoleLabel(doctor.pubmedRole);
  const evidence = doctor.evidence;
  const provenanceLabel = PROVENANCE_LABEL[addedViaOf(doctor)];
  const idBadge = identityBadge(doctor.identityConfidence);

  const dataRecs = doctor.parentRecs ?? [];
  const dataRecCount = evidence.parentRecCount ?? dataRecs.length;
  const familyRecCount = dataRecs.length + localRecs.length;
  const venues = practiceList(doctor, userLoc);

  const publications = doctor.publications;
  const visiblePublications = showAllPubs
    ? publications
    : publications.slice(0, TOP_PUBLICATIONS);
  const recordLink = publicationRecordLink(doctor.slug, doctor.name);

  return (
    <section className="page page--doctor">
      <SpecialistDisclaimer />
      <div className="dprofile__hero">
        <div className="dprofile__hero-top">
          <div>
            {doctor.role ? <div className="dprofile__role">{doctor.role}</div> : null}
            <h1 className="dprofile__name">{doctor.name}</h1>
            <div className="dprofile__spec">
              {doctor.specialty?.trim() ? (
                doctor.specialty
              ) : (
                <span className="dprofile__spec--unverified">Specialty not verified</span>
              )}
            </div>
            <div className="dprofile__inst">
              {doctor.institution} · {doctorLocation(doctor)}
            </div>
            <div className="dprofile__chips">
              {provenanceLabel ? (
                <span className="tag tag--source">{provenanceLabel}</span>
              ) : null}
              {idBadge ? (
                <span
                  className={`tag ${idBadge.ok ? "tag--ok" : "tag--warn"}`}
                  title={idBadge.title}
                >
                  {idBadge.label}
                </span>
              ) : null}
              {doctor.reviewStatus === "pending" ? (
                <span className="tag tag--warn">Pending review</span>
              ) : null}
              {familyRecCount > 0 ? (
                <span className="tag tag--ok">
                  Recommended by {familyRecCount}{" "}
                  {familyRecCount === 1 ? "family" : "families"}
                </span>
              ) : null}
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
            <div className={`ev${dataRecCount > 0 ? " ev--ok" : ""}`}>
              <span>Recommended by families</span>
              <b>{dataRecCount}</b>
            </div>
          </div>
        </div>
      </div>

      <Section title="Diseases" sub="Areas of expertise supported by publications.">
        <div className="dprofile__disease-rows">
          {doctor.diseases.map((diseaseSlug) => {
            const disease = diseases.find((d) => d.slug === diseaseSlug);
            const tier = tierForDisease(doctor, diseaseSlug);
            return (
              <div key={diseaseSlug} className="dprofile__disease-row">
                <button
                  type="button"
                  className="chip chip--btn"
                  onClick={() => onNav(`/diseases/${diseaseSlug}`)}
                >
                  {disease?.nameShort ?? diseaseSlug}
                </button>
                <span className={`tag tag--role tag--${tier}`}>{pubmedRoleLabel(tier)}</span>
              </div>
            );
          })}
        </div>
      </Section>

      <Section
        title="Selected publications"
        count={publications.length}
        sub="What this specialist has actually published on these conditions."
        divider
      >
        {publications.length === 0 ? (
          <p className="d-panel-empty">
            No indexed publications for this profile in the catalog seed.
          </p>
        ) : (
          <>
            <ul className="pubs">
              {visiblePublications.map((pub) => (
                <li key={pub.pmid} className="pub">
                  <div className="pub__pos">{pub.position}</div>
                  <div className="pub__body">
                    <div className="pub__title">
                      {pub.title}
                      {pub.meshMajor ? (
                        <span title="The disease is a major MeSH topic of this paper — it is about the disease, not just mentioning it.">
                          {" "}
                          <Badge variant="ok">★ MeSH-major</Badge>
                        </span>
                      ) : null}
                    </div>
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
            <div className="pubs__actions">
              {publications.length > TOP_PUBLICATIONS ? (
                <button
                  type="button"
                  className="link-btn pubs__more"
                  onClick={() => setShowAllPubs((value) => !value)}
                >
                  {showAllPubs
                    ? "Show fewer"
                    : `Show all ${publications.length} selected publications`}
                </button>
              ) : null}
              {recordLink ? (
                <a
                  className="pubs__shelf"
                  href={recordLink.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {recordLink.label} →
                </a>
              ) : null}
            </div>
          </>
        )}
      </Section>

      <Section title="Where they practise" count={venues.length} divider>
        <ul className="venues">
          {venues.map(({ practice, km: venueKm, nearest: isNearest }, index) => (
            <li key={`${practice.name}-${index}`} className="venue">
              <div className="venue__head">
                <span className="venue__name">{practice.name}</span>
                {isNearest ? <span className="tag tag--ok">Nearest</span> : null}
                {venueKm != null ? <DistancePill km={venueKm} /> : null}
              </div>
              <div className="venue__type">{practice.type}</div>
              {practice.address ? <div className="venue__addr">{practice.address}</div> : null}
              <div className="venue__city">{practice.city}</div>
              {practice.website ? (
                <a
                  className="venue__link"
                  href={practice.website}
                  target="_blank"
                  rel="noreferrer"
                >
                  {practice.website}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Parent recommendations"
        count={dataRecs.length + localRecs.length}
        sub="Family experiences PubMed mining cannot surface."
        divider
      >
        {dataRecs.length + localRecs.length === 0 ? (
          <p className="d-panel-empty">No family recommendations yet.</p>
        ) : (
          <ul className="recs">
            {dataRecs.map((rec, index) => (
              <li key={`data-${index}`} className="rec">
                <p className="rec__text">{rec.text}</p>
                <div className="rec__meta">
                  {rec.by}
                  {rec.region ? ` · ${rec.region}` : ""}
                  {rec.date ? ` · ${rec.date}` : ""}
                </div>
              </li>
            ))}
            {localRecs.map((rec, index) => (
              <li key={`local-${index}`} className="rec rec--local">
                <p className="rec__text">{rec.text}</p>
                <div className="rec__meta">
                  {rec.relation === "carer" ? "carer" : "parent"}
                  {rec.region ? ` · ${rec.region}` : ""}
                  {rec.date ? ` · ${rec.date}` : ""}
                </div>
                <div className="rec__local-note">
                  Saved on this device — will enter moderation once accounts launch.
                </div>
              </li>
            ))}
          </ul>
        )}
        <AddRecForm doctorSlug={slug} account={account} onAdd={addRec} />
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

      {evidence.runsClinicalTrial ? (
        <Section
          title="Related trials"
          sub="This specialist is involved in clinical-trial research. Below are active trials for this condition on ClinicalTrials.gov — not necessarily this doctor's own."
          divider
        >
          {relatedTrials.loading ? (
            <p className="d-panel-empty">Loading trials…</p>
          ) : relatedTrials.error != null ? (
            <p className="d-panel-empty">Could not load trials: {relatedTrials.error}</p>
          ) : (
            <TrialsList trials={relatedTrials.trials} />
          )}
        </Section>
      ) : null}

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
          {doctor.rodo?.note ? (
            <p className="dprofile__rodo">{doctor.rodo.note}</p>
          ) : null}
        </div>
        <Button type="button" variant="ghost" onClick={() => onNav("/about")}>
          About GeneQuest & contact
        </Button>
      </div>
    </section>
  );
}

type AccountCtx = ReturnType<typeof useAccountContext>;

interface AddRecFormProps {
  readonly doctorSlug: string;
  readonly account: AccountCtx;
  readonly onAdd: (rec: LocalParentRec) => void;
}

/**
 * Recommendation form, env-gated on VITE_AUTH0_DOMAIN via the account context:
 * - Auth0 unset (`signInAvailable` false): localStorage echo, exactly as today.
 * - Auth0 on, signed-out: a sign-in CTA in place of the form.
 * - Auth0 on, signed-in parent: a real POST; on success the author's entry is
 *   echoed locally and labelled "Awaiting moderation".
 */
function AddRecForm({ doctorSlug, account, onAdd }: AddRecFormProps) {
  const [text, setText] = useState("");
  const [region, setRegion] = useState("");
  const [relation, setRelation] = useState<LocalRecRelation>("parent");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const trimmed = text.trim();
  const tooShort = trimmed.length < MIN_REC_CHARS;

  const mode = recFormMode({
    signInAvailable: account.signInAvailable,
    isAuthenticated: account.isAuthenticated,
    role: account.account?.role,
  });
  // "post" hits the API; "local" keeps the historical localStorage echo.
  const writePathLive = mode === "post";

  // Signed-out / non-contributor (Auth0 on): a sign-in CTA in place of the form.
  if (mode === "sign-in" || mode === "not-allowed") {
    return (
      <div className="rec-form rec-form--signin">
        <div className="rec-form__title">Add your recommendation</div>
        {mode === "not-allowed" ? (
          <p className="rec-form__disclaimer">
            Only parents and carers can leave a recommendation.
          </p>
        ) : (
          <button type="button" className="link-btn" onClick={account.login}>
            Sign in to recommend this doctor
          </button>
        )}
      </div>
    );
  }

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (tooShort) {
      setTouched(true);
      return;
    }
    const rec: LocalParentRec = {
      text: trimmed,
      region: region.trim(),
      relation,
      date: new Date().toISOString().slice(0, 10),
    };
    if (writePathLive) {
      setSubmitting(true);
      setSubmitError(null);
      try {
        await repositories().doctors.submitParentRec(doctorSlug, {
          text: trimmed,
          region: region.trim() || undefined,
          relation,
        });
      } catch (e: unknown) {
        const message =
          e instanceof ApiRequestError || e instanceof Error
            ? e.message
            : "Could not submit — please try again.";
        setSubmitError(message);
        setSubmitting(false);
        return;
      }
      setSubmitting(false);
    }
    // Echo locally so the author sees their entry immediately (labelled
    // "Awaiting moderation" via the rec--local note in the list above).
    onAdd(rec);
    setText("");
    setRegion("");
    setRelation("parent");
    setTouched(false);
  }

  return (
    <form className="rec-form" onSubmit={(e) => void handleSubmit(e)}>
      <div className="rec-form__title">Add your recommendation</div>
      <textarea
        className="rec-form__textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => setTouched(true)}
        placeholder={`What was your experience? (at least ${MIN_REC_CHARS} characters)`}
        rows={3}
        required
      />
      {touched && tooShort ? (
        <p className="rec-form__error">Please write at least {MIN_REC_CHARS} characters.</p>
      ) : null}
      {submitError != null ? (
        <p className="rec-form__error" role="alert">
          {submitError}
        </p>
      ) : null}
      <div className="rec-form__row">
        <input
          className="rec-form__input"
          type="text"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          placeholder="Region (optional)"
        />
        <select
          className="rec-form__select"
          value={relation}
          onChange={(e) => setRelation(e.target.value === "carer" ? "carer" : "parent")}
          aria-label="Your relation"
        >
          <option value="parent">Parent</option>
          <option value="carer">Carer</option>
        </select>
        <Button type="submit" variant="ghost" disabled={submitting}>
          {submitting ? "Submitting…" : "Save recommendation"}
        </Button>
      </div>
      <p className="rec-form__disclaimer">
        {writePathLive
          ? "Submitted for moderation — your entry appears publicly once a reviewer approves it."
          : "Saved on this device for now. Publication requires moderation once accounts launch."}
      </p>
    </form>
  );
}
