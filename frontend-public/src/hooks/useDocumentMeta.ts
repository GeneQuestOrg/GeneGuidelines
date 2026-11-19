import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { Route } from "../router/types";
import { withLocalePrefix, type Locale } from "../router/locale";

const ORIGIN = "https://geneguidelines.genequest.org";

/**
 * Which `seo.json` entry describes a route.
 *
 * Only the pages prerendered at build time (frontend-public/prerender): the about page and the four FD pages. This keeps what the browser shows after an in-app navigation identical to what the server already served. The home page and every other route keep the site-level title rather than inheriting a stale one.
 */
function seoKeyFor(route: Route): string | null {
  if (route.name === "about") {
    return "about";
  }
  if (route.name === "disease" && route.slug === "fd") {
    return "fd";
  }
  if (route.name === "diseaseMap" && route.slug === "fd") {
    return "fdMap";
  }
  if (route.name === "diseaseTests" && route.slug === "fd") {
    return "fdTests";
  }
  if (route.name === "guidelines" && route.slug === "fd") {
    return "fdGuidelines";
  }
  return null;
}

/** The in-app path a route was reached by, for the canonical/og:url tags. */
function pathFor(route: Route): string {
  switch (route.name) {
    case "disease":
      return `/diseases/${route.slug}`;
    case "diseaseMap":
      return `/diseases/${route.slug}/map`;
    case "diseaseTests":
      return `/diseases/${route.slug}/tests`;
    case "guidelines":
      return `/diseases/${route.slug}/guidelines`;
    case "about":
      return "/about";
    default:
      return "/";
  }
}

/**
 * The canonical URL. A described page and the home page have a fixed one; any other route is its own page, so it names itself. Pointing it at "/" — what this used to do — tells a search engine /diseases/mas is a copy of the home page.
 */
function canonicalFor(route: Route, key: string | null, locale: Locale): string {
  if (key != null) {
    return `${ORIGIN}${withLocalePrefix(pathFor(route), locale)}`;
  }
  if (route.name === "home") {
    return `${ORIGIN}${withLocalePrefix("/", locale)}`;
  }
  return `${ORIGIN}${window.location.pathname}`;
}

function setMeta(selector: string, attribute: string, value: string): void {
  document.head.querySelector(selector)?.setAttribute(attribute, value);
}

/** The shell served for most routes has no canonical link, so create it once. */
function setCanonical(url: string): void {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (link == null) {
    link = document.createElement("link");
    link.rel = "canonical";
    document.head.appendChild(link);
  }
  link.href = url;
}

/**
 * Keep the document head in step with the route. The served HTML already carries
 * the right tags for a crawler or a link unfurler; this is for the browser, which
 * otherwise keeps the title of whichever page the visitor landed on first.
 */
export function useDocumentMeta(route: Route, locale: Locale): void {
  const { t } = useTranslation("seo");
  const key = seoKeyFor(route);

  useEffect(() => {
    const title = key == null ? t("siteTitle") : `${t(`${key}.title`)}${t("titleSuffix")}`;
    const description = key == null ? t("siteDescription") : t(`${key}.description`);
    const url = canonicalFor(route, key, locale);

    document.title = title;
    setMeta('meta[name="description"]', "content", description);
    setCanonical(url);
    setMeta('meta[property="og:title"]', "content", title);
    setMeta('meta[property="og:description"]', "content", description);
    setMeta('meta[property="og:url"]', "content", url);
    setMeta('meta[name="twitter:title"]', "content", title);
    setMeta('meta[name="twitter:description"]', "content", description);
  }, [key, route, locale, t]);
}
