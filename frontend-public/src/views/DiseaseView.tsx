import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { UserLocation } from "../router/types";
import { useAudienceCopy } from "../copy";
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

function parseAlertFromSearch(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return new URLSearchParams(window.location.search).get("alert") ?? undefined;
}

export function DiseaseView({ slug, role, userLoc, onNav, alert }: DiseaseViewProps) {
  const { t } = useTranslation("disease");
  const [showSubscribe, setShowSubscribe] = useState(false);
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionUiStatus>("none");
  const [bannerAlert] = useState<string | undefined>(alert ?? parseAlertFromSearch());
  const { disease, loading, error } = useDisease(slug);
  const { related, loading: relatedLoading } = useRelatedDiseases(disease?.related ?? []);
  const { pointer: officialPointer } = useOfficialGuideline(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);
  const { signInAvailable, login } = useAccountContext();
  // Surface "this disease is being re-processed now" from the live research feed
  // (the worker refreshes a disease's content/specialists). 50 = the endpoint cap,
  // so this disease's run is not missed even when several diseases process at once.
  const { runs: activeRuns } = useActiveResearchRuns(50);
  const reprocessingRun = activeRuns.find((r) => r.diseaseSlug === slug) ?? null;
  const copy = useAudienceCopy(audienceForRole(role)).disease;
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
        <p className="page__lead">{t("loading")}</p>
      </section>
    );
  }

  if (error != null) {
    return (
      <PlaceholderView
        title={t("errorLoadTitle")}
        description={error}
        primaryAction={{ label: t("errorLoadAction"), path: "/" }}
        onNav={onNav}
      />
    );
  }

  if (disease == null) {
    return (
      <PlaceholderView
        title={t("notFoundTitle")}
        description={t("notFoundDesc", { slug })}
        primaryAction={{ label: t("notFoundAction"), path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  return (
    <section className="page page--disease">
      {role === "anon" && signInAvailable ? (
        <aside className="viewer-cta" role="note">
          <span className="viewer-cta__text">{t("clinicianCta")}</span>
          <Button variant="primary" size="sm" type="button" onClick={login}>
            {t("signIn")}
          </Button>
        </aside>
      ) : null}
      {role === "doctor-unverified" ? (
        <p className="viewer-pending" role="status">
          <span className="viewer-pending__dot" aria-hidden="true" />
          {t("clinicianPending")}
        </p>
      ) : null}
      {!disease.listed ? (
        <p className="disease-pending-badge" role="status">
          <span className="disease-pending-badge__dot" aria-hidden="true" />
          {t("notListedBadge")}
        </p>
      ) : null}
      {reprocessingRun ? (
        <p className="disease-pending-badge disease-pending-badge--refresh" role="status">
          <span
            className="disease-pending-badge__dot disease-pending-badge__dot--pulse"
            aria-hidden="true"
          />
          {t("refreshing", {
            label: reprocessingRun.label || t("researchInProgress"),
            elapsed: reprocessingRun.elapsedSec != null ? ` · ${reprocessingRun.elapsedSec}s` : "",
          })}
        </p>
      ) : null}
      {bannerAlert === "confirmed" ? (
        <p className="d-alert-banner d-alert-banner--ok" role="status">
          {t("alertConfirmed", { disease: disease.nameShort })}
        </p>
      ) : null}
      {bannerAlert === "unsubscribed" ? (
        <p className="d-alert-banner d-alert-banner--muted" role="status">
          {t("alertUnsubscribed", { disease: disease.nameShort })}
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
          title={t("guidelinesTitle")}
          sub={t("synthesisSub")}
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
