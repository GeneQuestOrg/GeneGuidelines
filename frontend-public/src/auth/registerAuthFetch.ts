import type { AuthTokenGetter } from "./authToken";

let tokenGetter: AuthTokenGetter = async () => null;

export function registerAuthFetch(getter: AuthTokenGetter): void {
  tokenGetter = getter;
}

export async function resolveAuthHeaders(): Promise<Readonly<Record<string, string>>> {
  const legacy = import.meta.env.VITE_GENEGUIDELINES_API_KEY;
  if (typeof legacy === "string" && legacy.trim().length > 0) {
    return { Authorization: `Bearer ${legacy.trim()}` };
  }
  const token = await tokenGetter();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function appendClerkTokenQueryForSse(pathOrUrl: string): Promise<string> {
  const legacy = import.meta.env.VITE_GENEGUIDELINES_API_KEY;
  if (typeof legacy === "string" && legacy.trim().length > 0) {
    const sep = pathOrUrl.includes("?") ? "&" : "?";
    return `${pathOrUrl}${sep}api_key=${encodeURIComponent(legacy.trim())}`;
  }
  const token = await tokenGetter();
  if (token) {
    const sep = pathOrUrl.includes("?") ? "&" : "?";
    return `${pathOrUrl}${sep}clerk_token=${encodeURIComponent(token)}`;
  }
  return pathOrUrl;
}
