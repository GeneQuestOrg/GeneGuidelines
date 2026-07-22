import { useTranslation } from "react-i18next";
import "./synthesis-teaser.css";

export interface SynthesisTeaserProps {
  diseaseName: string;
  sourceCount: number;
  /** When false, the disease has no agreed guideline — AI-built draft framing. */
  hasOfficial: boolean;
  onOpen: () => void;
}

/**
 * Synthesis teaser — draft12 `synthcard` (views-main.jsx ~436). ONE card that
 * stands in for the (disliked) inline 4-column source grid on the overview:
 * "<N> sources / <disease> — guideline synthesis / Read the guideline →",
 * linking to the reader at /diseases/:slug/guidelines.
 */
export function SynthesisTeaser({
  diseaseName,
  sourceCount,
  hasOfficial,
  onOpen,
}: SynthesisTeaserProps) {
  const { t } = useTranslation("common");
  const tag = hasOfficial
    ? t("synthesisTeaser.tagSources", { count: sourceCount })
    : t("synthesisTeaser.tagAiDraft");
  const title = hasOfficial
    ? t("synthesisTeaser.titleSynthesis", { disease: diseaseName })
    : t("synthesisTeaser.titleAiDraft", { disease: diseaseName });
  const sub = hasOfficial
    ? t("synthesisTeaser.subSynthesis")
    : t("synthesisTeaser.subAiDraft");

  return (
    <button type="button" className="synthcard" onClick={onOpen}>
      <span className="synthcard__icon" aria-hidden>
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2 2 7l10 5 10-5-10-5z" />
          <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
        </svg>
      </span>
      <span className="synthcard__body">
        <span className="synthcard__tag">{tag}</span>
        <span className="synthcard__title">{title}</span>
        <span className="synthcard__sub">{sub}</span>
      </span>
      <span className="synthcard__cta">{t("synthesisTeaser.cta")}</span>
    </button>
  );
}
