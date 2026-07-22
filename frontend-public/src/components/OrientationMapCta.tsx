import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import "../styles/my-case.css";

export interface OrientationMapCtaProps {
  disease: Disease;
  onNav: (path: string) => void;
}

/**
 * "Start here" entry from the disease data-hub to the parent orientation map
 * (/diseases/{slug}/map). Shown to non-clinicians near the top of the page —
 * the map's value is orientation *before* you know what to look for, so it leads.
 */
export function OrientationMapCta({ disease, onNav }: OrientationMapCtaProps) {
  const { t } = useTranslation("disease");
  const path = `/diseases/${disease.slug}/map`;

  return (
    <a
      href={path}
      className="orientation-cta"
      onClick={(e) => {
        e.preventDefault();
        onNav(path);
      }}
    >
      <span className="orientation-cta__icon" aria-hidden>
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21 3 6" />
          <line x1="9" y1="3" x2="9" y2="18" />
          <line x1="15" y1="6" x2="15" y2="21" />
        </svg>
      </span>
      <div className="orientation-cta__body">
        <div className="orientation-cta__title">{t("orientationCtaTitle")}</div>
        <div className="orientation-cta__sub">
          {t("orientationCtaSub", { disease: disease.nameShort })}
        </div>
      </div>
      <span className="orientation-cta__arrow" aria-hidden>
        →
      </span>
    </a>
  );
}
