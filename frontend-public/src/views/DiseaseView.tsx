import type { UserLocation } from "../router/types";
import { getAudienceCopy } from "../copy";
import { useAccountContext } from "../auth/accountContext";
import { audienceForRole, isClinicianView, type ViewRole } from "../auth/resolveRole";
import { DiseaseHero } from "../components/DiseaseHero";
import { DiseaseTabs } from "../components/DiseaseTabs";
import { OfficialGuidelineBlock } from "../components/OfficialGuidelineBlock";
import { SourceShelf } from "../components/guidelines/SourceShelf";
import { useDisease } from "../hooks/useDisease";
import { useOfficialGuideline } from "../hooks/useOfficialGuideline";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { useRelatedDiseases } from "../hooks/useRelatedDiseases";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/disease-page.css";

export interface DiseaseViewProps {
  slug: string;
  role: ViewRole;
  userLoc: UserLocation | null;
  onNav: (path: string) => void;
}

export function DiseaseView({ slug, role, userLoc, onNav }: DiseaseViewProps) {
  const { disease, guideline, loading, error } = useDisease(slug);
  const { related, loading: relatedLoading } = useRelatedDiseases(disease?.related ?? []);
  const { pointer: officialPointer } = useOfficialGuideline(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);
  const { signInAvailable, login } = useAccountContext();
  const copy = getAudienceCopy(audienceForRole(role)).disease;
  const isClinician = isClinicianView(role);

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
      {role === "anon" && signInAvailable ? (
        <aside className="viewer-cta" role="note">
          <span className="viewer-cta__text">
            Are you a clinician? Sign in to see AI suggestions and the literature trail.
          </span>
          <button type="button" className="viewer-cta__btn" onClick={login}>
            Sign in
          </button>
        </aside>
      ) : null}
      {role === "doctor-unverified" ? (
        <p className="viewer-pending" role="status">
          <span className="viewer-pending__dot" aria-hidden="true" />
          Clinician account pending verification — you can read AI suggestions; rating
          unlocks once verified.
        </p>
      ) : null}
      {!disease.listed ? (
        <p className="disease-pending-badge" role="status">
          <span className="disease-pending-badge__dot" aria-hidden="true" />
          Not yet in the public catalog — pending curation.
        </p>
      ) : null}
      <DiseaseHero
        disease={disease}
        guideline={guideline}
        copy={copy}
        isClinician={isClinician}
        onNav={onNav}
      />
      {sourceDocs.length > 0 ? (
        <SourceShelf docs={sourceDocs} parent={!isClinician} />
      ) : officialPointer != null ? (
        <OfficialGuidelineBlock pointer={officialPointer} />
      ) : null}
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
