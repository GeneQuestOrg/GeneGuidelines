import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Disease } from "../types/disease";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";
import { weightedSuggestionScore } from "../types/guidelineSuggestion";
import type { GuidelineBaseline } from "../types/guidelineBaseline";
import type { SourceDoc } from "../types/sourceDoc";
import type { ViewRole } from "../auth/resolveRole";
import type { SynthSignalMap } from "../hooks/useSynthSignals";
import { SourceShelf } from "../components/guidelines/SourceShelf";
import { SynthDisclaimer } from "../components/guidelines/SynthDisclaimer";
import { ProvenanceRow } from "../components/guidelines/ProvenanceRow";
import { SynthSignal } from "../components/guidelines/SynthSignal";
import { SuggestionCard } from "../components/guidelines/SuggestionCard";
import { useBibliography } from "../hooks/useBibliography";
import { GuidelineBaselineView } from "../components/guidelines/GuidelineBaselineView";
import {
  citationIndex,
  orderedSynthesisPmids,
  pubmedUrl,
} from "../utils/guidelineSynthesis";

export interface GuidelineClinicianViewProps {
  disease: Disease;
  synthesis: GuidelineSynthesis | null;
  suggestions: readonly GuidelineSuggestion[];
  signals: SynthSignalMap;
  /** Level-(c) AI baseline draft, when no guideline exists (GL-5). */
  baseline: GuidelineBaseline | null;
  hasOfficial: boolean;
  role: ViewRole;
  docs: readonly SourceDoc[];
  onNav: (path: string) => void;
}

/** Pending-verification banner — read everything, signal held (ported .gx-unver). */
function UnverifiedBanner() {
  const { t } = useTranslation("guidelines");
  return (
    <div className="gx-unver">
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
      <div>
        <b>{t("unverifiedBannerTitle")}</b>
        <p>{t("unverifiedBannerBody")}</p>
      </div>
    </div>
  );
}

export function GuidelineClinicianView({
  disease,
  synthesis,
  suggestions,
  signals,
  baseline,
  hasOfficial,
  role,
  docs,
  onNav,
}: GuidelineClinicianViewProps) {
  const { t } = useTranslation("guidelines");
  const orderedPmids = useMemo(
    () => (synthesis != null ? orderedSynthesisPmids(synthesis) : []),
    [synthesis],
  );
  const rankedSuggestions = useMemo(
    () =>
      [...suggestions].sort(
        (a, b) => weightedSuggestionScore(b.signal) - weightedSuggestionScore(a.signal),
      ),
    [suggestions],
  );
  const held = role === "doctor-unverified";
  const isResearcher = role === "researcher";
  const suggZoneRef = useRef<HTMLElement | null>(null);
  const { papers: bibliographyPapers } = useBibliography(disease.slug);

  const scrollToSuggestions = () => {
    const el = suggZoneRef.current;
    if (el == null) {
      return;
    }
    const y = el.getBoundingClientRect().top + window.scrollY - 80;
    window.scrollTo({ top: y, behavior: "smooth" });
  };

  // Level (c): no synthesis. A clinician/researcher sees the AI-built baseline
  // draft for review (GL-5); without one, a quiet placeholder.
  if (!hasOfficial) {
    return (
      <>
        {held ? <UnverifiedBanner /> : null}
        {baseline != null ? (
          <GuidelineBaselineView
            baseline={baseline}
            diseaseName={disease.name}
            held={held}
          />
        ) : (
          <div className="gx-empty">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 2 2 7l10 5 10-5-10-5z" />
              <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
            </svg>
            <div>
              <b>{t("noOfficialGuidelineYet", { disease: disease.name })}</b>
              <p>
                {t("noBaselinePrefix")}{" "}
                <a
                  href={`/diseases/${disease.slug}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNav(`/diseases/${disease.slug}`);
                  }}
                >
                  {t("returnToOverviewLink")}
                </a>
                .
              </p>
            </div>
          </div>
        )}
        {docs.length > 0 ? <SourceShelf docs={docs} /> : null}
      </>
    );
  }

  const doc = synthesis!;
  const suggestionWord = t(
    rankedSuggestions.length === 1 ? "aiSuggestionSingular" : "aiSuggestionPlural",
  );

  return (
    <>
      {held ? <UnverifiedBanner /> : null}

      {/* Researcher depth ladder: synthesis ⇄ fully AI-built version (GL-6 stub). */}
      {isResearcher ? (
        <div className="gx-modetabs" role="tablist" aria-label={t("modeTablistAriaLabel")}>
          <button type="button" role="tab" aria-selected="true" className="on">
            {t("modeSynthesisLabel")} <span>{t("modeSynthesisTag")}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected="false"
            disabled
            title={t("modeFullAiTitle")}
          >
            {t("modeFullAiLabel")} <span>{t("modeFullAiTag")}</span>
          </button>
        </div>
      ) : null}

      <SynthDisclaimer text={doc.synthDisclaimer} />

      {rankedSuggestions.length > 0 ? (
        <button type="button" className="gx-sugglink" onClick={scrollToSuggestions}>
          <span className="gx-sugglink__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2 2 7l10 5 10-5-10-5z" />
              <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </span>
          <span className="gx-sugglink__tx">
            <b>
              {t("suggBeyondDocsBold", {
                count: rankedSuggestions.length,
                word: suggestionWord,
              })}
            </b>{" "}
            {t("suggBeyondDocsTail")}
          </span>
          <span className="gx-sugglink__go">
            {t("goToSuggestionsButton")}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14M19 12l-7 7-7-7" />
            </svg>
          </span>
        </button>
      ) : null}

      <article className="gx-doc gx-doc--full">
        {doc.sections.map((sec) => (
          <section key={sec.id} className="gx-sec">
            <h2 className="gx-sec__h">{sec.title}</h2>
            {sec.intro != null ? <p className="gx-sec__intro">{sec.intro}</p> : null}
            {sec.paragraphs.map((p) => (
              <div key={p.id} className="gx-para">
                <p>
                  {p.text}
                  {p.citations?.map((pmid) => (
                    <a
                      key={pmid}
                      className="gx-cit"
                      href={pubmedUrl(pmid)}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={t("pmidLabel", { pmid })}
                    >
                      [{citationIndex(orderedPmids, pmid)}]
                    </a>
                  ))}
                </p>
                <ProvenanceRow slug={disease.slug} docs={docs} para={p} onNav={onNav} />
              </div>
            ))}
            <SynthSignal signal={signals[sec.id]} held={held} />
          </section>
        ))}

        <SourceShelf docs={docs} />
      </article>

      <section ref={suggZoneRef} className="gx-suggzone">
        <div className="gx-suggzone__head">
          <div>
            <div className="gx-suggzone__tag">
              {t("suggzoneTag", { count: rankedSuggestions.length })}
            </div>
            <h2 className="gx-suggzone__title">{t("suggzoneTitle")}</h2>
          </div>
        </div>
        <p className="gx-suggzone__lead">
          {t("suggzoneLeadPart1")} <b>{t("suggzoneLeadBold1")}</b>. {t("suggzoneLeadPart2")}{" "}
          — <b>{t("suggzoneLeadBold2")}</b>, {t("suggzoneLeadPart3")}
        </p>
        {rankedSuggestions.length === 0 ? (
          <div className="gx-empty">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <div>
              <b>{t("noAiSuggestionsTitle")}</b>
              <p>{t("noAiSuggestionsBody")}</p>
            </div>
          </div>
        ) : (
          <div className="gx-suggrid">
            {rankedSuggestions.map((s) => (
              <SuggestionCard
                // Re-key on myVote/ratings so a refetch (e.g. once auth resolves)
                // remounts the card with the clinician's restored rating.
                key={`${s.id}:${s.myVote ?? ""}:${s.signal.ratings}`}
                slug={disease.slug}
                suggestion={s}
                held={held}
                onNav={onNav}
              />
            ))}
          </div>
        )}
        <div className="gx-bib-entry">
          <p>
            {rankedSuggestions.length > 0 ? (
              <>
                {t("bibTipPrefix")} <b>{rankedSuggestions.length}</b> {t("bibTipSuffix")}
                {bibliographyPapers.length > 0 ? (
                  <>
                    {" "}
                    — <b>{bibliographyPapers.length}</b> {t("bibTipPapersScored")}
                  </>
                ) : null}
                {t("bibTipRejectedSuffix")}
              </>
            ) : (
              t("bibNoSuggestions")
            )}
          </p>
          <button
            type="button"
            className="gx-bib-entry__btn"
            onClick={() => onNav(`/diseases/${disease.slug}/bibliography`)}
          >
            {t("viewBibliographyButton")}
          </button>
        </div>
      </section>
    </>
  );
}
