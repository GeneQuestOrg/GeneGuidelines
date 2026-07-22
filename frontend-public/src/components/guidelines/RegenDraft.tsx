import { useTranslation } from "react-i18next";
import type { RegenSeed } from "../../types/guidelineSuggestion";

/**
 * Regenerated-draft banner (draft10 `RegenDraft`, .gx-draft). Produced only
 * when a clinician explicitly regenerates with their note — a new, explicitly
 * versioned draft, never a silent overwrite.
 */
export interface RegenDraftProps {
  seed: RegenSeed;
  onDiscard: () => void;
}

export function RegenDraft({ seed, onDiscard }: RegenDraftProps) {
  const { t } = useTranslation("guidelines");
  return (
    <div className="gx-draft">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M9 15l2 2 4-4" />
      </svg>
      <div>
        <span className="v">{seed.version}</span> <b>{t("newDraftGenerated")}</b>
        <p>
          {seed.note} {t("basedOnLabel")} <em>{seed.basedOn}</em>.
        </p>
        <div className="gx-draft__actions">
          <button type="button" className="btn btn--sm btn--primary">
            {t("reviewV2Button")}
          </button>
          <button type="button" className="btn btn--sm btn--ghost" onClick={onDiscard}>
            {t("discardDraftButton")}
          </button>
        </div>
      </div>
    </div>
  );
}
