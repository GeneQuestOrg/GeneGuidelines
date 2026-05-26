import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button } from "@gene-guidelines/ui";
import {
  bootstrapDisease,
  fetchAgentRunResult,
  type ModelProfile,
} from "../api/client";
import { useDefaultModelProfile } from "../hooks/useDefaultModelProfile";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { registerRunStart } from "../runHistory";
import {
  DISEASE_BOOTSTRAP_PIPELINE_LABEL,
  isDiseaseBootstrapPipeline,
} from "../utils/pipelineKinds";
import "../styles/ops-forms.css";

const MODEL_PROFILES: ModelProfile[] = ["production", "openrouter", "test", "vllm"];

export interface DiseaseBootstrapPanelProps {
  initialDiseaseSlug?: string;
  viewExecutionId?: string | null;
  viewPipeline?: string | null;
  onBootstrapStarted?: (meta: {
    disease_slug: string;
    execution_ids: Record<string, string>;
  }) => void;
  onRunAgain?: () => void;
}

export function DiseaseBootstrapPanel({
  initialDiseaseSlug = "",
  viewExecutionId = null,
  viewPipeline = null,
  onBootstrapStarted,
  onRunAgain,
}: DiseaseBootstrapPanelProps) {
  const { diseases, loading: catalogLoading, error: catalogError } = useDiseaseCatalog();
  const defaultModelProfile = useDefaultModelProfile();
  const [diseaseSlug, setDiseaseSlug] = useState(initialDiseaseSlug);
  const [profile, setProfile] = useState<ModelProfile>(defaultModelProfile);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastExecutionIds, setLastExecutionIds] = useState<Record<string, string> | null>(
    null,
  );
  const [viewOutput, setViewOutput] = useState<string | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  useEffect(() => {
    if (initialDiseaseSlug) {
      setDiseaseSlug(initialDiseaseSlug);
    }
  }, [initialDiseaseSlug]);

  const selectedDisease = useMemo(
    () => diseases.find((d) => d.slug === diseaseSlug) ?? null,
    [diseases, diseaseSlug],
  );

  const loadViewResult = useCallback(async (executionId: string) => {
    setViewLoading(true);
    setViewOutput(null);
    setViewError(null);
    try {
      const raw = await fetchAgentRunResult(executionId);
      if (raw.error) {
        setViewError(raw.error);
      }
      const out = raw.output;
      if (out != null) {
        setViewOutput(typeof out === "string" ? out : JSON.stringify(out, null, 2));
      }
    } catch (err) {
      setViewError(String(err));
    } finally {
      setViewLoading(false);
    }
  }, []);

  useEffect(() => {
    if (viewExecutionId) {
      void loadViewResult(viewExecutionId);
    }
  }, [viewExecutionId, loadViewResult]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!diseaseSlug || !selectedDisease) {
      setError("Select a catalog disease.");
      return;
    }
    setError(null);
    setSubmitting(true);
    setLastExecutionIds(null);
    try {
      const res = await bootstrapDisease({
        slug: diseaseSlug,
        name: selectedDisease.name,
        gene: selectedDisease.gene,
        summary: selectedDisease.summary,
        profile,
      });
      setLastExecutionIds(res.execution_ids);
      const startedAt = new Date().toISOString();
      for (const [key, execution_id] of Object.entries(res.execution_ids)) {
        if (!execution_id) continue;
        const pipeline =
          key === "official_guidelines"
            ? "official_guidelines_finder"
            : key === "trials"
              ? "trials_finder"
              : key === "therapies"
                ? "therapies_finder"
                : key === "foundations"
                  ? "foundations_finder"
                  : key === "doctor_finder"
                    ? "doctor_finder"
                    : key === "guideline"
                      ? "guideline"
                      : key;
        registerRunStart({
          execution_id,
          pipeline: pipeline as "guideline" | "doctor_finder" | "legacy",
          label: `${selectedDisease.name} — ${key}`,
          started_at: startedAt,
          done: false,
          disease_slug: diseaseSlug,
        });
      }
      onBootstrapStarted?.({
        disease_slug: res.disease_slug,
        execution_ids: res.execution_ids,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const viewLabel =
    viewPipeline && isDiseaseBootstrapPipeline(viewPipeline)
      ? DISEASE_BOOTSTRAP_PIPELINE_LABEL[viewPipeline]
      : viewPipeline ?? "Workflow";

  const showForm = !viewExecutionId;

  return (
    <div className="ops-panel">
      <h2 className="ops-panel__title">
        {viewExecutionId ? viewLabel : "Re-run disease research"}
      </h2>
      <p className="ops-panel__lead">
        Fan out all catalog research workflows for one disease: official guideline pointer,
        trials, therapies, foundations, specialist finder, and the living PubMed guideline
        pipeline. Safe to run again — each workflow gets a new execution id.
      </p>

      {viewExecutionId && onRunAgain ? (
        <div className="ops-panel__toolbar">
          <Button type="button" variant="ghost" onClick={onRunAgain}>
            Re-run all workflows for another disease
          </Button>
        </div>
      ) : null}

      {showForm ? (
        <form onSubmit={(e) => void handleSubmit(e)}>
          <div className="ops-form-grid">
            <div className="ops-field ops-field--wide">
              <label htmlFor="bs-disease">Disease (catalog)</label>
              <select
                id="bs-disease"
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
              <label htmlFor="bs-profile">Model profile</label>
              <select
                id="bs-profile"
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
            {submitting ? "Starting workflows…" : "Re-run all research workflows"}
          </Button>
        </form>
      ) : null}

      {error ? <div className="ops-error">{error}</div> : null}

      {lastExecutionIds ? (
        <section className="ops-bootstrap-started" aria-label="Started workflows">
          <p className="ops-panel__lead">
            <Badge variant="ok">Started</Badge> New runs for{" "}
            <strong>{selectedDisease?.name ?? diseaseSlug}</strong> — pick them in the run
            list on the left.
          </p>
          <ul className="ops-bootstrap-started__list">
            {Object.entries(lastExecutionIds).map(([key, id]) =>
              id ? (
                <li key={key}>
                  <code>{key}</code> → <code>{id}</code>
                </li>
              ) : null,
            )}
          </ul>
        </section>
      ) : null}

      {viewExecutionId ? (
        <section className="ops-guideline-preview" aria-label="Workflow run output">
          {viewLoading ? <p className="ops-panel__lead">Loading run output…</p> : null}
          {viewError ? <div className="ops-error">{viewError}</div> : null}
          {viewOutput?.trim() ? (
            <pre className="ops-raw-output">{viewOutput}</pre>
          ) : !viewLoading && !viewError ? (
            <p className="ops-panel__lead">No persisted output for this run.</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
