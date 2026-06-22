import { useRef, useState } from "react";
import { Badge, Button } from "@gene-guidelines/ui";
import { usePrivateContexts, type RedactionStage } from "../hooks/usePrivateContexts";
import type {
  PiiBreakdown,
  PrivateContext,
  PrivateContextStatus,
} from "../types/privateContext";
import "./private-context-panel.css";

export interface PrivateContextPanelProps {
  diseaseSlug: string;
}

function statusVariant(
  status: PrivateContextStatus,
): "ok" | "default" {
  return status === "ready" ? "ok" : "default";
}

function formatBytes(chars: number): string {
  if (chars < 1000) return `${chars} chars`;
  return `${(chars / 1000).toFixed(1)} k chars`;
}

function formatHash(sha256: string): string {
  // Group the hex string into 4-char chunks separated by middots so the
  // hash is scannable in the UI without word-wrapping mid-segment.
  if (!sha256) return "—";
  return sha256.match(/.{1,4}/g)?.join("·") ?? sha256;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const seconds = Math.max(1, Math.floor((now - then) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}

const STAGE_LABELS: Record<Exclude<RedactionStage, "idle">, string> = {
  reading: "Local file read…",
  redacting: "Gemma 4 stripping personal identifiers…",
  extracting: "Extracting structured clinical facts…",
  discarding: "Destroying the original in memory…",
};

const STAGE_ORDER: ReadonlyArray<Exclude<RedactionStage, "idle">> = [
  "reading",
  "redacting",
  "extracting",
  "discarding",
];

function StageProgress({ stage }: { stage: RedactionStage }) {
  if (stage === "idle") return null;
  const activeIndex = STAGE_ORDER.indexOf(stage);
  return (
    <div className="pc-progress" role="status" aria-live="polite">
      <div className="pc-progress__pulse" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="pc-progress__title">{STAGE_LABELS[stage]}</div>
      <ol className="pc-progress__steps">
        {STAGE_ORDER.map((s, i) => {
          const cls =
            i < activeIndex
              ? "is-done"
              : i === activeIndex
              ? "is-active"
              : "";
          return (
            <li key={s} className={cls}>
              {STAGE_LABELS[s].replace("…", "")}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function RedactedFactsView({ ctx }: { ctx: PrivateContext }) {
  const r = ctx.redacted;
  return (
    <div className="pc-facts">
      {r.clinical_findings.length > 0 ? (
        <section>
          <h4>Clinical findings</h4>
          <ul>
            {r.clinical_findings.map((f, i) => (
              <li key={i}>
                <span className="pc-tag">{f.category}</span> {f.text}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {r.interventions.length > 0 ? (
        <section>
          <h4>Interventions</h4>
          <ul>
            {r.interventions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {r.mutations.length > 0 ? (
        <section>
          <h4>Mutations</h4>
          <ul>
            {r.mutations.map((s, i) => (
              <li key={i}>
                <code>{s}</code>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {r.outcomes.length > 0 ? (
        <section>
          <h4>Outcomes</h4>
          <ul>
            {r.outcomes.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function DestroyedOriginal({ ctx }: { ctx: PrivateContext }) {
  return (
    <div className="pc-original">
      <div className="pc-original__head">
        <span className="pc-original__eyebrow">Original document</span>
        <Badge variant="ok">🛡 Local only</Badge>
      </div>
      <div className="pc-original__icon" aria-hidden>
        <svg
          width="40"
          height="40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 6h18" />
          <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
        </svg>
      </div>
      <h3 className="pc-original__title">Original destroyed</h3>
      <p className="pc-original__sub">
        The file lived in server memory for the duration of one request handler.
        It never touched disk, never reached a backup, and is gone now.
      </p>
      <dl className="pc-original__meta">
        <div>
          <dt>Filename</dt>
          <dd>
            <code>{ctx.originalFilename}</code>
          </dd>
        </div>
        <div>
          <dt>Size in memory</dt>
          <dd>{formatBytes(ctx.originalChars)}</dd>
        </div>
        <div>
          <dt>SHA-256</dt>
          <dd>
            <code className="pc-original__hash">{formatHash(ctx.originalSha256)}</code>
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <span className="pc-original__dot" aria-hidden /> Destroyed {relativeTime(ctx.uploadedAt)}
          </dd>
        </div>
        <div>
          <dt>Redacted by</dt>
          <dd>
            <code>{ctx.modelUsed}</code>
          </dd>
        </div>
      </dl>
      <p className="pc-original__note">
        The hash is the only memento. Two uploads of the same document
        produce the same hash — without anyone needing to know what was inside.
      </p>
    </div>
  );
}

function AuditBadge({ ctx }: { ctx: PrivateContext }) {
  const b: PiiBreakdown = ctx.piiBreakdown;
  return (
    <aside className="pc-audit" role="status">
      <div className="pc-audit__dot" aria-hidden />
      <div className="pc-audit__body">
        <div className="pc-audit__headline">
          PII Redaction Success ·{" "}
          <b>0 personal identifiers</b> reached the synthesis model
        </div>
        <div className="pc-audit__meta">
          <span>
            Names: <b>{b.names}</b>
          </span>
          <span>
            Gov IDs: <b>{b.government_ids}</b>
          </span>
          <span>
            Absolute dates: <b>{b.absolute_dates}</b>
          </span>
          <span>
            Addresses: <b>{b.addresses}</b>
          </span>
          <span>
            Contact: <b>{b.document_numbers}</b>
          </span>
          <span className="pc-audit__sep">·</span>
          <span>
            Processed by <code>{ctx.modelUsed}</code> · in-memory only
          </span>
        </div>
      </div>
    </aside>
  );
}

export function PrivateContextPanel({ diseaseSlug }: PrivateContextPanelProps) {
  const { contexts, uploading, stage, error, lastUpload, upload } =
    usePrivateContexts(diseaseSlug);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const handlePick = () => fileRef.current?.click();

  // Upload several files one after another (the hook is single-flight on
  // `uploading`), so a parent can add a list of documents instead of one
  // oversized PDF — each lands in the list below as it finishes.
  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      await upload(file);
    }
  };

  // The "previous uploads" list excludes the most-recent one (it is already
  // rendered up top in the split-view).
  const previousUploads = lastUpload
    ? contexts.filter((c) => c.id !== lastUpload.id)
    : contexts;

  return (
    <div className="pc-panel">
      <p className="pc-blurb">
        Your medical data is treated as a{" "}
        <strong>deposit for seconds, not for storage</strong>. The document
        arrives over an encrypted channel, is processed only in the memory of
        an isolated worker, and the original is destroyed right after the
        extraction — it never touches disk, and never reaches any backup.
      </p>

      <div className="pc-controls">
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.pdf"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = ""; // allow re-uploading the same file
            if (files.length > 0) {
              void handleFiles(files);
            }
          }}
        />
        <Button
          type="button"
          variant="primary"
          onClick={handlePick}
          disabled={uploading}
        >
          {uploading ? "Gemma 4 redacting…" : "Add private context"}
        </Button>
        <span className="pc-supported">Supported: .txt · .md · .pdf · ≤ 30 MB · add several to build a list</span>
      </div>

      {error != null ? (
        <p className="pc-error" role="alert">
          {error}
        </p>
      ) : null}

      <StageProgress stage={stage} />

      {lastUpload != null && lastUpload.status === "ready" ? (
        <>
          <section className="pc-split">
            <DestroyedOriginal ctx={lastUpload} />
            <div className="pc-extracted">
              <div className="pc-extracted__head">
                <span className="pc-extracted__eyebrow">Extracted clinical facts</span>
                <Badge>{lastUpload.clinicalFactsExtracted} fields</Badge>
              </div>
              <RedactedFactsView ctx={lastUpload} />
              <p className="pc-extracted__foot">
                These facts — and only these facts — are the input to the next
                AI guideline draft for this disease.
              </p>
            </div>
          </section>
          <AuditBadge ctx={lastUpload} />
        </>
      ) : null}

      {lastUpload != null && lastUpload.status === "failed" ? (
        <p className="pc-error" role="alert">
          {lastUpload.error ?? "Redaction failed."}
        </p>
      ) : null}

      {contexts.length === 0 && !uploading ? (
        <p className="pc-empty">No private context uploaded yet.</p>
      ) : null}

      {previousUploads.length > 0 ? (
        <>
          <h4 className="pc-history-head">Previous uploads</h4>
          <ul className="pc-list">
            {previousUploads.map((ctx) => {
              const isOpen = expandedId === ctx.id;
              return (
                <li
                  key={ctx.id}
                  className={`pc-row${ctx.status === "failed" ? " pc-row--failed" : ""}`}
                >
                  <button
                    type="button"
                    className="pc-row__head"
                    onClick={() => setExpandedId(isOpen ? null : ctx.id)}
                    aria-expanded={isOpen}
                  >
                    <span className="pc-row__filename">{ctx.originalFilename}</span>
                    <Badge variant={statusVariant(ctx.status)}>{ctx.status}</Badge>
                    <span className="pc-row__metric">
                      <strong>{ctx.piiTokensRemoved}</strong> identifiers stripped
                    </span>
                    <span className="pc-row__metric">
                      <strong>{ctx.clinicalFactsExtracted}</strong> facts kept
                    </span>
                    <span className="pc-row__chevron" aria-hidden>
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="pc-row__body">
                      {ctx.status === "failed" ? (
                        <p className="pc-error" role="alert">
                          {ctx.error ?? "Redaction failed."}
                        </p>
                      ) : (
                        <RedactedFactsView ctx={ctx} />
                      )}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}
