import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, Section } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import { useAudienceCopy } from "../copy";
import type { DiseaseSuggestion } from "../api/diseaseIndex";
import { slugifyDisease } from "../utils/slugifyDisease";
import { ActiveResearchSection } from "../components/ActiveResearchSection";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { DiseaseCard } from "../components/DiseaseCard";
import { NewDiseaseCard } from "../components/NewDiseaseCard";
import { useActiveResearchRuns } from "../hooks/useActiveResearchRuns";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../components/disease-grid.css";
import "../styles/home.css";

export interface HomeViewProps {
  view: AudienceView;
  onNav: (path: string) => void;
}

/* ── inline icons (match draft13 v2) ─────────────────────────────────────── */
const findIcons: ReactNode[] = [
  <svg key="doc" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M6 9V3h12v6" />
    <rect x="4" y="9" width="16" height="8" rx="2" />
    <path d="M8 15h8v6H8z" strokeLinejoin="round" />
  </svg>,
  <svg key="steth" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M7 3v6a5 5 0 0 0 10 0V3" />
    <path d="M12 14v3a4 4 0 0 0 4 4" />
    <circle cx="18" cy="17" r="2" />
  </svg>,
  <svg key="globe" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" strokeLinecap="round" />
    <path d="M12 3c2.7 2.4 4 5.6 4 9s-1.3 6.6-4 9c-2.7-2.4-4-5.6-4-9s1.3-6.6 4-9z" />
  </svg>,
  <svg key="heart" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M20.8 6.6a5 5 0 0 0-7-.2L12 8 10.2 6.4a5 5 0 1 0-6.8 7.3L12 21l8.6-7.3a5 5 0 0 0 .2-7.1z" strokeLinejoin="round" />
  </svg>,
];
const iconChat: ReactNode = (
  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M21 11.5a8.4 8.4 0 0 1-9 8.3L4 21l1.2-3.8A8.4 8.4 0 1 1 21 11.5z" strokeLinejoin="round" />
  </svg>
);

export function HomeView({ view, onNav }: HomeViewProps) {
  const { diseases, stats, loading, error } = useDiseaseCatalog();
  const { runs: activeRuns } = useActiveResearchRuns(3);
  const { t } = useTranslation("common");
  const copy = useAudienceCopy(view).home;

  // LEFT card — "I know the disease": forgiving multilingual typeahead over the
  // rare-disease index (same DiseaseAutocomplete used on /start-research).
  // Every pick now lands on the canonical /diseases/<slug> page: a researched
  // disease shows its full page, a not-yet-researched one shows the client-side
  // STUB (real index facts + skeleton + "Run research" CTA). The stub reverse-
  // resolves the same deterministic slug the index pick produced.
  const goPickedDisease = (suggestion: DiseaseSuggestion) => {
    const slug =
      suggestion.hasLocalRecord && suggestion.localSlug
        ? suggestion.localSlug
        : slugifyDisease(suggestion.canonicalName);
    onNav(`/diseases/${encodeURIComponent(slug)}`);
  };

  // Feedback bar — commission an AI research run for any disease.
  const goResearch = () => onNav("/start-research");


  return (
    <div className="page page--home">
      {/* ── HERO — WARIANT A (default) ── */}
      <div className="intro">
        <span className="eyebrow">
          <span className="dot" aria-hidden />
          {copy.eyebrow}
        </span>
        <h1 className="intro__title">
          {copy.titleLine1}
          <br />
          <em>{copy.titleEmphasis}</em>
        </h1>
        <p className="intro__sub">{copy.subtitle}</p>
        <p className="intro__why">
          <a
            className="lnk"
            href="/about"
            onClick={(e) => {
              e.preventDefault();
              onNav("/about");
            }}
          >
            {copy.whyLink} <span className="arw" aria-hidden>→</span>
          </a>
        </p>
      </div>

      {/* ── SEARCH BAR ──
          A bare bar, not a card. Ported from drafty-ui/draft11 (.intro__bar +
          .intro__meta): the field, one action beside it, and the counters that say
          how much is actually in here. The card wrapper around this used to carry a
          kicker, a heading and a paragraph explaining the field — visual noise in
          front of the one control the page exists for. */}
      <div className="intro__bar">
        <DiseaseAutocomplete
          placeholder={copy.searchPlaceholder}
          onPick={goPickedDisease}
          onMissingClick={goResearch}
        />
        <a
          href="/start-research"
          className="intro__startbtn"
          onClick={(e) => {
            e.preventDefault();
            goResearch();
          }}
        >
          {copy.newDiseaseAction}
        </a>
      </div>
      {stats != null ? (
        <div className="intro__meta">
          <span>
            <b>{stats.diseaseCount}</b> {copy.metaDiseases}
          </span>
          <span>
            <b>{stats.doctorCount}</b> {copy.metaDoctors}
          </span>
          <span>
            <b>{stats.recruitingTrialCount}</b> {copy.metaTrials}
          </span>
          <span>
            <b>{stats.openPrCount}</b> {copy.metaSuggestions}
          </span>
        </div>
      ) : null}

      {/* ── CO TU ZNAJDZIESZ ── */}
      <Section title={copy.findsTitle} sub={copy.findsSub} divider>
        <div className="finds">
          {copy.finds.map((f, i) => (
            <div className="find" key={f.title}>
              <span className="find__ic" aria-hidden>
                {findIcons[i]}
              </span>
              <div>
                <p className="find__t">{f.title}</p>
                <p className="find__d">{f.body}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="finds-foot">
          <span>{copy.honestFootnote}</span>
        </p>
      </Section>

      {error != null ? (
        <p className="catalog-error" role="alert">
          {error}
        </p>
      ) : null}

      <ActiveResearchSection runs={activeRuns} onNav={onNav} />

      {/* ── OSTATNIO DODANE ── */}
      <Section
        title={copy.diseasesSectionTitle}
        sub={copy.diseasesSectionSub}
        count={loading ? undefined : diseases.length}
        divider
      >
        {loading ? (
          <p className="page__lead">{t("loadingCatalog")}</p>
        ) : (
          <div className="d-grid">
            {diseases.map((d) => (
              <DiseaseCard key={d.slug} disease={d} onNav={onNav} />
            ))}
            <NewDiseaseCard copy={copy} onNav={onNav} />
          </div>
        )}
      </Section>

      {/* ── FEEDBACK BAR — add your disease ── */}
      <div className="fb">
        <span className="fb__ic" aria-hidden>
          {iconChat}
        </span>
        <div className="fb__b">
          <div className="fb__t">{copy.addTitle}</div>
          <div className="fb__s">{copy.addSub}</div>
        </div>
        {/* A button, not a second field. The input here discarded what was typed
            (goResearch() ignored its value), so anyone who filled it in landed on
            an empty form on /start-research — where the real field lives. */}
        <div className="fb__form">
          <Button type="button" variant="primary" onClick={goResearch}>
            {copy.addCta}
          </Button>
        </div>
      </div>
    </div>
  );
}
