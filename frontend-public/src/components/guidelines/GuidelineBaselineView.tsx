import { useTranslation } from "react-i18next";
import type { GuidelineBaseline } from "../../types/guidelineBaseline";
import { EvidenceMeter } from "./EvidenceMeter";
import { CitationRow } from "./CitationRow";
import { SignalBlock } from "./SignalBlock";

/**
 * Level-(c) baseline render (draft10 `GLBaseline`): a disease with no agreed
 * guideline, where AI assembled a draft from scratch FOR REVIEW — explicitly not
 * a guideline. Clinician/researcher only (the parent gets the safety gate, GL-2).
 * The build steps are shown as static provenance; the live from-scratch run is
 * the researcher/workflow surface (GL-6 / the engine).
 */
export interface GuidelineBaselineViewProps {
  baseline: GuidelineBaseline;
  diseaseName: string;
  /** doctor-unverified: can read, signal held. */
  held?: boolean;
}

export function GuidelineBaselineView({
  baseline,
  diseaseName,
  held = false,
}: GuidelineBaselineViewProps) {
  const { t } = useTranslation("guidelines");
  return (
    <>
      <div className="gx-baseflag">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
        <div>
          <b>{t("baselineNoGuidelineTitle", { disease: diseaseName.toLowerCase() })}</b>
          <p>
            {t("baselineDisclaimerPart1")} <b>{t("baselineDisclaimerBold")}</b>{" "}
            {t("baselineDisclaimerPart2", { builtFrom: baseline.builtFrom })}
          </p>
        </div>
      </div>

      <div className="gx-run">
        <div className="gx-run__top">
          <span className="gx-run__pulse" aria-hidden="true" />
          <span className="gx-run__t">
            {t("evidenceWorkflowTitle")} <span className="by">{t("evidenceWorkflowSub")}</span>
          </span>
        </div>
        <ol className="gx-run__steps">
          {baseline.runSteps.map((step) => (
            <li
              key={step.label}
              className={step.done ? "done" : step.active ? "active" : ""}
            >
              <span className="mk" aria-hidden="true" />
              {step.label}
              <em>{step.meta}</em>
            </li>
          ))}
        </ol>
      </div>

      {baseline.sections.map((section) => (
        <section key={section.id} className="gx-basesec">
          <h2 className="gx-sec__h">{section.title}</h2>
          {section.items.map((item) => (
            <div key={item.id} className="gx-baseitem">
              <div className="gx-baseitem__text">{item.text}</div>
              <div className="gx-rationale">
                <span className="lbl">{t("provenanceLabel")}</span>
                {item.provenance}
              </div>
              <EvidenceMeter level={item.evidence} />
              {item.citations.length > 0 ? (
                <div className="gx-cits">
                  {item.citations.map((pmid) => (
                    <CitationRow key={pmid} pmid={pmid} />
                  ))}
                </div>
              ) : null}
              <SignalBlock sig={item.signal} held={held} />
            </div>
          ))}
        </section>
      ))}
    </>
  );
}
