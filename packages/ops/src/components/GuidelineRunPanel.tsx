import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  agentTraceUrl,
  fetchAgentRunResult,
  startGuidelineRun,
  type ModelProfile,
} from "../api/client";
import { useDefaultModelProfile } from "../hooks/useDefaultModelProfile";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useLiveRunTrace } from "../hooks/useLiveRunTrace";
import {
  loadRunSnapshot,
  markRunFinished,
  registerRunStart,
  saveRunSnapshot,
} from "../runHistory";
import {
  extractGuidelineRunOutput,
  snapshotToGuidelineView,
  type RunSnapshotPayload,
} from "../utils/runOutput";
import { sanitizeGeneratedHtml } from "../utils/pubmedOutput";
import type { PubmedQualitySnapshot } from "../api/client";
import { GuidelineQualitySummary } from "./GuidelineQualitySummary";
import { GuidelinePromptEditor } from "./GuidelinePromptEditor";
import { RunTracePanel } from "./RunTracePanel";
import "../styles/ops-forms.css";

const MODEL_PROFILES: ModelProfile[] = ["production", "openrouter", "test", "vllm"];

export interface GuidelineRunPanelProps {
  onRunStarted?: (meta: {
    execution_id: string;
    pipeline: "guideline";
    label: string;
    started_at: string;
  }) => void;
  viewExecutionId?: string | null;
  runLive?: boolean;
}

export function GuidelineRunPanel({
  onRunStarted,
  viewExecutionId = null,
  runLive = false,
}: GuidelineRunPanelProps) {
  const { diseases, loading: catalogLoading, error: catalogError } = useDiseaseCatalog();
  const defaultModelProfile = useDefaultModelProfile();
  const [diseaseSlug, setDiseaseSlug] = useState("");
  const [profile, setProfile] = useState<ModelProfile>(defaultModelProfile);
  const profileSynced = useRef(false);

  useEffect(() => {
    if (profileSynced.current) return;
    setProfile(defaultModelProfile);
    profileSynced.current = true;
  }, [defaultModelProfile]);
  const [submitting, setSubmitting] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pubmed, setPubmed] = useState<ReturnType<typeof extractGuidelineRunOutput>["pubmed"]>(null);
  const [rawOutput, setRawOutput] = useState<string | null>(null);
  const [qualitySnapshot, setQualitySnapshot] = useState<PubmedQualitySnapshot | null>(
    null,
  );
  const [resultLoading, setResultLoading] = useState(false);
  const finishedRunIdRef = useRef<string | null>(null);

  const traceExecutionId = activeId ?? (runLive ? viewExecutionId : null);
  const traceEnabled = Boolean(
    traceExecutionId && (submitting || runLive || activeId),
  );

  const traceUrl = traceExecutionId ? agentTraceUrl(traceExecutionId) : null;

  const applyOutputView = useCallback(
    (
      view: ReturnType<typeof extractGuidelineRunOutput>,
      runError?: string | null,
      quality?: PubmedQualitySnapshot | null,
    ) => {
      setPubmed(view.pubmed);
      setRawOutput(view.rawOutput);
      setQualitySnapshot(quality ?? null);
      if (runError) {
        setError(runError);
      }
    },
    [],
  );

  const handleTraceEvent = useCallback(
    (raw: Record<string, unknown>) => {
      if (raw.kind === "output" && typeof raw.output === "string") {
        applyOutputView(extractGuidelineRunOutput(null, raw.output));
      }
    },
    [applyOutputView],
  );

  const { lines, connected, finished, streamError } = useLiveRunTrace(
    traceUrl,
    traceEnabled,
    { onTraceEvent: handleTraceEvent, runKind: "guideline" },
  );

  const selectedDisease = useMemo(
    () => diseases.find((d) => d.slug === diseaseSlug) ?? null,
    [diseases, diseaseSlug],
  );

  const loadResult = useCallback(
    async (executionId: string) => {
      setResultLoading(true);
      const snapshot = loadRunSnapshot<RunSnapshotPayload>(executionId);
      if (snapshot) {
        applyOutputView(snapshotToGuidelineView(snapshot), snapshot.error);
      }
      try {
        const raw = await fetchAgentRunResult(executionId);
        const view = extractGuidelineRunOutput(raw);
        applyOutputView(view, raw.error, raw.quality_snapshot);
        saveRunSnapshot(executionId, {
          pubmed: view.pubmed,
          rawOutput: view.rawOutput,
          error: raw.error,
        });
        markRunFinished(executionId, { done: raw.done, error: raw.error });
      } catch {
        if (!snapshot) {
          setError(
            "Run result not on server — restart backend clears in-memory runs. Re-run the pipeline or check persisted DB if this run just finished.",
          );
        }
      } finally {
        setResultLoading(false);
      }
    },
    [applyOutputView],
  );

  useEffect(() => {
    if (viewExecutionId) {
      void loadResult(viewExecutionId);
    }
  }, [viewExecutionId, loadResult]);

  useEffect(() => {
    if (!finished || !traceExecutionId) {
      return;
    }
    if (finishedRunIdRef.current === traceExecutionId) {
      return;
    }
    finishedRunIdRef.current = traceExecutionId;
    setSubmitting(false);
    markRunFinished(traceExecutionId, { done: true, error: streamError });
    void fetchAgentRunResult(traceExecutionId).then((raw) => {
      const view = extractGuidelineRunOutput(raw);
      applyOutputView(view, raw.error ?? streamError, raw.quality_snapshot);
      saveRunSnapshot(traceExecutionId, {
        pubmed: view.pubmed,
        rawOutput: view.rawOutput,
        error: raw.error ?? streamError,
      });
    });
  }, [finished, traceExecutionId, streamError, applyOutputView]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!diseaseSlug) {
      setError("Select a disease from the catalog.");
      return;
    }
    const label = selectedDisease?.name ?? diseaseSlug;
    setError(null);
    setPubmed(null);
    setRawOutput(null);
    setQualitySnapshot(null);
    finishedRunIdRef.current = null;
    setSubmitting(true);
    try {
      const { execution_id } = await startGuidelineRun(diseaseSlug, profile);
      const startedAt = new Date().toISOString();
      setActiveId(execution_id);
      registerRunStart({
        execution_id,
        pipeline: "guideline",
        label,
        flow_key: "pubmed",
        profile,
        started_at: startedAt,
        done: false,
      });
      onRunStarted?.({
        execution_id,
        pipeline: "guideline",
        label,
        started_at: startedAt,
      });
    } catch (err) {
      setSubmitting(false);
      setError(String(err));
    }
  };

  const showForm = !viewExecutionId;
  const showTrace =
    traceEnabled || (Boolean(viewExecutionId) && runLive);

  const hasOutput = pubmed != null || Boolean(rawOutput?.trim());

  return (
    <div className="ops-panel">
      <h2 className="ops-panel__title">
        {viewExecutionId ? "Guideline run" : "Generate clinical guideline"}
      </h2>
      <p className="ops-panel__lead">
        Run the PubMed evidence pipeline for a catalog disease. Output appears below
        when the run finishes and is saved to the server database and browser storage.
      </p>

      {showForm ? (
        <form onSubmit={(e) => void handleSubmit(e)}>
          <div className="ops-form-grid">
            <div className="ops-field ops-field--wide">
              <label htmlFor="gg-disease">Disease (catalog)</label>
              <select
                id="gg-disease"
                value={diseaseSlug}
                onChange={(ev) => setDiseaseSlug(ev.target.value)}
                disabled={submitting || catalogLoading}
                required
              >
                <option value="">
                  {catalogLoading ? "Loading diseases…" : "Select a disease…"}
                </option>
                {diseases.map((d) => (
                  <option key={d.slug} value={d.slug}>
                    {d.name}
                    {d.gene ? ` · ${d.gene}` : ""}
                    {d.coverage === "skeleton" ? " (skeleton)" : ""}
                  </option>
                ))}
              </select>
              {catalogError ? (
                <p className="ops-field__hint ops-field__hint--error">{catalogError}</p>
              ) : null}
              {selectedDisease?.summary ? (
                <p className="ops-field__hint">{selectedDisease.summary}</p>
              ) : null}
              {diseaseSlug ? <GuidelinePromptEditor diseaseSlug={diseaseSlug} /> : null}
            </div>
            <div className="ops-field">
              <label htmlFor="gg-profile">Model profile</label>
              <select
                id="gg-profile"
                value={profile}
                onChange={(ev) => setProfile(ev.target.value as ModelProfile)}
                disabled={submitting}
              >
                {MODEL_PROFILES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Button type="submit" variant="primary" disabled={submitting || !diseaseSlug}>
            {submitting ? "Generating…" : "Start guideline run"}
          </Button>
        </form>
      ) : null}

      <RunTracePanel
        lines={lines}
        connected={connected}
        finished={finished}
        streamError={streamError}
        active={showTrace}
      />

      {error ? <div className="ops-error">{error}</div> : null}

      {resultLoading ? (
        <p className="ops-panel__lead">Loading run output…</p>
      ) : null}

      {finished && !hasOutput && !resultLoading ? (
        <p className="ops-panel__lead">
          Run finished but no structured guideline was returned. Check the live trace
          for errors, or verify API keys under Settings.
        </p>
      ) : null}

      <GuidelineQualitySummary snapshot={qualitySnapshot} />

      {pubmed ? (
        <section className="ops-guideline-preview" aria-label="Generated guideline">
          <h3 className="ops-guideline-preview__heading">Generated guideline</h3>
          {pubmed.disease_name ? <h4>{pubmed.disease_name}</h4> : null}
          {pubmed.key_updates ? (
            <p>
              <strong>Key updates:</strong> {pubmed.key_updates}
            </p>
          ) : null}
          {pubmed.guideline_html ? (
            <div
              dangerouslySetInnerHTML={{
                __html: sanitizeGeneratedHtml(pubmed.guideline_html),
              }}
            />
          ) : (
            <p style={{ color: "var(--ink-3)" }}>Guideline HTML not present in output.</p>
          )}
        </section>
      ) : null}

      {!pubmed && rawOutput?.trim() ? (
        <section className="ops-guideline-preview" aria-label="Raw run output">
          <h3 className="ops-guideline-preview__heading">Raw output</h3>
          <pre className="ops-raw-output">{rawOutput}</pre>
        </section>
      ) : null}
    </div>
  );
}