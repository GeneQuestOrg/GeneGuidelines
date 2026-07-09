import { CITATIONS } from "../../data";
import type { Citation } from "../../types/guidelineDocument";
import type { GuidelinePrDetail } from "../../types/contentPr";
import { citationDisplayIndex } from "../../utils/guidelineReader";
import { pubmedArticleUrl } from "../../utils/pubmedUrl";
import { CitationParaphrase, GuidelineCitationItem } from "./GuidelineCitationItem";

export interface GuidelineCitationRailProps {
  orderedPmids: readonly string[];
  railPmids: readonly string[];
  activeParaId: string | null;
  diffMode: boolean;
  pr: GuidelinePrDetail | null;
  /**
   * Feature 4: grounded paraphrases keyed by PMID for the active paragraph
   * (our own words, "supported" claims only). A PMID with no entry falls back
   * to the plain PubMed link, so this is fully additive.
   */
  paraphrasesByPmid?: Readonly<Record<string, string>>;
}

function lookupCitation(pmid: string): Citation | null {
  return CITATIONS[pmid] ?? null;
}

interface RailItem {
  pmid: string;
  citation: Citation | null;
  index: number;
}

interface CitationStubProps {
  pmid: string;
  index: number;
  highlight?: boolean;
  paraphrase?: string;
}

function CitationStub({ pmid, index, highlight = false, paraphrase }: CitationStubProps) {
  const url = pubmedArticleUrl(pmid);
  const showParaphrase = paraphrase !== undefined && paraphrase.trim() !== "";
  return (
    <li className={["gl__cit", highlight ? "gl__cit--hl" : ""].filter(Boolean).join(" ")}>
      <span className="gl__cit-num">{index}</span>
      <div className="gl__cit-body">
        <div className="gl__cit-title">
          <a href={url} target="_blank" rel="noopener noreferrer">
            View on PubMed
          </a>
        </div>
        {showParaphrase ? <CitationParaphrase text={paraphrase} url={url} /> : null}
        <div className="gl__cit-tags">
          <code className="gl__cit-pmid">PMID {pmid}</code>
        </div>
      </div>
    </li>
  );
}

export function GuidelineCitationRail({
  orderedPmids,
  railPmids,
  activeParaId,
  diffMode,
  pr,
  paraphrasesByPmid,
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

  const items: RailItem[] = (diffMode ? prPmids : railPmids).map((pmid) => {
    const citation = lookupCitation(pmid);
    const index = citationDisplayIndex(orderedPmids, pmid);
    return { pmid, citation, index: index ?? 0 };
  });

  const contextItems: RailItem[] = contextPmids.map((pmid) => {
    const citation = lookupCitation(pmid);
    const index = citationDisplayIndex(orderedPmids, pmid);
    return { pmid, citation, index: index ?? 0 };
  });

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
              <p className="gl__cits-empty">No indexed citations for this proposed update.</p>
            ) : (
              <ol className="gl__cits">
                {items.map(({ pmid, citation }, i) =>
                  citation != null ? (
                    <GuidelineCitationItem
                      key={pmid}
                      citation={citation}
                      index={i + 1}
                      highlight
                    />
                  ) : (
                    <CitationStub key={pmid} pmid={pmid} index={i + 1} />
                  ),
                )}
              </ol>
            )}
            {contextItems.length > 0 ? (
              <>
                <hr />
                <p className="gl__rail-context-label">Context citations</p>
                <ol className="gl__cits gl__cits--dim">
                  {contextItems.map(({ pmid, citation }, i) =>
                    citation != null ? (
                      <GuidelineCitationItem
                        key={pmid}
                        citation={citation}
                        index={i + 1}
                      />
                    ) : (
                      <CitationStub key={pmid} pmid={pmid} index={i + 1} />
                    ),
                  )}
                </ol>
              </>
            ) : null}
          </div>
        ) : items.length === 0 ? (
          <p className="gl__cits-empty">No citations found for this block.</p>
        ) : (
          <ol className="gl__cits">
            {items.slice(0, 12).map(({ pmid, citation, index }) =>
              citation != null ? (
                <GuidelineCitationItem
                  key={pmid}
                  citation={citation}
                  index={index}
                  highlight={activeParaId != null}
                  paraphrase={paraphrasesByPmid?.[pmid]}
                />
              ) : (
                <CitationStub
                  key={pmid}
                  pmid={pmid}
                  index={index}
                  highlight={activeParaId != null}
                  paraphrase={paraphrasesByPmid?.[pmid]}
                />
              ),
            )}
          </ol>
        )}
      </div>
    </aside>
  );
}
