import { useMemo, useState } from "react";
import { Button, Section } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import type { UserLocation } from "../router/types";
import { DiseaseCard } from "./DiseaseCard";
import { DoctorCard } from "./DoctorCard";
import { DiseaseOpenPrList } from "./DiseaseOpenPrList";
import { FoundationsList } from "./FoundationsList";
import { QuestionsForDoctor } from "./QuestionsForDoctor";
import { TherapiesList } from "./TherapiesList";
import { TrialsList } from "./TrialsList";
import { CompactSourceShelf } from "./guidelines/CompactSourceShelf";
import { useContentPrs } from "../hooks/useContentPrs";
import { useDiseaseDoctors } from "../hooks/useDiseaseDoctors";
import { useDiseaseFoundations } from "../hooks/useDiseaseFoundations";
import { useDiseaseTherapies } from "../hooks/useDiseaseTherapies";
import { useDiseaseTrials } from "../hooks/useDiseaseTrials";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { isWorkflowDoctorSource } from "../types/doctor";
import {
  attachDoctorDistances,
  sortDoctorsByDistanceThenScore,
} from "../utils/doctorSort";
import "../styles/disease-page.css";
import "../styles/doctors.css";

export type DiseaseTabId = "overview" | "doctors" | "trials" | "guidelines";

export interface DiseaseTabsProps {
  disease: Disease;
  copy: DiseaseCopy;
  isClinician: boolean;
  related: readonly Disease[];
  relatedLoading: boolean;
  userLoc: UserLocation | null;
  onNav: (path: string) => void;
}

const TAB_ORDER: readonly DiseaseTabId[] = [
  "overview",
  "doctors",
  "trials",
  "guidelines",
];

/** How many trials the disease-page hub previews before linking out to the /trials browser. */
const TRIALS_PREVIEW_COUNT = 3;

export function DiseaseTabs({
  disease,
  copy,
  isClinician,
  related,
  relatedLoading,
  userLoc,
  onNav,
}: DiseaseTabsProps) {
  const [tab, setTab] = useState<DiseaseTabId>("overview");
  const slug = disease.slug;
  const { openPrs, loading: prsLoading, error: prsError } = useContentPrs(slug);
  const {
    payload: doctorsPayload,
    loading: doctorsLoading,
    error: doctorsError,
  } = useDiseaseDoctors(slug);
  const {
    trials,
    loading: trialsLoading,
    error: trialsError,
  } = useDiseaseTrials(slug);
  const {
    therapies,
    loading: therapiesLoading,
    error: therapiesError,
  } = useDiseaseTherapies(slug);
  const {
    foundations,
    loading: foundationsLoading,
    error: foundationsError,
  } = useDiseaseFoundations(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);

  // Parent-only copy blocks. Clinician copy omits `orientation`.
  const orientation = isClinician ? undefined : copy.orientation;

  const previewDoctors = useMemo(() => {
    if (doctorsPayload == null) {
      return [];
    }
    const rows = attachDoctorDistances(doctorsPayload.doctors, userLoc);
    return sortDoctorsByDistanceThenScore(rows).slice(0, 5);
  }, [doctorsPayload, userLoc]);

  // The disease page is an orientation hub, not a full directory: show the top few
  // trials (the hook already returns active-first) and link out to the faceted
  // /trials browser for the complete, filterable set.
  const previewTrials = useMemo(() => trials.slice(0, TRIALS_PREVIEW_COUNT), [trials]);

  return (
    <>
      <div className="d-tabs" role="tablist" aria-label="Disease sections">
        {TAB_ORDER.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`d-tabs__btn${tab === id ? " is-active" : ""}`}
            onClick={() => setTab(id)}
          >
            {copy.tabs[id]}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="d-tab-panel">
        {tab === "overview" ? (
          <>
            <Section
              title={orientation?.whatToDoNowTitle ?? copy.pathwayTitle}
              sub={orientation?.whatToDoNowBody ?? copy.pathwaySub}
            >
              <div className="path">
                <ol className="path__steps">
                  {copy.pathwaySteps.map((step, i) => (
                    <li key={step.title}>
                      <b>
                        {i + 1}. {step.title}
                      </b>{" "}
                      {step.body}
                    </li>
                  ))}
                </ol>
                <aside className="path__redflags">
                  <h3>{copy.redFlagsTitle}</h3>
                  <ul>
                    {copy.redFlags.map((flag) => (
                      <li key={flag.text}>{flag.text}</li>
                    ))}
                  </ul>
                </aside>
              </div>
            </Section>

            {orientation != null ? (
              <Section
                title={orientation.questionsForDoctorTitle}
                sub={orientation.questionsForDoctorSub}
                divider
              >
                <QuestionsForDoctor questions={orientation.questionsForDoctor} />
              </Section>
            ) : null}

            {previewDoctors.length > 0 ? (
              <Section
                title="Specialists"
                sub={copy.doctorsSub(disease.doctorsCount)}
                divider
              >
                <div className="d-doctors-preview">
                  {previewDoctors.slice(0, 3).map((doctor) => (
                    <DoctorCard
                      key={doctor.slug}
                      doctor={doctor}
                      km={doctor.km}
                      compact
                      onNav={onNav}
                    />
                  ))}
                </div>
                <div className="page__actions">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => onNav(`/doctors?disease=${slug}`)}
                  >
                    See all specialists →
                  </Button>
                </div>
              </Section>
            ) : null}

            <Section title={copy.trialsTitle} sub={copy.trialsSub(trials.length)} divider>
              {trialsError != null ? (
                <p className="d-panel-empty" role="alert">{trialsError}</p>
              ) : trialsLoading ? (
                <p className="d-panel-empty">Loading trials…</p>
              ) : trials.length === 0 ? (
                <p className="d-panel-empty">No active trials matching this disease right now.</p>
              ) : (
                <>
                  <TrialsList trials={previewTrials} />
                  <div className="page__actions">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => onNav(`/trials?disease=${slug}`)}
                    >
                      See all trials ({trials.length}) →
                    </Button>
                  </div>
                </>
              )}
            </Section>

            <Section title="Therapies" divider>
              <p className="d-panel-note">
                These options manage symptoms and slow progression — none of them fully reverses
                established disease changes.
              </p>
              {therapiesError != null ? (
                <p className="d-panel-empty" role="alert">{therapiesError}</p>
              ) : therapiesLoading ? (
                <p className="d-panel-empty">Loading therapies…</p>
              ) : (
                <TherapiesList therapies={therapies} />
              )}
            </Section>

            <Section title="Supporting foundations" divider>
              {foundationsError != null ? (
                <p className="d-panel-empty" role="alert">{foundationsError}</p>
              ) : foundationsLoading ? (
                <p className="d-panel-empty">Loading foundations…</p>
              ) : (
                <FoundationsList foundations={foundations} diseaseName={disease.name} />
              )}
            </Section>

            {orientation != null && sourceDocs.length > 0 ? (
              <Section
                title={orientation.familyDoctorTitle}
                sub={orientation.familyDoctorSub}
                action={
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => window.print()}
                  >
                    {orientation.takeToDoctorCta}
                  </Button>
                }
                divider
              >
                <CompactSourceShelf
                  docs={sourceDocs}
                  onSeeAll={() => onNav(`/diseases/${slug}/guidelines`)}
                />
              </Section>
            ) : null}

            {openPrs.length > 0 ? (
              <Section
                title={copy.openPrsTitle}
                sub={copy.openPrsSub(openPrs.length)}
                divider
              >
                <DiseaseOpenPrList
                  prs={openPrs}
                  loading={prsLoading}
                  error={prsError}
                  diseaseSlug={slug}
                  onNav={onNav}
                />
              </Section>
            ) : null}

            {disease.related.length > 0 ? (
              <Section title={copy.relatedTitle} divider>
                {relatedLoading ? (
                  <p className="d-panel-empty">Loading related conditions…</p>
                ) : related.length === 0 ? (
                  <p className="d-panel-empty">No related entries found.</p>
                ) : (
                  <div className="d-related">
                    {related.map((d) => (
                      <DiseaseCard key={d.slug} disease={d} onNav={onNav} />
                    ))}
                  </div>
                )}
              </Section>
            ) : null}
          </>
        ) : null}

        {tab === "doctors" ? (
          <Section title={copy.doctorsTitle}>
            <p className="d-panel-stat">{copy.doctorsSub(disease.doctorsCount)}</p>
            <div className="page__actions">
              <Button variant="primary" type="button" onClick={() => onNav(`/doctors?disease=${slug}`)}>
                {isClinician
                  ? `Open expert directory for ${disease.nameShort}`
                  : `See ${disease.nameShort} specialists`}
              </Button>
              <Button type="button" onClick={() => onNav("/doctors")}>
                Browse full directory
              </Button>
            </div>
            {doctorsLoading ? (
              <p className="d-panel-empty">Loading specialists…</p>
            ) : null}
            {doctorsError != null ? (
              <p className="d-panel-empty" role="alert">
                {doctorsError}
              </p>
            ) : null}
            {!doctorsLoading && doctorsError == null && previewDoctors.length > 0 ? (
              <>
                {isWorkflowDoctorSource(doctorsPayload?.source) ? (
                  <p className="d-doctors-source">
                    {doctorsPayload?.source === "merged"
                      ? "Curated profiles merged with the latest Doctor Finder evidence where available."
                      : "Ranked from the latest Doctor Finder run."}
                  </p>
                ) : null}
                <div className="d-doctors-preview">
                  {previewDoctors.map((doctor) => (
                    <DoctorCard
                      key={doctor.slug}
                      doctor={doctor}
                      km={doctor.km}
                      compact
                      onNav={onNav}
                    />
                  ))}
                </div>
              </>
            ) : null}
            {!doctorsLoading && doctorsError == null && previewDoctors.length === 0 ? (
              <p className="d-panel-empty">{copy.doctorsEmpty}</p>
            ) : null}
          </Section>
        ) : null}

        {tab === "trials" ? (
          <Section title={copy.trialsTitle}>
            <p className="d-panel-stat">{copy.trialsSub(trials.length)}</p>
            <div className="page__actions">
              <Button
                variant="primary"
                type="button"
                onClick={() => onNav(`/trials?disease=${slug}`)}
              >
                See {disease.nameShort} trials
              </Button>
              <Button type="button" onClick={() => onNav("/trials")}>
                Browse all trials
              </Button>
            </div>
            {trialsError != null ? (
              <p className="d-panel-empty" role="alert">{trialsError}</p>
            ) : trialsLoading ? (
              <p className="d-panel-empty">Loading trials…</p>
            ) : trials.length === 0 ? (
              <p className="d-panel-empty">No active trials matching this disease right now.</p>
            ) : (
              <TrialsList trials={previewTrials} />
            )}
          </Section>
        ) : null}

        {tab === "guidelines" ? (
          <Section title={copy.guidelinesTitle} sub={copy.guidelinesSub}>
            <p className="d-panel-stat">{copy.openPrsSub(disease.openPRs)}</p>
            <div className="page__actions">
              <Button variant="primary" type="button" onClick={() => onNav(`/diseases/${slug}/guidelines`)}>
                {copy.synthesisCta}
              </Button>
            </div>
            {openPrs.length > 0 ? (
              <Section title={copy.openPrsTitle} sub={copy.openPrsSub(openPrs.length)} divider>
                <DiseaseOpenPrList
                  prs={openPrs}
                  loading={prsLoading}
                  error={prsError}
                  diseaseSlug={slug}
                  onNav={onNav}
                />
              </Section>
            ) : null}
            <Section title={copy.officialGuidelineTitle} sub={copy.officialGuidelineSub} divider>
              <p className="d-panel-stat">
                Consensus document for {disease.name} — full text in the guideline reader.
              </p>
            </Section>
          </Section>
        ) : null}
      </div>
    </>
  );
}
