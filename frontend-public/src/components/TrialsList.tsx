import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Badge } from "@gene-guidelines/ui";
import type { Trial } from "../types/trial";
import "./trials-list.css";

export interface TrialsListProps {
  trials: readonly Trial[];
}

function statusVariant(status: string): "ok" | "default" {
  switch (status) {
    case "recruiting":
    case "active_not_recruiting":
      return "ok";
    default:
      return "default";
  }
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function enrollmentLabel(
  enrolled: number | null,
  target: number | null,
  t: TFunction,
): string | null {
  if (enrolled == null && target == null) {
    return null;
  }
  if (enrolled != null && target != null) {
    return t("trialsList.enrollmentBoth", { enrolled, target });
  }
  if (target != null) {
    return t("trialsList.enrollmentPlanned", { target });
  }
  return t("trialsList.enrollmentEnrolledOnly", { enrolled });
}

function clinicalTrialsUrl(nct: string): string {
  return `https://clinicaltrials.gov/study/${encodeURIComponent(nct)}`;
}

export function TrialsList({ trials }: TrialsListProps) {
  const { t } = useTranslation("common");
  if (trials.length === 0) {
    return <p className="trials-list__empty">{t("trialsList.empty")}</p>;
  }

  return (
    <div className="trials-list">
      {trials.map((trial) => {
        const enrollment = enrollmentLabel(trial.enrolled, trial.enrollmentTarget, t);
        return (
          <article key={trial.nct} className="trial-card">
            <div className="trial-card__top">
              <span className="trial-card__nct">{trial.nct}</span>
              <Badge variant={statusVariant(trial.status)}>
                {statusLabel(trial.status)}
              </Badge>
              <span className="trial-card__phase">{trial.phase}</span>
            </div>
            <h3 className="trial-card__title">{trial.title}</h3>
            <p className="trial-card__sponsor">{trial.sponsor}</p>
            {trial.eligibilitySummary ? (
              <p className="trial-card__eligibility">{trial.eligibilitySummary}</p>
            ) : null}
            <dl className="trial-card__facts">
              {trial.principalInvestigator ? (
                <div>
                  <dt>{t("trialsList.pi")}</dt>
                  <dd>{trial.principalInvestigator}</dd>
                </div>
              ) : null}
              {trial.city || trial.country ? (
                <div>
                  <dt>{t("trialsList.location")}</dt>
                  <dd>
                    {[trial.city, trial.country].filter(Boolean).join(", ")}
                  </dd>
                </div>
              ) : null}
              {trial.ageRange ? (
                <div>
                  <dt>{t("trialsList.ages")}</dt>
                  <dd>{trial.ageRange}</dd>
                </div>
              ) : null}
              {enrollment != null ? (
                <div>
                  <dt>{t("trialsList.enrollment")}</dt>
                  <dd>{enrollment}</dd>
                </div>
              ) : null}
            </dl>
            <div className="trial-card__actions">
              <a
                className="trial-card__cta"
                href={clinicalTrialsUrl(trial.nct)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("trialsList.openOnClinicalTrials")}
              </a>
              {trial.contact ? (
                <a
                  className="trial-card__contact"
                  href={`mailto:${trial.contact}`}
                >
                  {trial.contact}
                </a>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
