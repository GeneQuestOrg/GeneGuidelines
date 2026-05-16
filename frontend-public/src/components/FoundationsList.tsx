import type { Foundation } from "../types/foundation";
import "./foundations-list.css";

export interface FoundationsListProps {
  foundations: readonly Foundation[];
}

function externalUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  return `https://${url}`;
}

export function FoundationsList({ foundations }: FoundationsListProps) {
  if (foundations.length === 0) {
    return (
      <p className="foundations-list__empty">
        No supporting foundations recorded yet for this disease.
      </p>
    );
  }
  return (
    <ul className="foundations-list">
      {foundations.map((f) => (
        <li key={f.name} className="foundation-card">
          <div className="foundation-card__head">
            <a
              className="foundation-card__name"
              href={externalUrl(f.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {f.name}
            </a>
            <span className="foundation-card__scope">{f.scope}</span>
          </div>
          {f.city || f.country ? (
            <p className="foundation-card__loc">
              {[f.city, f.country].filter(Boolean).join(" · ")}
            </p>
          ) : null}
          {f.services.length > 0 ? (
            <ul className="foundation-card__services">
              {f.services.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
