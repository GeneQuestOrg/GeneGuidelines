import { Button } from "@gene-guidelines/ui";
import type { ViewRole } from "../auth/resolveRole";
import { isClinicianView, isParentSide } from "../auth/resolveRole";
import { useAccountContext } from "../auth/accountContext";
import { useDisease } from "../hooks/useDisease";
import { useGuidelineSynthesis } from "../hooks/useGuidelineSynthesis";
import { useGuidelineSuggestions } from "../hooks/useGuidelineSuggestions";
import { useSynthSignals } from "../hooks/useSynthSignals";
import { useGuidelineBaseline } from "../hooks/useGuidelineBaseline";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { RolePill } from "../components/guidelines/RolePill";
import { GuidelineParentView } from "./GuidelineParentView";
import { GuidelineClinicianView } from "./GuidelineClinicianView";
import { FocusedReviewView } from "./FocusedReviewView";
import { ProvenanceDetailView } from "./ProvenanceDetailView";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/guideline-synthesis.css";
import "../styles/guideline-suggestions.css";
import "../styles/guideline-provenance.css";
import "../styles/guideline-baseline.css";
import "../styles/guideline-bibliography.css";

export interface GuidelinesViewProps {
  slug: string;
  /** Focused-review target (`/guidelines/pr/:id`) — clinician-only. */
  prId?: string;
  /** Provenance-detail target (`/guidelines/source/:paraId`) — clinician-only. */
  srcParaId?: string;
  role: ViewRole;
  onNav: (path: string) => void;
}

/**
 * Guidelines layer v2 — ONE synthesis object, three renderings gated by the
 * viewer's role (chat 019). Parent/guest get the condensed, actionable
 * projection; clinician/researcher get the full text with provenance plus the
 * AI-suggestions rail. The role comes from auth (resolveRole), not a toggle.
 */
export function GuidelinesView({
  slug,
  prId,
  srcParaId,
  role,
  onNav,
}: GuidelinesViewProps) {
  const { signInAvailable, login, account } = useAccountContext();
  const { disease, loading: diseaseLoading, error: diseaseError } = useDisease(slug);
  const { synthesis, loading: synthLoading } = useGuidelineSynthesis(slug);
  // Pass the account id so the rail refetches once auth resolves and each
  // suggestion's `myVote` (the clinician's own rating) is populated.
  const { suggestions, loading: suggLoading } = useGuidelineSuggestions(
    slug,
    account?.id ?? null,
  );
  const { signals, loading: signalsLoading } = useSynthSignals(slug);
  // A baseline (level (c)) only exists when there is no official guideline.
  // Skip the fetch once synthesis has loaded with an official guideline — an
  // ungated call 404s on every disease (no backend route) and spams the console.
  const hasOfficialSynthesis = synthesis != null && synthesis.status !== "pending";
  const baselineEnabled = !synthLoading && !hasOfficialSynthesis;
  const { baseline, loading: baselineLoading } = useGuidelineBaseline(slug, baselineEnabled);
  const { docs, loading: shelfLoading } = useSourceShelf(slug);

  const loading =
    diseaseLoading ||
    synthLoading ||
    suggLoading ||
    signalsLoading ||
    baselineLoading ||
    shelfLoading;

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

  // Focused review of one suggestion — clinician-only. Parents hitting the URL
  // fall through to the normal (parent) projection.
  if (prId != null && isClinicianView(role)) {
    const suggestion = suggestions.find((s) => s.id === prId);
    if (suggestion != null) {
      return (
        <FocusedReviewView
          slug={slug}
          disease={disease}
          suggestion={suggestion}
          role={role}
          onNav={onNav}
        />
      );
    }
  }

  // Provenance detail ("where we know this from") — public: the source trail behind a claim is
  // shown to everyone (incl. logged-out) to make the evidence transparent and raise credibility.
  if (srcParaId != null && synthesis != null) {
    return (
      <ProvenanceDetailView
        slug={slug}
        disease={disease}
        synthesis={synthesis}
        docs={docs}
        paraId={srcParaId}
        role={role}
        onNav={onNav}
      />
    );
  }

  const hasOfficial = hasOfficialSynthesis;
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
          suggestions={suggestions}
          signals={signals}
          baseline={baseline}
          hasOfficial={hasOfficial}
          role={role}
          docs={docs}
          onNav={onNav}
        />
      ) : (
        <GuidelineParentView
          disease={disease}
          synthesis={synthesis}
          suggestions={suggestions}
          baseline={baseline}
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
