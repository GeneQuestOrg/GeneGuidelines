import { useCallback, useEffect, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  ApiRequestError,
  appendApiKeyQueryForSse,
  getApiBaseUrl,
} from "../api/client";
import { type AgentRunPayloadV1, fetchAgentRun } from "../api/guidelineRun";
import "../styles/research.css";

const POLL_MS = 2000;
const MAX_TRACE_LINES = 80;

export interface ResearchRunViewProps {
  readonly executionId: string;
  readonly diseaseSlug?: string;
  readonly queryTag?: string;
  readonly onNav: (path: string) => void;
}

function formatTraceLine(raw: string): string {
  try {
    const ev = JSON.parse(raw) as Record<string, unknown>;
    if (ev.done === true) {
      return "[done]";
    }
    const kind = typeof ev.kind === "string" ? ev.kind : "";
    const text =
      typeof ev.text === "string"
        ? ev.text
        : typeof ev.output === "string"
          ? ev.output
          : JSON.stringify(ev);
    return kind ? `[${kind}] ${text}` : text;
  } catch {
    return raw;
  }
}

export function ResearchRunView({
  executionId,
  diseaseSlug,
  queryTag,
  onNav,
}: ResearchRunViewProps) {
  const [run, setRun] = useState<AgentRunPayloadV1 | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);

  const appendLines = useCallback((next: string[]) => {
    setLines((prev) => {
      const merged = [...prev, ...next].slice(-MAX_TRACE_LINES);
      return merged;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const payload = await fetchAgentRun(executionId);
        if (!cancelled) {
          setRun(payload);
          setPollError(null);
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiRequestError && e.status === 404) {
          setPollError(
            "Run not found — it may have expired from server memory. Try starting a new job from Start research.",
          );
        } else if (e instanceof Error) {
          setPollError(e.message);
        } else {
          setPollError("Could not load run status.");
        }
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [executionId]);

  useEffect(() => {
    const base = getApiBaseUrl();
    const path = appendApiKeyQueryForSse(
      `/api/agent/trace/${encodeURIComponent(executionId)}`,
    );
    const url = base ? `${base}${path}` : path;
    const es = new EventSource(url);
    es.onmessage = (event) => {
      appendLines([formatTraceLine(event.data)]);
    };
    es.onerror = () => {
      appendLines(["[sse] connection interrupted — polling still runs"]);
      es.close();
    };
    return () => {
      es.close();
    };
  }, [appendLines, executionId]);

  const done = run?.done ?? false;
  const err = run?.error ?? null;
  const outPreview =
    run?.output != null && run.output.length > 4000
      ? `${run.output.slice(0, 4000)}…`
      : run?.output;

  const guidelinePath =
    diseaseSlug != null && diseaseSlug !== ""
      ? `/diseases/${diseaseSlug}/guidelines`
      : null;

  return (
    <section className="page page--research">
      <h1>Research run</h1>
      <p className="research__lead">
        <code>{executionId}</code>
        {diseaseSlug != null ? (
          <>
            {" "}
            · <code>{diseaseSlug}</code>
          </>
        ) : null}
        {queryTag != null ? (
          <>
            {" "}
            · tag <code>{queryTag}</code>
          </>
        ) : null}
      </p>
      {pollError != null ? (
        <p className="research__error" role="alert">
          {pollError}
        </p>
      ) : null}
      <p>
        <strong>Status:</strong>{" "}
        {done ? "finished" : "running"}
        {err != null ? (
          <>
            {" "}
            — <span style={{ color: "var(--st-red, #dc2626)" }}>{err}</span>
          </>
        ) : null}
      </p>
      {lines.length > 0 ? (
        <div className="research__trace" aria-label="Live trace">
          <pre>{lines.join("\n")}</pre>
        </div>
      ) : (
        <p className="research__hint">Waiting for trace events…</p>
      )}
      {done && outPreview != null && outPreview !== "" ? (
        <details style={{ marginTop: 20 }}>
          <summary>Structured output (preview)</summary>
          <pre className="research__trace" style={{ maxHeight: 360 }}>
            {outPreview}
          </pre>
        </details>
      ) : null}
      <div className="research__actions">
        {guidelinePath != null ? (
          <Button
            variant="primary"
            type="button"
            onClick={() => onNav(guidelinePath)}
          >
            Open guideline
          </Button>
        ) : null}
        <Button type="button" onClick={() => onNav("/start-research")}>
          New run
        </Button>
        <Button type="button" onClick={() => onNav("/")}>
          Home
        </Button>
      </div>
    </section>
  );
}
