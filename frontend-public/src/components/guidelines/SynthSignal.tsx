import { useState } from "react";
import { useTranslation } from "react-i18next";
import { submitFeedback } from "../../api/feedback";
import type { SynthSectionSignal } from "../../types/guidelineSynthesis";

/**
 * Asymmetric signal on a synthesis section (draft10 `SynthSignal`, .gx-synthsig):
 * thumbs-up OR "report a problem" with a note — no bare "not useful". The signal
 * is about summary QUALITY (faithful / complete / safe), not the guideline's
 * validity.
 *
 * Both actions post to the real feedback channel (`POST /api/feedback`, which
 * emails the founder). They used to be pure local state: the thumb bumped a
 * counter that reset on reload, and "report a problem" showed "report sent" while
 * sending nothing anywhere. A clinician reporting a wrong clinical claim and
 * being told it was delivered is the worst bug this product can have, so the
 * cheap real channel wins over the unbuilt per-section table.
 *
 * The aggregate row shows server-side counts only — never the caller's own click,
 * which is not stored per section.
 */
export interface SynthSignalProps {
  signal?: SynthSectionSignal;
  /** doctor-unverified: held until verified. */
  held?: boolean;
  /** Disease slug + section title, so the email says which claim is disputed. */
  diseaseSlug: string;
  sectionTitle: string;
}

type SendState = "idle" | "sending" | "sent" | "failed";

export function SynthSignal({
  signal,
  held = false,
  diseaseSlug,
  sectionTitle,
}: SynthSignalProps) {
  const { t } = useTranslation("guidelines");
  const seed = signal ?? { up: 0, flags: 0, verified: 0 };
  const [vote, setVote] = useState<"up" | "flag" | null>(null);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [state, setState] = useState<SendState>("idle");

  const context = `${diseaseSlug} · ${sectionTitle}`;

  const send = (message: string) => {
    setState("sending");
    void submitFeedback({ message, context })
      .then(() => setState("sent"))
      .catch(() => setState("failed"));
  };

  const thumbUp = () => {
    if (vote === "up") return; // no un-send: it already left as an email
    setVote("up");
    setOpen(false);
    send(
      `Clinician signal (thumbs up): the "${sectionTitle}" section of the ` +
        `${diseaseSlug} synthesis reads as faithful, complete and safe.`,
    );
  };

  const hasAggregate = seed.up > 0 || seed.verified > 0 || seed.flags > 0;

  return (
    <div className="gx-synthsig">
      <div className="gx-synthsig__row">
        <span className="gx-synthsig__q">{t("faithfulSafeQuestion")}</span>
        <button
          type="button"
          className={`gx-up ${vote === "up" ? "on" : ""}`}
          disabled={held || state === "sending"}
          onClick={thumbUp}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M7 10v11M2 10h5v11H2zM7 10l4-7a2 2 0 0 1 3 1.5V8h5a2 2 0 0 1 2 2.3l-1.3 8A2 2 0 0 1 16.7 20H7" />
          </svg>
          {t("usefulThumbButton")}
        </button>
        <button
          type="button"
          className={`gx-flag ${vote === "flag" || open ? "on" : ""}`}
          disabled={held || state === "sending"}
          onClick={() => {
            setOpen((o) => !o);
            setVote("flag");
            setState("idle");
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
            <line x1="4" y1="22" x2="4" y2="15" />
          </svg>
          {t("reportProblemButton")}
        </button>
        {held ? <span className="gx-held">{t("heldUnverified")}</span> : null}
      </div>

      {open && state !== "sent" ? (
        <div className="gx-synthsig__flag">
          <textarea
            className="gx-cmt__box"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("flagNotePlaceholder")}
          />
          <button
            type="button"
            className="btn btn--sm btn--primary"
            // The channel needs 20 characters to accept a note; asking for a
            // sentence is also what makes a report actionable.
            disabled={note.trim().length < 20 || state === "sending"}
            onClick={() => send(`Section report — ${context}\n\n${note.trim()}`)}
          >
            {state === "sending" ? t("signalSending") : t("sendReportButton")}
          </button>
        </div>
      ) : null}

      {state === "sent" ? (
        <div className="gx-synthsig__sent">{t("reportSentMessage")}</div>
      ) : null}
      {state === "failed" ? (
        <div className="gx-synthsig__sent">{t("signalSendFailed")}</div>
      ) : null}

      {hasAggregate ? (
        <div className="gx-synthsig__agg">
          <b>{seed.up}</b> {t("foundUsefulSuffix")}
          {seed.verified > 0 ? (
            <span className="gx-agg__ver">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5z" />
                <path d="M9 12l2 2 4-4" />
              </svg>
              {t("verifiedCount", { count: seed.verified })}
            </span>
          ) : null}
          {seed.flags > 0 ? (
            <span className="gx-synthsig__flagcount">
              {t(seed.flags === 1 ? "openReportSingular" : "openReportPlural", {
                count: seed.flags,
              })}
            </span>
          ) : null}
        </div>
      ) : null}

      {seed.flagNotes?.map((f, i) => (
        <div key={i} className="gx-synthsig__note">
          <b>{f.who}:</b> {f.text}
        </div>
      ))}
    </div>
  );
}
