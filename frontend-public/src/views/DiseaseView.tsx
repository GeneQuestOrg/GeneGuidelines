import type { AudienceView, UserLocation } from "../router/types";
import { getAudienceCopy } from "../copy";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import { DiseaseHero } from "../components/DiseaseHero";
import { DiseaseTabs } from "../components/DiseaseTabs";
import { useDisease } from "../hooks/useDisease";
import { useRelatedDiseases } from "../hooks/useRelatedDiseases";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/disease-page.css";

export interface DiseaseViewProps {
  slug: string;
  view: AudienceView;
  userLoc: UserLocation | null;
  onViewChange: (view: AudienceView) => void;
  onNav: (path: string) => void;
}

export function DiseaseView({ slug, view, userLoc, onViewChange, onNav }: DiseaseViewProps) {
  const { disease, guideline, loading, error } = useDisease(slug);
  const { related, loading: relatedLoading } = useRelatedDiseases(disease?.related ?? []);
  const copy = getAudienceCopy(view).disease;
  const isClinician = view === "doctor";

  if (loading) {
    return (
      <section className="page page--disease">
        <p className="page__lead">Loading disease…</p>
      </section>
    );
  }

  if (error != null) {
    return (
      <PlaceholderView
        title="Could not load disease"
        description={error}
        primaryAction={{ label: "Back to home", path: "/" }}
        onNav={onNav}
      />
    );
  }

  if (disease == null) {
    return (
      <PlaceholderView
        title="Disease not found"
        description={`No guideline catalog entry for “${slug}”. Try browsing the disease list.`}
        primaryAction={{ label: "Browse diseases", path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  return (
    <section className="page page--disease">
      <PersonaSwitcher view={view} onChange={onViewChange} />
      <DiseaseHero
        disease={disease}
        guideline={guideline}
        copy={copy}
        isClinician={isClinician}
        onNav={onNav}
      />
      <DiseaseTabs
        disease={disease}
        copy={copy}
        isClinician={isClinician}
        related={related}
        relatedLoading={relatedLoading}
        userLoc={userLoc}
        onNav={onNav}
      />
    </section>
  );
}
