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
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
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

export interface StartResearchViewProps {
  readonly initialDiseaseSlug?: string;
  readonly onNav: (path: string) => void;
}

type Picked =
  | { kind: "indexed"; suggestion: DiseaseSuggestion }
  | { kind: "wider"; candidate: WiderSearchCandidate };

export function StartResearchView({ onNav }: StartResearchViewProps) {
  const { t } = useTranslation("start-research");
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
        setError(t("errorUnauthorized"));
      } else if (e instanceof ApiRequestError && e.status === 409) {
        // Fair-share queue refusal — the anonymous session already has the
        // maximum number of runs in flight. Surface the friendly server text.
        setError(e.message || t("errorQueueFull"));
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError(t("errorGeneric"));
      }
      setBusy(false);
    }
  }, [busy, consent, onNav, picked, t]);

  const submitLabel = pickSubmitLabel(picked, busy, t);
  const canSubmit = picked != null && consent && !busy;

  // Six finder pipelines fan out in parallel from the bootstrap endpoint
  // (``backend/services/disease_bootstrap.py``). The fast ones write to
  // the disease page in under a minute; the long-running guideline draft
  // takes ~9 minutes. The /research/<id> page mirrors this structure.
  const workstreamList: ReadonlyArray<{ label: string; sub: string }> = [
    {
      label: t("workstreamGuidelineLabel"),
      sub: t("workstreamGuidelineSub"),
    },
    {
      label: t("workstreamFindersLabel"),
      sub: t("workstreamFindersSub"),
    },
  ];

  return (
    <section className="page page--start">
      <div className="start">
        <div className="start__intro">
          <h1>{t("title")}</h1>
          <p>{t("intro")}</p>
          <ol className="start__how">
            {workstreamList.map((stage) => (
              <li key={stage.label}>
                <b>{stage.label}</b> · {stage.sub}
              </li>
            ))}
          </ol>
          <p className="start__priv">
            <span aria-hidden="true">🔒</span>
            {t("privacyNote")}
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
              {t("findDiseaseLabel")} <em>·</em> {t("requiredLabel")}
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

            <span className="field__hint">{t("fieldHint")}</span>
          </div>

          <label className="field field--check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              required
            />
            <span>
              {t("consentPrefix")} <b>{t("consentBold")}</b>{" "}
              {t("consentSuffix")}
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
              {t("cancel")}
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
              setError(t("symptomComingSoon"));
            }}
          >
            <span className="symp-link__body">
              {t("symptomLinkPrefix")} <em>{t("symptomLinkCta")}</em>
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

function pickSubmitLabel(
  picked: Picked | null,
  busy: boolean,
  t: TFunction,
): string {
  if (busy) return t("submitLaunching");
  if (picked == null) return t("submitPickDisease");
  if (picked.kind === "indexed" && picked.suggestion.hasLocalRecord) {
    return t("submitOpenGuidelines");
  }
  return t("submitRunResearch");
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
  const { t } = useTranslation("start-research");
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
              {t("pickedFromLiterature", { model: picked.candidate.modelUsed })}
            </span>
          ) : null}
        </div>
      </div>
      <div className="picked__side">
        {covered ? (
          <span className="picked__badge picked__badge--ok">
            {t("pickedBadgeOk")}
          </span>
        ) : (
          <span className="picked__badge picked__badge--new">
            {t("pickedBadgeNew")}
          </span>
        )}
        <button
          type="button"
          className="picked__clear"
          onClick={onClear}
          aria-label={t("pickedClear")}
        >
          ×
        </button>
      </div>
    </div>
  );
}
