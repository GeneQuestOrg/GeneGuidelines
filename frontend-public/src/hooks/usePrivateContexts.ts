import { useCallback, useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { PrivateContext } from "../types/privateContext";

export interface PrivateContextsState {
  contexts: readonly PrivateContext[];
  loading: boolean;
  uploading: boolean;
  error: string | null;
  lastUpload: PrivateContext | null;
  upload(file: File): Promise<PrivateContext | null>;
  reload(): Promise<void>;
}

export function usePrivateContexts(diseaseSlug: string): PrivateContextsState {
  const [contexts, setContexts] = useState<readonly PrivateContext[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<PrivateContext | null>(null);

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
        setUploading(false);
      }
    },
    [diseaseSlug],
  );

  return { contexts, loading, uploading, error, lastUpload, upload, reload };
}
