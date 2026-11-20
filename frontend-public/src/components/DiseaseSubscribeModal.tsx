import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import { SUMMARY_CHANGE_PREFS, subscribeToDiseaseAlerts } from "../api/subscriptions";
import type { Disease } from "../types";
import {
  clearStoredSubscriptionRef,
  ensureSubscriptionRef,
  readStoredSubscriptionRef,
} from "../utils/diseaseSubscriptionStorage";
import "../styles/disease-subscribe-modal.css";

export interface DiseaseSubscribeModalProps {
  disease: Disease;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * "Email me when this summary changes" — the one alert GeneGuidelines actually sends.
 *
 * Until 2026-11-20 this form offered alerts about trials, therapies and nearby doctors within a radius, none of which was ever sent. It now asks only for what it delivers, plus a separate, unticked consent to be contacted about testing the product.
 */
export function DiseaseSubscribeModal({ disease, onClose, onSaved }: DiseaseSubscribeModalProps) {
  const { t } = useTranslation("common");
  const hasStoredRef = readStoredSubscriptionRef(disease.slug) != null;
  const [email, setEmail] = useState("");
  const [community, setCommunity] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [devConfirmUrl, setDevConfirmUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = email.trim();
    if (trimmed === "") {
      setError(t("subscribeModal.errorEmailRequired"));
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError(t("subscribeModal.errorEmailInvalid"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const response = await subscribeToDiseaseAlerts(disease.slug, {
        email: trimmed,
        prefs: SUMMARY_CHANGE_PREFS,
        radius_km: null,
        client_ref: ensureSubscriptionRef(disease.slug),
        community,
      });
      setMessage(response.message);
      setDevConfirmUrl(response.dev_confirm_url ?? null);
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("subscribeModal.errorSaveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const forgetOnThisDevice = () => {
    clearStoredSubscriptionRef(disease.slug);
    onSaved();
    onClose();
  };

  return (
    <div className="dsub-modal" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="dsub-modal__sheet" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="dsub-modal__close"
          onClick={onClose}
          aria-label={t("subscribeModal.closeAriaLabel")}
        >
          ×
        </button>
        <div className="dsub-modal__head">
          <span className="dsub-modal__icon" aria-hidden>
            🔔
          </span>
          <div>
            <h2 className="dsub-modal__title">
              {t("subscribeModal.title", { short: disease.nameShort })}
            </h2>
            <p className="dsub-modal__sub">
              {t("subscribeModal.subtitle", { name: disease.name })}
            </p>
          </div>
        </div>
        {saved ? (
          <div className="dsub-modal__success">
            <p>{message}</p>
            {devConfirmUrl != null ? (
              <p className="dsub-modal__dev-link">
                {t("subscribeModal.devConfirmLabel")}{" "}
                <a href={devConfirmUrl} target="_blank" rel="noreferrer">
                  {t("subscribeModal.devConfirmLink")}
                </a>
              </p>
            ) : null}
            <Button type="button" variant="primary" onClick={onClose}>
              {t("subscribeModal.done")}
            </Button>
          </div>
        ) : (
          <form className="dsub-modal__form" onSubmit={(e) => void save(e)}>
            <label className="dsub-modal__field">
              <span className="dsub-modal__label">{t("subscribeModal.emailLabel")}</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("subscribeModal.emailPlaceholder")}
                disabled={submitting}
              />
            </label>
            <label className="dsub-modal__pref">
              <input
                type="checkbox"
                checked={community}
                onChange={() => setCommunity((value) => !value)}
                disabled={submitting}
              />
              <div>
                <b>{t("subscribeModal.communityTitle")}</b>
                <span>{t("subscribeModal.communityBody")}</span>
              </div>
            </label>
            <p className="dsub-modal__hint">{t("subscribeModal.privacyNote")}</p>
            {error != null ? (
              <p className="dsub-modal__error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="dsub-modal__actions">
              {hasStoredRef ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={forgetOnThisDevice}
                  disabled={submitting}
                >
                  {t("subscribeModal.clearSavedEmail")}
                </Button>
              ) : null}
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? t("subscribeModal.sending") : t("subscribeModal.save")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
