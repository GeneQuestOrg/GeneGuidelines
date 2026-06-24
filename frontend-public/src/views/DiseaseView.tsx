import { useEffect, useState } from "react";
import type { UserLocation } from "../router/types";
import { getAudienceCopy } from "../copy";
import { useAccountContext } from "../auth/accountContext";
import { audienceForRole, isClinicianView, type ViewRole } from "../auth/resolveRole";
import { Section, Button } from "@gene-guidelines/ui";
import { DiseaseHero } from "../components/DiseaseHero";
import { DiseaseSubscribeModal } from "../components/DiseaseSubscribeModal";
import { loadSubscriptionUiStatus } from "../utils/loadSubscriptionUiStatus";
import { MyCaseCta } from "../components/MyCaseCta";
import { OrientationMapCta } from "../components/OrientationMapCta";
import { DiseaseTabs } from "../components/DiseaseTabs";
import { OfficialGuidelineBlock } from "../components/OfficialGuidelineBlock";
import { SynthesisTeaser } from "../components/guidelines/SynthesisTeaser";
import { CompactSourceShelf } from "../components/guidelines/CompactSourceShelf";
import { useDisease } from "../hooks/useDisease";
import { useOfficialGuideline } from "../hooks/useOfficialGuideline";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { useRelatedDiseases } from "../hooks/useRelatedDiseases";
import { useActiveResearchRuns } from "../hooks/useActiveResearchRuns";
import type { SubscriptionUiStatus } from "../utils/diseaseSubscriptionStorage";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/disease-page.css";
import "../styles/my-case.css";

export interface DiseaseViewProps {
  slug: string;
  role: ViewRole;
  userLoc: UserLocation | null;
  onNav: (path: string) => void;
  alert?: string;
}

function parseAlertFromHash(): string | undefined {
  if (typeof window === "undefined") return undefined;
  const query = window.location.hash.split("?")[1];
  if (!query) return undefined;
  return new URLSearchParams(query).get("alert") ?? undefined;
}

export function DiseaseView({ slug, role, userLoc, onNav, alert }: DiseaseViewProps) {
  const [showSubscribe, setShowSubscribe] = useState(false);
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionUiStatus>("none");
  const [bannerAlert] = useState<string | undefined>(alert ?? parseAlertFromHash());
  const { disease, loading, error } = useDisease(slug);
  const { related, loading: relatedLoading } = useRelatedDiseases(disease?.related ?? []);
  const { pointer: officialPointer } = useOfficialGuideline(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);
  const { signInAvailable, login } = useAccountContext();
  // Surface "this disease is being re-processed now" from the live research feed
  // (the worker refreshes a disease's content/specialists). 25 covers a realistic
  // burst of concurrent runs so this disease's run is not missed by the top-N cap.
  const { runs: activeRuns } = useActiveResearchRuns(25);
  const reprocessingRun = activeRuns.find((r) => r.diseaseSlug === slug) ?? null;
  const copy = getAudienceCopy(audienceForRole(role)).disease;
  const isClinician = isClinicianView(role);

  useEffect(() => {
    let cancelled = false;
    void loadSubscriptionUiStatus(slug).then((status) => {
      if (!cancelled) setSubscriptionStatus(status);
    });
    return () => {
      cancelled = true;
    };
  }, [slug, showSubscribe]);

  useEffect(() => {
    if (bannerAlert === "confirmed") {
      void loadSubscriptionUiStatus(slug).then(setSubscriptionStatus);
    }
  }, [bannerAlert, slug]);

  const refreshSubscriptionStatus = () => {
    void loadSubscriptionUiStatus(slug).then(setSubscriptionStatus);
  };

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
          <Button variant="primary" size="sm" type="button" onClick={login}>
            Sign in
          </Button>
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
      {reprocessingRun ? (
        <p className="disease-pending-badge disease-pending-badge--refresh" role="status">
          <span
            className="disease-pending-badge__dot disease-pending-badge__dot--pulse"
            aria-hidden="true"
          />
          Refreshing now — {reprocessingRun.label || "research in progress"}
          {reprocessingRun.elapsedSec != null ? ` · ${reprocessingRun.elapsedSec}s` : ""}.
          Showing the latest saved results; they may change shortly.
        </p>
      ) : null}
      {bannerAlert === "confirmed" ? (
        <p className="d-alert-banner d-alert-banner--ok" role="status">
          Email alerts confirmed for {disease.nameShort}. We will only email when something
          substantive changes.
        </p>
      ) : null}
      {bannerAlert === "unsubscribed" ? (
        <p className="d-alert-banner d-alert-banner--muted" role="status">
          You are unsubscribed from {disease.nameShort} alerts.
        </p>
      ) : null}
      <DiseaseHero
        disease={disease}
        copy={copy}
        isClinician={isClinician}
        subscriptionStatus={subscriptionStatus}
        onNav={onNav}
        onSubscribe={() => setShowSubscribe(true)}
      />
      {showSubscribe ? (
        <DiseaseSubscribeModal
          disease={disease}
          onClose={() => {
            setShowSubscribe(false);
            refreshSubscriptionStatus();
          }}
          onSaved={() => refreshSubscriptionStatus()}
        />
      ) : null}
      {!isClinician ? <OrientationMapCta disease={disease} onNav={onNav} /> : null}
      {!isClinician ? <MyCaseCta disease={disease} onNav={onNav} /> : null}
      {sourceDocs.length > 0 ? (
        <Section
          title="Guidelines"
          sub="There is no single document. Below is one synthesis combining every source — and under it, a shelf of the sources themselves."
        >
          <SynthesisTeaser
            diseaseName={disease.name}
            sourceCount={sourceDocs.length}
            hasOfficial={disease.status !== "pending"}
            onOpen={() => onNav(`/diseases/${slug}/guidelines`)}
          />
          <CompactSourceShelf
            docs={sourceDocs}
            onSeeAll={() => onNav(`/diseases/${slug}/guidelines`)}
          />
        </Section>
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
