import type { TFunction } from "i18next";

/**
 * Diseases whose page has its own entry in `seo.json`: the name in that entry's `title` is what the app puts in the browser tab for the disease page (hooks/useDocumentMeta.ts) and what the prerendered page calls it (prerender/pages.mjs). It is the only name the app has in every language; every other disease has just the English name from its database record.
 */
const SEO_NAMED_DISEASES: ReadonlySet<string> = new Set(["fd"]);

/** The disease's name in the page's language, from `seo.json`, or null when the app has none (the caller then shows the database name). `tSeo` is the "seo" namespace's `t`. */
export function localizedDiseaseName(slug: string, tSeo: TFunction): string | null {
  if (!SEO_NAMED_DISEASES.has(slug)) {
    return null;
  }
  const key = `${slug}.title`;
  const name = tSeo(key);
  return typeof name === "string" && name.length > 0 && name !== key ? name : null;
}
