import { useCallback, useEffect, useRef, useState } from "react";
import { parseAgentTraceEvent, type AgentTraceEvent } from "../api/agentContract";

const MAX_TRACE_LINES = 120;

export interface TraceLine {
  id: string;
  kind: string;
  text: string;
}

function formatAgentEvent(ev: AgentTraceEvent, runKind?: LiveRunKind): string {
  if (ev.text) return ev.text;
  if (ev.error) return `Error: ${ev.error}`;
  if (ev.kind === "diagnostic" && ev.tool) {
    return `${ev.tool}: ${ev.result ?? "ok"}`;
  }
  if (ev.kind === "ai_summary" && ev.issue) {
    return `Summary: ${ev.issue}`;
  }
  if (ev.kind === "output") {
    if (runKind === "pathway") {
      return "Patient chart run finished — server stored the draft; check the preview below.";
    }
    if (runKind === "doctor_finder") {
      return "Doctor finder finished — open the run result panel for details.";
    }
    return "Guideline output received";
  }
  return ev.kind ? `[${ev.kind}]` : "…";
}

function formatRawEvent(data: Record<string, unknown>): string {
  if (typeof data.text === "string") return data.text;
  if (typeof data.error === "string") return `Error: ${data.error}`;
  if (data.kind === "doctor_finder_progress") {
    const stage = String(data.stage ?? "");
    const count = data.count != null ? ` (${data.count})` : "";
    return `${stage}${count}`;
  }
  return JSON.stringify(data).slice(0, 240);
}

export type LiveRunKind = "guideline" | "pathway" | "doctor_finder";

export interface UseLiveRunTraceOptions {
  onTraceEvent?: (raw: Record<string, unknown>, parsed: AgentTraceEvent | null) => void;
  /** Drives the human-readable line when the server emits `kind: output`. */
  runKind?: LiveRunKind;
}

export function useLiveRunTrace(
  traceUrl: string | null,
  enabled: boolean,
  options?: UseLiveRunTraceOptions,
): {
  lines: TraceLine[];
  connected: boolean;
  finished: boolean;
  streamError: string | null;
  clear: () => void;
} {
  const [lines, setLines] = useState<TraceLine[]>([]);
  const [connected, setConnected] = useState(false);
  const [finished, setFinished] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const lineId = useRef(0);
  const onTraceEventRef = useRef(options?.onTraceEvent);
  onTraceEventRef.current = options?.onTraceEvent;
  const runKindRef = useRef(options?.runKind);
  runKindRef.current = options?.runKind;

  const clear = useCallback(() => {
    setLines([]);
    setConnected(false);
    setFinished(false);
    setStreamError(null);
    lineId.current = 0;
  }, []);

  useEffect(() => {
    if (!enabled || !traceUrl) {
      esRef.current?.close();
      esRef.current = null;
      return;
    }

    setLines([]);
    setConnected(false);
    setFinished(false);
    setStreamError(null);
    lineId.current = 0;

    const es = new EventSource(traceUrl);
    esRef.current = es;

    es.onopen = () => setConnected(true);

    es.onmessage = (evt) => {
      try {
        const raw = JSON.parse(evt.data) as Record<string, unknown>;
        const parsed = parseAgentTraceEvent(raw);
        onTraceEventRef.current?.(raw, parsed);
        const kind =
          (parsed?.kind as string | undefined) ??
          (typeof raw.kind === "string" ? raw.kind : "sys");
        const text = parsed
          ? formatAgentEvent(parsed, runKindRef.current)
          : formatRawEvent(raw);
        if (!text.trim()) return;

        lineId.current += 1;
        setLines((prev) => {
          const next = [
            ...prev,
            { id: String(lineId.current), kind, text },
          ];
          return next.length > MAX_TRACE_LINES
            ? next.slice(-MAX_TRACE_LINES)
            : next;
        });

        if (parsed?.done || raw.done === true) {
          es.close();
          setFinished(true);
          if (parsed?.error || typeof raw.error === "string") {
            setStreamError(String(parsed?.error ?? raw.error));
          }
        }
      } catch {
        // ignore malformed chunk
      }
    };

    es.onerror = () => {
      es.close();
      setStreamError(
        "Lost connection to live trace. The run may still be active on the server.",
      );
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [traceUrl, enabled, options?.onTraceEvent, options?.runKind]);

  return { lines, connected, finished, streamError, clear };
}
