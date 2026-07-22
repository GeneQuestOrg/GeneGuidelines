/** Modal for a signed-in parent to propose a clinician we are missing (DOC-5).
 *
 * Launched from DoctorsView ("Recommend a doctor we're missing"). Collects
 * name, specialty, institution, city, country, disease (via the existing
 * DiseaseAutocomplete) and a free-text note, POSTs through the doctor
 * repository, and lands on a "Submitted for moderation" state.
 *
 * Auth is the caller's concern: the parent button only mounts this modal when
 * a parent session is active (env-gated on VITE_AUTH0_DOMAIN). The repository
 * call carries the bearer token via the shared API client.
 */

import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import type { DiseaseSuggestion } from "../api/diseaseIndex";
import { repositories } from "../repositories";
import { submitReducer } from "../utils/contributionGating";
import { DiseaseAutocomplete } from "./DiseaseAutocomplete";
import "../styles/add-doctor-modal.css";

export interface AddDoctorModalProps {
  readonly onClose: () => void;
  /** Optional pre-selected disease slug (e.g. when launched from a filtered list). */
  readonly initialDiseaseSlug?: string | null;
}

export function AddDoctorModal({ onClose, initialDiseaseSlug }: AddDoctorModalProps) {
  const { t } = useTranslation("doctors-page");
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [institution, setInstitution] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [note, setNote] = useState("");
  const [diseaseSlug, setDiseaseSlug] = useState<string | null>(
    initialDiseaseSlug ?? null,
  );
  const [diseaseLabel, setDiseaseLabel] = useState<string | null>(null);
  const [state, dispatch] = useReducer(submitReducer, { status: "editing" });
  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  // Close on Escape — matches the missing-disease dialog interaction.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handlePickDisease = useCallback((suggestion: DiseaseSuggestion) => {
    setDiseaseSlug(suggestion.localSlug ?? null);
    setDiseaseLabel(suggestion.canonicalName);
  }, []);

  const trimmedName = name.trim();
  const canSubmit = trimmedName.length > 0 && state.status !== "submitting";

  const handleSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (trimmedName.length === 0) {
        return;
      }
      dispatch({ type: "submit" });
      try {
        const result = await repositories().doctors.submitDoctor({
          name: trimmedName,
          specialty: specialty.trim(),
          institution: institution.trim(),
          city: city.trim(),
          country: country.trim(),
          diseaseSlug: diseaseSlug ?? "",
          note: note.trim(),
        });
        dispatch({ type: "success", possibleDuplicate: result.possibleDuplicate });
      } catch (e: unknown) {
        const message =
          e instanceof ApiRequestError || e instanceof Error
            ? e.message
            : t("addDoctorModal.submitError");
        dispatch({ type: "failure", message });
      }
    },
    [trimmedName, specialty, institution, city, country, diseaseSlug, note, t],
  );

  return (
    <div
      className="add-doc-modal"
      role="dialog"
      aria-modal="true"
      aria-label={t("addDoctorModal.dialogAriaLabel")}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="add-doc-modal__sheet">
        <button
          type="button"
          className="add-doc-modal__close"
          onClick={onClose}
          aria-label={t("addDoctorModal.closeAriaLabel")}
        >
          ×
        </button>

        {state.status === "submitted" ? (
          <SubmittedPanel
            possibleDuplicate={state.possibleDuplicate}
            onClose={onClose}
          />
        ) : (
          <>
            <div className="add-doc-modal__head">
              <h2 className="add-doc-modal__title">{t("addDoctorModal.title")}</h2>
              <p className="add-doc-modal__sub">{t("addDoctorModal.sub")}</p>
            </div>

            <form className="add-doc-form" onSubmit={handleSubmit}>
              <label className="add-doc-form__field">
                <span className="add-doc-form__label">{t("addDoctorModal.nameLabel")}</span>
                <input
                  ref={firstFieldRef}
                  className="add-doc-form__input"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>

              <div className="add-doc-form__row">
                <label className="add-doc-form__field">
                  <span className="add-doc-form__label">{t("addDoctorModal.specialtyLabel")}</span>
                  <input
                    className="add-doc-form__input"
                    type="text"
                    value={specialty}
                    onChange={(e) => setSpecialty(e.target.value)}
                  />
                </label>
                <label className="add-doc-form__field">
                  <span className="add-doc-form__label">{t("addDoctorModal.institutionLabel")}</span>
                  <input
                    className="add-doc-form__input"
                    type="text"
                    value={institution}
                    onChange={(e) => setInstitution(e.target.value)}
                  />
                </label>
              </div>

              <div className="add-doc-form__row">
                <label className="add-doc-form__field">
                  <span className="add-doc-form__label">{t("addDoctorModal.cityLabel")}</span>
                  <input
                    className="add-doc-form__input"
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                  />
                </label>
                <label className="add-doc-form__field">
                  <span className="add-doc-form__label">{t("addDoctorModal.countryLabel")}</span>
                  <input
                    className="add-doc-form__input"
                    type="text"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    placeholder={t("addDoctorModal.countryPlaceholder")}
                  />
                </label>
              </div>

              <div className="add-doc-form__field">
                <span className="add-doc-form__label">{t("addDoctorModal.diseaseLabel")}</span>
                {diseaseLabel != null ? (
                  <div className="add-doc-form__picked">
                    <span>{diseaseLabel}</span>
                    <button
                      type="button"
                      className="add-doc-form__picked-x"
                      onClick={() => {
                        setDiseaseSlug(null);
                        setDiseaseLabel(null);
                      }}
                      aria-label={t("addDoctorModal.clearDiseaseAriaLabel")}
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <DiseaseAutocomplete
                    placeholder={t("addDoctorModal.diseasePlaceholder")}
                    onPick={handlePickDisease}
                    onMissingClick={() => undefined}
                  />
                )}
              </div>

              <label className="add-doc-form__field">
                <span className="add-doc-form__label">{t("addDoctorModal.noteLabel")}</span>
                <textarea
                  className="add-doc-form__textarea"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  placeholder={t("addDoctorModal.notePlaceholder")}
                />
              </label>

              {state.status === "error" ? (
                <p className="add-doc-form__error" role="alert">
                  {state.message}
                </p>
              ) : null}

              <div className="add-doc-form__actions">
                <Button type="button" variant="ghost" onClick={onClose}>
                  {t("addDoctorModal.cancel")}
                </Button>
                <Button type="submit" disabled={!canSubmit}>
                  {state.status === "submitting"
                    ? t("addDoctorModal.submitting")
                    : t("addDoctorModal.submit")}
                </Button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

function SubmittedPanel({
  possibleDuplicate,
  onClose,
}: {
  possibleDuplicate: boolean;
  onClose: () => void;
}): ReactNode {
  const { t } = useTranslation("doctors-page");
  return (
    <div className="add-doc-modal__done">
      <h2 className="add-doc-modal__title">{t("addDoctorModal.submittedTitle")}</h2>
      <p className="add-doc-modal__sub">{t("addDoctorModal.submittedBody")}</p>
      {possibleDuplicate ? (
        <p className="add-doc-modal__hint">{t("addDoctorModal.duplicateHint")}</p>
      ) : null}
      <div className="add-doc-form__actions">
        <Button type="button" onClick={onClose}>
          {t("addDoctorModal.done")}
        </Button>
      </div>
    </div>
  );
}
