import { useCallback, useEffect, useState } from "react";
import { Badge } from "@gene-guidelines/ui";
import { fetchPipelineRuns } from "../api/client";
import { DiseaseBootstrapPanel } from "../components/DiseaseBootstrapPanel";
import { DoctorFinderPanel } from "../components/DoctorFinderPanel";
import { GuidelineRunPanel } from "../components/GuidelineRunPanel";
import { PathwayRunPanel } from "../components/PathwayRunPanel";
import { mergeRunsWithServer, type RunIndexEntry } from "../runHistory";
import {
  DISEASE_BOOTSTRAP_PIPELINE_LABEL,
  isDiseaseBootstrapPipeline,
} from "../utils/pipelineKinds";
import "../styles/ops-hub.css";

const POLL_MS = 5000;

type LaunchMode =
  | "guideline"
  | "doctor_finder"
  | "parent_pathway"
  | "disease_bootstrap"
  | null;

const CORE_PIPELINE_LABEL: Record<string, string> = {
  guideline: "Guideline",
  doctor_finder: "Specialists",
  parent_pathway: "Patient chart",
  legacy: "Legacy",
};

function pipelineLabel(pipeline: string): string {
  if (isDiseaseBootstrapPipeline(pipeline)) {
    return DISEASE_BOOTSTRAP_PIPELINE_LABEL[pipeline];
  }
  return CORE_PIPELINE_LABEL[pipeline] ?? pipeline;
}

function pipelineBadgeVariant(pipeline: string): "default" | "ok" {
  if (
    pipeline === "guideline" ||
    pipeline === "parent_pathway" ||
    isDiseaseBootstrapPipeline(pipeline)
  ) {
    return "ok";
  }
  return "default";
}

export function RunsView() {
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [launch, setLaunch] = useState<LaunchMode>("guideline");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prefillSlug, setPrefillSlug] = useState("");
  const [listError, setListError] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const server = await fetchPipelineRuns();
      setRuns(mergeRunsWithServer(server));
      setListError(null);
    } catch (e) {
      setListError(String(e));
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
    const t = window.setInterval(() => void refreshRuns(), POLL_MS);
    return () => window.clearInterval(t);
  }, [refreshRuns]);

  const selected = runs.find((r) => r.execution_id === selectedId) ?? null;

  const openLauncher = useCallback((mode: LaunchMode, slug = "") => {
    setLaunch(mode);
    setSelectedId(null);
    setPrefillSlug(slug);
  }, []);

  const rerunForSelected = useCallback(() => {
    const slug = selected?.disease_slug ?? "";
    if (!selected) return;
    if (isDiseaseBootstrapPipeline(selected.pipeline)) {
      openLauncher("disease_bootstrap", slug);
      return;
    }
    if (selected.pipeline === "guideline") {
      openLauncher("guideline", slug);
      return;
    }
    if (selected.pipeline === "parent_pathway") {
      openLauncher("parent_pathway", slug);
      return;
    }
    if (selected.pipeline === "doctor_finder") {
      openLauncher("doctor_finder", slug);
    }
  }, [openLauncher, selected]);

  const handleGuidelineStarted = useCallback(
    (meta: {
      execution_id: string;
      label: string;
      started_at: string;
      disease_slug?: string;
    }) => {
      setSelectedId(meta.execution_id);
      setLaunch(null);
      setPrefillSlug("");
      void refreshRuns();
    },
    [refreshRuns],
  );

  return (
    <div className="ops-hub">
      <div className="ops-hub__body">
        <aside className="ops-hub__aside" aria-label="Pipeline launcher">
          <div className="ops-hub__aside-head">
            <h2>Pipelines</h2>
          </div>
          <div className="ops-hub__launch">
            <button
              type="button"
              className={
                launch === "disease_bootstrap"
                  ? "ops-launch-card is-active"
                  : "ops-launch-card"
              }
              onClick={() => openLauncher("disease_bootstrap")}
            >
              <p className="ops-launch-card__title">Re-run disease research</p>
              <p className="ops-launch-card__desc">
                All bootstrap workflows (guidelines pointer, trials, therapies,
                foundations, specialists, living guideline).
              </p>
            </button>
            <button
              type="button"
              className={
                launch === "guideline"
                  ? "ops-launch-card is-active"
                  : "ops-launch-card"
              }
              onClick={() => openLauncher("guideline")}
            >
              <p className="ops-launch-card__title">Generate guideline</p>
              <p className="ops-launch-card__desc">
                PubMed evidence → structured clinical guideline draft.
              </p>
            </button>
            <button
              type="button"
              className={
                launch === "doctor_finder"
                  ? "ops-launch-card is-active"
                  : "ops-launch-card"
              }
              onClick={() => openLauncher("doctor_finder")}
            >
              <p className="ops-launch-card__title">Find specialists</p>
              <p className="ops-launch-card__desc">
                Rank disease experts from publication profiles.
              </p>
            </button>
            <button
              type="button"
              className={
                launch === "parent_pathway"
                  ? "ops-launch-card is-active"
                  : "ops-launch-card"
              }
              onClick={() => openLauncher("parent_pathway")}
            >
              <p className="ops-launch-card__title">Generate patient chart</p>
              <p className="ops-launch-card__desc">
                Plain-language next-steps chart from the published guideline — for patients,
                families, and caregivers.
              </p>
            </button>
          </div>
          {listError ? <p className="ops-hub__empty">{listError}</p> : null}
          {runs.length === 0 ? (
            <p className="ops-hub__empty">No runs yet — start a pipeline above.</p>
          ) : (
            <ul className="ops-hub__runs">
              {runs.map((run) => (
                <li key={run.execution_id}>
                  <button
                    type="button"
                    className={
                      selectedId === run.execution_id
                        ? "ops-run-item is-active"
                        : "ops-run-item"
                    }
                    onClick={() => {
                      setSelectedId(run.execution_id);
                      setLaunch(null);
                      setPrefillSlug("");
                    }}
                  >
                    <div className="ops-run-item__label">{run.label}</div>
                    <div className="ops-run-item__meta">
                      <Badge variant={pipelineBadgeVariant(run.pipeline)}>
                        {pipelineLabel(run.pipeline)}
                      </Badge>
                      <span>{run.done ? "Done" : "Running"}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="ops-hub__main">
          {launch === "disease_bootstrap" ? (
            <DiseaseBootstrapPanel
              initialDiseaseSlug={prefillSlug}
              onBootstrapStarted={() => {
                setPrefillSlug("");
                void refreshRuns();
              }}
            />
          ) : launch === "guideline" ? (
            <GuidelineRunPanel
              initialDiseaseSlug={prefillSlug}
              onRunStarted={handleGuidelineStarted}
            />
          ) : launch === "doctor_finder" ? (
            <DoctorFinderPanel
              onRunStarted={() => void refreshRuns()}
            />
          ) : launch === "parent_pathway" ? (
            <PathwayRunPanel
              initialDiseaseSlug={prefillSlug}
              onRunStarted={() => {
                setSelectedId(null);
                setPrefillSlug("");
                void refreshRuns();
              }}
            />
          ) : selected && isDiseaseBootstrapPipeline(selected.pipeline) ? (
            <DiseaseBootstrapPanel
              viewExecutionId={selected.execution_id}
              viewPipeline={selected.pipeline}
              onRunAgain={rerunForSelected}
            />
          ) : selected?.pipeline === "guideline" ? (
            <GuidelineRunPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
              onRunAgain={rerunForSelected}
            />
          ) : selected?.pipeline === "doctor_finder" ? (
            <DoctorFinderPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
              onRunStarted={() => void refreshRuns()}
              onRunAgain={rerunForSelected}
            />
          ) : selected?.pipeline === "parent_pathway" ? (
            <PathwayRunPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
              onRunAgain={rerunForSelected}
            />
          ) : selected ? (
            <div className="ops-hub__empty">
              Legacy run — open Workflows or use a new pipeline above.
            </div>
          ) : (
            <div className="ops-hub__empty">
              Choose a pipeline to start, or pick a recent run from the list.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
