import { useMemo, useState } from "react";
import { Button, Section } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import type { UserLocation } from "../router/types";
import { DiseaseCard } from "./DiseaseCard";
import { DoctorCard } from "./DoctorCard";
import { DiseaseOpenPrList } from "./DiseaseOpenPrList";
import { useContentPrs } from "../hooks/useContentPrs";
import { useDiseaseDoctors } from "../hooks/useDiseaseDoctors";
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

  const previewDoctors = useMemo(() => {
    if (doctorsPayload == null) {
      return [];
    }
    const rows = attachDoctorDistances(doctorsPayload.doctors, userLoc);
    return sortDoctorsByDistanceThenScore(rows).slice(0, 5);
  }, [doctorsPayload, userLoc]);

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
            <Section title={copy.pathwayTitle} sub={copy.pathwaySub}>
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
              <Button variant="primary" type="button" onClick={() => onNav("/doctors")}>
                {isClinician ? "Open expert directory" : "Browse specialists"}
              </Button>
              <Button type="button" onClick={() => onNav(`/doctors?disease=${slug}`)}>
                Filter directory
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
            {!doctorsLoading &&
            doctorsError == null &&
            previewDoctors.length === 0 &&
            disease.doctorsCount === 0 ? (
              <p className="d-panel-empty">{copy.doctorsEmpty}</p>
            ) : null}
          </Section>
        ) : null}

        {tab === "trials" ? (
          <Section title={copy.trialsTitle}>
            <p className="d-panel-stat">{copy.trialsSub(disease.trialsCount)}</p>
            <div className="page__actions">
              <Button
                type="button"
                onClick={() =>
                  onNav(
                    `/trials?q=${encodeURIComponent(disease.name)}`,
                  )
                }
              >
                View all trials
              </Button>
            </div>
            {disease.trialsCount === 0 ? (
              <p className="d-panel-empty">{copy.trialsEmpty}</p>
            ) : null}
          </Section>
        ) : null}

        {tab === "guidelines" ? (
          <Section title={copy.guidelinesTitle} sub={copy.guidelinesSub}>
            <p className="d-panel-stat">{copy.openPrsSub(disease.openPRs)}</p>
            <div className="page__actions">
              <Button variant="primary" type="button" onClick={() => onNav(`/diseases/${slug}/guidelines`)}>
                {copy.guidelinesCta}
              </Button>
              <Button type="button" onClick={() => onNav(`/diseases/${slug}/flowchart`)}>
                View pathway
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
