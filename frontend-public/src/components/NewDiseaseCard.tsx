import type { HomeCopy } from "../copy";
import "../styles/disease-page.css";

export interface NewDiseaseCardProps {
  copy: HomeCopy;
  onNav: (path: string) => void;
}

export function NewDiseaseCard({ copy, onNav }: NewDiseaseCardProps) {
  return (
    <a
      href="#/start-research"
      className="new-disease-card"
      onClick={(e) => {
        e.preventDefault();
        onNav("/start-research");
      }}
    >
      <h3 className="new-disease-card__title">{copy.newDiseaseTitle}</h3>
      <p className="new-disease-card__sub">{copy.newDiseaseSub}</p>
      <span className="new-disease-card__cta">{copy.newDiseaseCta}</span>
    </a>
  );
}
