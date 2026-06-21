import { useState, type FormEvent } from "react";
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
      setError("Email is required — we send a confirmation link before any alerts.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError("Enter a valid email address.");
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
      setError(err instanceof Error ? err.message : "Could not save subscription.");
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
        <button type="button" className="dsub-modal__close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <div className="dsub-modal__head">
          <span className="dsub-modal__icon" aria-hidden>
            🔔
          </span>
          <div>
            <h2 className="dsub-modal__title">Alerts · {disease.nameShort}</h2>
            <p className="dsub-modal__sub">
              Email when something material changes for {disease.name}. No marketing — substantive
              updates only. You must confirm via a link in your inbox before we send anything.
            </p>
          </div>
        </div>
        {saved ? (
          <div className="dsub-modal__success">
            <p>{message}</p>
            {devConfirmUrl != null ? (
              <p className="dsub-modal__dev-link">
                Dev confirmation:{" "}
                <a href={devConfirmUrl} target="_blank" rel="noreferrer">
                  open link
                </a>
              </p>
            ) : null}
            <Button type="button" variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <form className="dsub-modal__form" onSubmit={(e) => void save(e)}>
            <label className="dsub-modal__field">
              <span className="dsub-modal__label">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={submitting}
              />
            </label>
            <fieldset className="dsub-modal__prefs">
              <legend>What to notify you about</legend>
              <label className="dsub-modal__pref">
                <input
                  type="checkbox"
                  checked={prefs.guidelines}
                  onChange={() => togglePref("guidelines")}
                  disabled={submitting}
                />
                <div>
                  <b>Guideline updates</b>
                  <span>When the living guideline layer changes in a meaningful way.</span>
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
                  <b>New recruiting trials nearby</b>
                  <span>Trials recruiting within your chosen radius.</span>
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
                  <b>Therapy status changes</b>
                  <span>When a promising therapy advances (e.g. preclinical → phase 1).</span>
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
                  <b>New specialists nearby</b>
                  <span>When a relevant expert appears within your radius.</span>
                </div>
              </label>
            </fieldset>
            {prefs.trials || prefs.doctors ? (
              <label className="dsub-modal__field">
                <span className="dsub-modal__label">Radius</span>
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
                  <b>{radiusKm} km</b> from your location
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
                  Clear saved email
                </Button>
              ) : null}
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? "Sending…" : "Save — confirm by email"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
