import { useTranslation } from "react-i18next";
import type { EvidenceStrength } from "../../types/guidelineSuggestion";

/** Evidence-strength meter — 3 bars filled by level (draft10 `EvidenceMeter`). */
const EVID_LABEL_KEY: Record<EvidenceStrength, string> = {
  strong: "evidenceStrong",
  moderate: "evidenceModerate",
  low: "evidenceLow",
};
const EVID_FILL: Record<EvidenceStrength, number> = { strong: 3, moderate: 2, low: 1 };

export function EvidenceMeter({ level }: { level: EvidenceStrength }) {
  const { t } = useTranslation("guidelines");
  const fill = EVID_FILL[level];
  return (
    <div className={`gx-evid gx-evid--${level}`}>
      <span className="gx-evid__bars">
        {[0, 1, 2].map((i) => (
          <i key={i} className={i < fill ? "on" : ""} />
        ))}
      </span>
      <span className="gx-evid__lbl">{t(EVID_LABEL_KEY[level])}</span>
    </div>
  );
}

export { EVID_LABEL_KEY };
