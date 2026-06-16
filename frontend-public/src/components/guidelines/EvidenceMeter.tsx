import type { EvidenceStrength } from "../../types/guidelineSuggestion";

/** Evidence-strength meter — 3 bars filled by level (draft10 `EvidenceMeter`). */
const EVID_LABEL: Record<EvidenceStrength, string> = {
  strong: "Strong evidence",
  moderate: "Moderate evidence",
  low: "Limited evidence",
};
const EVID_FILL: Record<EvidenceStrength, number> = { strong: 3, moderate: 2, low: 1 };

export function EvidenceMeter({ level }: { level: EvidenceStrength }) {
  const fill = EVID_FILL[level];
  return (
    <div className={`gx-evid gx-evid--${level}`}>
      <span className="gx-evid__bars">
        {[0, 1, 2].map((i) => (
          <i key={i} className={i < fill ? "on" : ""} />
        ))}
      </span>
      <span className="gx-evid__lbl">{EVID_LABEL[level]}</span>
    </div>
  );
}

export { EVID_LABEL };
