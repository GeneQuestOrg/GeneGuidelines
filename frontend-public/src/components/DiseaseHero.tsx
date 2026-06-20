import { Button, Status } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import "../styles/disease-page.css";

export interface DiseaseHeroProps {
  disease: Disease;
  copy: DiseaseCopy;
  isClinician: boolean;
  onNav: (path: string) => void;
}

export function DiseaseHero({
  disease,
  copy,
  isClinician,
  onNav,
}: DiseaseHeroProps) {
  const slug = disease.slug;

  return (
    <div className={`d-hero d-hero--${disease.accent}`}>
      <div className="d-hero__top">
        <div className="d-hero__abbr">{disease.nameShort}</div>
        <div className="d-hero__title-block">
          <h1 className="d-hero__name">{disease.name}</h1>
        </div>
        <Status status={disease.status} />
      </div>
      <p className="d-hero__summary">{disease.summary}</p>
      <dl className="d-hero__facts">
        <div>
          <dt>Gene</dt>
          <dd>
            <code>{disease.gene}</code>
          </dd>
        </div>
        <div>
          <dt>OMIM</dt>
          <dd>
            <code>{disease.omim}</code>
          </dd>
        </div>
        <div>
          <dt>Inheritance</dt>
          <dd>{disease.inheritance}</dd>
        </div>
        <div>
          <dt>Prevalence</dt>
          <dd>{disease.prevalenceText}</dd>
        </div>
        <div>
          <dt>Types</dt>
          <dd>{disease.types.join(" · ")}</dd>
        </div>
        {(disease.statusDate ?? disease.aiDraftDate) != null ? (
          <div>
            <dt>Last revised</dt>
            <dd>{disease.statusDate ?? disease.aiDraftDate}</dd>
          </div>
        ) : null}
      </dl>
      {disease.coverage === "skeleton" ? (
        <div className="d-hero__notice" role="note">
          <span aria-hidden>⚠️</span>
          <p>
            <b>{copy.skeletonNoticeTitle}</b> {copy.skeletonNoticeBody}
          </p>
        </div>
      ) : null}
      <div className="d-hero__actions">
        <Button variant="primary" type="button" onClick={() => onNav(`/diseases/${slug}/guidelines`)}>
          {isClinician ? "Open guidelines" : copy.guidelinesCta}
        </Button>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}/flowchart`)}>
          View pathway
        </Button>
        <Button variant="ghost" type="button" onClick={() => onNav(`/start-research?disease=${encodeURIComponent(slug)}`)}>
          {copy.researchRunCta}
        </Button>
        <Button variant="ghost" type="button" onClick={() => onNav(`/doctors?disease=${encodeURIComponent(slug)}`)}>
          {isClinician ? "Expert directory" : "Find specialists"} ({disease.doctorsCount})
        </Button>
      </div>
    </div>
  );
}
