import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import { trackEvent } from "../utils/analytics";
import "../styles/disease-map.css";

const CONTACT_EMAIL = "kontakt@genequest.org";

export interface UnusualCaseContactProps {
  readonly disease: Disease;
}

/**
 * The last block of the parent disease page: a family whose case does not fit the general picture can write to the foundation.
 *
 * A plain e-mail link, not a form: nothing is stored on our side, and the message lands in the foundation's inbox like any other letter. The copy promises only what a person at the foundation can do (point to papers and doctors, help word questions for the family's own doctor) and says what it will not do (diagnose, judge treatment). It asks for no records or identifying details, because a description of a child's illness is health data. The click is counted (no content, only the disease slug), since the parent test asks whether families want help with their own case.
 */
export function UnusualCaseContact({ disease }: UnusualCaseContactProps) {
  const { t } = useTranslation("disease-map");
  const subject = t("unusualSubject", { name: disease.nameShort || disease.name });
  const href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`;

  return (
    <aside className="dmap-unusual" aria-labelledby="dmap-unusual-title">
      <div className="dmap-unusual__body">
        <h2 id="dmap-unusual-title" className="dmap-unusual__title">
          {t("unusualTitle")}
        </h2>
        <p className="dmap-unusual__lede">{t("unusualBody")}</p>
        <p className="dmap-unusual__note">{t("unusualNote", { email: CONTACT_EMAIL })}</p>
      </div>
      <a
        className="dmap-btn dmap-btn--accent dmap-unusual__cta"
        href={href}
        onClick={() => trackEvent("contact-unusual-case", { disease: disease.slug })}
      >
        {t("unusualCta")}
        <span className="dmap-btn__arr" aria-hidden>→</span>
      </a>
    </aside>
  );
}
