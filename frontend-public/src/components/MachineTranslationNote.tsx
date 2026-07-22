import { useTranslation } from "react-i18next";
import { DEFAULT_LOCALE, readLocaleFromLocation } from "../router/locale";
import "./machine-translation-note.css";

/**
 * Discreet honesty note for translated content surfaces.
 *
 * PR1-4 machine-translate the AI-drafted English content (disease summary,
 * guideline synthesis, therapies, foundations) into the active locale. That is
 * a machine translation of AI-authored text, not a human-reviewed one — a
 * non-English reader deserves to know that, without a loud banner and without
 * implying human verification. English is the source of record, so the note
 * is hidden there; it appears only once the reader is on a translated locale
 * (e.g. `/pl/…`).
 */
export function MachineTranslationNote() {
  const { t } = useTranslation("common");

  if (readLocaleFromLocation() === DEFAULT_LOCALE) {
    return null;
  }

  return (
    <p className="mt-note" role="note">
      <svg
        className="mt-note__icon"
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="11" x2="12" y2="16" />
        <circle cx="12" cy="7.5" r="0.5" fill="currentColor" stroke="none" />
      </svg>
      <span>{t("machineTranslation.note")}</span>
    </p>
  );
}
