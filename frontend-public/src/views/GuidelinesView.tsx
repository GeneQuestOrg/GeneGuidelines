import { Button } from "@gene-guidelines/ui";
import type { ViewRole } from "../auth/resolveRole";
import { isClinicianView, isParentSide } from "../auth/resolveRole";
import { useAccountContext } from "../auth/accountContext";
import { useDisease } from "../hooks/useDisease";
import { useGuidelineSynthesis } from "../hooks/useGuidelineSynthesis";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { GuidelineParentView } from "./GuidelineParentView";
import { GuidelineClinicianView } from "./GuidelineClinicianView";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/guideline-synthesis.css";

export interface GuidelinesViewProps {
  slug: string;
  role: ViewRole;
  onNav: (path: string) => void;
}

const ROLE_PILL: Record<ViewRole, readonly [string, string]> = {
  anon: ["gx-role--anon", "Reading as · guest"],
  parent: ["gx-role--parent", "Reading as · parent"],
  doctor: ["gx-role--clin", "Reading as · clinician"],
  "doctor-unverified": ["gx-role--clin", "Clinician · unverified"],
  researcher: ["gx-role--clin", "Reading as · researcher"],
};

function RolePill({ role }: { role: ViewRole }) {
  const [cls, label] = ROLE_PILL[role];
  return (
    <span className={`gx-role ${cls}`}>
      <span className="d" aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * Guidelines layer v2 — ONE synthesis object, three renderings gated by the
 * viewer's role (chat 019). Parent/guest get the condensed, actionable
 * projection; clinician/researcher get the full text with provenance. The role
 * comes from auth (resolveRole), not a free toggle.
 */
export function GuidelinesView({ slug, role, onNav }: GuidelinesViewProps) {
  const { disease, loading: diseaseLoading, error: diseaseError } = useDisease(slug);
  const { synthesis, loading: synthLoading } = useGuidelineSynthesis(slug);
  const { docs, loading: shelfLoading } = useSourceShelf(slug);
  const { signInAvailable, login } = useAccountContext();

  const loading = diseaseLoading || synthLoading || shelfLoading;

  if (loading) {
    return (
      <section className="page page--gl2">
        <p className="page__lead">Loading guideline…</p>
      </section>
    );
  }

  if (diseaseError != null) {
    return (
      <PlaceholderView
        title="Could not load guideline"
        description={diseaseError}
        primaryAction={{ label: "Disease overview", path: `/diseases/${slug}` }}
        onNav={onNav}
      />
    );
  }

  if (disease == null) {
    return (
      <PlaceholderView
        title="Disease not found"
        description={`No guideline catalog entry for “${slug}”.`}
        primaryAction={{ label: "Browse diseases", path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  const hasOfficial = synthesis != null && synthesis.status !== "pending";
  const parentSide = isParentSide(role);

  const versionLabel = hasOfficial ? synthesis!.version : "no agreed guideline · level (c)";
  const title = hasOfficial
    ? parentSide
      ? `${disease.name} — what the guidelines say`
      : synthesis!.title
    : `${disease.name} — guidelines`;

  return (
    <section className="page page--gl2">
      <header className="gx-bar">
        <div className="gx-bar__left">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => onNav(`/diseases/${slug}`)}
          >
            ← {disease.nameShort}
          </Button>
          <div>
            <span className={`gx-bar__ver${hasOfficial ? "" : " gx-bar__ver--c"}`}>
              {versionLabel}
            </span>
            <h1 className="gx-bar__title">{title}</h1>
          </div>
        </div>
        <RolePill role={role} />
      </header>

      {isClinicianView(role) ? (
        <GuidelineClinicianView
          disease={disease}
          synthesis={synthesis}
          hasOfficial={hasOfficial}
          role={role}
          docs={docs}
          onNav={onNav}
        />
      ) : (
        <GuidelineParentView
          disease={disease}
          synthesis={synthesis}
          hasOfficial={hasOfficial}
          role={role}
          docs={docs}
          signInAvailable={signInAvailable}
          onSignIn={login}
          onNav={onNav}
        />
      )}
    </section>
  );
}
