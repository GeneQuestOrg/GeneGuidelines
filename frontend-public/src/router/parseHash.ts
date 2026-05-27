import { normalizeDiseaseSlug } from "./slug";
import type { Route } from "./types";

function parseQuery(queryRaw: string | undefined): Record<string, string> {
  const query: Record<string, string> = {};
  if (!queryRaw) {
    return query;
  }
  for (const part of queryRaw.split("&")) {
    const [key, value] = part.split("=");
    if (key) {
      query[key] = decodeURIComponent(value ?? "");
    }
  }
  return query;
}

/** Parse `window.location.hash` into a typed route (English path segments). */
export function parseHash(hash: string): Route {
  const raw = hash || "#/";
  const withoutHash = raw.startsWith("#") ? raw.slice(1) : raw;
  const [pathRaw, queryRaw] = withoutHash.split("?");
  const path = pathRaw || "/";
  const query = parseQuery(queryRaw);
  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) {
    return { name: "home" };
  }

  if (parts[0] === "dev" && parts[1] === "components") {
    return { name: "devComponents" };
  }

  if (parts[0] === "diseases") {
    const slugRaw = parts[1];
    if (!slugRaw) {
      return { name: "diseaseIndex", query: query.q };
    }
    const slug = normalizeDiseaseSlug(slugRaw);
    if (slug == null) {
      return { name: "home" };
    }
    if (parts[2] === "flowchart") {
      return { name: "flowchart", slug };
    }
    if (parts[2] === "guidelines") {
      if (parts[3] === "pr" && parts[4]) {
        return { name: "guidelines", slug, prId: parts[4] };
      }
      return { name: "guidelines", slug };
    }
    if (parts.length > 2) {
      return { name: "home" };
    }
    return { name: "disease", slug };
  }

  if (parts[0] === "doctors") {
    const disease = query.disease ? normalizeDiseaseSlug(query.disease) : null;
    return disease != null ? { name: "doctors", disease } : { name: "doctors" };
  }

  if (parts[0] === "doctor" && parts[1]) {
    return { name: "doctor", slug: parts[1] };
  }

  if (parts[0] === "add-disease" || parts[0] === "start-research") {
    const diseaseSlug = query.disease ? normalizeDiseaseSlug(query.disease) : null;
    return {
      name: "startResearch",
      ...(diseaseSlug != null ? { diseaseSlug } : {}),
    };
  }

  if (parts[0] === "trials") {
    return { name: "trials", query: query.q };
  }

  if (parts[0] === "about") {
    return { name: "about" };
  }

  if (parts[0] === "account") {
    return { name: "account" };
  }

  if (parts[0] === "research" && parts[1]) {
    const diseaseSlug = query.disease ? normalizeDiseaseSlug(query.disease) : null;
    const diseaseName =
      typeof query.name === "string" && query.name.trim().length > 0
        ? query.name.trim()
        : null;
    return {
      name: "researchRun",
      id: parts[1],
      query: query.q,
      ...(diseaseSlug != null ? { diseaseSlug } : {}),
      ...(diseaseName != null ? { diseaseName } : {}),
    };
  }

  return { name: "home" };
}
