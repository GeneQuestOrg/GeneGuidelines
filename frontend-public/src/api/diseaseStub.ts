/** Client-side stub resolution for not-yet-researched diseases.
 *
 * A disease that exists in the Tier-1 rare-disease index but has never been
 * researched has no local content record and no ``localSlug``. Its page still
 * needs a canonical URL (``/diseases/<slug>``) so a family can land on a "stub"
 * view — real index facts + a "Run research" call to action — before any AI
 * content exists (see ``views/DiseaseStubView.tsx``).
 *
 * There is deliberately **no dedicated backend endpoint**: the Tier-1
 * ``GET /api/disease-index/suggest`` response already carries every field the
 * stub hero needs (canonical name, OMIM, gene, inheritance, summary, Orphanet
 * id, external URLs, ``hasLocalRecord``/``localSlug``). We resolve a stub by
 * de-slugging the URL back into a query, running that Tier-1 lookup, and
 * keeping the single suggestion whose deterministic slug matches — the same
 * ``slugifyDisease`` transform the home autocomplete used to build the URL.
 */
import { slugifyDisease } from "../utils/slugifyDisease";
import { suggestDiseases, type DiseaseSuggestion } from "./diseaseIndex";

export interface DiseaseStubMeta {
  /** The URL slug this metadata resolves for. */
  slug: string;
  canonicalName: string;
  summary: string;
  gene: string | null;
  omim: string | null;
  /** Bare Orphanet number, e.g. "558" (derived from the ``ORPHA:558`` id). */
  orphaCode: string | null;
  inheritance: string | null;
  omimUrl: string | null;
  orphaUrl: string | null;
  /** True once a real content record exists — the caller should send the user
   *  to the full disease page instead of the stub. */
  hasLocalRecord: boolean;
  localSlug: string | null;
}

function orphaCodeFrom(primaryId: string): string | null {
  return primaryId.startsWith("ORPHA:")
    ? primaryId.slice("ORPHA:".length) || null
    : null;
}

function toStubMeta(slug: string, s: DiseaseSuggestion): DiseaseStubMeta {
  return {
    slug,
    canonicalName: s.canonicalName,
    summary: s.summary,
    gene: s.geneSymbols[0] ?? null,
    omim: s.omimCodes[0] ?? null,
    orphaCode: orphaCodeFrom(s.primaryId),
    inheritance: s.inheritance,
    omimUrl: s.omimUrl,
    orphaUrl: s.orphaUrl,
    hasLocalRecord: s.hasLocalRecord,
    localSlug: s.localSlug,
  };
}

/**
 * Resolve a ``/diseases/<slug>`` URL to Tier-1 index metadata for the stub
 * view. Returns ``null`` when no index entry produces that exact slug (a
 * genuinely unknown disease → the caller falls back to its not-found state).
 */
export async function resolveDiseaseStub(
  slug: string,
): Promise<DiseaseStubMeta | null> {
  const query = slug.replace(/-+/g, " ").trim();
  if (!query) return null;

  let suggestions: DiseaseSuggestion[];
  try {
    const res = await suggestDiseases(query, 10);
    suggestions = res.suggestions;
  } catch {
    // Index degraded / offline — the stub can't be resolved; let the caller
    // render its not-found fallback rather than surfacing a raw error.
    return null;
  }

  // Prefer an entry already linked to this slug (a researched disease whose
  // localSlug equals the URL), then any entry whose canonical name slugifies
  // back to the requested slug.
  const match =
    suggestions.find((s) => s.localSlug === slug) ??
    suggestions.find((s) => slugifyDisease(s.canonicalName) === slug);

  return match ? toStubMeta(slug, match) : null;
}
