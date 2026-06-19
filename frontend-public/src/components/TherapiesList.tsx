import { useState } from "react";
import type { Therapy, TherapyStatus } from "../types/therapy";
import "./therapies-list.css";

export interface TherapiesListProps {
  therapies: readonly Therapy[];
}

const STATUS_LABEL: Record<TherapyStatus, string> = {
  consensus: "Consensus",
  verified: "Verified",
  pending: "Pending",
  preclinical: "Preclinical",
};

function pubmedUrl(pmid: string): string {
  return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
}

interface TherapyRowProps {
  therapy: Therapy;
}

function TherapyRow({ therapy: t }: TherapyRowProps) {
  const [expanded, setExpanded] = useState(false);
  const hasSources = t.pmids.length > 0;

  return (
    <li className={`therapy-row therapy-row--${t.status}`}>
      <div className="therapy-row__head">
        <span className="therapy-row__name">{t.name}</span>
        <span className="therapy-row__status">{STATUS_LABEL[t.status]}</span>
      </div>
      {t.note ? <p className="therapy-row__note">{t.note}</p> : null}
      {hasSources && (
        <div className="therapy-row__sources">
          <button
            className="therapy-row__sources-toggle"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? "Hide sources" : `${t.pmids.length} PubMed source${t.pmids.length > 1 ? "s" : ""}`}
          </button>
          {expanded && (
            <ul className="therapy-row__pmid-list">
              {t.pmids.map((pmid) => (
                <li key={pmid}>
                  <a
                    href={pubmedUrl(pmid)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="therapy-row__pmid-link"
                  >
                    PMID {pmid}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

export function TherapiesList({ therapies }: TherapiesListProps) {
  if (therapies.length === 0) {
    return (
      <p className="therapies-list__empty">
        No therapy lines recorded for this disease yet.
      </p>
    );
  }
  return (
    <ul className="therapies-list">
      {therapies.map((t) => (
        <TherapyRow key={t.name} therapy={t} />
      ))}
    </ul>
  );
}
