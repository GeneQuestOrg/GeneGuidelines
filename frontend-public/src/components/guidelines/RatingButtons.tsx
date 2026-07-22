import { useTranslation } from "react-i18next";

/**
 * 3-state rating control for an AI suggestion (draft10 `RatingButtons`,
 * .gx-rate / .gx-sig). useful / not useful / incorrect. This is a SIGNAL for
 * the next clinician — it does not publish or change anything. In GL-3 the
 * value is local state only; the write-path (weighted ranking) lands in W4/SIG-1.
 *
 * Rendered as a segmented control: three connected buttons sharing one border.
 * "Incorrect" carries no resting color — only the active/pressed state brings
 * a muted amber-red tint, preventing it from reading as a badge/verdict at rest.
 */
export type Rating = "useful" | "not" | "wrong";

export interface RatingButtonsProps {
  value: Rating | null;
  onChange: (value: Rating | null) => void;
  /** doctor-unverified: can rate locally, but the signal is held until verified. */
  held?: boolean;
}

export function RatingButtons({ value, onChange, held = false }: RatingButtonsProps) {
  const { t } = useTranslation("guidelines");
  const pick = (v: Rating) => onChange(value === v ? null : v);
  return (
    <div className="gx-rate" role="group" aria-label={t("rateThisSuggestionAria")}>
      <div className="gx-rate__seg">
        <button
          type="button"
          className="gx-sig gx-sig--useful"
          aria-pressed={value === "useful"}
          aria-label={t("markUsefulAria")}
          onClick={() => pick("useful")}
        >
          {t("ratingUsefulLabel")}
        </button>
        <button
          type="button"
          className="gx-sig gx-sig--not"
          aria-pressed={value === "not"}
          aria-label={t("markNotUsefulAria")}
          onClick={() => pick("not")}
        >
          {t("ratingNotUsefulLabel")}
        </button>
        <button
          type="button"
          className="gx-sig gx-sig--wrong"
          aria-pressed={value === "wrong"}
          aria-label={t("markIncorrectAria")}
          onClick={() => pick("wrong")}
        >
          {t("ratingIncorrectLabel")}
        </button>
      </div>
      {held ? <span className="gx-held">{t("heldUnverified")}</span> : null}
    </div>
  );
}
