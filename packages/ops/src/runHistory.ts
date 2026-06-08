import type { PipelineRunItem } from "./api/client";

const RUN_INDEX_KEY = "gg_run_index_v1";
const RUN_SNAPSHOT_PREFIX = "gg_run_snapshot_";

export interface RunIndexEntry {
  execution_id: string;
  pipeline: string;
  label: string;
  flow_key?: string;
  ticket_id?: number;
  profile?: string;
  disease_slug?: string;
  started_at: string;
  done?: boolean;
  error?: string | null;
}

function readIndex(): RunIndexEntry[] {
  try {
    const raw = window.localStorage.getItem(RUN_INDEX_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RunIndexEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeIndex(entries: RunIndexEntry[]): void {
  try {
    window.localStorage.setItem(RUN_INDEX_KEY, JSON.stringify(entries.slice(0, 100)));
  } catch {
    // quota
  }
}

export function registerRunStart(meta: RunIndexEntry): void {
  const entries = readIndex().filter((e) => e.execution_id !== meta.execution_id);
  writeIndex([meta, ...entries]);
}

export function markRunFinished(
  executionId: string,
  patch: { done?: boolean; error?: string | null },
): void {
  const entries = readIndex().map((e) =>
    e.execution_id === executionId ? { ...e, ...patch } : e,
  );
  writeIndex(entries);
}

export function saveRunSnapshot(executionId: string, payload: unknown): void {
  try {
    window.localStorage.setItem(
      `${RUN_SNAPSHOT_PREFIX}${executionId}`,
      JSON.stringify(payload),
    );
  } catch {
    // ignore
  }
}

export function loadRunSnapshot<T>(executionId: string): T | null {
  try {
    const raw = window.localStorage.getItem(`${RUN_SNAPSHOT_PREFIX}${executionId}`);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function mergeRunRows(
  server: PipelineRunItem[],
  local: RunIndexEntry[],
): RunIndexEntry[] {
  const byId = new Map<string, RunIndexEntry>();
  for (const row of local) {
    byId.set(row.execution_id, row);
  }
  for (const row of server) {
    const existing = byId.get(row.execution_id);
    byId.set(row.execution_id, {
      execution_id: row.execution_id,
      pipeline: row.pipeline,
      label: row.label || existing?.label || row.pipeline,
      flow_key: existing?.flow_key,
      ticket_id: existing?.ticket_id,
      profile: existing?.profile,
      disease_slug: row.disease_slug ?? existing?.disease_slug,
      started_at: row.started_at ?? existing?.started_at ?? "",
      done: row.done,
      error: row.error,
    });
  }
  return [...byId.values()].sort((a, b) =>
    (b.started_at || "").localeCompare(a.started_at || ""),
  );
}

export function mergeRunsWithServer(server: PipelineRunItem[]): RunIndexEntry[] {
  return mergeRunRows(server, readIndex());
}
