import { useCallback, useEffect, useRef, useState } from "react";
import { repositories } from "../repositories";
import type { PrivateContext } from "../types/privateContext";

export type RedactionStage =
  | "idle"
  | "reading"
  | "redacting"
  | "extracting"
  | "discarding";

export type QueueItemStatus = "queued" | "processing" | "done" | "failed";

/** One document in a multi-file upload batch, with its own live status. */
export interface QueueItem {
  readonly id: string;
  readonly filename: string;
  readonly status: QueueItemStatus;
  /** Facts extracted (set once done). */
  readonly facts?: number;
  /** Error text when status === "failed". */
  readonly error?: string;
}

/** Reject obviously-too-many files before we hammer the single-worker backend.
 * A parent adding a whole imaging CD (thousands of files) is a mistake we catch
 * up front with a clear message rather than a 20-minute silent grind. */
export const MAX_BATCH_FILES = 25;

export interface PrivateContextsState {
  contexts: readonly PrivateContext[];
  loading: boolean;
  uploading: boolean;
  stage: RedactionStage;
  error: string | null;
  lastUpload: PrivateContext | null;
  /** Per-file status for the in-flight (or just-finished) batch. */
  queue: readonly QueueItem[];
  upload(file: File): Promise<PrivateContext | null>;
  uploadBatch(files: File[]): Promise<void>;
  retryItem(id: string): Promise<void>;
  clearQueue(): void;
  reload(): Promise<void>;
}

function factCount(ctx: PrivateContext): number {
  return ctx.clinicalFactsExtracted;
}

export function usePrivateContexts(diseaseSlug: string): PrivateContextsState {
  const [contexts, setContexts] = useState<readonly PrivateContext[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState<RedactionStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<PrivateContext | null>(null);
  const [queue, setQueue] = useState<readonly QueueItem[]>([]);
  const stageTimersRef = useRef<number[]>([]);
  // Retain each batch file so a failed row can be retried (transient endpoint timeouts are common).
  const filesRef = useRef<Map<string, File>>(new Map());

  const clearStageTimers = useCallback(() => {
    stageTimersRef.current.forEach((id) => window.clearTimeout(id));
    stageTimersRef.current = [];
  }, []);

  const clearQueue = useCallback(() => {
    setQueue([]);
    filesRef.current.clear();
  }, []);

  const reload = useCallback(async () => {
    const repo = repositories().privateContexts;
    setLoading(true);
    setError(null);
    try {
      const list = await repo.listForDisease(diseaseSlug);
      setContexts(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contexts.");
      setContexts([]);
    } finally {
      setLoading(false);
    }
  }, [diseaseSlug]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await repositories().privateContexts.listForDisease(
          diseaseSlug,
        );
        if (!cancelled) {
          setContexts(list);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load contexts.",
          );
          setContexts([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug]);

  const upload = useCallback(
    async (file: File): Promise<PrivateContext | null> => {
      setUploading(true);
      setError(null);
      // Walk the user through the four conceptual stages of redaction while
      // the real Gemma call runs. Timings are tuned to a typical 3-5s call;
      // if the response arrives early the hook short-circuits to the final
      // state; if it arrives late, we hold on the last stage with the
      // animation continuing.
      clearStageTimers();
      setStage("reading");
      stageTimersRef.current.push(
        window.setTimeout(() => setStage("redacting"), 700),
        window.setTimeout(() => setStage("extracting"), 1800),
        window.setTimeout(() => setStage("discarding"), 3200),
      );

      try {
        const result = await repositories().privateContexts.upload(
          diseaseSlug,
          file,
        );
        if (result != null) {
          setLastUpload(result);
          setContexts((prev) => [result, ...prev]);
        }
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed.");
        return null;
      } finally {
        clearStageTimers();
        setStage("idle");
        setUploading(false);
      }
    },
    [diseaseSlug, clearStageTimers],
  );

  // Upload a batch of files one after another (the backend is single-worker,
  // so we deliberately go sequential rather than stampede it) and surface a
  // per-file status so the parent can watch 15 documents land instead of a
  // single opaque spinner. Each file gets its own queue row that transitions
  // queued → processing → done | failed. A `failed` row from the backend
  // (unsupported type, OCR came back empty, redaction timed out) is a
  // per-file failure that must NOT stop the rest of the batch.
  const uploadBatch = useCallback(
    async (files: File[]): Promise<void> => {
      if (files.length === 0) return;
      const capped = files.slice(0, MAX_BATCH_FILES);
      if (files.length > MAX_BATCH_FILES) {
        setError(
          `You selected ${files.length} files. Processing the first ${MAX_BATCH_FILES} — ` +
            "add the rest in another batch. (Please don't upload a whole imaging CD; " +
            "those thousands of scan slices aren't documents to read.)",
        );
      } else {
        setError(null);
      }

      const items: QueueItem[] = capped.map((f, i) => ({
        id: `${Date.now()}-${i}-${f.name}`,
        filename: f.name,
        status: "queued",
      }));
      setQueue(items);
      setUploading(true);

      const patch = (id: string, next: Partial<QueueItem>) =>
        setQueue((prev) =>
          prev.map((it) => (it.id === id ? { ...it, ...next } : it)),
        );

      for (let i = 0; i < capped.length; i++) {
        const file = capped[i];
        const item = items[i];
        patch(item.id, { status: "processing" });
        filesRef.current.set(item.id, file);
        clearStageTimers();
        setStage("reading");
        stageTimersRef.current.push(
          window.setTimeout(() => setStage("redacting"), 700),
          window.setTimeout(() => setStage("extracting"), 1800),
          window.setTimeout(() => setStage("discarding"), 3200),
        );
        try {
          const result = await repositories().privateContexts.upload(
            diseaseSlug,
            file,
          );
          clearStageTimers();
          setStage("idle");
          if (result == null) {
            patch(item.id, { status: "failed", error: "Disease not found." });
            continue;
          }
          setLastUpload(result);
          setContexts((prev) => [result, ...prev]);
          if (result.status === "failed") {
            patch(item.id, {
              status: "failed",
              error: result.error ?? "Redaction failed.",
            });
          } else {
            patch(item.id, { status: "done", facts: factCount(result) });
          }
        } catch (err) {
          clearStageTimers();
          setStage("idle");
          patch(item.id, {
            status: "failed",
            error: err instanceof Error ? err.message : "Upload failed.",
          });
        }
      }

      clearStageTimers();
      setStage("idle");
      setUploading(false);
    },
    [diseaseSlug, clearStageTimers],
  );

  // Re-run one failed document (its File is retained in filesRef). Transient endpoint
  // timeouts are common (chat-029), so a retry usually succeeds where the first attempt failed.
  const retryItem = useCallback(
    async (id: string): Promise<void> => {
      const file = filesRef.current.get(id);
      if (!file) return;
      const patch = (next: Partial<QueueItem>) =>
        setQueue((prev) => prev.map((it) => (it.id === id ? { ...it, ...next } : it)));
      patch({ status: "processing", error: undefined });
      setUploading(true);
      clearStageTimers();
      setStage("reading");
      stageTimersRef.current.push(
        window.setTimeout(() => setStage("redacting"), 700),
        window.setTimeout(() => setStage("extracting"), 1800),
        window.setTimeout(() => setStage("discarding"), 3200),
      );
      try {
        const result = await repositories().privateContexts.upload(diseaseSlug, file);
        clearStageTimers();
        setStage("idle");
        if (result == null) {
          patch({ status: "failed", error: "Disease not found." });
          return;
        }
        setLastUpload(result);
        setContexts((prev) => [result, ...prev]);
        if (result.status === "failed") {
          patch({ status: "failed", error: result.error ?? "Redaction failed." });
        } else {
          patch({ status: "done", facts: factCount(result) });
        }
      } catch (err) {
        clearStageTimers();
        setStage("idle");
        patch({
          status: "failed",
          error: err instanceof Error ? err.message : "Upload failed.",
        });
      } finally {
        setUploading(false);
      }
    },
    [diseaseSlug, clearStageTimers],
  );

  useEffect(() => () => clearStageTimers(), [clearStageTimers]);

  return {
    contexts,
    loading,
    uploading,
    stage,
    error,
    lastUpload,
    queue,
    upload,
    uploadBatch,
    retryItem,
    clearQueue,
    reload,
  };
}
