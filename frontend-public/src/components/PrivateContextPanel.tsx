import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Badge, Button } from "@gene-guidelines/ui";
import {
  usePrivateContexts,
  type QueueItem,
  type RedactionStage,
} from "../hooks/usePrivateContexts";
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

const CONTEXT_STATUS_LABEL_KEYS: Record<PrivateContextStatus, string> = {
  pending: "statusPending",
  ready: "statusReady",
  failed: "statusFailed",
};

function formatBytes(chars: number, t: TFunction): string {
  if (chars < 1000) return t("charsUnit", { count: chars });
  return t("kCharsUnit", { count: Number((chars / 1000).toFixed(1)) });
}

function formatHash(sha256: string): string {
  // Group the hex string into 4-char chunks separated by middots so the
  // hash is scannable in the UI without word-wrapping mid-segment.
  if (!sha256) return "—";
  return sha256.match(/.{1,4}/g)?.join("·") ?? sha256;
}

function relativeTime(iso: string, t: TFunction): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const seconds = Math.max(1, Math.floor((now - then) / 1000));
  if (seconds < 60) return t("secondsAgo", { count: seconds });
  if (seconds < 3600) return t("minutesAgo", { count: Math.floor(seconds / 60) });
  return t("hoursAgo", { count: Math.floor(seconds / 3600) });
}

const STAGE_LABEL_KEYS: Record<Exclude<RedactionStage, "idle">, string> = {
  reading: "stageReading",
  redacting: "stageRedacting",
  extracting: "stageExtracting",
  discarding: "stageDiscarding",
};

const STAGE_ORDER: ReadonlyArray<Exclude<RedactionStage, "idle">> = [
  "reading",
  "redacting",
  "extracting",
  "discarding",
];

function StageProgress({ stage }: { stage: RedactionStage }) {
  const { t } = useTranslation("my-case");
  if (stage === "idle") return null;
  const activeIndex = STAGE_ORDER.indexOf(stage);
  return (
    <div className="pc-progress" role="status" aria-live="polite">
      <div className="pc-progress__pulse" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="pc-progress__title">{t(STAGE_LABEL_KEYS[stage])}</div>
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
              {t(STAGE_LABEL_KEYS[s]).replace("…", "")}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const QUEUE_STATUS_LABEL_KEYS: Record<QueueItem["status"], string> = {
  queued: "queueStatusQueued",
  processing: "queueStatusProcessing",
  done: "queueStatusDone",
  failed: "queueStatusFailed",
};

function BatchQueue({
  queue,
  onRetry,
}: {
  queue: readonly QueueItem[];
  onRetry: (id: string) => void;
}) {
  const { t } = useTranslation("my-case");
  if (queue.length === 0) return null;
  const done = queue.filter((q) => q.status === "done").length;
  const failed = queue.filter((q) => q.status === "failed").length;
  const pending = queue.length - done - failed;
  return (
    <div className="pc-queue" role="status" aria-live="polite">
      <div className="pc-queue__head">
        <span className="pc-queue__title">
          {t("processingDocuments", { count: queue.length })}
        </span>
        <span className="pc-queue__counts">
          <b>{done}</b> {t("doneLabel")}
          {failed > 0 ? (
            <>
              {" · "}
              <b className="pc-queue__failed">{failed}</b> {t("failedLabel")}
            </>
          ) : null}
          {pending > 0 ? <> · {t("leftCount", { count: pending })}</> : null}
        </span>
      </div>
      <ul className="pc-queue__list">
        {queue.map((q) => (
          <li key={q.id} className={`pc-queue__item is-${q.status}`}>
            <span className="pc-queue__dot" aria-hidden />
            <span className="pc-queue__name">{q.filename}</span>
            <span className="pc-queue__status">
              {q.status === "done" && typeof q.facts === "number"
                ? t("factsCount", { count: q.facts })
                : t(QUEUE_STATUS_LABEL_KEYS[q.status])}
            </span>
            {q.status === "failed" && q.error ? (
              <span className="pc-queue__err" title={q.error}>
                {q.error}
              </span>
            ) : null}
            {q.status === "failed" ? (
              <button
                type="button"
                className="pc-queue__retry"
                onClick={() => onRetry(q.id)}
              >
                {t("retryButton")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RedactedFactsView({ ctx }: { ctx: PrivateContext }) {
  const { t } = useTranslation("my-case");
  const r = ctx.redacted;
  return (
    <div className="pc-facts">
      {r.clinical_findings.length > 0 ? (
        <section>
          <h4>{t("findingsHeading")}</h4>
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
          <h4>{t("interventionsHeading")}</h4>
          <ul>
            {r.interventions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {r.mutations.length > 0 ? (
        <section>
          <h4>{t("mutationsHeading")}</h4>
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
          <h4>{t("outcomesHeading")}</h4>
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
  const { t } = useTranslation("my-case");
  return (
    <div className="pc-original">
      <div className="pc-original__head">
        <span className="pc-original__eyebrow">{t("originalDocEyebrow")}</span>
        <Badge variant="ok">{t("localOnlyBadge")}</Badge>
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
      <h3 className="pc-original__title">{t("originalDestroyedTitle")}</h3>
      <p className="pc-original__sub">{t("originalDestroyedBody")}</p>
      <dl className="pc-original__meta">
        <div>
          <dt>{t("filenameLabel")}</dt>
          <dd>
            <code>{ctx.originalFilename}</code>
          </dd>
        </div>
        <div>
          <dt>{t("sizeInMemoryLabel")}</dt>
          <dd>{formatBytes(ctx.originalChars, t)}</dd>
        </div>
        <div>
          <dt>{t("sha256Label")}</dt>
          <dd>
            <code className="pc-original__hash">{formatHash(ctx.originalSha256)}</code>
          </dd>
        </div>
        <div>
          <dt>{t("statusLabel")}</dt>
          <dd>
            <span className="pc-original__dot" aria-hidden />{" "}
            {t("destroyedAt", { when: relativeTime(ctx.uploadedAt, t) })}
          </dd>
        </div>
        <div>
          <dt>{t("redactedByLabel")}</dt>
          <dd>
            <code>{ctx.modelUsed}</code>
          </dd>
        </div>
      </dl>
      <p className="pc-original__note">{t("hashMementoNote")}</p>
    </div>
  );
}

function AuditBadge({ ctx }: { ctx: PrivateContext }) {
  const { t } = useTranslation("my-case");
  const b: PiiBreakdown = ctx.piiBreakdown;
  return (
    <aside className="pc-audit" role="status">
      <div className="pc-audit__dot" aria-hidden />
      <div className="pc-audit__body">
        <div className="pc-audit__headline">
          {t("auditHeadlinePrefix")}{" "}
          <b>{t("auditHeadlineBold")}</b> {t("auditHeadlineSuffix")}
        </div>
        <div className="pc-audit__meta">
          <span>
            {t("namesLabel")}: <b>{b.names}</b>
          </span>
          <span>
            {t("govIdsLabel")}: <b>{b.government_ids}</b>
          </span>
          <span>
            {t("absoluteDatesLabel")}: <b>{b.absolute_dates}</b>
          </span>
          <span>
            {t("addressesLabel")}: <b>{b.addresses}</b>
          </span>
          <span>
            {t("contactLabel")}: <b>{b.document_numbers}</b>
          </span>
          <span className="pc-audit__sep">·</span>
          <span>
            {t("processedByPrefix")} <code>{ctx.modelUsed}</code> {t("processedBySuffix")}
          </span>
        </div>
      </div>
    </aside>
  );
}

export function PrivateContextPanel({ diseaseSlug }: PrivateContextPanelProps) {
  const { contexts, uploading, stage, error, lastUpload, queue, uploadBatch, retryItem } =
    usePrivateContexts(diseaseSlug);
  const { t } = useTranslation("my-case");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const handlePick = () => fileRef.current?.click();

  // The "previous uploads" list excludes the most-recent one (it is already
  // rendered up top in the split-view).
  const previousUploads = lastUpload
    ? contexts.filter((c) => c.id !== lastUpload.id)
    : contexts;

  return (
    <div className="pc-panel">
      <p className="pc-blurb">
        {t("blurbPrefix")}{" "}
        <strong>{t("blurbBold")}</strong>
        {t("blurbSuffix")}
      </p>

      <div className="pc-controls">
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.pdf,.jpg,.jpeg,.png,image/jpeg,image/png"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = ""; // allow re-uploading the same file
            if (files.length > 0) {
              void uploadBatch(files);
            }
          }}
        />
        <Button
          type="button"
          variant="primary"
          onClick={handlePick}
          disabled={uploading}
        >
          {uploading ? t("uploadingButton") : t("addContextButton")}
        </Button>
        <span className="pc-supported">{t("supportedFormats")}</span>
      </div>

      {error != null ? (
        <p className="pc-error" role="alert">
          {error}
        </p>
      ) : null}

      <BatchQueue queue={queue} onRetry={retryItem} />

      <StageProgress stage={stage} />

      {lastUpload != null && lastUpload.status === "ready" ? (
        <>
          <section className="pc-split">
            <DestroyedOriginal ctx={lastUpload} />
            <div className="pc-extracted">
              <div className="pc-extracted__head">
                <span className="pc-extracted__eyebrow">{t("extractedFactsEyebrow")}</span>
                <Badge>{t("fieldsCount", { count: lastUpload.clinicalFactsExtracted })}</Badge>
              </div>
              <RedactedFactsView ctx={lastUpload} />
              <p className="pc-extracted__foot">{t("extractedFoot")}</p>
            </div>
          </section>
          <AuditBadge ctx={lastUpload} />
        </>
      ) : null}

      {lastUpload != null && lastUpload.status === "failed" ? (
        <p className="pc-error" role="alert">
          {lastUpload.error ?? t("redactionFailed")}
        </p>
      ) : null}

      {contexts.length === 0 && !uploading ? (
        <p className="pc-empty">{t("noContextYet")}</p>
      ) : null}

      {previousUploads.length > 0 ? (
        <>
          <h4 className="pc-history-head">{t("previousUploadsHeading")}</h4>
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
                    <Badge variant={statusVariant(ctx.status)}>
                      {t(CONTEXT_STATUS_LABEL_KEYS[ctx.status])}
                    </Badge>
                    <span className="pc-row__metric">
                      <strong>{ctx.piiTokensRemoved}</strong> {t("identifiersStrippedLabel")}
                    </span>
                    <span className="pc-row__metric">
                      <strong>{ctx.clinicalFactsExtracted}</strong> {t("factsKeptLabel")}
                    </span>
                    <span className="pc-row__chevron" aria-hidden>
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="pc-row__body">
                      {ctx.status === "failed" ? (
                        <p className="pc-error" role="alert">
                          {ctx.error ?? t("redactionFailed")}
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
