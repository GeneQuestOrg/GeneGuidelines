import { useState } from "react";
import { useTranslation } from "react-i18next";
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

const PROVENANCE_KEY: Record<AddedVia, string | null> = {
  pubmed: "provenance.pubmed",
  parent: "provenance.parent",
  consortium: "provenance.consortium",
  nil: null,
};

const MIN_REC_CHARS = 20;

/** How many publications to show before the reader opts into the full shelf. */
const TOP_PUBLICATIONS = 3;

interface IdentityBadge {
  readonly labelKey: string;
  readonly titleKey: string;
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
      labelKey: "identity.verifiedLabel",
      titleKey: "identity.verifiedTitle",
      ok: true,
    };
  }
  if (confidence === "low") {
    return {
      labelKey: "identity.nameMatchedLabel",
      titleKey: "identity.nameMatchedTitle",
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
  const { t } = useTranslation("doctor-profile");
  const { doctor, loading, error } = useDoctor(slug);
  const { diseases } = useDiseaseCatalog();
  const { recs: localRecs, addRec } = useLocalParentRecs(slug);
  const relatedTrials = useRelatedTrials(doctor?.diseases ?? []);
  const account = useAccountContext();
  const [showAllPubs, setShowAllPubs] = useState(false);

  if (loading) {
    return (
      <section className="page page--doctor">
        <p className="page__loading">{t("loading")}</p>
      </section>
    );
  }

  if (error != null) {
    return (
      <PlaceholderView
        title={t("errorLoadTitle")}
        description={error}
        primaryAction={{ label: t("allSpecialistsAction"), path: "/doctors" }}
        onNav={onNav}
      />
    );
  }

  if (doctor == null) {
    return (
      <PlaceholderView
        title={t("notFoundTitle")}
        description={t("notFoundDescription", { slug })}
        primaryAction={{ label: t("allSpecialistsAction"), path: "/doctors" }}
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
  const provenanceKey = PROVENANCE_KEY[addedViaOf(doctor)];
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
                <span className="dprofile__spec--unverified">{t("specialtyNotVerified")}</span>
              )}
            </div>
            <div className="dprofile__inst">
              {doctor.institution} · {doctorLocation(doctor)}
            </div>
            <div className="dprofile__chips">
              {provenanceKey ? (
                <span className="tag tag--source">{t(provenanceKey)}</span>
              ) : null}
              {idBadge ? (
                <span
                  className={`tag ${idBadge.ok ? "tag--ok" : "tag--warn"}`}
                  title={t(idBadge.titleKey)}
                >
                  {t(idBadge.labelKey)}
                </span>
              ) : null}
              {doctor.reviewStatus === "pending" ? (
                <span className="tag tag--warn">{t("pendingReview")}</span>
              ) : null}
              {familyRecCount > 0 ? (
                <span className="tag tag--ok">
                  {t("recommendedByFamilies", { count: familyRecCount })}
                </span>
              ) : null}
            </div>
          </div>
          {km != null ? <DistancePill km={km} /> : null}
        </div>

        {doctor.bio ? <p className="dprofile__bio">{doctor.bio}</p> : null}

        <div className="dprofile__score-row">
          <div className="dprofile__score">
            <div className="dprofile__score-label">{t("score.label")}</div>
            <div className="dprofile__score-num">
              {doctor.score}
              <span>{t("score.outOf")}</span>
            </div>
            <div className="dprofile__score-meter" aria-hidden>
              <i style={{ width: `${doctor.score}%` }} />
            </div>
          </div>
          <div className="dprofile__role-tag">
            <div className="dprofile__score-label">{t("classification")}</div>
            <span className={`tag tag--role tag--${doctor.pubmedRole} tag--lg`}>{roleLabel}</span>
            {isWorkflowDoctorSource(doctor.source) ? (
              <Badge variant="ok">{t("doctorFinderBadge")}</Badge>
            ) : null}
          </div>
        </div>

        <div className="dprofile__evidence">
          <div className="dprofile__label">{t("evidence.title")}</div>
          <div className="ev-grid">
            <div className="ev">
              <span>{t("evidence.firstOrLastAuthorPapers")}</span>
              <b>{evidence.firstOrLastAuthorPapers}</b>
            </div>
            <div className="ev">
              <span>{t("evidence.reviewPapers")}</span>
              <b>{evidence.reviewPapers}</b>
            </div>
            <div className={`ev${evidence.citesRecentGuidelines ? " ev--ok" : " ev--warn"}`}>
              <span>{t("evidence.citesRecentGuidelines")}</span>
              <b>{evidence.citesRecentGuidelines ? t("evidence.yes") : t("evidence.no")}</b>
            </div>
            <div className={`ev${evidence.activeLast2y ? " ev--ok" : " ev--warn"}`}>
              <span>{t("evidence.activeLast2y")}</span>
              <b>{evidence.activeLast2y ? t("evidence.yes") : t("evidence.no")}</b>
            </div>
            <div className={`ev${evidence.guidelineOrConsensusCoauthor ? " ev--ok" : ""}`}>
              <span>{t("evidence.guidelineOrConsensusCoauthor")}</span>
              <b>{evidence.guidelineOrConsensusCoauthor ? t("evidence.yes") : "—"}</b>
            </div>
            <div className={`ev${dataRecCount > 0 ? " ev--ok" : ""}`}>
              <span>{t("evidence.recommendedByFamiliesLabel")}</span>
              <b>{dataRecCount}</b>
            </div>
          </div>
        </div>
      </div>

      <Section title={t("diseases.title")} sub={t("diseases.sub")}>
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
        title={t("publications.title")}
        count={publications.length}
        sub={t("publications.sub")}
        divider
      >
        {publications.length === 0 ? (
          <p className="d-panel-empty">{t("publications.empty")}</p>
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
                        <span title={t("publications.meshMajorTitle")}>
                          {" "}
                          <Badge variant="ok">{t("publications.meshMajorBadge")}</Badge>
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
                            {t("publications.pmid", { pmid: pub.pmid })}
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
                    ? t("publications.showFewer")
                    : t("publications.showAll", { count: publications.length })}
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

      <Section title={t("venues.title")} count={venues.length} divider>
        <ul className="venues">
          {venues.map(({ practice, km: venueKm, nearest: isNearest }, index) => (
            <li key={`${practice.name}-${index}`} className="venue">
              <div className="venue__head">
                <span className="venue__name">{practice.name}</span>
                {isNearest ? <span className="tag tag--ok">{t("venues.nearest")}</span> : null}
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
        title={t("recs.title")}
        count={dataRecs.length + localRecs.length}
        sub={t("recs.sub")}
        divider
      >
        {dataRecs.length + localRecs.length === 0 ? (
          <p className="d-panel-empty">{t("recs.empty")}</p>
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
                  {rec.relation === "carer" ? t("recs.relationCarer") : t("recs.relationParent")}
                  {rec.region ? ` · ${rec.region}` : ""}
                  {rec.date ? ` · ${rec.date}` : ""}
                </div>
                <div className="rec__local-note">{t("recs.localNote")}</div>
              </li>
            ))}
          </ul>
        )}
        <AddRecForm doctorSlug={slug} account={account} onAdd={addRec} />
      </Section>

      <Section title={t("endorsements.title")} divider>
        {doctor.endorsements.length === 0 ? (
          <p className="d-panel-empty">{t("endorsements.empty")}</p>
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
        <Section title={t("trials.title")} sub={t("trials.sub")} divider>
          {relatedTrials.loading ? (
            <p className="d-panel-empty">{t("trials.loading")}</p>
          ) : relatedTrials.error != null ? (
            <p className="d-panel-empty">{t("trials.error", { error: relatedTrials.error })}</p>
          ) : (
            <TrialsList trials={relatedTrials.trials} />
          )}
        </Section>
      ) : null}

      <div className="dprofile__contact">
        <div>
          <h2>{t("contact.title")}</h2>
          <p>{t("contact.body")}</p>
          <p className="dprofile__source">
            {t("contact.publicSource", { source: doctor.publicSource || "—" })}
            {isWorkflowDoctorSource(doctor.source) && doctor.executionId
              ? t("contact.doctorFinderRun", { id: doctor.executionId })
              : ""}
          </p>
          {doctor.rodo?.note ? (
            <p className="dprofile__rodo">{doctor.rodo.note}</p>
          ) : null}
        </div>
        <Button type="button" variant="ghost" onClick={() => onNav("/about")}>
          {t("contact.cta")}
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
  const { t } = useTranslation("doctor-profile");
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
        <div className="rec-form__title">{t("addRecForm.title")}</div>
        {mode === "not-allowed" ? (
          <p className="rec-form__disclaimer">{t("addRecForm.signInOnlyNote")}</p>
        ) : (
          <button type="button" className="link-btn" onClick={account.login}>
            {t("addRecForm.signInCta")}
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
            : t("addRecForm.genericSubmitError");
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
      <div className="rec-form__title">{t("addRecForm.title")}</div>
      <textarea
        className="rec-form__textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => setTouched(true)}
        placeholder={t("addRecForm.textareaPlaceholder", { min: MIN_REC_CHARS })}
        rows={3}
        required
      />
      {touched && tooShort ? (
        <p className="rec-form__error">{t("addRecForm.tooShortError", { min: MIN_REC_CHARS })}</p>
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
          placeholder={t("addRecForm.regionPlaceholder")}
        />
        <select
          className="rec-form__select"
          value={relation}
          onChange={(e) => setRelation(e.target.value === "carer" ? "carer" : "parent")}
          aria-label={t("addRecForm.relationAriaLabel")}
        >
          <option value="parent">{t("addRecForm.relationParentOption")}</option>
          <option value="carer">{t("addRecForm.relationCarerOption")}</option>
        </select>
        <Button type="submit" variant="ghost" disabled={submitting}>
          {submitting ? t("addRecForm.submitting") : t("addRecForm.submit")}
        </Button>
      </div>
      <p className="rec-form__disclaimer">
        {writePathLive ? t("addRecForm.disclaimerLive") : t("addRecForm.disclaimerLocal")}
      </p>
    </form>
  );
}
