import { useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { SearchBar, Button, Section } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import { useAudienceCopy } from "../copy";
import { ActiveResearchSection } from "../components/ActiveResearchSection";
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
const iconSearch: ReactNode = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.5" y2="16.5" strokeLinecap="round" />
  </svg>
);
const iconBulb: ReactNode = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
    <path d="M12 3a7 7 0 0 0-4 12.7V18h8v-2.3A7 7 0 0 0 12 3z" strokeLinejoin="round" />
    <line x1="9" y1="21" x2="15" y2="21" strokeLinecap="round" />
  </svg>
);
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
  const [query, setQuery] = useState("");
  const [symptomQuery, setSymptomQuery] = useState("");
  const [addQuery, setAddQuery] = useState("");
  const { diseases, loading, error } = useDiseaseCatalog(query);
  const { runs: activeRuns } = useActiveResearchRuns(3);
  const { t } = useTranslation("common");
  const copy = useAudienceCopy(view).home;

  // LEFT card — "I know the disease": forgiving multilingual catalog search.
  const goSearch = () => {
    const q = query.trim();
    onNav(q ? `/diseases?q=${encodeURIComponent(q)}` : "/diseases");
  };

  // RIGHT card — "I don't know the diagnosis". There is no dedicated
  // disease-agnostic symptom/orientation route yet (the orientation map at
  // /diseases/:slug/map needs a known disease), so route the symptom/variant
  // input to the same forgiving catalog search — the closest existing surface.
  const goSymptom = () => {
    const q = symptomQuery.trim();
    onNav(q ? `/diseases?q=${encodeURIComponent(q)}` : "/diseases");
  };

  // Feedback bar — commission an AI research run for any disease.
  const goResearch = () => onNav("/start-research");

  const chips = diseases.slice(0, 3);

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
      </div>

      {/* ── TWO DOORS ── */}
      <div className="doors">
        {/* LEFT — know the disease */}
        <div className="door door--know">
          <div className="door__k">
            <span className="door__ic" aria-hidden>
              {iconSearch}
            </span>
            {copy.knowKicker}
          </div>
          <h2 className="door__title">{copy.knowTitle}</h2>
          <p className="door__desc">{copy.knowDesc}</p>
          <form
            className="door__form"
            onSubmit={(e) => {
              e.preventDefault();
              goSearch();
            }}
          >
            <SearchBar
              value={query}
              onChange={setQuery}
              placeholder={copy.searchPlaceholder}
              icon={iconSearch}
              aria-label={copy.knowTitle}
            />
          </form>
          <p className="door__hint">{copy.searchHint}</p>
          {chips.length > 0 ? (
            <div className="quicklinks">
              {chips.map((d) => (
                <a
                  key={d.slug}
                  className="ql"
                  href={`/diseases/${d.slug}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNav(`/diseases/${d.slug}`);
                  }}
                >
                  <b>{d.name}</b>
                  <code>{d.gene}</code>
                </a>
              ))}
            </div>
          ) : null}
        </div>

        {/* RIGHT — don't know the diagnosis */}
        <div className="door door--dont">
          <div className="door__k">
            <span className="door__ic" aria-hidden>
              {iconBulb}
            </span>
            {copy.dontKicker}
            <span className="badge-soon">{copy.dontBadge}</span>
          </div>
          <h2 className="door__title">{copy.dontTitle}</h2>
          <p className="door__desc">
            {copy.dontDescLead}
            <b className="door__desc-emph">{copy.dontDescEmph}</b>
          </p>
          <form
            className="door__form"
            onSubmit={(e) => {
              e.preventDefault();
              goSymptom();
            }}
          >
            <SearchBar
              value={symptomQuery}
              onChange={setSymptomQuery}
              placeholder={copy.symptomPlaceholder}
              icon={iconBulb}
              aria-label={copy.dontTitle}
            />
          </form>
          <div className="quicklinks">
            {copy.symptomExamples.map((ex) => (
              <button
                key={ex.label}
                type="button"
                className="ql"
                onClick={() => setSymptomQuery(ex.hint)}
              >
                <b>{ex.label}</b>
                <span>{ex.hint}</span>
              </button>
            ))}
          </div>
          <Button
            type="button"
            variant="primary"
            size="lg"
            className="door__cta"
            onClick={goSymptom}
          >
            {copy.dontCta} <span className="arw" aria-hidden>→</span>
          </Button>
        </div>
      </div>

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
          <span>{copy.honestFootnote}</span>{" "}
          <a
            className="lnk"
            href="/about"
            onClick={(e) => {
              e.preventDefault();
              onNav("/about");
            }}
          >
            {copy.honestLinkLabel} <span className="arw" aria-hidden>→</span>
          </a>
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
        <form
          className="fb__form"
          onSubmit={(e) => {
            e.preventDefault();
            goResearch();
          }}
        >
          <input
            value={addQuery}
            onChange={(e) => setAddQuery(e.target.value)}
            placeholder={copy.addPlaceholder}
            aria-label={copy.addTitle}
          />
          <Button type="submit" variant="primary">
            {copy.addCta}
          </Button>
        </form>
      </div>
    </div>
  );
}
