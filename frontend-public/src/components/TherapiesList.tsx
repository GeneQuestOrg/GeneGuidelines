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
        <li key={t.name} className={`therapy-row therapy-row--${t.status}`}>
          <div className="therapy-row__head">
            <span className="therapy-row__name">{t.name}</span>
            <span className="therapy-row__status">{STATUS_LABEL[t.status]}</span>
          </div>
          {t.note ? <p className="therapy-row__note">{t.note}</p> : null}
        </li>
      ))}
    </ul>
  );
}
