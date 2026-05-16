import { Button, Section } from "@gene-guidelines/ui";

const CLINICAL_TRIALS_BASE = "https://clinicaltrials.gov/search";

function buildCtGovUrl(query?: string): string {
  if (query == null || !query.trim()) {
    return CLINICAL_TRIALS_BASE;
  }
  return `${CLINICAL_TRIALS_BASE}?cond=${encodeURIComponent(query.trim())}`;
}

export interface TrialsViewProps {
  readonly initialQuery?: string;
  readonly onNav: (path: string) => void;
}

export function TrialsView({ initialQuery, onNav }: TrialsViewProps) {
  const href = buildCtGovUrl(initialQuery);
  return (
    <section className="page">
      <header className="page__head">
        <h1 className="page__title">Clinical trials</h1>
        <p className="page__lead">
          GeneGuidelines does not host trial recruitment. Use the official registry to search
          studies, eligibility, and sites.
        </p>
      </header>
      <Section title="ClinicalTrials.gov" sub="U.S. National Library of Medicine registry.">
        <p className="d-panel-stat">
          {initialQuery?.trim()
            ? `Suggested search term from this visit: “${initialQuery.trim()}”.`
            : "Open the registry to search by condition, intervention, or location."}
        </p>
        <div className="page__actions">
          <Button variant="primary" as="a" href={href} target="_blank" rel="noreferrer">
            Search ClinicalTrials.gov
          </Button>
          <Button type="button" variant="ghost" onClick={() => onNav("/diseases")}>
            Browse diseases
          </Button>
        </div>
      </Section>
    </section>
  );
}
