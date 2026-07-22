import { useTranslation } from "react-i18next";
import { Status } from "@gene-guidelines/ui";
import type { Disease } from "../types";

export interface DiseaseCardProps {
  disease: Disease;
  onNav: (path: string) => void;
}

export function DiseaseCard({ disease, onNav }: DiseaseCardProps) {
  const { t } = useTranslation("common");
  return (
    <a
      href={`/diseases/${disease.slug}`}
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
          <dt>{t("diseaseFacts.gene")}</dt>
          <dd>
            <code>{disease.gene}</code>
          </dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.prevalence")}</dt>
          <dd>{disease.prevalenceText}</dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.inheritance")}</dt>
          <dd>{disease.inheritance || "—"}</dd>
        </div>
        {disease.types.length > 0 ? (
          <div>
            <dt>{t("diseaseFacts.types")}</dt>
            <dd>{disease.types.join(" · ")}</dd>
          </div>
        ) : null}
      </dl>
      <div className="d-card__meta">
        <span>{t("diseaseCard.specialists", { count: disease.doctorsCount })}</span>
        <span>{t("diseaseCard.trials", { count: disease.trialsCount })}</span>
      </div>
    </a>
  );
}
