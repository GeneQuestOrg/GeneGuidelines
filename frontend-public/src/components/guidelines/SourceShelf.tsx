import { useTranslation } from "react-i18next";
import type { SourceDoc } from "../../types/sourceDoc";
import { SourceDocCard } from "./SourceDocCard";
import "./source-shelf.css";

export interface SourceShelfProps {
  docs: readonly SourceDoc[];
  /** Parent projection: secondary framing ("what this summary is based on"). */
  parent?: boolean;
  /** No summary was built from these documents (the parent gate's level (c)): the heading and lead must not speak of one. */
  unsummarised?: boolean;
  /** Anchor id, for links that open the page at the shelf. */
  id?: string;
}

export function SourceShelf({ docs, parent = false, unsummarised = false, id }: SourceShelfProps) {
  const { t } = useTranslation("guidelines");
  if (docs.length === 0) {
    return null;
  }
  const title = unsummarised
    ? t("sourceShelfTitleUnsummarised")
    : parent
      ? t("sourceShelfTitleParent")
      : t("sourceShelfTitleDefault");
  const lead = unsummarised
    ? t("sourceShelfLeadUnsummarised")
    : parent
      ? t("sourceShelfLeadParent")
      : t("sourceShelfLeadDefault");
  return (
    <section className="srcshelf" id={id}>
      <div className="srcshelf__head">
        <div className="srcshelf__tag">{t("sourceDocsTag", { count: docs.length })}</div>
        <h3 className="srcshelf__title">{title}</h3>
      </div>
      <p className="srcshelf__lead">{lead}</p>
      <div className="srcshelf__grid">
        {docs.map((doc) => (
          <SourceDocCard key={doc.id} doc={doc} parent={parent} />
        ))}
      </div>
    </section>
  );
}
