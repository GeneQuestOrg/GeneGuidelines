/** Modal dialog for the "missing disease — wider search" flow.
 *
 * Opens when the autocomplete cannot match the user's text against the
 * local rare-disease index. The user re-types or refines the query, hits
 * "Search the literature", and Gemma 4 (via
 * ``POST /api/disease-index/wider-search``) returns one or more candidate
 * diseases together with a category classification (genetic, infectious,
 * multifactorial, …).
 *
 * Out-of-scope categories (infectious / acquired) are surfaced explicitly
 * — the user sees that the platform recognised the disease but does not
 * cover it. Genetic / predominantly_genetic candidates can be promoted
 * to a research run via ``onPickCandidate``.
 */

import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  type WiderSearchCandidate,
  type WiderSearchResponse,
  widerSearchDisease,
} from "../api/diseaseIndex";
import "../styles/missing-disease-dialog.css";

export interface MissingDiseaseDialogProps {
  readonly initialQuery: string;
  readonly onClose: () => void;
  /**
   * Called when the user accepts an in-scope candidate. The parent should
   * close the modal and pre-fill its own form / launch the research run.
   * Out-of-scope candidates are blocked at the Use button so this never
   * fires for them.
   */
  readonly onPickCandidate: (candidate: WiderSearchCandidate) => void;
}

export function MissingDiseaseDialog({
  initialQuery,
  onClose,
  onPickCandidate,
}: MissingDiseaseDialogProps) {
  const { t } = useTranslation("common");
  const [query, setQuery] = useState(initialQuery);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<WiderSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Auto-focus + select-all so the user can either tweak the query or
  // hit Enter immediately to run the search.
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  // Esc closes the dialog. We also stop propagation on the inner sheet
  // so a click on the inputs does not bubble up to the backdrop.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      const trimmed = query.trim();
      if (trimmed.length < 2) {
        setError(t("missingDiseaseDialog.errorTooShort"));
        return;
      }
      setBusy(true);
      setError(null);
      setResult(null);
      try {
        const response = await widerSearchDisease(trimmed);
        setResult(response);
      } catch (e) {
        if (e instanceof ApiRequestError) {
          setError(e.message);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError(t("missingDiseaseDialog.errorSearchFailed"));
        }
      } finally {
        setBusy(false);
      }
    },
    [query, t],
  );

  return (
    <div
      className="miss-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="miss-modal-title"
      onClick={onClose}
    >
      <div className="miss-modal__sheet" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="miss-modal__close"
          onClick={onClose}
          aria-label={t("missingDiseaseDialog.closeAriaLabel")}
        >
          ×
        </button>

        <div className="miss-modal__head">
          <h2 id="miss-modal-title" className="miss-modal__title">
            {t("missingDiseaseDialog.title")}
          </h2>
          <p className="miss-modal__sub">{t("missingDiseaseDialog.subtitle")}</p>
        </div>

        <form className="miss-modal__form" onSubmit={submit}>
          <label className="miss-modal__field">
            <span className="miss-modal__label">
              {t("missingDiseaseDialog.fieldLabel")}
            </span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("missingDiseaseDialog.fieldPlaceholder")}
              disabled={busy}
              required
            />
            <span className="miss-modal__hint">
              {t("missingDiseaseDialog.fieldHint")}
            </span>
          </label>

          <div className="miss-modal__hints">
            <Hint code="OMIM" label={t("missingDiseaseDialog.hintOmim")} />
            <Hint code="ORPHA" label={t("missingDiseaseDialog.hintOrpha")} />
            <Hint code="GENE" label={t("missingDiseaseDialog.hintGene")} />
            <Hint code="NAME" label={t("missingDiseaseDialog.hintName")} />
          </div>

          <div className="miss-modal__pipeline">
            <span className="miss-modal__pipe-label">
              {t("missingDiseaseDialog.pipelineLabel")}
            </span>
            <ol>
              <li>
                <b>Gemma 4</b> {t("missingDiseaseDialog.pipelineStep1")}
              </li>
              <li>
                <b>{t("missingDiseaseDialog.pipelineStep2Lead")}</b> —{" "}
                {t("missingDiseaseDialog.pipelineStep2")}
              </li>
              <li>
                <b>{t("missingDiseaseDialog.pipelineStep3Lead")}</b> —{" "}
                {t("missingDiseaseDialog.pipelineStep3")}
              </li>
              <li>
                <b>{t("missingDiseaseDialog.pipelineStep4Lead")}</b> —{" "}
                {t("missingDiseaseDialog.pipelineStep4")}
              </li>
            </ol>
          </div>

          {error ? (
            <div className="miss-modal__error" role="alert">
              {error}
            </div>
          ) : null}

          <div className="miss-modal__actions">
            <Button
              variant="primary"
              type="submit"
              disabled={!query.trim() || busy}
            >
              {busy
                ? t("missingDiseaseDialog.searching")
                : t("missingDiseaseDialog.searchCta")}
            </Button>
            <Button type="button" onClick={onClose}>
              {t("missingDiseaseDialog.cancel")}
            </Button>
            <span className="miss-modal__cost">
              {t("missingDiseaseDialog.costNote")}
            </span>
          </div>
        </form>

        {result !== null ? (
          <CandidatesList result={result} onPick={onPickCandidate} />
        ) : null}
      </div>
    </div>
  );
}

function Hint({ code, label }: { code: string; label: string }): ReactNode {
  return (
    <div className="miss-modal__hint-item">
      <code>{code}</code>
      <span>{label}</span>
    </div>
  );
}

/** Renders the candidate cards returned by the wider-search endpoint.
 *
 * The endpoint runs a fast model to propose candidates and a second, stronger
 * model to verify them. We surface both: the ``notes`` string (what was found,
 * corrected, rejected, or why nothing was identified) as a context banner, and
 * a small badge saying whether the result was independently verified. When no
 * candidate survives, the honest ``notes`` explanation replaces the cards
 * rather than a generic "not found".
 *
 * In-scope candidates show a green "Use this" CTA; out-of-scope ones
 * (infectious / acquired) render with the "Use this" disabled and a
 * scope-explanation banner. ``unknown`` falls back to a soft warning
 * but still lets the user proceed — the bootstrap flow itself enforces
 * the gate server-side.
 */
function CandidatesList({
  result,
  onPick,
}: {
  result: WiderSearchResponse;
  onPick: (candidate: WiderSearchCandidate) => void;
}): ReactNode {
  const { t } = useTranslation("common");
  const { candidates, notes, judged } = result;

  if (candidates.length === 0) {
    return (
      <div className="miss-modal__results miss-modal__results--empty">
        <p>
          {notes?.trim() ? notes : t("missingDiseaseDialog.notFoundFallback")}
        </p>
      </div>
    );
  }
  return (
    <div className="miss-modal__results">
      <div className="miss-modal__results-head">
        <h3 className="miss-modal__results-title">
          {t("missingDiseaseDialog.resultsTitle")}
        </h3>
        <span
          className={`miss-modal__verify miss-modal__verify--${judged ? "yes" : "no"}`}
          title={
            judged
              ? t("missingDiseaseDialog.verifiedTitle")
              : t("missingDiseaseDialog.unverifiedTitle")
          }
        >
          {judged
            ? t("missingDiseaseDialog.verifiedBadge")
            : t("missingDiseaseDialog.unverifiedBadge")}
        </span>
      </div>
      {notes?.trim() ? <p className="miss-modal__notes">{notes}</p> : null}
      {candidates.map((candidate, index) => (
        <CandidateCard
          key={`${candidate.canonicalName}-${index}`}
          candidate={candidate}
          onPick={onPick}
        />
      ))}
    </div>
  );
}

function CandidateCard({
  candidate,
  onPick,
}: {
  candidate: WiderSearchCandidate;
  onPick: (candidate: WiderSearchCandidate) => void;
}): ReactNode {
  const { t } = useTranslation("common");
  const blocked = candidate.isHardBlocked;
  const inScope = candidate.isInScope;
  const confidencePct = Math.round(candidate.confidence * 100);

  return (
    <div
      className={`miss-card miss-card--${
        blocked ? "blocked" : inScope ? "in-scope" : "warn"
      }`}
    >
      <div className="miss-card__head">
        <div className="miss-card__title">{candidate.canonicalName}</div>
        <span className="miss-card__scope">{candidate.scopeLabel}</span>
      </div>

      {candidate.summary ? (
        <p className="miss-card__summary">{candidate.summary}</p>
      ) : null}

      <dl className="miss-card__meta">
        {candidate.omim ? (
          <>
            <dt>{t("diseaseFacts.omim")}</dt>
            <dd>
              <code>{candidate.omim}</code>
            </dd>
          </>
        ) : null}
        {candidate.gene ? (
          <>
            <dt>{t("diseaseFacts.gene")}</dt>
            <dd>
              <code>{candidate.gene}</code>
            </dd>
          </>
        ) : null}
        {candidate.inheritance ? (
          <>
            <dt>{t("diseaseFacts.inheritance")}</dt>
            <dd>{candidate.inheritance}</dd>
          </>
        ) : null}
        <dt>{t("missingDiseaseDialog.confidenceLabel")}</dt>
        <dd>{confidencePct}%</dd>
      </dl>

      {candidate.evidence ? (
        <p className="miss-card__evidence">
          <span className="miss-card__evidence-label">
            {t("missingDiseaseDialog.whyThisMatch")}
          </span>
          {candidate.evidence}
        </p>
      ) : null}

      {blocked ? (
        <p className="miss-card__notice">
          {t("missingDiseaseDialog.blockedNotice", { category: candidate.category })}
        </p>
      ) : null}

      <div className="miss-card__actions">
        <Button
          variant="primary"
          type="button"
          disabled={blocked}
          onClick={() => onPick(candidate)}
        >
          {blocked
            ? t("missingDiseaseDialog.outOfScopeCta")
            : t("missingDiseaseDialog.useThisCta")}
        </Button>
      </div>
    </div>
  );
}
