import { useTranslation } from "react-i18next";
import type { Therapy, TherapyStatus } from "../types/therapy";
import "./therapies-list.css";

export interface TherapiesListProps {
  therapies: readonly Therapy[];
}

// Maps the evidence-tier status to a "common" i18n key (resolved at render).
// Therapy `consensus`/`verified` are evidence tiers (literature-backed), NOT a
// platform sign-off — distinct from the disease Status component's framing.
const STATUS_KEY: Record<TherapyStatus, string> = {
  consensus: "therapies.statusConsensus",
  verified: "therapies.statusVerified",
  pending: "therapies.statusPending",
  preclinical: "therapies.statusPreclinical",
};

export function TherapiesList({ therapies }: TherapiesListProps) {
  const { t } = useTranslation("common");
  if (therapies.length === 0) {
    return <p className="therapies-list__empty">{t("therapies.empty")}</p>;
  }
  return (
    <ul className="therapies-list">
      {therapies.map((therapy) => (
        <li
          key={therapy.name}
          className={`therapy-row therapy-row--${therapy.status}`}
        >
          <div className="therapy-row__head">
            {/* therapy.name / therapy.note are AI-generated content → translated
                at research time (content pipeline), not here. */}
            <span className="therapy-row__name">{therapy.name}</span>
            <span className="therapy-row__status">{t(STATUS_KEY[therapy.status])}</span>
          </div>
          {therapy.note ? <p className="therapy-row__note">{therapy.note}</p> : null}
        </li>
      ))}
    </ul>
  );
}
