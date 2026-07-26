import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import { submitFeedback } from "../api/feedback";
import "../styles/feedback-modal.css";

export interface FeedbackModalProps {
  onClose: () => void;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_MESSAGE_LENGTH = 20;
const MAX_MESSAGE_LENGTH = 4000;

export function FeedbackModal({ onClose }: FeedbackModalProps) {
  const { t } = useTranslation("common");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (trimmedMessage.length < MIN_MESSAGE_LENGTH) {
      setError(t("feedbackModal.errorTooShort"));
      return;
    }
    const trimmedEmail = email.trim();
    if (trimmedEmail !== "" && !EMAIL_RE.test(trimmedEmail)) {
      setError(t("feedbackModal.errorEmailInvalid"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await submitFeedback({
        message: trimmedMessage,
        email: trimmedEmail === "" ? undefined : trimmedEmail,
        context: `${window.location.pathname}${window.location.search}`,
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("feedbackModal.errorSendFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fb-modal" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="fb-modal__sheet" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="fb-modal__close"
          onClick={onClose}
          aria-label={t("feedbackModal.closeAriaLabel")}
        >
          ×
        </button>
        <div className="fb-modal__head">
          <span className="fb-modal__icon" aria-hidden>
            💬
          </span>
          <div>
            <h2 className="fb-modal__title">{t("feedbackModal.title")}</h2>
            <p className="fb-modal__sub">{t("feedbackModal.subtitle")}</p>
          </div>
        </div>
        {sent ? (
          <div className="fb-modal__success">
            <p>{t("feedbackModal.successMessage")}</p>
            <Button type="button" variant="primary" onClick={onClose}>
              {t("feedbackModal.done")}
            </Button>
          </div>
        ) : (
          <form className="fb-modal__form" onSubmit={(e) => void submit(e)}>
            <label className="fb-modal__field">
              <span className="fb-modal__label">{t("feedbackModal.messageLabel")}</span>
              <textarea
                required
                rows={5}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={t("feedbackModal.messagePlaceholder")}
                disabled={submitting}
                maxLength={MAX_MESSAGE_LENGTH}
              />
            </label>
            <label className="fb-modal__field">
              <span className="fb-modal__label">{t("feedbackModal.emailLabel")}</span>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("feedbackModal.emailPlaceholder")}
                disabled={submitting}
              />
            </label>
            {error != null ? (
              <p className="fb-modal__error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="fb-modal__actions">
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? t("feedbackModal.sending") : t("feedbackModal.send")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
