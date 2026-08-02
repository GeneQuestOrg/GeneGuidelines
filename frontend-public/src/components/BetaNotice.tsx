import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FeedbackModal } from "./FeedbackModal";
import { getSupportUrl } from "../config/supportUrl";
import "./beta-notice.css";

/** The "Public beta" pill, made explainable.
 *
 * People land on a medical page and see a beta badge with no way to ask what that
 * means for them. Clicking it says what is still unfinished, and offers the two
 * things that actually help right now: telling us what is wrong, and paying for the
 * compute a disease costs.
 *
 * Deliberately a click-to-open popover rather than a banner: a parent reading about
 * their child's condition should not be asked for money by a page they did not ask
 * a question of.
 */
export function BetaNotice() {
  const { t, i18n } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="beta-notice" ref={wrapRef}>
      <button
        type="button"
        className="hdr__beta beta-notice__pill"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={t("betaNotice.pillTitle")}
      >
        {t("betaBadge")}
      </button>

      {open ? (
        <div className="beta-notice__pop" role="dialog" aria-label={t("betaNotice.title")}>
          <p className="beta-notice__title">{t("betaNotice.title")}</p>
          <p className="beta-notice__body">{t("betaNotice.body")}</p>
          <div className="beta-notice__actions">
            <button
              type="button"
              className="beta-notice__btn beta-notice__btn--primary"
              onClick={() => {
                setOpen(false);
                setShowFeedback(true);
              }}
            >
              {t("betaNotice.feedbackCta")}
            </button>
            <a
              className="beta-notice__btn"
              href={getSupportUrl(i18n.language)}
              target="_blank"
              rel="noopener"
              onClick={() => setOpen(false)}
            >
              {t("betaNotice.supportCta")}
            </a>
          </div>
          <p className="beta-notice__note">{t("betaNotice.supportNote")}</p>
        </div>
      ) : null}

      {showFeedback ? <FeedbackModal onClose={() => setShowFeedback(false)} /> : null}
    </div>
  );
}
