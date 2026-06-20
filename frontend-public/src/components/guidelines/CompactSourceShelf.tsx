import type { SourceDoc } from "../../types/sourceDoc";
import { sourceDocUrl } from "../../types/sourceDoc";
import "./compact-source-shelf.css";

export interface CompactSourceShelfProps {
  docs: readonly SourceDoc[];
  /** "See all sources" affordance — links to the reader, which holds the full grid. */
  onSeeAll?: () => void;
}

function firstAuthor(authors: string): string {
  return authors.split(",")[0]?.trim() ?? authors;
}

function idLabel(doc: SourceDoc): string {
  if (doc.pmid) {
    return `PMID ${doc.pmid}`;
  }
  if (doc.bookshelf) {
    return `NCBI ${doc.bookshelf}`;
  }
  return "";
}

/**
 * Compact source shelf — draft12 `srctiles` (styles.css ~4986). Small tiles
 * showing only role + clamped title + `{firstAuthor} · {year}` + id. It OMITS
 * journal and scope (matches draft12 and hides the malformed
 * "· gene · 2015/02/26 00:00" journal/scope on the overview). The full card
 * grid lives on the guideline reader, reachable via "See all sources".
 */
export function CompactSourceShelf({ docs, onSeeAll }: CompactSourceShelfProps) {
  if (docs.length === 0) {
    return null;
  }
  return (
    <div className="srctiles">
      <div className="srctiles__lbl">
        Sources ({docs.length}) — click to open the original
      </div>
      <div className="srctiles__grid">
        {docs.map((doc) => {
          const id = idLabel(doc);
          return (
            <a
              key={doc.id}
              className="srctile"
              href={sourceDocUrl(doc)}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="srctile__top">
                <span className="srctile__role">{doc.role}</span>
                {doc.isNew ? <span className="gx-new">NEWER</span> : null}
              </span>
              <span className="srctile__title">{doc.title}</span>
              <span className="srctile__foot">
                <span className="srctile__meta">
                  {firstAuthor(doc.authors)} · {doc.year}
                </span>
                {id ? <span className="srctile__id">{id} ↗</span> : null}
              </span>
            </a>
          );
        })}
      </div>
      {onSeeAll != null ? (
        <button type="button" className="srctiles__seeall" onClick={onSeeAll}>
          See all sources →
        </button>
      ) : null}
    </div>
  );
}
