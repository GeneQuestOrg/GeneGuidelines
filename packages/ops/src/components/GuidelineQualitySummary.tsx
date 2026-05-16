import type { PubmedQualitySnapshot } from "../api/client";

export interface GuidelineQualitySummaryProps {
  snapshot: PubmedQualitySnapshot | null | undefined;
}

export function GuidelineQualitySummary({ snapshot }: GuidelineQualitySummaryProps) {
  if (!snapshot) {
    return null;
  }

  const evalSnap = snapshot.pm_eval;
  const fixSnap = snapshot.pm_fix;
  const retrySnap = snapshot.targeted_retry;

  if (!evalSnap && !fixSnap && !retrySnap) {
    return null;
  }

  return (
    <section className="ops-quality-summary" aria-label="Quality check summary">
      <h3 className="ops-guideline-preview__heading">Quality checks</h3>
      {evalSnap ? (
        <div className="ops-quality-summary__block">
          <p>
            <strong>Evaluation (pm_eval):</strong>{" "}
            {evalSnap.ok === false || evalSnap.issues_found
              ? "Issues found"
              : "Passed"}
            {typeof evalSnap.issue_count === "number"
              ? ` · ${evalSnap.issue_count} issue(s)`
              : null}
          </p>
          {evalSnap.quality_summary ? (
            <p className="ops-quality-summary__text">{evalSnap.quality_summary}</p>
          ) : null}
          {evalSnap.correction_instructions ? (
            <details className="ops-quality-summary__details">
              <summary>Correction instructions</summary>
              <pre className="ops-raw-output">{evalSnap.correction_instructions}</pre>
            </details>
          ) : null}
        </div>
      ) : null}
      {fixSnap ? (
        <p className="ops-quality-summary__text">
          <strong>Revision (pm_fix):</strong>{" "}
          {fixSnap.applied
            ? `Guideline revised${fixSnap.disease_name ? ` for ${fixSnap.disease_name}` : ""}.`
            : "No revision applied."}
        </p>
      ) : null}
      {retrySnap?.retried_sections?.length ? (
        <p className="ops-quality-summary__text">
          <strong>Targeted retry:</strong> re-ran{" "}
          {retrySnap.retried_sections.join(", ")}
        </p>
      ) : null}
    </section>
  );
}
