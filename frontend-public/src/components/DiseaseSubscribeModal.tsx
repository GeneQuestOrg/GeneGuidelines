import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import {
  subscribeToDiseaseAlerts,
  type AlertPrefsPayload,
} from "../api/subscriptions";
import type { Disease } from "../types";
import {
  clearStoredSubscriptionEmail,
  readStoredSubscriptionEmail,
  writeStoredSubscriptionEmail,
} from "../utils/diseaseSubscriptionStorage";
import "../styles/disease-subscribe-modal.css";

export interface DiseaseSubscribeModalProps {
  disease: Disease;
  onClose: () => void;
  onSaved: () => void;
}

const DEFAULT_PREFS: AlertPrefsPayload = {
  guidelines: true,
  trials: true,
  therapies: false,
  doctors: true,
};

export function DiseaseSubscribeModal({
  disease,
  onClose,
  onSaved,
}: DiseaseSubscribeModalProps) {
  const { t } = useTranslation("common");
  const storedEmail = readStoredSubscriptionEmail(disease.slug);
  const [email, setEmail] = useState(storedEmail ?? "");
  const [prefs, setPrefs] = useState<AlertPrefsPayload>(DEFAULT_PREFS);
  const [radiusKm, setRadiusKm] = useState(500);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [devConfirmUrl, setDevConfirmUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const togglePref = (key: keyof AlertPrefsPayload) => {
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  };

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
        prefs,
        radius_km: radiusKm,
      });
      writeStoredSubscriptionEmail(disease.slug, trimmed);
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

  const unsubscribe = () => {
    clearStoredSubscriptionEmail(disease.slug);
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
            <fieldset className="dsub-modal__prefs">
              <legend>{t("subscribeModal.prefsLegend")}</legend>
              <label className="dsub-modal__pref">
                <input
                  type="checkbox"
                  checked={prefs.guidelines}
                  onChange={() => togglePref("guidelines")}
                  disabled={submitting}
                />
                <div>
                  <b>{t("subscribeModal.prefGuidelinesTitle")}</b>
                  <span>{t("subscribeModal.prefGuidelinesBody")}</span>
                </div>
              </label>
              <label className="dsub-modal__pref">
                <input
                  type="checkbox"
                  checked={prefs.trials}
                  onChange={() => togglePref("trials")}
                  disabled={submitting}
                />
                <div>
                  <b>{t("subscribeModal.prefTrialsTitle")}</b>
                  <span>{t("subscribeModal.prefTrialsBody")}</span>
                </div>
              </label>
              <label className="dsub-modal__pref">
                <input
                  type="checkbox"
                  checked={prefs.therapies}
                  onChange={() => togglePref("therapies")}
                  disabled={submitting}
                />
                <div>
                  <b>{t("subscribeModal.prefTherapiesTitle")}</b>
                  <span>{t("subscribeModal.prefTherapiesBody")}</span>
                </div>
              </label>
              <label className="dsub-modal__pref">
                <input
                  type="checkbox"
                  checked={prefs.doctors}
                  onChange={() => togglePref("doctors")}
                  disabled={submitting}
                />
                <div>
                  <b>{t("subscribeModal.prefDoctorsTitle")}</b>
                  <span>{t("subscribeModal.prefDoctorsBody")}</span>
                </div>
              </label>
            </fieldset>
            {prefs.trials || prefs.doctors ? (
              <label className="dsub-modal__field">
                <span className="dsub-modal__label">{t("subscribeModal.radiusLabel")}</span>
                <input
                  type="range"
                  min={50}
                  max={2000}
                  step={50}
                  value={radiusKm}
                  onChange={(e) => setRadiusKm(Number(e.target.value))}
                  disabled={submitting}
                />
                <span className="dsub-modal__hint">
                  <b>{radiusKm} km</b> {t("subscribeModal.radiusHintSuffix")}
                </span>
              </label>
            ) : null}
            {error != null ? (
              <p className="dsub-modal__error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="dsub-modal__actions">
              {storedEmail != null ? (
                <Button type="button" variant="ghost" onClick={unsubscribe} disabled={submitting}>
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
