import { useRef, useState } from "react";
import { Badge, Button } from "@gene-guidelines/ui";
import { usePrivateContexts } from "../hooks/usePrivateContexts";
import type {
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

export function PrivateContextPanel({ diseaseSlug }: PrivateContextPanelProps) {
  const { contexts, uploading, error, lastUpload, upload } =
    usePrivateContexts(diseaseSlug);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const handlePick = () => fileRef.current?.click();

  const handleFile = async (file: File) => {
    const result = await upload(file);
    if (result != null) {
      setExpandedId(result.id);
    }
  };

  return (
    <div className="pc-panel">
      <p className="pc-blurb">
        Have a discharge summary, biopsy report, or lab result that never made
        it into PubMed? Upload it — Gemma 4 strips every identifier (names,
        dates, PESEL, addresses) <strong>before anything is persisted</strong>.
        Only the structured clinical facts are kept, and only those facts feed
        the next AI guideline draft for this disease.
      </p>

      <div className="pc-controls">
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.pdf"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // allow re-uploading the same file
            if (file) {
              void handleFile(file);
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
        <span className="pc-supported">Supported: .txt · .md · .pdf · ≤ 4 MB</span>
      </div>

      {error != null ? (
        <p className="pc-error" role="alert">
          {error}
        </p>
      ) : null}

      {lastUpload != null && lastUpload.status === "ready" ? (
        <div className="pc-audit" role="status">
          <span className="pc-audit__dot" aria-hidden />
          <div className="pc-audit__body">
            <strong>Redaction complete.</strong>
            <span>
              <b>{lastUpload.piiTokensRemoved}</b> identifier-like tokens
              stripped before storage.
            </span>
            <span>
              <b>0</b> identifiers reached the synthesis model.
            </span>
            <span className="pc-audit__model">
              Model: <code>{lastUpload.modelUsed}</code>
            </span>
          </div>
        </div>
      ) : null}

      {contexts.length === 0 && !uploading ? (
        <p className="pc-empty">No private context uploaded yet.</p>
      ) : null}

      <ul className="pc-list">
        {contexts.map((ctx) => {
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
                    <>
                      <div className="pc-meta">
                        <span>
                          <strong>Original size:</strong>{" "}
                          {formatBytes(ctx.originalChars)}{" "}
                          <em>(text was held in memory only — never written to disk)</em>
                        </span>
                        <span>
                          <strong>Model:</strong> <code>{ctx.modelUsed}</code>
                        </span>
                        <span>
                          <strong>Evidence quality:</strong>{" "}
                          {ctx.redacted.evidence_quality}
                        </span>
                      </div>
                      <RedactedFactsView ctx={ctx} />
                      <p className="pc-note">
                        These facts — and only these facts — are the input to
                        the next AI guideline draft. The original document is
                        gone.
                      </p>
                    </>
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
