import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AnalyzedPaper, AnalyzedPaperVerdict } from "../types/analyzedPaper";
import type { ViewRole } from "../auth/resolveRole";
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
  const { t } = useTranslation("common");
  // OA/paywall detection is deferred (v1): show a chip only when access is known,
  // rather than tagging nearly every row with a meaningless "Unknown".
  if (access === "unknown") {
    return null;
  }
  const meta = BIB_ACCESS_META[access] ?? BIB_ACCESS_META.unknown;
  return <span className={`bib-access bib-access--${access}`}>{t(meta.short)}</span>;
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
  const { t } = useTranslation("misc");
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
            {t(`common:${verdict.short}`)}
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
          <span className="bib-reason__lbl">{t("bibliography.aiVerdictLabel")}</span>
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
            <span className="bib-prob" title={t("bibliography.changeLikelihoodTooltip")}>
              <span className="bib-prob__bar">
                <i style={{ width: `${prob}%` }} />
              </span>
              <b>{prob}%</b> {t("bibliography.changeLikelihoodSuffix")}
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
              {t("bibliography.becameSuggestion")}
            </button>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function BibliographyView({ slug, role, onNav }: BibliographyViewProps) {
  const { t } = useTranslation("misc");
  const { disease, loading: diseaseLoading } = useDisease(slug);
  const { papers, loading, error } = useBibliography(slug);
  const [filter, setFilter] = useState<AnalyzedPaperVerdict | "all">("all");

  const counts = useMemo(() => bibliographyCounts(papers), [papers]);
  const groups = useMemo(
    () => groupBibliographyByVerdict(papers, filter),
    [papers, filter],
  );
  const usedCount = (counts.shelf ?? 0) + (counts.suggestion ?? 0);

  // Sources are public: the analyzed bibliography is shown to everyone (incl. logged-out) to
  // make the evidence trail transparent and raise credibility. No role gate.

  if (diseaseLoading) {
    return <p className="page__loading">{t("bibliography.loading")}</p>;
  }

  if (disease == null) {
    return (
      <div className="page">
        <div className="gx-empty">
          <div>
            <b>{t("bibliography.diseaseNotFound")}</b>
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
            {t("bibliography.backToSynthesis")}
          </button>
          <div>
            <span className="gx-bar__ver">{t("bibliography.eyebrow")}</span>
            <h1 className="gx-bar__title">{t("bibliography.title")}</h1>
            <p className="gx-bar__src">
              {t("bibliography.sourceIntroLead", { disease: disease.name })}{" "}
              <b>{t("bibliography.sourceIntroBold")}</b> {t("bibliography.sourceIntroTail")}
            </p>
          </div>
        </div>
        <RolePill role={role} />
      </header>

      <div className="bib-frame">
        <div>
          <b>{t("bibliography.auditLogTitle")}</b>
          <p>
            {t("bibliography.negativePathLead")} <b>{t("bibliography.negativePathWhy")}</b>{" "}
            {t("bibliography.negativePathMid")}{" "}
            <b>{t("bibliography.negativePathNot")}</b> {t("bibliography.negativePathTail")}
          </p>
        </div>
      </div>

      {loading ? (
        <p className="page__loading">{t("bibliography.loadingCorpus")}</p>
      ) : error != null ? (
        <div className="gx-empty">
          <div>
            <b>{t("bibliography.loadErrorTitle")}</b>
            <p>{error}</p>
          </div>
        </div>
      ) : papers.length === 0 ? (
        <div className="gx-empty">
          <div>
            <b>{t("bibliography.emptyTitle")}</b>
            <p>{t("bibliography.emptyDesc")}</p>
          </div>
        </div>
      ) : (
        <>
          <div className="bib-funnel">
            <div className="bib-funnel__step">
              <span className="bib-funnel__n">{papers.length}</span>
              <span className="bib-funnel__l">{t("bibliography.funnelScoredLabel")}</span>
              <span className="bib-funnel__d">{t("bibliography.funnelScoredDesc")}</span>
            </div>
            <div className="bib-funnel__step bib-funnel__step--out">
              <span className="bib-funnel__n">{usedCount}</span>
              <span className="bib-funnel__l">{t("bibliography.funnelUsedLabel")}</span>
              <span className="bib-funnel__d">{t("bibliography.funnelUsedDesc")}</span>
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
              {t("bibliography.filterAll")} <b>{counts.all}</b>
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
                {t(`common:${BIB_VERDICT_META[v].label}`)} <b>{counts[v] ?? 0}</b>
              </button>
            ))}
          </div>

          {groups.map((g) => (
            <section key={g.verdict} className="bib-group">
              <header className={`bib-group__head bib-group__head--${g.verdict}`}>
                <span className="bib-group__dot" aria-hidden="true" />
                <h2 className="bib-group__title">
                  {t(`common:${BIB_VERDICT_META[g.verdict].label}`)}
                </h2>
                <span className="bib-group__count">{g.items.length}</span>
                <span className="bib-group__hint">
                  {t(`common:${BIB_VERDICT_META[g.verdict].hint}`)}
                </span>
              </header>
              <ul className="bib-list">
                {g.items.map((paper) => (
                  <BibRow key={`${paper.step}-${paper.ref}`} paper={paper} slug={slug} onNav={onNav} />
                ))}
              </ul>
            </section>
          ))}

          <p className="bib-foot">{t("bibliography.footNote")}</p>
        </>
      )}
    </section>
  );
}
