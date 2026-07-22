import { useTranslation } from "react-i18next";
import { Button, Section } from "@gene-guidelines/ui";
import { DiseaseCard } from "../components/DiseaseCard";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../components/disease-grid.css";

export interface DiseaseIndexViewProps {
  initialQuery?: string;
  onNav: (path: string) => void;
}

export function DiseaseIndexView({ initialQuery = "", onNav }: DiseaseIndexViewProps) {
  const { t } = useTranslation("disease-index");
  const { diseases, loading, error } = useDiseaseCatalog(initialQuery);

  return (
    <div className="page page--home">
      <h1 className="page__title">{t("title")}</h1>
      <p className="page__lead">
        {initialQuery ? t("resultsFor", { query: initialQuery }) : t("lead")}
      </p>
      <div style={{ marginBottom: "1.25rem" }}>
        <Button type="button" variant="primary" onClick={() => onNav("/start-research")}>
          {t("startResearch")}
        </Button>
      </div>
      {error != null ? (
        <p className="catalog-error" role="alert">
          {error}
        </p>
      ) : null}
      <Section title={t("sectionTitle")} count={loading ? undefined : diseases.length}>
        {loading ? (
          <p className="page__lead">{t("loading")}</p>
        ) : diseases.length === 0 ? (
          <p className="page__lead">{t("empty")}</p>
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
