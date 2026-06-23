export interface PaginationProps {
  /** 1-based current page. */
  readonly page: number;
  /** Total number of pages (>= 1). */
  readonly pageCount: number;
  readonly onPage: (page: number) => void;
}

type PageToken = number | "gap";

/**
 * Build the compact page-token list: always the first and last page, the current page with one
 * neighbour each side, and "gap" ellipses for the runs in between. Keeps the control to a fixed
 * width no matter how many pages exist (1 … 4 5 6 … 84).
 */
function pageTokens(page: number, pageCount: number): PageToken[] {
  const pages = new Set<number>([1, pageCount, page, page - 1, page + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b);
  const tokens: PageToken[] = [];
  let prev = 0;
  for (const p of sorted) {
    if (prev && p - prev > 1) tokens.push("gap");
    tokens.push(p);
    prev = p;
  }
  return tokens;
}

/**
 * Numbered pagination with prev/next. Renders nothing for a single page. The chosen page is
 * driven entirely by the parent (URL-synced in the doctors directory), so this stays a pure
 * presentational control.
 */
export function Pagination({ page, pageCount, onPage }: PaginationProps) {
  if (pageCount <= 1) {
    return null;
  }
  const safePage = Math.min(Math.max(1, page), pageCount);
  const tokens = pageTokens(safePage, pageCount);

  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="pagination__btn pagination__btn--nav"
        onClick={() => onPage(safePage - 1)}
        disabled={safePage <= 1}
        aria-label="Previous page"
      >
        ‹
      </button>
      {tokens.map((token, i) =>
        token === "gap" ? (
          <span key={`gap-${i}`} className="pagination__gap" aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={token}
            type="button"
            className={`pagination__btn${token === safePage ? " is-active" : ""}`}
            onClick={() => onPage(token)}
            aria-current={token === safePage ? "page" : undefined}
            aria-label={`Page ${token}`}
          >
            {token}
          </button>
        ),
      )}
      <button
        type="button"
        className="pagination__btn pagination__btn--nav"
        onClick={() => onPage(safePage + 1)}
        disabled={safePage >= pageCount}
        aria-label="Next page"
      >
        ›
      </button>
    </nav>
  );
}
