import type { SourceDoc } from "../../types/sourceDoc";
import { SourceDocCard } from "./SourceDocCard";
import "./source-shelf.css";

export interface SourceShelfProps {
  docs: readonly SourceDoc[];
  /** Parent projection: secondary framing ("what this summary is based on"). */
  parent?: boolean;
}

export function SourceShelf({ docs, parent = false }: SourceShelfProps) {
  if (docs.length === 0) {
    return null;
  }
  return (
    <section className="srcshelf">
      <div className="srcshelf__head">
        <div className="srcshelf__tag">Source documents · {docs.length}</div>
        <h3 className="srcshelf__title">
          {parent
            ? "What this summary is based on"
            : "Source shelf — there is no single document"}
        </h3>
      </div>
      <p className="srcshelf__lead">
        {parent
          ? "The summary above combines these papers. If you prefer, read straight from the source — each opens its original."
          : "There is rarely a single “guideline.” This is a curated set of real documents; the synthesis summarizes them together, and every claim links to its source."}
      </p>
      <div className="srcshelf__grid">
        {docs.map((doc) => (
          <SourceDocCard key={doc.id} doc={doc} parent={parent} />
        ))}
      </div>
    </section>
  );
}
