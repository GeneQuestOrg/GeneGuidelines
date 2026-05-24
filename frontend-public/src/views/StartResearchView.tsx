/** Start research view — entry point for "I want guidelines for a disease".
 *
 * Single autocomplete field powered by the local rare-disease index
 * (``GET /api/disease-index/suggest``). When the user picks a hit:
 *
 * - the disease already has full GeneGuidelines content
 *   (``hasLocalRecord``) → we navigate straight to that disease page;
 * - the disease is in the index but not yet bootstrapped → we launch a
 *   guideline pipeline run (``POST /api/pipeline/guideline-run`` in
 *   custom mode) and forward the user to the run progress screen.
 *
 * If the user types something the local index does not know, the
 * autocomplete shows a "Help us find this disease" CTA which opens the
 * :class:`MissingDiseaseDialog` modal — Tier 2 wider search backed by
 * Gemma 4. Out-of-scope categories (infectious / acquired) are blocked
 * inside the modal so a research run cannot be triggered for them.
 *
 * The legacy multi-mode form (radio + custom-name + AI-generated aliases
 * textarea) was the previous incarnation of this view; it is replaced
 * here by the streamlined single-field flow approved in
 * ``draft6/src/views-research.jsx``.
 */

import {
  type ReactNode,
  useCallback,
  useState,
} from "react";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  type DiseaseSuggestion,
  type WiderSearchCandidate,
} from "../api/diseaseIndex";
import { startGuidelineRunPublic } from "../api/guidelineRun";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { MissingDiseaseDialog } from "../components/MissingDiseaseDialog";
import "../styles/research.css";
import "../styles/start-research.css";

const _STAGE_LIST: ReadonlyArray<{ label: string; sub: string }> = [
  { label: "Stage 1 (5–8 min)", sub: "PubMed search + abstract categorisation" },
  { label: "Stage 2 (3–5 min)", sub: "Therapy + diagnostic path extraction" },
  { label: "Stage 3 (4–6 min)", sub: "Doctor identification + scoring" },
  { label: "Stage 4 (2–3 min)", sub: "Trials + foundations + final assembly" },
];

export interface StartResearchViewProps {
  readonly initialDiseaseSlug?: string;
  readonly onNav: (path: string) => void;
}

type Picked =
  | { kind: "indexed"; suggestion: DiseaseSuggestion }
  | { kind: "wider"; candidate: WiderSearchCandidate };

export function StartResearchView({ onNav }: StartResearchViewProps) {
  const [picked, setPicked] = useState<Picked | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missingDialog, setMissingDialog] = useState<
    { open: false } | { open: true; initialQuery: string }
  >({ open: false });

  // Wrapping the picked-state setter clears any stale error message
  // from a previous failed attempt at the same call-site, avoiding the
  // "set state inside effect" anti-pattern.
  const setPickedAndClearError = useCallback((next: Picked | null) => {
    setPicked(next);
    setError(null);
  }, []);

  const submit = useCallback(async () => {
    if (!picked || !consent || busy) return;

    if (picked.kind === "indexed" && picked.suggestion.hasLocalRecord) {
      // Already in the catalog with full content — no need to launch a
      // research run. Send the user straight to the disease page.
      const slug = picked.suggestion.localSlug;
      if (slug) {
        onNav(`/diseases/${encodeURIComponent(slug)}`);
        return;
      }
    }

    const diseaseName =
      picked.kind === "indexed"
        ? picked.suggestion.canonicalName
        : picked.candidate.canonicalName;

    setBusy(true);
    setError(null);
    try {
      const { execution_id } = await startGuidelineRunPublic({
        mode: "custom",
        diseaseName,
        diseaseAliases: collectAliases(picked),
      });
      const q = `?name=${encodeURIComponent(diseaseName)}`;
      onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError(
          "The server rejected the request (401). Set VITE_GENEGUIDELINES_API_KEY when the backend has its API gate enabled, or run jobs from the operator console.",
        );
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not start the research run.");
      }
      setBusy(false);
    }
  }, [busy, consent, onNav, picked]);

  const submitLabel = pickSubmitLabel(picked, busy);
  const canSubmit = picked != null && consent && !busy;

  return (
    <section className="page page--start">
      <div className="start">
        <div className="start__intro">
          <h1>Start research for a new disease</h1>
          <p>
            Our AI pipeline will scan PubMed (10 years back), pull the
            recognised guidelines, identify clinicians with documented
            expertise, check active clinical trials and assemble a
            first-pass guideline draft for clinician review.
          </p>
          <ol className="start__how">
            {_STAGE_LIST.map((stage) => (
              <li key={stage.label}>
                <b>{stage.label}</b> · {stage.sub}
              </li>
            ))}
          </ol>
          <p className="start__priv">
            <span aria-hidden="true">🔒</span>
            We don&rsquo;t store patient data — only the disease name and
            the research criteria. You will receive a public link to the
            run progress page.
          </p>
        </div>

        <form
          className="start__form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="field">
            <span className="field__label">
              Find a disease <em>·</em> required
            </span>

            {picked ? (
              <PickedCard
                picked={picked}
                onClear={() => setPickedAndClearError(null)}
              />
            ) : (
              <DiseaseAutocomplete
                onPick={(suggestion) =>
                  setPickedAndClearError({ kind: "indexed", suggestion })
                }
                onMissingClick={(query) =>
                  setMissingDialog({ open: true, initialQuery: query })
                }
              />
            )}

            <span className="field__hint">
              Search by canonical name, alternative names, gene symbol,
              OMIM or Orphanet ID. If the disease is not yet in our
              catalogue, we will help identify it and launch the research.
            </span>
          </div>

          <label className="field field--check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              required
            />
            <span>
              I understand the AI output is <b>pending verification</b>{" "}
              until reviewed by a specialist clinician. The content does
              not replace medical advice.
            </span>
          </label>

          {error ? (
            <p className="research__error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="start__actions">
            <Button
              variant="primary"
              type="submit"
              disabled={!canSubmit}
            >
              {submitLabel}
            </Button>
            <Button type="button" onClick={() => onNav("/")}>
              Cancel
            </Button>
          </div>

          {/* Lightweight pointer to the symptom-based search (future
              feature, see master-plan §7a F11). Kept visually separate
              with a divider so its diagnostic-research framing does not
              bleed into the disease-name flow above. */}
          <a
            href="#/start-research/by-symptoms"
            className="symp-link"
            onClick={(event) => {
              event.preventDefault();
              // The route does not exist yet; keep the click harmless
              // until F11 ships. Once the page lands this becomes a
              // straight `onNav("/start-research/by-symptoms")`.
              setError(
                "Symptom-based search is coming soon. For now, please type a disease name.",
              );
            }}
          >
            <span className="symp-link__body">
              No diagnosis yet? <em>Search a disease by symptoms</em>
            </span>
            <span className="symp-link__arrow">→</span>
          </a>
        </form>
      </div>

      {missingDialog.open ? (
        <MissingDiseaseDialog
          initialQuery={missingDialog.initialQuery}
          onClose={() => setMissingDialog({ open: false })}
          onPickCandidate={(candidate) => {
            setPickedAndClearError({ kind: "wider", candidate });
            setMissingDialog({ open: false });
          }}
        />
      ) : null}
    </section>
  );
}

function pickSubmitLabel(picked: Picked | null, busy: boolean): string {
  if (busy) return "Launching research…";
  if (picked == null) return "Pick a disease from the list";
  if (picked.kind === "indexed" && picked.suggestion.hasLocalRecord) {
    return "Open guidelines →";
  }
  return "Run research →";
}

function collectAliases(picked: Picked): string[] {
  if (picked.kind === "indexed") {
    return [
      ...picked.suggestion.geneSymbols,
      ...picked.suggestion.omimCodes,
    ];
  }
  // Wider-search candidates already flatten to single strings.
  const aliases: string[] = [];
  if (picked.candidate.gene) aliases.push(picked.candidate.gene);
  if (picked.candidate.omim) aliases.push(picked.candidate.omim);
  return aliases;
}

function PickedCard({
  picked,
  onClear,
}: {
  picked: Picked;
  onClear: () => void;
}): ReactNode {
  const isIndexed = picked.kind === "indexed";
  const covered = isIndexed && picked.suggestion.hasLocalRecord;
  const canonical = isIndexed
    ? picked.suggestion.canonicalName
    : picked.candidate.canonicalName;

  const omim = isIndexed
    ? picked.suggestion.omimCodes[0] ?? ""
    : picked.candidate.omim;
  const orphaCode = isIndexed
    ? picked.suggestion.primaryId.startsWith("ORPHA:")
      ? picked.suggestion.primaryId.slice("ORPHA:".length)
      : ""
    : "";
  const gene = isIndexed
    ? picked.suggestion.geneSymbols[0] ?? ""
    : picked.candidate.gene;

  return (
    <div className={`picked ${covered ? "picked--covered" : "picked--new"}`}>
      <div className="picked__main">
        <div className="picked__name">{canonical}</div>
        <div className="picked__meta">
          {omim ? <code>OMIM {omim}</code> : null}
          {orphaCode ? <code>ORPHA {orphaCode}</code> : null}
          {gene ? <code>{gene}</code> : null}
          {!isIndexed ? (
            <span className="picked__source">
              from literature ({picked.candidate.modelUsed})
            </span>
          ) : null}
        </div>
      </div>
      <div className="picked__side">
        {covered ? (
          <span className="picked__badge picked__badge--ok">
            ✓ Guidelines available
          </span>
        ) : (
          <span className="picked__badge picked__badge--new">
            Research run will be launched
          </span>
        )}
        <button
          type="button"
          className="picked__clear"
          onClick={onClear}
          aria-label="Clear"
        >
          ×
        </button>
      </div>
    </div>
  );
}
