import { useEffect, useState } from "react";
import { repositories } from "../repositories";
import type { SynthSectionSignal } from "../types/guidelineSynthesis";

export type SynthSignalMap = Readonly<Record<string, SynthSectionSignal>>;

export interface SynthSignalsState {
  signals: SynthSignalMap;
  loading: boolean;
  error: string | null;
}

export function useSynthSignals(diseaseSlug: string): SynthSignalsState {
  const [signals, setSignals] = useState<SynthSignalMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await repositories().officialGuidelines.getSynthSignals(diseaseSlug);
        if (!cancelled) {
          setSignals(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load synthesis signals.",
          );
          setSignals({});
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diseaseSlug]);

  return { signals, loading, error };
}
