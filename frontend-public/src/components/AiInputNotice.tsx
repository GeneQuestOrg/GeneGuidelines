import { useTranslation } from "react-i18next";
import { privacyPolicyHref } from "../content/privacyPolicy.mjs";
import "./ai-input-notice.css";

export interface AiInputNoticeProps {
  /** The helper-text class of the field it sits under, so it reads as part of that field. */
  readonly className: string;
}

/**
 * One quiet line under a field whose text is sent to an AI model: no personal data, no description of a specific person's health. The privacy policy promises we neither ask for nor keep health data; a family typing a child's history "by the way" is the case it has to hold for.
 *
 * The policy opens in a new tab so what the visitor already typed stays where it was.
 */
export function AiInputNotice({ className }: AiInputNoticeProps) {
  const { t, i18n } = useTranslation("common");
  const locale = (i18n.resolvedLanguage ?? i18n.language) === "pl" ? "pl" : "en";
  return (
    <span className={`${className} ai-input-notice`}>
      {t("aiInputNotice.text")}{" "}
      <a href={privacyPolicyHref(locale)} target="_blank" rel="noopener">
        {t("aiInputNotice.link")}
      </a>
    </span>
  );
}
