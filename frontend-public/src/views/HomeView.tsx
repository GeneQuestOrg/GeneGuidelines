import { useState } from "react";
import { SearchBar, Button, Section } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import { getAudienceCopy } from "../copy";
import { ActiveResearchSection } from "../components/ActiveResearchSection";
import { DiseaseCard } from "../components/DiseaseCard";
import { InfoHint } from "../components/InfoHint";
import { NewDiseaseCard } from "../components/NewDiseaseCard";
import { useActiveResearchRuns } from "../hooks/useActiveResearchRuns";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../components/disease-grid.css";
import "../styles/disease-page.css";

export interface HomeViewProps {
  view: AudienceView;
  onNav: (path: string) => void;
}

export function HomeView({ view, onNav }: HomeViewProps) {
  const [query, setQuery] = useState("");
  const { diseases, stats, loading, error } = useDiseaseCatalog(query);
  const { runs: activeRuns } = useActiveResearchRuns(3);
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
        <h1 className="hero__title">
          {copy.titleLine1}
          <br />
          <em>{copy.titleEmphasis}</em>
        </h1>
        <p className="hero__lead">
          {copy.subtitle}{" "}
          <a
            href="#/about"
            className="hero__about-link"
            onClick={(e) => {
              e.preventDefault();
              onNav("/about");
            }}
          >
            {copy.aboutLinkLabel} →
          </a>
        </p>
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
          <Button
            type="button"
            variant="ghost"
            onClick={() => onNav("/start-research")}
          >
            + {copy.researchCta}
          </Button>
        </div>
        {stats != null ? (
          <div className="intro__meta">
            <span>
              <b>{stats.diseaseCount}</b> diseases{" "}
              <InfoHint label="(growing)" ariaLabel="Why the disease count is growing">
                We add diseases on demand and in regular batches — covering all of rare
                disease at once is costly, so we prioritise the conditions families
                actually ask for.
              </InfoHint>
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

      <ActiveResearchSection runs={activeRuns} onNav={onNav} />

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
