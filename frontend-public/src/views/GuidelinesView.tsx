import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Status } from "@gene-guidelines/ui";
import { GuidelineCitationRail } from "../components/guidelines/GuidelineCitationRail";
import { GuidelineParagraphBlock } from "../components/guidelines/GuidelineParagraphBlock";
import { useContentPrs } from "../hooks/useContentPrs";
import { useDisease } from "../hooks/useDisease";
import { useGuidelineDocument } from "../hooks/useGuidelineDocument";
import { useGuidelinePr } from "../hooks/useGuidelinePr";
import { useParentPathway } from "../hooks/useParentPathway";
import { ParentGuidePanel } from "../components/guidelines/ParentGuidePanel";
import {
  buildSectionsForPrPreview,
  filterDocumentForReader,
  isParagraphInPrTarget,
} from "../utils/guidelineDiff";
import { collectCitationPmids } from "../utils/guidelineReader";
import { collectPathwayCitedPmids } from "../utils/pathwayCitations";
import type { AudienceView } from "../router/types";
import type { ParentPathway } from "../types/parentPathway";
import { ClinicalDisclaimer } from "../components/ClinicalDisclaimer";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/guidelines.css";

export interface GuidelinesViewProps {
  slug: string;
  prId?: string;
  view: AudienceView;
  onNav: (path: string) => void;
}

function scrollToSection(sectionId: string): void {
  document.getElementById(`sec-${sectionId}`)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

interface PathwayOnlyGuidelineProps {
  slug: string;
  diseaseLabel: string;
  diseaseName: string | null;
  pathway: ParentPathway;
  view: AudienceView;
  onNav: (path: string) => void;
}

function PathwayOnlyLivingGuideline({
  slug,
  diseaseLabel,
  diseaseName,
  pathway,
  view,
  onNav,
}: PathwayOnlyGuidelineProps) {
  const tree = pathway.tree;
  const pathwayPmids = collectPathwayCitedPmids(tree);

  return (
    <section className="page page--guidelines">
      <a href="#gl-main" className="gl__skip">
        Skip to document
      </a>

      <header className="gl__bar">
        <div className="gl__bar-left">
          <Button
            variant="ghost"
            type="button"
            onClick={() => onNav(`/diseases/${slug}`)}
          >
            ← {diseaseLabel}
          </Button>
          <div className="gl__doctitle">
            <span className="gl__version">{pathway.version}</span>
            <h1>Living guideline</h1>
            <p className="gl__pathway-only-sub">{tree.title}</p>
          </div>
        </div>
        <div className="gl__bar-right">
          <Button variant="ghost" type="button" onClick={() => window.print()}>
            Print
          </Button>
        </div>
      </header>

      <ClinicalDisclaimer view={view} />

      <p className="gl__pathway-only-lead">
        Patient-friendly summary of the current consensus evidence and practical next steps.
        {diseaseName != null
          ? ` Full clinician guideline for ${diseaseName} is not published separately yet.`
          : ""}
      </p>

      <div className="gl__meta">
        <div>
          <span className="gl__metalabel">Version</span> <code>{pathway.version}</code>
        </div>
        <div>
          <span className="gl__metalabel">Last updated</span> {pathway.generatedAt}
        </div>
        <div className="gl__basedon">
          <span className="gl__metalabel">Based on</span> {pathway.basedOn || tree.basedOn || "—"}
        </div>
      </div>

      <div className="gl__layout gl__layout--pathway-only">
        <article id="gl-main" className="gl__doc gl__doc--pathway-only">
          <ParentGuidePanel pathway={pathway} slug={slug} onNav={onNav} />
        </article>

        <GuidelineCitationRail
          orderedPmids={pathwayPmids}
          railPmids={pathwayPmids}
          activeParaId={null}
          diffMode={false}
          pr={null}
        />
      </div>
    </section>
  );
}

export function GuidelinesView({ slug, prId, view, onNav }: GuidelinesViewProps) {
  const diffMode = prId != null;
  const { disease, loading: diseaseLoading } = useDisease(slug);
  const { document: rawDoc, loading: docLoading, error: docError } =
    useGuidelineDocument(slug);
  const { pr, loading: prLoading, error: prError } = useGuidelinePr(prId);
  const { openPrs: openPrsForDoc } = useContentPrs(slug);
  const {
    pathway: parentPathway,
    loading: pathwayLoading,
    error: pathwayError,
  } = useParentPathway(slug);
  const [activeParaId, setActiveParaId] = useState<string | null>(null);
  const [focusedPmid, setFocusedPmid] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const sections = useMemo(() => {
    if (rawDoc == null) {
      return null;
    }
    if (diffMode && prId != null) {
      return buildSectionsForPrPreview(rawDoc, pr?.paragraphMap ?? null, prId);
    }
    return filterDocumentForReader(rawDoc).sections;
  }, [rawDoc, diffMode, prId, pr?.paragraphMap]);

  const orderedPmids = useMemo(() => {
    if (rawDoc == null || sections == null) {
      return [];
    }
    const readerOptions =
      diffMode && prId != null ? { diffPrId: prId } : undefined;
    return collectCitationPmids({ ...rawDoc, sections }, readerOptions);
  }, [rawDoc, sections, diffMode, prId]);

  const railPmids = useMemo(() => {
    if (focusedPmid != null) {
      return [focusedPmid];
    }
    if (activeParaId != null && sections != null) {
      for (const sec of sections) {
        const para = sec.paragraphs.find((p) => p.id === activeParaId);
        if (para?.citations != null && para.citations.length > 0) {
          return para.citations;
        }
      }
    }
    return orderedPmids;
  }, [activeParaId, sections, focusedPmid, orderedPmids]);

  useEffect(() => {
    if (sections == null || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) {
          const id = visible[0].target.getAttribute("data-para-id");
          if (id != null) {
            setActiveParaId(id);
            setFocusedPmid(null);
          }
        }
      },
      { rootMargin: "-30% 0px -50% 0px", threshold: [0, 0.5, 1] },
    );
    observerRef.current = observer;
    document.querySelectorAll("[data-para-id]").forEach((el) => {
      observer.observe(el);
    });
    return () => observer.disconnect();
  }, [sections, prId]);

  const loading =
    diseaseLoading ||
    docLoading ||
    pathwayLoading ||
    (diffMode && prLoading);
  const error = docError ?? (diffMode ? prError : null);

  if (loading) {
    return (
      <section className="page page--guidelines">
        <p className="page__lead">Loading guideline…</p>
      </section>
    );
  }

  if (error != null) {
    return (
      <PlaceholderView
        title="Could not load guideline"
        description={error}
        primaryAction={{ label: "Disease overview", path: `/diseases/${slug}` }}
        onNav={onNav}
      />
    );
  }

  const pathwayOnly =
    !diffMode &&
    rawDoc == null &&
    parentPathway != null &&
    parentPathway.tree.children.length > 0;

  if (pathwayOnly) {
    const diseaseLabel = disease?.nameShort ?? slug;
    return (
      <PathwayOnlyLivingGuideline
        slug={slug}
        diseaseLabel={diseaseLabel}
        diseaseName={disease?.name ?? null}
        pathway={parentPathway}
        view={view}
        onNav={onNav}
      />
    );
  }

  if (
    !diffMode &&
    rawDoc == null &&
    !pathwayLoading &&
    parentPathway == null &&
    pathwayError != null
  ) {
    return (
      <PlaceholderView
        title="Could not load care pathway"
        description={pathwayError}
        primaryAction={{ label: "Disease overview", path: `/diseases/${slug}` }}
        onNav={onNav}
      />
    );
  }

  if (rawDoc == null || sections == null) {
    return (
      <PlaceholderView
        title="Guideline not available"
        description={
          disease != null
            ? `A living guideline document or published care pathway for ${disease.name} is not available yet.`
            : `No guideline document for “${slug}”.`
        }
        primaryAction={{ label: "Browse diseases", path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  if (diffMode && pr == null) {
    return (
      <PlaceholderView
        title="Pull request not found"
        description={`No guideline change request “${prId}” for this disease.`}
        primaryAction={{ label: "Published guideline", path: `/diseases/${slug}/guidelines` }}
        onNav={onNav}
      />
    );
  }

  const doc = rawDoc;
  const diseaseLabel = disease?.nameShort ?? slug;
  const paraMap = pr?.paragraphMap ?? null;

  return (
    <section className="page page--guidelines">
      <a href="#gl-main" className="gl__skip">
        Skip to document
      </a>

      <header className="gl__bar">
        <div className="gl__bar-left">
          <Button
            variant="ghost"
            type="button"
            onClick={() => onNav(`/diseases/${slug}`)}
          >
            ← {diseaseLabel}
          </Button>
          <div className="gl__doctitle">
            <span className="gl__version">{doc.version}</span>
            <h1>{doc.title}</h1>
          </div>
        </div>
        <div className="gl__bar-right">
          {diffMode ? (
            <Button
              variant="ghost"
              type="button"
              onClick={() => onNav(`/diseases/${slug}/guidelines`)}
            >
              Exit PR preview →
            </Button>
          ) : (
            <Button variant="ghost" type="button" onClick={() => window.print()}>
              Print
            </Button>
          )}
        </div>
      </header>

      <ClinicalDisclaimer view={view} />

      {diffMode && pr != null ? (
        <div className="gl__prbanner" role="region" aria-label="Pull request">
          <div className="gl__prbanner-top">
            <Status status={pr.status} compact />
            <code>{pr.id}</code>
            <span className="gl__prbanner-title">{pr.title}</span>
          </div>
          <p>{pr.summary}</p>
          <div className="gl__prbanner-meta">
            opened {pr.opened} · by {pr.author} · {pr.citationsCount} citations
            {pr.reviewer != null ? ` · reviewer: ${pr.reviewer}` : " · awaiting reviewer"}
          </div>
        </div>
      ) : null}

      {!diffMode && parentPathway?.tree ? (
        <ParentGuidePanel pathway={parentPathway} slug={slug} onNav={onNav} />
      ) : null}

      <div className="gl__meta">
        <div>
          <span className="gl__metalabel">Version</span> <code>{doc.version}</code>
        </div>
        <div>
          <span className="gl__metalabel">Last updated</span> {doc.lastUpdated}
        </div>
        <div>
          <span className="gl__metalabel">Status</span>{" "}
          <Status status={doc.status} compact />
        </div>
        {doc.statusBy != null ? (
          <div>
            <span className="gl__metalabel">Approved by</span> {doc.statusBy}
          </div>
        ) : null}
        <div className="gl__basedon">
          <span className="gl__metalabel">Based on</span> {doc.basedOn}
        </div>
      </div>

      <div className="gl__layout">
        <nav className="gl__toc" aria-label="Table of contents">
          <div className="gl__toc-label">Contents</div>
          <ul>
            {sections.map((sec) => (
              <li key={sec.id}>
                <a
                  href={`#sec-${sec.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    scrollToSection(sec.id);
                  }}
                >
                  {sec.title}
                </a>
              </li>
            ))}
          </ul>
          {!diffMode && openPrsForDoc.length > 0 ? (
            <>
              <div className="gl__toc-label gl__toc-label--spaced">Open PRs</div>
              <ul>
                {openPrsForDoc.map((p) => (
                  <li key={p.id}>
                    <a
                      href={`#/diseases/${slug}/guidelines/pr/${p.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        onNav(`/diseases/${slug}/guidelines/pr/${p.id}`);
                      }}
                    >
                      <Status status={p.status} compact /> <code>{p.id}</code>
                      <div className="gl__toc-prtitle">{p.title}</div>
                    </a>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </nav>

        <article id="gl-main" className="gl__doc">
          {sections.map((sec) => (
            <section
              key={sec.id}
              id={`sec-${sec.id}`}
              className={[
                "gl__section",
                diffMode && paraMap?.targetSection === sec.id
                  ? "gl__section--prtarget"
                  : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-labelledby={`sec-title-${sec.id}`}
            >
              <h2 id={`sec-title-${sec.id}`} className="gl__sectitle">
                {sec.title}
              </h2>
              {sec.intro != null ? <p className="gl__secintro">{sec.intro}</p> : null}
              {sec.paragraphs.map((para) => (
                <GuidelineParagraphBlock
                  key={para.id}
                  para={para}
                  orderedPmids={orderedPmids}
                  isActive={activeParaId === para.id}
                  diffMode={diffMode}
                  diffPrId={prId ?? null}
                  inPrTarget={isParagraphInPrTarget(para.id, paraMap)}
                  onFocusPara={setActiveParaId}
                  onCitationClick={(pmid) => {
                    setFocusedPmid(pmid);
                    setActiveParaId(para.id);
                  }}
                />
              ))}
            </section>
          ))}
        </article>

        <GuidelineCitationRail
          orderedPmids={orderedPmids}
          railPmids={railPmids}
          activeParaId={activeParaId}
          diffMode={diffMode}
          pr={pr}
        />
      </div>
    </section>
  );
}
