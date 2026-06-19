import { Button, Section } from "@gene-guidelines/ui";
import { TherapiesList } from "../components/TherapiesList";
import { TrialsList } from "../components/TrialsList";
import { useDiseaseTherapies } from "../hooks/useDiseaseTherapies";
import { useDiseaseTrials } from "../hooks/useDiseaseTrials";

export type DiseaseItemsListType = "therapies" | "trials";

export interface DiseaseItemsListViewProps {
  slug: string;
  type: DiseaseItemsListType;
  onNav: (path: string) => void;
}

/**
 * Universal sub-page that renders all therapies or all clinical trials for a disease.
 * Linked from the disease overview tab "View all" buttons.
 */
export function DiseaseItemsListView({ slug, type, onNav }: DiseaseItemsListViewProps) {
  const therapiesState = useDiseaseTherapies(type === "therapies" ? slug : "");
  const trialsState = useDiseaseTrials(type === "trials" ? slug : "");

  const isTherapies = type === "therapies";
  const title = isTherapies ? "Therapies" : "Clinical Trials";
  const loading = isTherapies ? therapiesState.loading : trialsState.loading;
  const error = isTherapies ? therapiesState.error : trialsState.error;

  return (
    <section className="page">
      <header className="page__head">
        <h1 className="page__title">{title}</h1>
      </header>
      <Section title={title}>
        <div className="page__actions" style={{ marginBottom: "1rem" }}>
          <Button type="button" variant="ghost" onClick={() => onNav(`/diseases/${slug}`)}>
            ← Back to disease
          </Button>
        </div>
        {error != null ? (
          <p className="d-panel-empty" role="alert">
            {error}
          </p>
        ) : loading ? (
          <p className="d-panel-empty">Loading…</p>
        ) : isTherapies ? (
          therapiesState.therapies.length === 0 ? (
            <p className="d-panel-empty">No therapies found for this disease yet.</p>
          ) : (
            <TherapiesList therapies={therapiesState.therapies} />
          )
        ) : trialsState.trials.length === 0 ? (
          <p className="d-panel-empty">No clinical trials found for this disease right now.</p>
        ) : (
          <TrialsList trials={trialsState.trials} />
        )}
      </Section>
    </section>
  );
}
