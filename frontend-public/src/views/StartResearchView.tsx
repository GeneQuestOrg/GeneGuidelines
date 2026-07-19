/** Start research view — entry point for "I want guidelines for a disease".
 *
 * Single autocomplete field powered by the local rare-disease index
 * (``GET /api/disease-index/suggest``). When the user picks a hit:
 *
 * - the disease already has full GeneGuidelines content
 *   (``hasLocalRecord``) → we navigate straight to that disease page;
 * - the disease is in the index but not yet bootstrapped → we fire the
 *   six-workflow bootstrap (``POST /api/pipeline/bootstrap-disease``)
 *   and forward the user to the guideline run progress screen. The
 *   finders (doctors, trials, therapies, foundations, official
 *   guidelines) populate ``/diseases/<slug>/...`` in parallel within
 *   ~45 s; the guideline pipeline is the long-running one (~9 min) and
 *   owns the SSE trace the user watches.
 *
 * If the user types something the local index does not know, the
 * autocomplete shows a "Help us find this disease" CTA which opens the
 * :class:`MissingDiseaseDialog` modal — Tier 2 wider search backed by
 * Gemma 4. Out-of-scope categories (infectious / acquired) are blocked
 * inside the modal so a research run cannot be triggered for them.
 */

import {
  type ReactNode,
  useCallback,
  useState,
} from "react";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  bootstrapDisease,
  type BootstrapDiseaseRequest,
} from "../api/bootstrapDisease";
import {
  type DiseaseSuggestion,
  type WiderSearchCandidate,
} from "../api/diseaseIndex";
import { DEFAULT_GUIDELINE_PROFILE } from "../api/guidelineRun";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { MissingDiseaseDialog } from "../components/MissingDiseaseDialog";
import "../styles/research.css";
import "../styles/start-research.css";

/** Six finder pipelines fan out in parallel from the bootstrap endpoint
 *  (``backend/services/disease_bootstrap.py``). The fast ones write to
 *  the disease page in under a minute; the long-running guideline draft
 *  takes ~9 minutes. The /research/<id> page mirrors this structure. */
const WORKSTREAM_LIST: ReadonlyArray<{ label: string; sub: string }> = [
  {
    label: "Guideline draft (~9 min)",
    sub: "PubMed mining → therapy + diagnostic extraction → drafted sections with PMID citations",
  },
  {
    label: "Five fast finders (~45 s each, in parallel)",
    sub: "Doctors · clinical trials · therapies · patient foundations · recognised consensus paper",
  },
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

    const body = bootstrapBodyFromPicked(picked);
    const diseaseName = body.name;

    setBusy(true);
    setError(null);
    try {
      const { execution_id } = await bootstrapDisease(body);
      const q = `?name=${encodeURIComponent(diseaseName)}&disease=${encodeURIComponent(body.slug)}`;
      // Hand the user to the long-running guideline trace — the five
      // finders complete in <45 s and surface on /diseases/<slug>/...
      // automatically once the disease row exists. The run may sit in the
      // fair-share queue first; the run page renders "Queued — position N".
      onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError(
          "The server rejected the request (401). Set VITE_GENEGUIDELINES_API_KEY when the backend has its API gate enabled, or run jobs from the operator console.",
        );
      } else if (e instanceof ApiRequestError && e.status === 409) {
        // Fair-share queue refusal — the anonymous session already has the
        // maximum number of runs in flight. Surface the friendly server text.
        setError(
          e.message ||
            "You already have several runs in the queue — wait for one to finish before starting another.",
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
            One click fans out six parallel workstreams: PubMed mining and
            the long guideline draft, plus five fast finders that pull
            specialist doctors, recruiting clinical trials, therapies,
            patient foundations and the recognised consensus paper. Each
            workstream writes its results directly to the disease page as
            it lands — you don't need to wait for the whole run to finish.
          </p>
          <ol className="start__how">
            {WORKSTREAM_LIST.map((stage) => (
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
              I understand the AI output is an <b>AI-generated draft</b> —
              a source-cited summary that no one has officially verified or
              signed off — and it does not replace medical advice; I should
              read it with a clinician.
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
            href="/start-research/by-symptoms"
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

/** Slugify a disease name for bootstrap. Mirrors the backend regex
 * ``^[a-z0-9][a-z0-9_-]*$`` and the 2–64 char window declared in
 * :class:`BootstrapDiseaseBody`. NFKD-strips diacritics so European
 * spellings ("McCune–Albright") round-trip safely. */
function slugifyForBootstrap(name: string): string {
  const ascii = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const slug = ascii
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "")
    .slice(0, 64);
  // Backend requires the first char to be alphanumeric. If the cleaned
  // string somehow starts with nothing valid, fall back to a stable
  // marker so the API rejects with a clean 400 rather than silently
  // erroring.
  return /^[a-z0-9]/.test(slug) ? slug : "disease";
}

function bootstrapBodyFromPicked(picked: Picked): BootstrapDiseaseRequest {
  const isIndexed = picked.kind === "indexed";
  const name = isIndexed
    ? picked.suggestion.canonicalName
    : picked.candidate.canonicalName;
  const slug =
    isIndexed && picked.suggestion.localSlug
      ? picked.suggestion.localSlug
      : slugifyForBootstrap(name);

  const omim = isIndexed
    ? picked.suggestion.omimCodes[0] ?? ""
    : picked.candidate.omim;
  const gene = isIndexed
    ? picked.suggestion.geneSymbols[0] ?? ""
    : picked.candidate.gene;
  const inheritance = isIndexed
    ? picked.suggestion.inheritance ?? ""
    : picked.candidate.inheritance;
  const summary = isIndexed
    ? picked.suggestion.summary
    : picked.candidate.summary;

  const body: BootstrapDiseaseRequest = {
    slug,
    name,
    name_short: name.slice(0, 24),
  };
  if (omim) body.omim = omim;
  if (gene) body.gene = gene;
  if (inheritance) body.inheritance = inheritance;
  if (summary) body.summary = summary;
  if (DEFAULT_GUIDELINE_PROFILE != null) body.profile = DEFAULT_GUIDELINE_PROFILE;
  return body;
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
