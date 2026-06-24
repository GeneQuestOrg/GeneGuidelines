import type { Foundation } from "../types/foundation";
import "./foundations-list.css";

export interface FoundationsListProps {
  foundations: readonly Foundation[];
  /** Disease name used to build the live "search elsewhere" queries. */
  diseaseName?: string;
}

function externalUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  return `https://${url}`;
}

/**
 * Live-search escape hatch. A curated catalog goes stale and never covers every
 * grassroots group, so we point families at a fresh web search and Facebook
 * groups for the disease — we don't pretend the list is complete.
 */
function SearchElsewhere({ diseaseName }: { diseaseName?: string }) {
  const q = (diseaseName ?? "").trim();
  if (!q) {
    return null;
  }
  const googleUrl = `https://www.google.com/search?q=${encodeURIComponent(
    `${q} patient foundation OR support organization`,
  )}`;
  const facebookUrl = `https://www.facebook.com/search/groups/?q=${encodeURIComponent(q)}`;
  return (
    <div className="foundations-more">
      <p className="foundations-more__note">
        This catalog can be incomplete or out of date. Search for more, including
        parent-to-parent communities:
      </p>
      <div className="foundations-more__btns">
        <a
          className="foundations-more__btn"
          href={googleUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Search Google ↗
        </a>
        <a
          className="foundations-more__btn"
          href={facebookUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Facebook groups ↗
        </a>
      </div>
    </div>
  );
}

export function FoundationsList({ foundations, diseaseName }: FoundationsListProps) {
  if (foundations.length === 0) {
    return (
      <>
        <p className="foundations-list__empty">
          No supporting foundations recorded yet for this disease.
        </p>
        <SearchElsewhere diseaseName={diseaseName} />
      </>
    );
  }
  return (
    <>
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
      <SearchElsewhere diseaseName={diseaseName} />
    </>
  );
}
