import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import type { Disease } from "../types/disease";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";
import type { GuidelineBaseline } from "../types/guidelineBaseline";
import type { SourceDoc } from "../types/sourceDoc";
import type { ViewRole } from "../auth/resolveRole";
import { SourceShelf } from "../components/guidelines/SourceShelf";
import { SynthDisclaimer } from "../components/guidelines/SynthDisclaimer";

export interface GuidelineParentViewProps {
  disease: Disease;
  synthesis: GuidelineSynthesis | null;
  /** Promoted (gate==="promoted") items surface as "to discuss" frames. */
  suggestions: readonly GuidelineSuggestion[];
  /** Level-(c) baseline — drives the gate's read-state line; never shown raw. */
  baseline: GuidelineBaseline | null;
  hasOfficial: boolean;
  role: ViewRole;
  docs: readonly SourceDoc[];
  signInAvailable: boolean;
  onSignIn: () => void;
  onNav: (path: string) => void;
}

/** Anonymous "are you a clinician?" sign-in nudge (ported from draft10 .gx-signin). */
function AnonSignin({ onSignIn }: { onSignIn: () => void }) {
  const { t } = useTranslation("guidelines");
  return (
    <div className="gx-signin">
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M7 3v6a5 5 0 0 0 10 0V3" />
        <path d="M12 14v3a4 4 0 0 0 4 4 4 4 0 0 0 4-4v-1" />
        <circle cx="20" cy="13" r="2" />
      </svg>
      <div className="gx-signin__b">
        <b>{t("anonSigninTitle")}</b>
        <p>{t("anonSigninBody")}</p>
      </div>
      <Button variant="primary" size="sm" type="button" onClick={onSignIn}>
        {t("signIn")}
      </Button>
    </div>
  );
}

export function GuidelineParentView({
  disease,
  synthesis,
  suggestions,
  baseline,
  hasOfficial,
  role,
  docs,
  signInAvailable,
  onSignIn,
  onNav,
}: GuidelineParentViewProps) {
  const { t } = useTranslation("guidelines");
  const showSignin = role === "anon" && signInAvailable;
  const readState =
    baseline?.readState ?? { read: false, note: t("gateNoReadYet") };

  // Level (c): no agreed guideline — the parent is the bridge to a clinician,
  // never the recipient of a raw AI baseline (wizja 02/04). Safety gate only.
  if (!hasOfficial) {
    return (
      <>
        {showSignin ? <AnonSignin onSignIn={onSignIn} /> : null}
        <div className="gx-gate">
          <div className="gx-gate__icon" aria-hidden="true">
            <svg
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="4" y="10" width="16" height="11" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            </svg>
          </div>
          <h2 className="gx-gate__t">{t("gateTitle")}</h2>
          <p className="gx-gate__p">
            {t("gateBody", { disease: disease.name.toLowerCase() })}
          </p>
          <span className={`gx-gate__read${readState.read ? " read" : ""}`}>
            <span className="d" aria-hidden="true" />
            {readState.read ? t("gateReadReviewed") : readState.note}
          </span>
          <div className="gx-gate__actions">
            <Button
              variant="primary"
              type="button"
              onClick={() => onNav(`/doctors?disease=${disease.slug}`)}
            >
              {t("gateFindSpecialist")}
            </Button>
          </div>
        </div>
      </>
    );
  }

  const doc = synthesis!;
  // Only promoted items reach the parent — as "to discuss with your doctor"
  // frames, never raw AI verdicts (wizja 02, per-item gate).
  const promoted = suggestions.filter((s) => s.gate === "promoted");
  return (
    <>
      {showSignin ? <AnonSignin onSignIn={onSignIn} /> : null}

      <SynthDisclaimer text={doc.synthDisclaimer} />

      <div className="gx-send">
        <span className="gx-send__icon" aria-hidden="true">
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
            <path d="M22 2 11 13" />
            <path d="M22 2 15 22l-4-9-9-4 20-7z" />
          </svg>
        </span>
        <div className="gx-send__b">
          <p className="gx-send__t">{t("sendDoctorTitle")}</p>
          <p className="gx-send__s">{t("sendDoctorBody")}</p>
        </div>
        <div className="gx-send__actions">
          <Button variant="primary" size="sm" type="button" disabled>
            {t("sendDoctorButton")}
          </Button>
          <Button size="sm" type="button" onClick={() => window.print()}>
            {t("printButton")}
          </Button>
        </div>
      </div>

      {/* Medical-safety: the hand-seeded parent layer (whatToDoNow / redFlags)
          is scrapped from the guideline surface — citation-less, never
          fact-checked, and it carried a factually false claim. The backend no
          longer serves those fields; the whole section (heading included) is
          dropped rather than rendered as an empty shell. A derived,
          source-grounded "what to do now" projection may return later. */}

      <article className="gx-doc">
        {doc.sections.map((sec) => (
          <section key={sec.id} className="gx-sec">
            <h2 className="gx-sec__h">
              {sec.title}
              <span className="epi epi--official">
                <span className="epi__d" aria-hidden="true" />
                {t("fromSourcesBadge")}
              </span>
            </h2>
            {sec.intro != null ? <p className="gx-sec__intro">{sec.intro}</p> : null}
            {/* Condensed projection: the first two paragraphs of each section. */}
            {sec.paragraphs.slice(0, 2).map((p) => (
              <div key={p.id} className="gx-para">
                <p>{p.text}</p>
              </div>
            ))}
            {promoted
              .filter((s) => s.targetSection === sec.id)
              .map((s) => (
                <div key={s.id} className="gx-discuss">
                  <span className="gx-discuss__l" aria-hidden="true">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                    {t("discussWithDoctor")}
                  </span>
                  <p>{s.parentText ?? s.summary}</p>
                </div>
              ))}
          </section>
        ))}
      </article>

      <SourceShelf docs={docs} parent />

      <p className="gx-parentfoot">
        {t("parentFooter", { date: doc.lastUpdated.slice(0, 7) })}
      </p>
    </>
  );
}
