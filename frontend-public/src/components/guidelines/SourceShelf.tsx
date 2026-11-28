import { useTranslation } from "react-i18next";
import type { SourceDoc } from "../../types/sourceDoc";
import { SourceDocCard } from "./SourceDocCard";
import "./source-shelf.css";

export interface SourceShelfProps {
  docs: readonly SourceDoc[];
  /** Parent projection: secondary framing ("what this summary is based on"). */
  parent?: boolean;
  /** Anchor id, for links that open the page at the shelf. */
  id?: string;
}

export function SourceShelf({ docs, parent = false, id }: SourceShelfProps) {
  const { t } = useTranslation("guidelines");
  if (docs.length === 0) {
    return null;
  }
  return (
    <section className="srcshelf" id={id}>
      <div className="srcshelf__head">
        <div className="srcshelf__tag">{t("sourceDocsTag", { count: docs.length })}</div>
        <h3 className="srcshelf__title">
          {parent ? t("sourceShelfTitleParent") : t("sourceShelfTitleDefault")}
        </h3>
      </div>
      <p className="srcshelf__lead">
        {parent ? t("sourceShelfLeadParent") : t("sourceShelfLeadDefault")}
      </p>
      <div className="srcshelf__grid">
        {docs.map((doc) => (
          <SourceDocCard key={doc.id} doc={doc} parent={parent} />
        ))}
      </div>
    </section>
  );
}
