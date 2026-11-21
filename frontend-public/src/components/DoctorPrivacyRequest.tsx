import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import { privacyPolicyHref } from "../content/privacyPolicy.mjs";
import {
  submitDoctorRequest,
  type DoctorRequestKind,
  type DoctorRequestRelation,
} from "../api/doctorRequests";

export interface DoctorPrivacyRequestProps {
  readonly slug: string;
}

/**
 * "Is this you? Ask us to correct or remove this entry." The directory is built from publications and public registers, so the people in it never gave us their data; the privacy policy promises them a simple way out, and this is it.
 *
 * The request is emailed to the foundation and nothing is stored. A removal is then applied by listing the profile in backend/doctor_removals.json, which also keeps it out of later directory updates.
 */
export function DoctorPrivacyRequest({ slug }: DoctorPrivacyRequestProps) {
  const { t, i18n } = useTranslation("doctor-profile");
  const locale = (i18n.resolvedLanguage ?? i18n.language) === "pl" ? "pl" : "en";
  const [kind, setKind] = useState<DoctorRequestKind>("removal");
  const [relation, setRelation] = useState<DoctorRequestRelation>("self");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError(t("privacyRequest.errorEmail"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await submitDoctorRequest(slug, {
        kind,
        relation,
        email: email.trim(),
        message: message.trim() || undefined,
      });
      setSent(true);
    } catch {
      setError(t("privacyRequest.errorSend"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <details className="dprofile__privacy">
      <summary>{t("privacyRequest.summary")}</summary>
      {sent ? (
        <p className="dprofile__privacy-done" role="status">
          {t("privacyRequest.done")}
        </p>
      ) : (
        <form className="dprofile__privacy-form" onSubmit={(e) => void submit(e)}>
          <p>{t("privacyRequest.intro")}</p>
          <p className="dprofile__privacy-policy">
            <a href={privacyPolicyHref(locale, "clinicians")} target="_blank" rel="noopener">
              {t("privacyRequest.policyLink")}
            </a>
          </p>
          <fieldset>
            <legend>{t("privacyRequest.kindLegend")}</legend>
            <label>
              <input
                type="radio"
                name="kind"
                checked={kind === "removal"}
                onChange={() => setKind("removal")}
              />{" "}
              {t("privacyRequest.kindRemoval")}
            </label>
            <label>
              <input
                type="radio"
                name="kind"
                checked={kind === "correction"}
                onChange={() => setKind("correction")}
              />{" "}
              {t("privacyRequest.kindCorrection")}
            </label>
          </fieldset>
          <label>
            {t("privacyRequest.relationLabel")}
            <select
              value={relation}
              onChange={(e) => setRelation(e.target.value as DoctorRequestRelation)}
            >
              <option value="self">{t("privacyRequest.relationSelf")}</option>
              <option value="representative">{t("privacyRequest.relationRepresentative")}</option>
            </select>
          </label>
          <label>
            {t("privacyRequest.emailLabel")}
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </label>
          <label>
            {t("privacyRequest.messageLabel")}
            <textarea
              rows={3}
              maxLength={2000}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={submitting}
            />
          </label>
          {error != null ? (
            <p className="dprofile__privacy-error" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="primary" size="sm" disabled={submitting}>
            {submitting ? t("privacyRequest.sending") : t("privacyRequest.send")}
          </Button>
        </form>
      )}
    </details>
  );
}
