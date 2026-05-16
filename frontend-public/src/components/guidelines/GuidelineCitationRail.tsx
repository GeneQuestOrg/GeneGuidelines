import { CITATIONS } from "../../data";
import type { Citation } from "../../types/guidelineDocument";
import type { GuidelinePrDetail } from "../../types/contentPr";
import { citationDisplayIndex } from "../../utils/guidelineReader";
import { GuidelineCitationItem } from "./GuidelineCitationItem";

export interface GuidelineCitationRailProps {
  orderedPmids: readonly string[];
  railPmids: readonly string[];
  activeParaId: string | null;
  diffMode: boolean;
  pr: GuidelinePrDetail | null;
}

function lookupCitation(pmid: string): Citation | null {
  return CITATIONS[pmid] ?? null;
}

export function GuidelineCitationRail({
  orderedPmids,
  railPmids,
  activeParaId,
  diffMode,
  pr,
}: GuidelineCitationRailProps) {
  const prPmids = pr?.papers.map((p) => p.pmid) ?? [];

  const label = diffMode
    ? "Evidence for this change"
    : activeParaId != null
      ? "Citations for selected paragraph"
      : "All citations in this document";

  const contextPmids = diffMode
    ? railPmids.filter((pmid) => !prPmids.includes(pmid)).slice(0, 4)
    : [];

  const items = (diffMode ? prPmids : railPmids)
    .map((pmid) => {
      const citation = lookupCitation(pmid);
      if (citation == null) {
        return null;
      }
      const index = citationDisplayIndex(orderedPmids, pmid);
      return { pmid, citation, index: index ?? 0 };
    })
    .filter((row): row is NonNullable<typeof row> => row != null);

  const contextItems = contextPmids
    .map((pmid) => {
      const citation = lookupCitation(pmid);
      if (citation == null) {
        return null;
      }
      const index = citationDisplayIndex(orderedPmids, pmid);
      return { pmid, citation, index: index ?? 0 };
    })
    .filter((row): row is NonNullable<typeof row> => row != null);

  return (
    <aside className="gl__rail" aria-label="Citations">
      <div className="gl__rail-sticky">
        <div className="gl__rail-label">{label}</div>
        {diffMode && pr != null ? (
          <div className="gl__rail-pr">
            <p className="gl__rail-pr-intro">
              AI Watcher proposed this update from {pr.papers.length} recent
              peer-reviewed article{pr.papers.length === 1 ? "" : "s"}.
            </p>
            {items.length === 0 ? (
              <p className="gl__cits-empty">No indexed citations for this PR.</p>
            ) : (
              <ol className="gl__cits">
                {items.map(({ pmid, citation }, i) => (
                  <GuidelineCitationItem
                    key={pmid}
                    citation={citation}
                    index={i + 1}
                    highlight
                  />
                ))}
              </ol>
            )}
            {contextItems.length > 0 ? (
              <>
                <hr />
                <p className="gl__rail-context-label">Context citations</p>
                <ol className="gl__cits gl__cits--dim">
                  {contextItems.map(({ pmid, citation }, i) => (
                    <GuidelineCitationItem
                      key={pmid}
                      citation={citation}
                      index={i + 1}
                    />
                  ))}
                </ol>
              </>
            ) : null}
          </div>
        ) : items.length === 0 ? (
          <p className="gl__cits-empty">No citations — this block is an AI draft.</p>
        ) : (
          <ol className="gl__cits">
            {items.slice(0, 12).map(({ pmid, citation, index }) => (
              <GuidelineCitationItem
                key={pmid}
                citation={citation}
                index={index}
                highlight={activeParaId != null}
              />
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
