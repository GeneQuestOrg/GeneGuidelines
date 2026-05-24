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
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  type WiderSearchCandidate,
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
  const [query, setQuery] = useState(initialQuery);
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<readonly WiderSearchCandidate[] | null>(null);
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
        setError("Type at least two characters before searching.");
        return;
      }
      setBusy(true);
      setError(null);
      setCandidates(null);
      try {
        const response = await widerSearchDisease(trimmed);
        setCandidates(response.candidates);
      } catch (e) {
        if (e instanceof ApiRequestError) {
          setError(e.message);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError("Wider search failed — please retry in a moment.");
        }
      } finally {
        setBusy(false);
      }
    },
    [query],
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
          aria-label="Close"
        >
          ×
        </button>

        <div className="miss-modal__head">
          <h2 id="miss-modal-title" className="miss-modal__title">
            Help us find your disease
          </h2>
          <p className="miss-modal__sub">
            Type whatever you have — an English or alternative name, a common
            abbreviation, an OMIM or Orphanet number, or a gene symbol.
            Gemma 4 will search public sources (OMIM, Orphanet, GeneReviews,
            PubMed) and try to identify the disease. If it does, we&rsquo;ll
            launch the research pipeline straight away.
          </p>
        </div>

        <form className="miss-modal__form" onSubmit={submit}>
          <label className="miss-modal__field">
            <span className="miss-modal__label">Disease, gene or identifier</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Bardet-Biedl · BBS10 · OMIM 209900 · ORPHA 110"
              disabled={busy}
              required
            />
            <span className="miss-modal__hint">
              One field for everything. You can type several leads separated
              by commas — the AI will combine them.
            </span>
          </label>

          <div className="miss-modal__hints">
            <Hint code="OMIM" label="6-digit number from omim.org" />
            <Hint code="ORPHA" label="number from orphanet.org" />
            <Hint code="GENE" label="HGNC symbol, e.g. FBN1, ATP7B" />
            <Hint code="NAME" label="English or alternative; abbreviation; eponym" />
          </div>

          <div className="miss-modal__pipeline">
            <span className="miss-modal__pipe-label">
              What happens after you click &ldquo;Search the literature&rdquo;:
            </span>
            <ol>
              <li><b>Gemma 4</b> normalises the input and proposes candidates from OMIM / Orphanet</li>
              <li><b>Match</b> against alternative names, gene symbols and variants (PubMed MeSH)</li>
              <li><b>Confirm</b> — you pick the right candidate from up to three best hits</li>
              <li><b>Run research</b> — your disease enters the standard 4-stage pipeline</li>
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
              {busy ? "Searching public sources…" : "Search the literature →"}
            </Button>
            <Button type="button" onClick={onClose}>
              Cancel
            </Button>
            <span className="miss-modal__cost">
              ~5–30 sec · no cost to the user
            </span>
          </div>
        </form>

        {candidates !== null ? (
          <CandidatesList
            candidates={candidates}
            onPick={onPickCandidate}
          />
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
 * In-scope candidates show a green "Use this" CTA; out-of-scope ones
 * (infectious / acquired) render with the "Use this" disabled and a
 * scope-explanation banner. ``unknown`` falls back to a soft warning
 * but still lets the user proceed — the bootstrap flow itself enforces
 * the gate server-side.
 */
function CandidatesList({
  candidates,
  onPick,
}: {
  candidates: readonly WiderSearchCandidate[];
  onPick: (candidate: WiderSearchCandidate) => void;
}): ReactNode {
  if (candidates.length === 0) {
    return (
      <div className="miss-modal__results miss-modal__results--empty">
        <p>No candidate found. Try a different spelling or include the gene.</p>
      </div>
    );
  }
  return (
    <div className="miss-modal__results">
      <h3 className="miss-modal__results-title">Candidates</h3>
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
            <dt>OMIM</dt>
            <dd>
              <code>{candidate.omim}</code>
            </dd>
          </>
        ) : null}
        {candidate.gene ? (
          <>
            <dt>Gene</dt>
            <dd>
              <code>{candidate.gene}</code>
            </dd>
          </>
        ) : null}
        {candidate.inheritance ? (
          <>
            <dt>Inheritance</dt>
            <dd>{candidate.inheritance}</dd>
          </>
        ) : null}
        <dt>Confidence</dt>
        <dd>{confidencePct}%</dd>
      </dl>

      {blocked ? (
        <p className="miss-card__notice">
          GeneGuidelines focuses on rare <em>genetic</em> diseases. This
          looks like an {candidate.category} disease, so we cannot launch
          the research pipeline here. Please consult a relevant registry.
        </p>
      ) : null}

      <div className="miss-card__actions">
        <Button
          variant="primary"
          type="button"
          disabled={blocked}
          onClick={() => onPick(candidate)}
        >
          {blocked ? "Out of scope" : "Use this disease →"}
        </Button>
      </div>
    </div>
  );
}
