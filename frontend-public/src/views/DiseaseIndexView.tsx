import { Button, Section } from "@gene-guidelines/ui";
import { DiseaseCard } from "../components/DiseaseCard";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../components/disease-grid.css";

export interface DiseaseIndexViewProps {
  initialQuery?: string;
  onNav: (path: string) => void;
}

export function DiseaseIndexView({ initialQuery = "", onNav }: DiseaseIndexViewProps) {
  const { diseases, loading, error } = useDiseaseCatalog(initialQuery);

  return (
    <div className="page page--home">
      <h1 className="page__title">Diseases</h1>
      <p className="page__lead">
        {initialQuery
          ? `Results for “${initialQuery}”`
          : "Rare genetic conditions with living, physician-reviewed guidelines."}
      </p>
      <div style={{ marginBottom: "1.25rem" }}>
        <Button type="button" variant="primary" onClick={() => onNav("/start-research")}>
          + Start research
        </Button>
      </div>
      {error != null ? (
        <p className="catalog-error" role="alert">
          {error}
        </p>
      ) : null}
      <Section title="All diseases" count={loading ? undefined : diseases.length}>
        {loading ? (
          <p className="page__lead">Loading catalog…</p>
        ) : diseases.length === 0 ? (
          <p className="page__lead">No diseases match your search.</p>
        ) : (
          <div className="d-grid">
            {diseases.map((d) => (
              <DiseaseCard key={d.slug} disease={d} onNav={onNav} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
