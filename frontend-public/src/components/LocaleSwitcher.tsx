import { useTranslation } from "react-i18next";
import { LOCALES, type Locale } from "../router/locale";
import "./locale-switcher.css";

export interface LocaleSwitcherProps {
  locale: Locale;
  onChange: (locale: Locale) => void;
}

const LABELS: Record<Locale, string> = {
  en: "EN",
  pl: "PL",
};

/**
 * EN ⇄ PL language toggle. The active locale is driven by the URL (``/pl/`` prefix);
 * clicking a segment re-prefixes the current route via the router's `setLocale`.
 */
export function LocaleSwitcher({ locale, onChange }: LocaleSwitcherProps) {
  const { t } = useTranslation("common");
  return (
    <div className="locale-switcher" role="group" aria-label={t("localeSwitcher.label")}>
      {LOCALES.map((code) => {
        const active = code === locale;
        return (
          <button
            key={code}
            type="button"
            className={active ? "locale-switcher__btn is-active" : "locale-switcher__btn"}
            aria-pressed={active}
            aria-label={code === "pl" ? t("localeSwitcher.polish") : t("localeSwitcher.english")}
            onClick={() => {
              if (!active) {
                onChange(code);
              }
            }}
          >
            {LABELS[code]}
          </button>
        );
      })}
    </div>
  );
}
