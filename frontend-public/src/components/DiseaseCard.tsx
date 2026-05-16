import { Status } from "@gene-guidelines/ui";
import type { Disease } from "../types";

export interface DiseaseCardProps {
  disease: Disease;
  onNav: (path: string) => void;
}

export function DiseaseCard({ disease, onNav }: DiseaseCardProps) {
  return (
    <a
      href={`#/diseases/${disease.slug}`}
      className={`d-card d-card--${disease.accent}`}
      onClick={(e) => {
        e.preventDefault();
        onNav(`/diseases/${disease.slug}`);
      }}
    >
      <div className="d-card__top">
        <span className="d-card__abbr">{disease.nameShort}</span>
        <Status status={disease.status} compact />
      </div>
      <h3 className="d-card__name">{disease.name}</h3>
      <p className="d-card__summary">{disease.summary}</p>
      <dl className="d-card__facts">
        <div>
          <dt>Gene</dt>
          <dd>
            <code>{disease.gene}</code>
          </dd>
        </div>
        <div>
          <dt>Prevalence</dt>
          <dd>{disease.prevalenceText}</dd>
        </div>
        <div>
          <dt>Inheritance</dt>
          <dd>{disease.inheritance}</dd>
        </div>
      </dl>
      <div className="d-card__meta">
        <span>{disease.doctorsCount} specialists</span>
        <span>{disease.trialsCount} trials</span>
        {disease.openPRs > 0 ? <span>{disease.openPRs} open PRs</span> : null}
      </div>
    </a>
  );
}
