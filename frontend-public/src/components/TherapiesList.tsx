import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Therapy, TherapyStatus } from "../types/therapy";
import { pubmedArticleUrl } from "../utils/pubmedUrl";
import "./therapies-list.css";

export interface TherapiesListProps {
  therapies: readonly Therapy[];
}

// Maps the status to a "common" i18n key (resolved at render). Medical-safety:
// the backend derives status from PMID-presence, not from the stored evidence
// tier. It serves "sourced" ("AI draft — source-backed", with PubMed links) for
// a row that has >=1 source PMID, and "unverified" ("AI draft — unverified") for
// a row with none. The evidence-tier keys remain for reversibility, but the live
// API only sends "unverified" / "sourced".
const STATUS_KEY: Record<TherapyStatus, string> = {
  unverified: "therapies.statusUnverified",
  sourced: "therapies.statusSourced",
  consensus: "therapies.statusConsensus",
  verified: "therapies.statusVerified",
  pending: "therapies.statusPending",
  preclinical: "therapies.statusPreclinical",
};

interface TherapyRowProps {
  therapy: Therapy;
  index: number;
}

function TherapyRow({ therapy, index }: TherapyRowProps) {
  const { t } = useTranslation("common");
  const [expanded, setExpanded] = useState(false);
  const hasSources = therapy.pmids.length > 0;
  const listId = `pmid-list-${index}`;

  return (
    <li className={`therapy-row therapy-row--${therapy.status}`}>
      <div className="therapy-row__head">
        {/* therapy.name / therapy.note are AI-generated content → translated
            at research time (content pipeline), not here. */}
        <span className="therapy-row__name">{therapy.name}</span>
        <span className="therapy-row__status">{t(STATUS_KEY[therapy.status])}</span>
      </div>
      {therapy.note ? <p className="therapy-row__note">{therapy.note}</p> : null}
      {hasSources && (
        <div className="therapy-row__sources">
          <button
            type="button"
            className="therapy-row__sources-toggle"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-controls={listId}
          >
            {expanded
              ? t("therapies.sourcesHide")
              : t("therapies.sourcesShow", { count: therapy.pmids.length })}
          </button>
          {expanded && (
            <ul id={listId} className="therapy-row__pmid-list">
              {therapy.pmids.map((pmid) => (
                <li key={pmid}>
                  <a
                    href={pubmedArticleUrl(pmid)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="therapy-row__pmid-link"
                  >
                    {t("therapies.pmidLabel", { pmid })}
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
  const { t } = useTranslation("common");
  if (therapies.length === 0) {
    return <p className="therapies-list__empty">{t("therapies.empty")}</p>;
  }
  return (
    <ul className="therapies-list">
      {therapies.map((therapy, index) => (
        // Key is safe: therapy names are unique per disease_slug by DB constraint.
        <TherapyRow key={therapy.name} therapy={therapy} index={index} />
      ))}
    </ul>
  );
}
