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

function enrollmentLabel(enrolled: number | null, target: number | null): string | null {
  if (enrolled == null && target == null) {
    return null;
  }
  if (enrolled != null && target != null) {
    return `${enrolled} / ${target} enrolled`;
  }
  if (target != null) {
    return `${target} planned`;
  }
  return `${enrolled} enrolled`;
}

function clinicalTrialsUrl(nct: string): string {
  return `https://clinicaltrials.gov/study/${encodeURIComponent(nct)}`;
}

export function TrialsList({ trials }: TrialsListProps) {
  if (trials.length === 0) {
    return (
      <p className="trials-list__empty">
        No registered trials yet for this disease.
      </p>
    );
  }

  return (
    <div className="trials-list">
      {trials.map((t) => {
        const enrollment = enrollmentLabel(t.enrolled, t.enrollmentTarget);
        return (
          <article key={t.nct} className="trial-card">
            <div className="trial-card__top">
              <span className="trial-card__nct">{t.nct}</span>
              <Badge variant={statusVariant(t.status)}>
                {statusLabel(t.status)}
              </Badge>
              <span className="trial-card__phase">{t.phase}</span>
            </div>
            <h3 className="trial-card__title">{t.title}</h3>
            <p className="trial-card__sponsor">{t.sponsor}</p>
            {t.eligibilitySummary ? (
              <p className="trial-card__eligibility">{t.eligibilitySummary}</p>
            ) : null}
            <dl className="trial-card__facts">
              {t.principalInvestigator ? (
                <div>
                  <dt>PI</dt>
                  <dd>{t.principalInvestigator}</dd>
                </div>
              ) : null}
              {t.city || t.country ? (
                <div>
                  <dt>Location</dt>
                  <dd>
                    {[t.city, t.country].filter(Boolean).join(", ")}
                  </dd>
                </div>
              ) : null}
              {t.ageRange ? (
                <div>
                  <dt>Ages</dt>
                  <dd>{t.ageRange}</dd>
                </div>
              ) : null}
              {enrollment != null ? (
                <div>
                  <dt>Enrollment</dt>
                  <dd>{enrollment}</dd>
                </div>
              ) : null}
            </dl>
            <div className="trial-card__actions">
              <a
                className="trial-card__cta"
                href={clinicalTrialsUrl(t.nct)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open on ClinicalTrials.gov →
              </a>
              {t.contact ? (
                <a
                  className="trial-card__contact"
                  href={`mailto:${t.contact}`}
                >
                  {t.contact}
                </a>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
