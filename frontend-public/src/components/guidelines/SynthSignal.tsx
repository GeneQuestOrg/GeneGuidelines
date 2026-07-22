import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SynthSectionSignal } from "../../types/guidelineSynthesis";

/**
 * Asymmetric signal on a synthesis section (draft10 `SynthSignal`, .gx-synthsig):
 * thumbs-up OR "report a problem" with a note — no bare "not useful". The signal
 * is about summary QUALITY (faithful / complete / safe), not the guideline's
 * validity. Vote is local state in GL-3; the write-path lands in W4/SIG-2.
 */
export interface SynthSignalProps {
  signal?: SynthSectionSignal;
  /** doctor-unverified: held until verified. */
  held?: boolean;
}

export function SynthSignal({ signal, held = false }: SynthSignalProps) {
  const { t } = useTranslation("guidelines");
  const seed = signal ?? { up: 0, flags: 0, verified: 0 };
  const [vote, setVote] = useState<"up" | "flag" | null>(null);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  return (
    <div className="gx-synthsig">
      <div className="gx-synthsig__row">
        <span className="gx-synthsig__q">{t("faithfulSafeQuestion")}</span>
        <button
          type="button"
          className={`gx-up ${vote === "up" ? "on" : ""}`}
          disabled={held}
          onClick={() => {
            setVote(vote === "up" ? null : "up");
            setOpen(false);
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M7 10v11M2 10h5v11H2zM7 10l4-7a2 2 0 0 1 3 1.5V8h5a2 2 0 0 1 2 2.3l-1.3 8A2 2 0 0 1 16.7 20H7" />
          </svg>
          {t("usefulThumbButton")}
        </button>
        <button
          type="button"
          className={`gx-flag ${vote === "flag" || open ? "on" : ""}`}
          disabled={held}
          onClick={() => {
            setOpen((o) => !o);
            setVote("flag");
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

      {open && !sent ? (
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
            disabled={note.trim() === ""}
            onClick={() => setSent(true)}
          >
            {t("sendReportButton")}
          </button>
        </div>
      ) : null}

      {sent ? (
        <div className="gx-synthsig__sent">{t("reportSentMessage")}</div>
      ) : null}

      <div className="gx-synthsig__agg">
        <b>{seed.up + (vote === "up" ? 1 : 0)}</b> {t("foundUsefulSuffix")}
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

      {seed.flagNotes?.map((f, i) => (
        <div key={i} className="gx-synthsig__note">
          <b>{f.who}:</b> {f.text}
        </div>
      ))}
    </div>
  );
}
