import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useOpenDetailsForPrint } from "../hooks/useOpenDetailsForPrint";
import type { GuidelinePoints } from "../types/guidelinePoints";

export interface GuidelinePointsBlockProps {
  readonly block: GuidelinePoints;
}

/**
 * The generated "What the guideline says about diagnosis – to show your doctor" block, in the same shape as FD's hand-written one: one collapsed row per point whose header is the open question; opening it shows the plain summary and the verbatim source sentence with its source. The quote stays English on every page (a translation would stop being a quotation). The AI notice is fixed copy from the locale files, never model text: nobody approved this block, and the page must always say so — it stays visible with the title, the note and the source line, outside the rows. Printing opens every row (useOpenDetailsForPrint).
 */
export function GuidelinePointsBlock({ block }: GuidelinePointsBlockProps) {
  const { t, i18n } = useTranslation("disease-map");
  const pl = i18n.language.startsWith("pl");
  const root = useRef<HTMLDivElement>(null);
  useOpenDetailsForPrint(root);
  return (
    <div className="dmap-ask" data-testid="generated-guideline-points" ref={root}>
      <div className="dmap-ask__hd">{pl ? block.titlePl : block.titleEn}</div>
      <p className="dmap-ask__note">{t("askGeneratedNote")}</p>
      <p className="dmap-ask__note dmap-ask__notice">{t("askGeneratedNotice")}</p>
      <ol className="dmap-ask__list">
        {block.points.map((point, index) => (
          <li key={point.id} className="dmap-ask__item">
            <details className="dmap-ask__row">
              <summary className="dmap-ask__sum">
                <span className="dmap-ask__n">{t("askNumber", { n: index + 1 })}</span>
                <span className="dmap-ask__q">{pl ? point.questionPl : point.questionEn}</span>
              </summary>
              <div className="dmap-ask__body">
                <p className="dmap-ask__point">{pl ? point.summaryPl : point.summaryEn}</p>
                <p className="dmap-ask__lbl">{t("askGeneratedQuoteLabel")}</p>
                <p className="dmap-ask__s">
                  <q lang="en">{point.quote}</q>
                </p>
                <p className="dmap-ask__src">
                  {point.docUrl ? (
                    <a href={point.docUrl} target="_blank" rel="noopener noreferrer">
                      {point.docCitation || point.docTitle}
                    </a>
                  ) : (
                    point.docCitation || point.docTitle
                  )}
                  {point.credit ? ` ${point.credit}` : null}
                </p>
              </div>
            </details>
          </li>
        ))}
      </ol>
      <p className="dmap-ask__src">{pl ? block.sourcePl : block.sourceEn}</p>
    </div>
  );
}
