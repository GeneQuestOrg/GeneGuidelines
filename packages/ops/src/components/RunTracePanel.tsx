import { useCallback, useEffect, useRef } from "react";
import type { TraceLine } from "../hooks/useLiveRunTrace";
import "../styles/ops-trace.css";

/** Pixels from bottom of the trace body to treat as "following" live output. */
const STICKY_BOTTOM_SLACK_PX = 72;

export interface RunTracePanelProps {
  title?: string;
  lines: TraceLine[];
  connected: boolean;
  finished: boolean;
  streamError: string | null;
  active: boolean;
}

export function RunTracePanel({
  title = "Live pipeline trace",
  lines,
  connected,
  finished,
  streamError,
  active,
}: RunTracePanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null);
  /** User is at (or near) the bottom — new lines should keep them pinned there. */
  const stickToBottomRef = useRef(true);

  const updateStickFromScroll = useCallback(() => {
    const el = bodyRef.current;
    if (!el) return;
    const slack = STICKY_BOTTOM_SLACK_PX;
    stickToBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight <= slack;
  }, []);

  useEffect(() => {
    if (active) {
      stickToBottomRef.current = true;
    }
  }, [active]);

  useEffect(() => {
    const el = bodyRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [lines.length, finished]);

  if (!active) return null;

  return (
    <section className="ops-trace-panel" aria-live="polite">
      <div className="ops-trace-panel__head">
        <h3 className="ops-trace-panel__title">{title}</h3>
        <span
          className={
            finished
              ? "ops-trace-panel__status ops-trace-panel__status--done"
              : connected
                ? "ops-trace-panel__status ops-trace-panel__status--live"
                : "ops-trace-panel__status"
          }
        >
          {finished ? "Finished" : connected ? "Live" : "Connecting…"}
        </span>
      </div>
      <div
        ref={bodyRef}
        className="ops-trace-panel__body"
        onScroll={updateStickFromScroll}
      >
        {lines.length === 0 ? (
          <p className="ops-trace-panel__placeholder">
            {connected
              ? "Pipeline started — waiting for first trace events…"
              : "Opening connection to the server…"}
          </p>
        ) : (
          lines.map((line) => (
            <div key={line.id} className={`ops-trace-line ops-trace-line--${line.kind}`}>
              {line.kind !== "sys" ? (
                <span className="ops-trace-line__kind">{line.kind}</span>
              ) : null}
              <span className="ops-trace-line__text">{line.text}</span>
            </div>
          ))
        )}
      </div>
      {streamError ? <p className="ops-trace-panel__error">{streamError}</p> : null}
    </section>
  );
}
