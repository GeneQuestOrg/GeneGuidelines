import type { GuidelineParagraph } from "../../types/guidelineDocument";
import {
  citationDisplayIndex,
  isParagraphVisibleInReader,
  type GuidelineReaderOptions,
} from "../../utils/guidelineReader";

export interface GuidelineParagraphBlockProps {
  para: GuidelineParagraph;
  orderedPmids: readonly string[];
  isActive: boolean;
  diffMode: boolean;
  diffPrId: string | null;
  inPrTarget: boolean;
  onFocusPara: (paraId: string) => void;
  onCitationClick: (pmid: string) => void;
}

function provenanceLabel(para: GuidelineParagraph): string {
  const change = para.lastChange;
  if (change == null) {
    return "";
  }
  if (change.type === "superseded") {
    return `Superseded by ${change.by ?? "update"} · ${change.date}`;
  }
  if (change.type === "pending") {
    return `AI draft · ${change.by ?? ""} · ${change.date}`.trim();
  }
  const prefix = change.type === "consensus" ? "Consensus" : "Verified";
  return `${prefix} by ${change.by ?? "panel"} · ${change.date}`;
}

export function GuidelineParagraphBlock({
  para,
  orderedPmids,
  isActive,
  diffMode,
  diffPrId,
  inPrTarget,
  onFocusPara,
  onCitationClick,
}: GuidelineParagraphBlockProps) {
  const readerOptions: GuidelineReaderOptions | undefined =
    diffPrId != null ? { diffPrId } : undefined;

  if (!isParagraphVisibleInReader(para, readerOptions)) {
    return null;
  }

  const removed = diffMode && para.prInDiff?.removed === true;
  const added = diffMode && para.prInDiff?.added === true;
  const superseded = !diffMode && para.lastChange?.type === "superseded";

  return (
    <div
      data-para-id={para.id}
      className={[
        "gl__para",
        isActive ? "gl__para--active" : "",
        removed ? "gl__para--removed" : "",
        added ? "gl__para--added" : "",
        inPrTarget && !removed && !added ? "gl__para--prtarget" : "",
        superseded ? "gl__para--superseded" : "",
        para.highlight ? "gl__para--highlight" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      tabIndex={0}
      onMouseEnter={() => onFocusPara(para.id)}
      onFocus={() => onFocusPara(para.id)}
    >
      {(removed || added) && (
        <span className="gl__para-mark" aria-hidden="true">
          {removed ? "−" : "+"}
        </span>
      )}
      <div className="gl__para-body">
        <p>
          {para.text}{" "}
          {(para.citations ?? []).map((pmid) => {
            const num = citationDisplayIndex(orderedPmids, pmid);
            return (
              <sup key={pmid}>
                <button
                  type="button"
                  className="gl__cit-ref"
                  onClick={(e) => {
                    e.stopPropagation();
                    onCitationClick(pmid);
                  }}
                  aria-label={`Citation ${num ?? pmid}`}
                >
                  [{num ?? "?"}]
                </button>
              </sup>
            );
          })}
        </p>
        {para.lastChange != null ? (
          <div className="gl__para-prov">
            <span>{provenanceLabel(para)}</span>
            {para.lastChange.prId != null && !diffMode ? (
              <>
                {" · "}
                <code>{para.lastChange.prId}</code>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

