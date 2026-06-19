import { useMemo, useState } from "react";
import type { AnalyzedPaper, AnalyzedPaperVerdict } from "../types/analyzedPaper";
import type { ViewRole } from "../auth/resolveRole";
import { isClinicianView } from "../auth/resolveRole";
import { RolePill } from "../components/guidelines/RolePill";
import { useBibliography } from "../hooks/useBibliography";
import { useDisease } from "../hooks/useDisease";
import {
  BIB_ACCESS_META,
  BIB_VERDICT_META,
  BIB_VERDICT_ORDER,
  bibliographyCounts,
  bibliographyRefLabel,
  bibliographySourceUrl,
  changeProbabilityPercent,
  groupBibliographyByVerdict,
} from "../utils/bibliography";
import "../styles/guideline-bibliography.css";

export interface BibliographyViewProps {
  slug: string;
  role: ViewRole;
  onNav: (path: string) => void;
}

function BibAccessFlag({ access }: { access: AnalyzedPaper["access"] }) {
  const meta = BIB_ACCESS_META[access] ?? BIB_ACCESS_META.unknown;
  return <span className={`bib-access bib-access--${access}`}>{meta.short}</span>;
}

function BibRow({
  paper,
  slug,
  onNav,
}: {
  paper: AnalyzedPaper;
  slug: string;
  onNav: (path: string) => void;
}) {
  const verdict = BIB_VERDICT_META[paper.verdict];
  const url = bibliographySourceUrl(paper);
  const prob = changeProbabilityPercent(paper.changeProbability);

  return (
    <li className={`bib-row bib-row--${paper.verdict}`}>
      <div className="bib-row__rail" aria-hidden="true" />
      <div className="bib-row__main">
        <div className="bib-row__top">
          <BibAccessFlag access={paper.access} />
          {paper.category ? <span className="bib-row__cat">{paper.category}</span> : null}
          <span className={`bib-verdict bib-verdict--${paper.verdict}`}>
            <span className="bib-verdict__dot" aria-hidden="true" />
            {verdict.short}
          </span>
        </div>
        <h3 className="bib-row__title">{paper.title}</h3>
        <div className="bib-row__cite">
          {paper.authors}
          <span className="bib-row__sep">·</span>
          <em>{paper.journal}</em>
          <span className="bib-row__sep">·</span>
          {paper.year}
        </div>
        <div className="bib-reason">
          <span className="bib-reason__lbl">AI verdict</span>
          <p>{paper.reason}</p>
        </div>
        <div className="bib-row__foot">
          <span className="bib-row__ref">
            {url != null ? (
              <a href={url} target="_blank" rel="noopener noreferrer">
                {bibliographyRefLabel(paper)}
              </a>
            ) : (
              <span className="bib-row__noref">{bibliographyRefLabel(paper)}</span>
            )}
          </span>
          {prob != null ? (
            <span className="bib-prob" title="Estimated chance this paper would change the guideline">
              <span className="bib-prob__bar">
                <i style={{ width: `${prob}%` }} />
              </span>
              <b>{prob}%</b> change likelihood
            </span>
          ) : null}
          {paper.suggestionId ? (
            <button
              type="button"
              className="bib-row__link"
              onClick={() =>
                onNav(`/diseases/${slug}/guidelines/pr/${paper.suggestionId}`)
              }
            >
              Became a suggestion →
            </button>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function BibliographyView({ slug, role, onNav }: BibliographyViewProps) {
  const { disease, loading: diseaseLoading } = useDisease(slug);
  const { papers, loading, error } = useBibliography(slug);
  const [filter, setFilter] = useState<AnalyzedPaperVerdict | "all">("all");

  const counts = useMemo(() => bibliographyCounts(papers), [papers]);
  const groups = useMemo(
    () => groupBibliographyByVerdict(papers, filter),
    [papers, filter],
  );
  const usedCount = (counts.shelf ?? 0) + (counts.suggestion ?? 0);

  if (!isClinicianView(role)) {
    return (
      <div className="page">
        <div className="gx-empty">
          <div>
            <b>Clinician sign-in required.</b>
            <p>
              The analyzed bibliography is an audit view for clinicians and researchers.
            </p>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => onNav(`/diseases/${slug}/guidelines`)}
            >
              ← Back to guidelines
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (diseaseLoading) {
    return <p className="page__loading">Loading…</p>;
  }

  if (disease == null) {
    return (
      <div className="page">
        <div className="gx-empty">
          <div>
            <b>Disease not found.</b>
          </div>
        </div>
      </div>
    );
  }

  return (
    <section className="page page--bib">
      <header className="gx-bar">
        <div className="gx-bar__left">
          <button
            type="button"
            className="btn btn--ghost btn--sm gx-bar__back"
            onClick={() => onNav(`/diseases/${slug}/guidelines`)}
          >
            ← Back to synthesis
          </button>
          <div>
            <span className="gx-bar__ver">analyzed corpus</span>
            <h1 className="gx-bar__title">AI-analyzed bibliography</h1>
            <p className="gx-bar__src">
              {disease.name} — every paper the engine read and scored on the latest run,
              including what it <b>rejected</b> and why.
            </p>
          </div>
        </div>
        <RolePill role={role} />
      </header>

      <div className="bib-frame">
        <div>
          <b>This is an audit log of what the engine read — not a recommendation list.</b>
          <p>
            The value is in the negative paths: you can see <b>why</b> a paper did{" "}
            <b>not</b> land on the source shelf or become a suggestion. Nothing here is
            for patient management.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="page__loading">Loading analyzed corpus…</p>
      ) : error != null ? (
        <div className="gx-empty">
          <div>
            <b>Could not load bibliography.</b>
            <p>{error}</p>
          </div>
        </div>
      ) : papers.length === 0 ? (
        <div className="gx-empty">
          <div>
            <b>No analyzed run yet for this disease.</b>
            <p>
              Run the source-shelf builder and literature monitor first; the verdict
              ledger appears here after a pipeline run.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="bib-funnel">
            <div className="bib-funnel__step">
              <span className="bib-funnel__n">{papers.length}</span>
              <span className="bib-funnel__l">scored</span>
              <span className="bib-funnel__d">shelf + monitor runs</span>
            </div>
            <div className="bib-funnel__step bib-funnel__step--out">
              <span className="bib-funnel__n">{usedCount}</span>
              <span className="bib-funnel__l">used</span>
              <span className="bib-funnel__d">on shelf or as a suggestion</span>
            </div>
          </div>

          <div className="bib-filters" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={filter === "all"}
              className={`bib-chip${filter === "all" ? " is-on" : ""}`}
              onClick={() => setFilter("all")}
            >
              All <b>{counts.all}</b>
            </button>
            {BIB_VERDICT_ORDER.map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={filter === v}
                className={`bib-chip bib-chip--${v}${filter === v ? " is-on" : ""}`}
                onClick={() => setFilter(v)}
              >
                {BIB_VERDICT_META[v].label} <b>{counts[v] ?? 0}</b>
              </button>
            ))}
          </div>

          {groups.map((g) => (
            <section key={g.verdict} className="bib-group">
              <header className={`bib-group__head bib-group__head--${g.verdict}`}>
                <span className="bib-group__dot" aria-hidden="true" />
                <h2 className="bib-group__title">{BIB_VERDICT_META[g.verdict].label}</h2>
                <span className="bib-group__count">{g.items.length}</span>
                <span className="bib-group__hint">{BIB_VERDICT_META[g.verdict].hint}</span>
              </header>
              <ul className="bib-list">
                {g.items.map((paper) => (
                  <BibRow key={`${paper.step}-${paper.ref}`} paper={paper} slug={slug} onNav={onNav} />
                ))}
              </ul>
            </section>
          ))}

          <p className="bib-foot">
            Refreshed on each shelf-build and literature-monitor run. Verdicts may change
            when new evidence appears or triage is tuned.
          </p>
        </>
      )}
    </section>
  );
}
