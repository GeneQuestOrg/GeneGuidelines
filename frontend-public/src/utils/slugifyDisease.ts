/** Deterministic disease-name -> URL slug.
 *
 * The single source of truth for turning a canonical disease name into the
 * slug used in ``/diseases/<slug>`` and in the bootstrap request body. It must
 * stay deterministic and stable: the home autocomplete routes a not-yet-
 * researched pick to ``/diseases/<slug>`` and the stub page reverse-resolves
 * that same slug back to a Tier-1 index entry (see ``api/diseaseStub.ts``), so
 * both sides have to agree on the exact transformation.
 *
 * Mirrors the backend regex ``^[a-z0-9][a-z0-9_-]*$`` and the 2-64 char window
 * declared in ``BootstrapDiseaseBody``. NFKD-strips diacritics so European
 * spellings ("McCune-Albright") round-trip safely.
 */
export function slugifyDisease(name: string): string {
  const ascii = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const slug = ascii
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "")
    .slice(0, 64);
  // Backend requires the first char to be alphanumeric. If the cleaned string
  // somehow starts with nothing valid, fall back to a stable marker so the API
  // rejects with a clean 400 rather than silently erroring.
  return /^[a-z0-9]/.test(slug) ? slug : "disease";
}
