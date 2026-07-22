import { useTranslation } from "react-i18next";
import { Section } from "@gene-guidelines/ui";
import { PrivateContextPanel } from "../components/PrivateContextPanel";
import { MyCaseGate } from "../components/MyCaseGate";
import { useAccountContext } from "../auth/accountContext";
import {
  canAccessMyCaseUpload,
  myCaseGateVariant,
} from "../auth/canAccessMyCaseUpload";
import { useDisease } from "../hooks/useDisease";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/my-case.css";

export interface MyCaseViewProps {
  slug: string;
  onNav: (path: string) => void;
}

function MyCaseCrumbs({
  slug,
  diseaseName,
  onNav,
}: {
  slug: string;
  diseaseName: string;
  onNav: (path: string) => void;
}) {
  const { t } = useTranslation("my-case");
  return (
    <nav className="mycase__crumbs" aria-label={t("breadcrumbAriaLabel")}>
      <a
        href="/"
        onClick={(e) => {
          e.preventDefault();
          onNav("/");
        }}
      >
        {t("breadcrumbHome")}
      </a>
      <span aria-hidden>›</span>
      <a
        href={`/diseases/${slug}`}
        onClick={(e) => {
          e.preventDefault();
          onNav(`/diseases/${slug}`);
        }}
      >
        {diseaseName}
      </a>
      <span aria-hidden>›</span>
      <span>{t("breadcrumbCurrent")}</span>
    </nav>
  );
}

export function MyCaseView({ slug, onNav }: MyCaseViewProps) {
  const { t } = useTranslation("my-case");
  const accountCtx = useAccountContext();
  const { disease, loading, error } = useDisease(slug);
  const canUpload = canAccessMyCaseUpload(accountCtx);

  if (loading || (accountCtx.signInAvailable && accountCtx.loading)) {
    return (
      <section className="page page--mycase">
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
    <section className="page page--mycase">
      <MyCaseCrumbs slug={slug} diseaseName={disease.nameShort} onNav={onNav} />

      {canUpload ? (
        <>
          <header className="mycase__header">
            <h1 className="mycase__title">{t("title")}</h1>
            <p className="mycase__lead">{t("lead")}</p>
          </header>

          <Section title={t("uploadSectionTitle")} sub={t("uploadSectionSub")}>
            <PrivateContextPanel diseaseSlug={slug} />
          </Section>
        </>
      ) : (
        <MyCaseGate
          disease={disease}
          variant={myCaseGateVariant(accountCtx)}
          onLogin={accountCtx.login}
        />
      )}
    </section>
  );
}
