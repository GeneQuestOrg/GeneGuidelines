import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import "../styles/my-case.css";

export interface MyCaseCtaProps {
  disease: Disease;
  onNav: (path: string) => void;
}

export function MyCaseCta({ disease, onNav }: MyCaseCtaProps) {
  const { t } = useTranslation("disease");
  const path = `/diseases/${disease.slug}/my-case`;

  return (
    <a
      href={path}
      className="mycase-cta"
      onClick={(e) => {
        e.preventDefault();
        onNav(path);
      }}
    >
      <span className="mycase-cta__icon" aria-hidden>
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
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </span>
      <div className="mycase-cta__body">
        <div className="mycase-cta__title">{t("myCaseCtaTitle")}</div>
        <div className="mycase-cta__sub">
          {t("myCaseCtaSub", { disease: disease.nameShort })}
        </div>
      </div>
      <span className="mycase-cta__arrow" aria-hidden>
        →
      </span>
    </a>
  );
}
