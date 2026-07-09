import type { Citation } from "../../types/guidelineDocument";
import { pubmedArticleUrl } from "../../utils/pubmedUrl";

export interface GuidelineCitationItemProps {
  citation: Citation;
  index: number;
  highlight?: boolean;
  /**
   * Feature 4: a grounded paraphrase (our own words, never verbatim) of the
   * passage in this abstract that backs the active claim. Shown only when the
   * claim was judged "supported"; omit it for the plain PubMed-link fallback.
   */
  paraphrase?: string;
}

export function GuidelineCitationItem({
  citation,
  index,
  highlight = false,
  paraphrase,
}: GuidelineCitationItemProps) {
  const url = pubmedArticleUrl(citation.pmid);
  const showParaphrase = paraphrase !== undefined && paraphrase.trim() !== "";

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
        {showParaphrase ? <CitationParaphrase text={paraphrase} url={url} /> : null}
        <div className="gl__cit-tags">
          <span className="tag">{citation.type}</span>
          {citation.isNew ? <span className="tag tag--warn">new since 2024</span> : null}
          <code className="gl__cit-pmid">PMID {citation.pmid}</code>
        </div>
      </div>
    </li>
  );
}

/**
 * Grounded-paraphrase block shared by the rich citation item and the bare stub.
 * Makes it visually explicit that this is our paraphrase of the abstract, not a
 * verbatim quote, and links straight to the original.
 */
export function CitationParaphrase({ text, url }: { text: string; url: string }) {
  return (
    <div className="gl__cit-para">
      <span className="gl__cit-para-tag">In our words — paraphrased, not a quote</span>
      <p className="gl__cit-para-tx">{text}</p>
      <a
        className="gl__cit-para-link"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        Read the original abstract on PubMed ↗
      </a>
    </div>
  );
}
