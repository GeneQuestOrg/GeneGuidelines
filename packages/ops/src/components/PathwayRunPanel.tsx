import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  agentTraceUrl,
  fetchAgentRunResult,
  publishParentPathway,
  startPathwayRun,
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
import { extractPathwayRunOutput } from "../utils/pathwayOutput";
import { RunTracePanel } from "./RunTracePanel";
import { SavedPathwayPreview } from "./pathway/SavedPathwayPreview";
import "../styles/ops-forms.css";

const MODEL_PROFILES: ModelProfile[] = ["production", "openrouter", "test", "vllm"];

export interface PathwayRunPanelProps {
  onRunStarted?: (meta: {
    execution_id: string;
    pipeline: "parent_pathway";
    label: string;
    started_at: string;
  }) => void;
  viewExecutionId?: string | null;
  runLive?: boolean;
}

export function PathwayRunPanel({
  onRunStarted,
  viewExecutionId = null,
  runLive = false,
}: PathwayRunPanelProps) {
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
  const [locale, setLocale] = useState("en");
  const [refreshPubmed, setRefreshPubmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pathwayPreview, setPathwayPreview] = useState<Record<string, unknown> | null>(
    null,
  );
  const [rawOutput, setRawOutput] = useState<string | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishOk, setPublishOk] = useState<string | null>(null);
  const finishedRunIdRef = useRef<string | null>(null);

  const traceExecutionId = activeId ?? (runLive ? viewExecutionId : null);
  const traceEnabled = Boolean(traceExecutionId && (submitting || runLive || activeId));
  const traceUrl = traceExecutionId ? agentTraceUrl(traceExecutionId) : null;

  const applyOutputView = useCallback(
    (view: ReturnType<typeof extractPathwayRunOutput>, runError?: string | null) => {
      setPathwayPreview(view.pathway);
      setRawOutput(view.rawOutput);
      if (runError) {
        setError(runError);
      }
    },
    [],
  );

  const handleTraceEvent = useCallback(
    (raw: Record<string, unknown>) => {
      if (raw.kind === "output" && typeof raw.output === "string") {
        applyOutputView(extractPathwayRunOutput(null, raw.output));
      }
    },
    [applyOutputView],
  );

  const { lines, connected, finished, streamError } = useLiveRunTrace(
    traceUrl,
    traceEnabled,
    { onTraceEvent: handleTraceEvent, runKind: "pathway" },
  );

  const selectedDisease = useMemo(
    () => diseases.find((d) => d.slug === diseaseSlug) ?? null,
    [diseases, diseaseSlug],
  );

  const loadResult = useCallback(
    async (executionId: string) => {
      setResultLoading(true);
      const snapshot = loadRunSnapshot<{
        pathway?: Record<string, unknown> | null;
        rawOutput?: string | null;
        error?: string | null;
      }>(executionId);
      if (snapshot) {
        applyOutputView(
          {
            pathway: snapshot.pathway ?? null,
            rawOutput: snapshot.rawOutput ?? null,
          },
          snapshot.error,
        );
      }
      try {
        const raw = await fetchAgentRunResult(executionId);
        const view = extractPathwayRunOutput(raw);
        applyOutputView(view, raw.error);
        saveRunSnapshot(executionId, {
          pathway: view.pathway,
          rawOutput: view.rawOutput,
          error: raw.error,
        });
        markRunFinished(executionId, { done: raw.done, error: raw.error });
      } catch {
        if (!snapshot) {
          setError(
            "Run result not on server — restart backend clears in-memory runs. Re-run the pipeline if needed.",
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
      const view = extractPathwayRunOutput(raw);
      applyOutputView(view, raw.error ?? streamError);
      saveRunSnapshot(traceExecutionId, {
        pathway: view.pathway,
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
    const label = `${selectedDisease?.name ?? diseaseSlug} — patient chart`;
    setError(null);
    setPathwayPreview(null);
    setRawOutput(null);
    finishedRunIdRef.current = null;
    setSubmitting(true);
    try {
      const { execution_id } = await startPathwayRun(diseaseSlug, profile, {
        locale,
        refreshPubmed,
      });
      const startedAt = new Date().toISOString();
      setActiveId(execution_id);
      registerRunStart({
        execution_id,
        pipeline: "parent_pathway",
        label,
        flow_key: "parent_pathway",
        profile,
        started_at: startedAt,
        done: false,
      });
      onRunStarted?.({
        execution_id,
        pipeline: "parent_pathway",
        label,
        started_at: startedAt,
      });
    } catch (err) {
      setSubmitting(false);
      setError(String(err));
    }
  };

  const showForm = !viewExecutionId;
  const showTrace = traceEnabled || Boolean(viewExecutionId && runLive);
  const hasOutput = pathwayPreview != null || Boolean(rawOutput?.trim());
  const treePreview =
    pathwayPreview && typeof pathwayPreview === "object"
      ? (pathwayPreview as { tree?: unknown }).tree ?? pathwayPreview
      : null;

  const publishSlug =
    diseaseSlug ||
    (pathwayPreview && typeof pathwayPreview === "object" && "diseaseSlug" in pathwayPreview
      ? String((pathwayPreview as { diseaseSlug?: string }).diseaseSlug ?? "")
      : "");

  return (
    <div className="ops-panel">
      <h2 className="ops-panel__title">
        {viewExecutionId ? "Patient chart run" : "Generate patient chart"}
      </h2>
      <p className="ops-panel__lead">
        Generate a plain-language next-steps chart for patients and families right after diagnosis
        (what to do first, who to call, what to ask) — derived from the published clinician
        guideline.
      </p>

      <aside className="ops-pathway-output-guide" aria-label="How to read patient chart output">
        <p className="ops-field__hint">
          <strong>What you get:</strong> the agent must call the <code>submit_parent_pathway</code> tool with
          valid JSON. That writes a <strong>draft</strong> in the server database for the disease you picked.
          When the flow finishes, this page shows that saved draft (same tree the public site would get after
          you press Publish). For debugging, fetch{' '}
          <code>
            GET /api/agent/run/
            {traceExecutionId ?? "{execution_id}"}
          </code>{' '}
          — the <code>output</code> field is JSON with <code>pathway</code> and the chart under{' '}
          <code>pathway.tree</code>.
        </p>
      </aside>

      {showForm ? (
        <form onSubmit={(e) => void handleSubmit(e)}>
          <div className="ops-form-grid">
            <div className="ops-field ops-field--wide">
              <label htmlFor="pp-disease">Disease (catalog)</label>
              <select
                id="pp-disease"
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
                  </option>
                ))}
              </select>
              {catalogError ? (
                <p className="ops-field__hint ops-field__hint--error">{catalogError}</p>
              ) : null}
            </div>
            <div className="ops-field">
              <label htmlFor="pp-locale">Patient chart locale</label>
              <select
                id="pp-locale"
                value={locale}
                onChange={(ev) => setLocale(ev.target.value)}
                disabled={submitting}
              >
                <option value="en">English</option>
                <option value="pl">Polish</option>
              </select>
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
            <div className="ops-field ops-field--wide">
              <label className="ops-checkbox">
                <input
                  type="checkbox"
                  checked={refreshPubmed}
                  onChange={(ev) => setRefreshPubmed(ev.target.checked)}
                  disabled={submitting}
                />
                Refresh targeted PubMed excerpts (treatment/diagnostics supplement)
              </label>
            </div>
          </div>
          <Button type="submit" variant="primary" disabled={submitting || !diseaseSlug}>
            {submitting ? "Generating…" : "Start patient chart run"}
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

      {resultLoading ? <p className="ops-panel__lead">Loading run output…</p> : null}

      {finished && !hasOutput && !resultLoading ? (
        <p className="ops-panel__lead">
          Run finished but no pathway preview was parsed. Inspect{' '}
          <code>GET /api/agent/run/{traceExecutionId ?? "…"}</code> (<code>output</code>) and the trace — the
          agent must end with a successful <code>submit_parent_pathway</code> call.
        </p>
      ) : null}

      {treePreview ? (
        <>
          <SavedPathwayPreview tree={treePreview} />
          <div className="ops-pathway-publish">
            <p className="ops-panel__lead">
              The run saved a <strong>draft</strong>. When the preview looks right, publish it to
              the public <strong>Living guideline</strong> tab (patient summary + next steps) and the
              full step-by-step flowchart.
            </p>
            <Button
              type="button"
              variant="primary"
              disabled={publishing || !publishSlug}
              onClick={() => {
                setPublishing(true);
                setPublishOk(null);
                setError(null);
                void publishParentPathway(publishSlug)
                  .then((res) => {
                    setPublishOk(
                      `Published ${res.diseaseSlug} (${res.version}) — refresh the public site.`,
                    );
                  })
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error ? err.message : "Publish failed — check backend logs.",
                    );
                  })
                  .finally(() => setPublishing(false));
              }}
            >
              {publishing ? "Publishing…" : "Publish to public site"}
            </Button>
            {publishOk ? <p className="ops-field__hint">{publishOk}</p> : null}
          </div>
        </>
      ) : null}

      {!treePreview && rawOutput?.trim() ? (
        <section className="ops-guideline-preview" aria-label="Raw run output">
          <h3 className="ops-guideline-preview__heading">Raw output</h3>
          <pre className="ops-raw-output">{rawOutput}</pre>
        </section>
      ) : null}
    </div>
  );
}
