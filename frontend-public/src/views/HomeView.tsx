import { useState } from "react";
import { SearchBar, Button, Section } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import { getAudienceCopy } from "../copy";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import { DiseaseCard } from "../components/DiseaseCard";
import { NewDiseaseCard } from "../components/NewDiseaseCard";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../components/disease-grid.css";
import "../styles/disease-page.css";

export interface HomeViewProps {
  view: AudienceView;
  onViewChange: (view: AudienceView) => void;
  onNav: (path: string) => void;
}

export function HomeView({ view, onViewChange, onNav }: HomeViewProps) {
  const [query, setQuery] = useState("");
  const { diseases, stats, loading, error } = useDiseaseCatalog(query);
  const copy = getAudienceCopy(view).home;

  const goSearch = () => {
    const q = query.trim();
    if (q) {
      onNav(`/diseases?q=${encodeURIComponent(q)}`);
    }
  };

  return (
    <div className="page page--home">
      <header className="hero">
        <div className="intro__eyebrow">
          <span className="intro__dot" aria-hidden />
          {copy.eyebrow}
        </div>
        <div className="hero__top">
          <PersonaSwitcher view={view} onChange={onViewChange} />
        </div>
        <h1 className="hero__title">
          {copy.titleLine1}
          <br />
          <em>{copy.titleEmphasis}</em>
        </h1>
        <p className="hero__lead">{copy.subtitle}</p>
        <div className="intro__bar">
          <form
            className="hero__search"
            onSubmit={(e) => {
              e.preventDefault();
              goSearch();
            }}
          >
            <SearchBar
              value={query}
              onChange={setQuery}
              placeholder={copy.searchPlaceholder}
              aria-label="Search diseases"
            />
          </form>
          <a
            href="#/about"
            className="intro__sublink"
            onClick={(e) => {
              e.preventDefault();
              onNav("/about");
            }}
          >
            {copy.aboutLinkLabel} →
          </a>
        </div>
        <div className="hero__cta">
          <Button variant="primary" type="button" onClick={() => onNav("/diseases")}>
            {copy.browseCta}
          </Button>
          <Button type="button" onClick={() => onNav("/start-research")}>
            {copy.researchCta}
          </Button>
        </div>
        {stats != null ? (
          <div className="intro__meta">
            <span>
              <b>{stats.diseaseCount}</b> diseases
            </span>
            <span>
              <b>{stats.doctorCount}</b> specialists
            </span>
            <span>
              <b>{stats.recruitingTrialCount}</b> recruiting trials
            </span>
            <span>
              <b>{stats.openPrCount}</b> open PRs
            </span>
          </div>
        ) : null}
      </header>

      {error != null ? (
        <p className="catalog-error" role="alert">
          {error}
        </p>
      ) : null}

      <Section title={copy.diseasesSectionTitle} count={loading ? undefined : diseases.length}>
        {loading ? (
          <p className="page__lead">Loading catalog…</p>
        ) : (
          <div className="d-grid">
            {diseases.map((d) => (
              <DiseaseCard key={d.slug} disease={d} onNav={onNav} />
            ))}
            <NewDiseaseCard copy={copy} onNav={onNav} />
          </div>
        )}
      </Section>
    </div>
  );
}
