import type { HomeCopy } from "../copy";
import "../styles/home.css";

export interface NewDiseaseCardProps {
  copy: HomeCopy;
  onNav: (path: string) => void;
}

/**
 * Emphasised "run research for any disease" tile (draft13 v2). This is the
 * primary call in the disease rail — a filled accent card, not a faint dashed
 * placeholder. Lives inside the `.d-grid`, styled by `.d-card--new` in home.css.
 */
export function NewDiseaseCard({ copy, onNav }: NewDiseaseCardProps) {
  return (
    <a
      href="/start-research"
      className="d-card d-card--new"
      onClick={(e) => {
        e.preventDefault();
        onNav("/start-research");
      }}
    >
      <span className="d-card__neweyebrow">
        <span aria-hidden>◆</span> {copy.newDiseaseEyebrow}
      </span>
      <div className="d-card__newic" aria-hidden>
        +
      </div>
      <h3 className="d-card__newt">{copy.newDiseaseTitle}</h3>
      <p className="d-card__news">{copy.newDiseaseSub}</p>
      <span className="d-card__newcta">
        {copy.newDiseaseCta} <span className="arw" aria-hidden>→</span>
      </span>
    </a>
  );
}
