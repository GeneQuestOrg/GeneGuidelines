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
  return (
    <nav className="mycase__crumbs" aria-label="Breadcrumb">
      <a
        href="#/"
        onClick={(e) => {
          e.preventDefault();
          onNav("/");
        }}
      >
        Home
      </a>
      <span aria-hidden>›</span>
      <a
        href={`#/diseases/${slug}`}
        onClick={(e) => {
          e.preventDefault();
          onNav(`/diseases/${slug}`);
        }}
      >
        {diseaseName}
      </a>
      <span aria-hidden>›</span>
      <span>My case</span>
    </nav>
  );
}

export function MyCaseView({ slug, onNav }: MyCaseViewProps) {
  const accountCtx = useAccountContext();
  const { disease, loading, error } = useDisease(slug);
  const canUpload = canAccessMyCaseUpload(accountCtx);

  if (loading || (accountCtx.signInAvailable && accountCtx.loading)) {
    return (
      <section className="page page--mycase">
        <p className="page__lead">Loading…</p>
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
        description={`No catalog entry for “${slug}”.`}
        primaryAction={{ label: "Browse diseases", path: "/diseases" }}
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
            <h1 className="mycase__title">My case — private zone</h1>
            <p className="mycase__lead">
              Upload results to keep them in one private place for your care team. We redact personal
              identifiers, extract clinical facts in memory, and destroy the original immediately.
            </p>
          </header>

          <Section
            title="Private document upload"
            sub="Powered by Gemma 4 · in-memory processing · original never stored on disk"
          >
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
