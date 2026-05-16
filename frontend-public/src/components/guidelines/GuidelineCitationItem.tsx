import type { Citation } from "../../types/guidelineDocument";
import { pubmedArticleUrl } from "../../utils/pubmedUrl";

export interface GuidelineCitationItemProps {
  citation: Citation;
  index: number;
  highlight?: boolean;
}

export function GuidelineCitationItem({
  citation,
  index,
  highlight = false,
}: GuidelineCitationItemProps) {
  const url = pubmedArticleUrl(citation.pmid);

  return (
    <li
      className={[
        "gl__cit",
        highlight ? "gl__cit--hl" : "",
        citation.isNew ? "gl__cit--new" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="gl__cit-num">{index}</span>
      <div className="gl__cit-body">
        <div className="gl__cit-title">
          <a href={url} target="_blank" rel="noopener noreferrer">
            {citation.title}
          </a>
        </div>
        <div className="gl__cit-meta">
          {citation.authors} · <em>{citation.journal}</em> · {citation.year}
        </div>
        <div className="gl__cit-tags">
          <span className="tag">{citation.type}</span>
          {citation.isNew ? <span className="tag tag--warn">new since 2024</span> : null}
          <code className="gl__cit-pmid">PMID {citation.pmid}</code>
        </div>
      </div>
    </li>
  );
}
