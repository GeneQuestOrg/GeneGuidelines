import { useCallback, useEffect, useRef, useState } from "react";
import { repositories } from "../repositories";
import type { PrivateContext } from "../types/privateContext";

export type RedactionStage =
  | "idle"
  | "reading"
  | "redacting"
  | "extracting"
  | "discarding";

export interface PrivateContextsState {
  contexts: readonly PrivateContext[];
  loading: boolean;
  uploading: boolean;
  stage: RedactionStage;
  error: string | null;
  lastUpload: PrivateContext | null;
  upload(file: File): Promise<PrivateContext | null>;
  reload(): Promise<void>;
}

export function usePrivateContexts(diseaseSlug: string): PrivateContextsState {
  const [contexts, setContexts] = useState<readonly PrivateContext[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState<RedactionStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<PrivateContext | null>(null);
  const stageTimersRef = useRef<number[]>([]);

  const clearStageTimers = useCallback(() => {
    stageTimersRef.current.forEach((id) => window.clearTimeout(id));
    stageTimersRef.current = [];
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

  useEffect(() => () => clearStageTimers(), [clearStageTimers]);

  return { contexts, loading, uploading, stage, error, lastUpload, upload, reload };
}
