/** Disease autocomplete — single field that resolves names, gene symbols,
 * OMIM and Orphanet codes against the local rare-disease index.
 *
 * Behaviour matches ``draft6/src/views-research.jsx``:
 * - debounced fuzzy search on every keystroke (300 ms) against
 *   ``/api/disease-index/suggest``;
 * - dropdown panel with highlighted matches, alias kind chips and a
 *   "✓ in catalog" / "○ research" badge;
 * - keyboard navigation (Arrow keys + Enter + Escape);
 * - empty-state CTA + always-on "missing disease" footer link that opens
 *   the wider-search dialog.
 *
 * The component is *headless* about what to do with a picked suggestion —
 * the parent decides whether to navigate to existing guidelines (when
 * ``hasLocalRecord``) or to launch a fresh research run.
 */

import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  type DiseaseSuggestion,
  suggestDiseases,
} from "../api/diseaseIndex";
import "../styles/disease-autocomplete.css";

const _DEBOUNCE_MS = 300;
const _MIN_QUERY_CHARS = 1;

export interface DiseaseAutocompleteProps {
  readonly disabled?: boolean;
  readonly placeholder?: string;
  readonly onPick: (suggestion: DiseaseSuggestion) => void;
  readonly onMissingClick: (currentQuery: string) => void;
  readonly autoFocus?: boolean;
}

export function DiseaseAutocomplete({
  disabled,
  placeholder,
  onPick,
  onMissingClick,
  autoFocus = false,
}: DiseaseAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(0);
  const [results, setResults] = useState<readonly DiseaseSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Display the empty state immediately when the user backspaces below
  // the minimum length — derived rather than reset via setState in an
  // effect so the synchronous-setState lint rule stays happy. Memoised
  // so the ``handleKey`` ``useCallback`` does not re-create on every
  // keystroke.
  const trimmedQuery = query.trim();
  const isQueryTooShort = trimmedQuery.length < _MIN_QUERY_CHARS;
  const displayResults: readonly DiseaseSuggestion[] = useMemo(
    () => (isQueryTooShort ? [] : results),
    [isQueryTooShort, results],
  );

  // Close the panel when a click lands outside it.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (
        wrapRef.current &&
        event.target instanceof Node &&
        !wrapRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Debounced fetch on every keystroke. We keep ``cancelled`` so an
  // in-flight request that finishes after a newer one cannot overwrite
  // the dropdown with stale matches. State resets for the short-query
  // case happen in :var:`displayResults` (derived) — see above.
  useEffect(() => {
    if (isQueryTooShort) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      // Mark loading inside the timer so the synchronous part of this
      // effect makes no state changes (silences react-hooks lint).
      if (cancelled) return;
      setLoading(true);
      try {
        const response = await suggestDiseases(trimmedQuery, 7);
        if (cancelled) return;
        setResults(response.suggestions);
        setHover(0);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setResults([]);
        setError(
          e instanceof Error ? e.message : "Search failed — please retry.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, _DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmedQuery, isQueryTooShort]);

  // Auto-focus the input when the parent mounts the component.
  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus();
    }
  }, [autoFocus]);

  const handleKey = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHover((h) => Math.min(h + 1, Math.max(displayResults.length - 1, 0)));
        setOpen(true);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setHover((h) => Math.max(h - 1, 0));
        setOpen(true);
        return;
      }
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }
      if (event.key === "Enter") {
        if (displayResults.length > 0 && open) {
          event.preventDefault();
          const picked = displayResults[hover] ?? displayResults[0];
          onPick(picked);
          setQuery("");
          setOpen(false);
          setResults([]);
        } else if (trimmedQuery.length >= 2 && displayResults.length === 0) {
          event.preventDefault();
          onMissingClick(trimmedQuery);
        }
      }
    },
    [displayResults, hover, onMissingClick, onPick, open, trimmedQuery],
  );

  const showPanel = open && !isQueryTooShort;

  return (
    <div ref={wrapRef} className={`ac ${showPanel ? "ac--open" : ""}`}>
      <div className="ac__inputwrap">
        <SearchIcon />
        <input
          ref={inputRef}
          type="text"
          className="ac__input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setHover(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKey}
          placeholder={placeholder ?? "Type a disease name, gene, OMIM or Orphanet ID…"}
          disabled={disabled}
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={showPanel}
          spellCheck={false}
        />
        {query ? (
          <button
            type="button"
            className="ac__clear"
            onClick={() => {
              setQuery("");
              setResults([]);
              inputRef.current?.focus();
            }}
            aria-label="Clear"
          >
            ×
          </button>
        ) : null}
      </div>

      {showPanel ? (
        <div className="ac__panel" role="listbox">
          {loading && displayResults.length === 0 ? (
            <div className="ac__loading">Searching…</div>
          ) : null}

          {displayResults.length > 0 ? (
            <ul className="ac__list">
              {displayResults.map((suggestion, index) => (
                <li
                  key={suggestion.primaryId}
                  className={`ac__item ${index === hover ? "ac__item--hover" : ""}`}
                  role="option"
                  aria-selected={index === hover}
                  onMouseEnter={() => setHover(index)}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    onPick(suggestion);
                    setQuery("");
                    setOpen(false);
                    setResults([]);
                  }}
                >
                  <SuggestionRow suggestion={suggestion} query={query} />
                </li>
              ))}
            </ul>
          ) : null}

          {!loading && displayResults.length === 0 ? (
            <div className="ac__empty">
              <div className="ac__empty-head">
                We could not find &ldquo;{trimmedQuery}&rdquo; in our catalogue.
              </div>
              <p>
                It might be listed under a different name, mistyped, or simply
                not yet in our index. Let us help you identify it.
              </p>
              <button
                type="button"
                className="ac__missing-btn"
                onMouseDown={(event) => {
                  event.preventDefault();
                  onMissingClick(trimmedQuery);
                }}
              >
                Help us find this disease →
              </button>
            </div>
          ) : null}

          {displayResults.length > 0 ? (
            <button
              type="button"
              className="ac__missing"
              onMouseDown={(event) => {
                event.preventDefault();
                onMissingClick(trimmedQuery);
              }}
            >
              <span>Not on the list? We&rsquo;ll help find your disease</span>
              <span className="ac__missing-arrow">→</span>
            </button>
          ) : null}

          {error ? <div className="ac__error">{error}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

/** Single dropdown row — name + alias chip + source / scope badges. */
function SuggestionRow({
  suggestion,
  query,
}: {
  suggestion: DiseaseSuggestion;
  query: string;
}): ReactNode {
  const primaryGene = suggestion.geneSymbols[0] ?? null;
  const primaryOmim = suggestion.omimCodes[0] ?? null;
  const aliasMatchesName =
    suggestion.matchedAlias.kind === "canonical" &&
    suggestion.matchedAlias.alias.toLowerCase() ===
      suggestion.canonicalName.toLowerCase();

  return (
    <>
      <div className="ac__item-main">
        <div className="ac__item-name">
          {highlight(suggestion.canonicalName, query)}
        </div>
        {!aliasMatchesName ? (
          <div className="ac__item-alias">
            matched <em>{suggestion.matchedAlias.kind}</em>:{" "}
            {highlight(suggestion.matchedAlias.alias, query)}
          </div>
        ) : null}
      </div>
      <div className="ac__item-side">
        {primaryGene ? <code className="ac__chip">{primaryGene}</code> : null}
        {primaryOmim ? (
          <code className="ac__chip ac__chip--dim">OMIM {primaryOmim}</code>
        ) : null}
        {suggestion.hasLocalRecord ? (
          <span className="ac__badge ac__badge--ok">✓ in catalog</span>
        ) : (
          <span className="ac__badge">research</span>
        )}
      </div>
    </>
  );
}

function highlight(text: string, query: string): ReactNode {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) {
    return text;
  }
  const haystack = text.toLowerCase();
  const needle = trimmedQuery.toLowerCase();
  const start = haystack.indexOf(needle);
  if (start < 0) {
    return text;
  }
  const end = start + needle.length;
  return (
    <>
      {text.slice(0, start)}
      <mark className="ac__mark">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}

function SearchIcon() {
  return (
    <svg
      className="ac__icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}
