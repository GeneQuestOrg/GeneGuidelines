import { useCallback, useEffect, useState } from "react";
import { Badge } from "@gene-guidelines/ui";
import { fetchPipelineRuns, type PipelineKind } from "../api/client";
import { DoctorFinderPanel } from "../components/DoctorFinderPanel";
import { GuidelineRunPanel } from "../components/GuidelineRunPanel";
import { PathwayRunPanel } from "../components/PathwayRunPanel";
import { mergeRunsWithServer, registerRunStart, type RunIndexEntry } from "../runHistory";
import "../styles/ops-hub.css";

const POLL_MS = 5000;

type LaunchMode = "guideline" | "doctor_finder" | "parent_pathway" | null;

const PIPELINE_LABEL: Record<PipelineKind, string> = {
  guideline: "Guideline",
  doctor_finder: "Specialists",
  parent_pathway: "Patient chart",
  legacy: "Legacy",
};

function pipelineBadgeVariant(
  pipeline: PipelineKind,
): "default" | "ok" {
  if (pipeline === "guideline" || pipeline === "parent_pathway") return "ok";
  return "default";
}

export function RunsView() {
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [launch, setLaunch] = useState<LaunchMode>("guideline");
  const [selectedId, setSelectedId] = useState<string | null>(null);
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

  const handleGuidelineStarted = useCallback(
    (meta: { execution_id: string; label: string; started_at: string }) => {
      registerRunStart({
        execution_id: meta.execution_id,
        pipeline: "guideline",
        label: meta.label,
        started_at: meta.started_at,
        flow_key: "pubmed",
        done: false,
      });
      setSelectedId(meta.execution_id);
      setLaunch(null);
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
                launch === "guideline"
                  ? "ops-launch-card is-active"
                  : "ops-launch-card"
              }
              onClick={() => {
                setLaunch("guideline");
                setSelectedId(null);
              }}
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
              onClick={() => {
                setLaunch("doctor_finder");
                setSelectedId(null);
              }}
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
              onClick={() => {
                setLaunch("parent_pathway");
                setSelectedId(null);
              }}
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
                    }}
                  >
                    <div className="ops-run-item__label">{run.label}</div>
                    <div className="ops-run-item__meta">
                      <Badge variant={pipelineBadgeVariant(run.pipeline)}>
                        {PIPELINE_LABEL[run.pipeline]}
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
          {launch === "guideline" ? (
            <GuidelineRunPanel onRunStarted={handleGuidelineStarted} />
          ) : launch === "doctor_finder" ? (
            <DoctorFinderPanel onRunStarted={() => void refreshRuns()} />
          ) : launch === "parent_pathway" ? (
            <PathwayRunPanel
              onRunStarted={() => {
                setSelectedId(null);
                void refreshRuns();
              }}
            />
          ) : selected?.pipeline === "guideline" ? (
            <GuidelineRunPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
            />
          ) : selected?.pipeline === "doctor_finder" ? (
            <DoctorFinderPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
              onRunStarted={() => void refreshRuns()}
            />
          ) : selected?.pipeline === "parent_pathway" ? (
            <PathwayRunPanel
              viewExecutionId={selected.execution_id}
              runLive={!selected.done}
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
