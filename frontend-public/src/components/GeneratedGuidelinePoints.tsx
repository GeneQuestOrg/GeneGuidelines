import { useTranslation } from "react-i18next";
import { useGuidelinePoints } from "../hooks/useGuidelinePoints";
import type { GuidelinePoints } from "../types/guidelinePoints";

export interface GuidelinePointsBlockProps {
  readonly block: GuidelinePoints;
}

/**
 * The generated "What the guideline says about diagnosis – to show your doctor" block, in the same shape as FD's hand-written one: a plain summary, one open question, and the verbatim source sentence underneath. The quote stays English on every page (a translation would stop being a quotation). The AI notice is fixed copy from the locale files, never model text: nobody approved this block, and the page must always say so.
 */
export function GuidelinePointsBlock({ block }: GuidelinePointsBlockProps) {
  const { t, i18n } = useTranslation("disease-map");
  const pl = i18n.language.startsWith("pl");
  return (
    <div className="dmap-ask" data-testid="generated-guideline-points">
      <div className="dmap-ask__hd">{pl ? block.titlePl : block.titleEn}</div>
      <p className="dmap-ask__note">{t("askGeneratedNote")}</p>
      <p className="dmap-ask__note dmap-ask__notice">{t("askGeneratedNotice")}</p>
      <ol className="dmap-ask__list">
        {block.points.map((point) => (
          <li key={point.id} className="dmap-ask__item">
            <p className="dmap-ask__point">{pl ? point.summaryPl : point.summaryEn}</p>
            <p className="dmap-ask__q">{pl ? point.questionPl : point.questionEn}</p>
            <details className="dmap-ask__src-q">
              <summary className="dmap-ask__lbl">{t("askGeneratedQuoteLabel")}</summary>
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
            </details>
          </li>
        ))}
      </ol>
      <p className="dmap-ask__src">{pl ? block.sourcePl : block.sourceEn}</p>
    </div>
  );
}

export interface GeneratedGuidelinePointsProps {
  readonly slug: string;
}

/** Fetches and shows the block; renders nothing while loading, when none is published, or on an error. */
export function GeneratedGuidelinePoints({ slug }: GeneratedGuidelinePointsProps) {
  const block = useGuidelinePoints(slug);
  if (!block || block.points.length === 0) return null;
  return <GuidelinePointsBlock block={block} />;
}
