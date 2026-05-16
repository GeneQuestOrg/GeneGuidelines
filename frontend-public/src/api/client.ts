/** Public JSON client: read APIs + optional mutating calls when ops key is set (dev/staging only). */

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_URL;
  if (typeof raw === "string" && raw.trim().length > 0) {
    let base = raw.trim().replace(/\/+$/, "");
    if (base.endsWith("/api")) {
      base = base.slice(0, -4);
    }
    return base.replace(/\/+$/, "");
  }
  return "";
}

/** Dev/staging only: must never be set for production public bundles (see ADR-001). */
export function getOptionalApiKey(): string | undefined {
  const k = import.meta.env.VITE_GENEGUIDELINES_API_KEY;
  if (typeof k === "string" && k.trim().length > 0) {
    return k.trim();
  }
  return undefined;
}

export function apiAuthHeaders(): Readonly<Record<string, string>> {
  const secret = getOptionalApiKey();
  if (secret == null) {
    return {};
  }
  return { Authorization: `Bearer ${secret}` };
}

/** EventSource cannot send Authorization; mirror backend `require_api_key_if_set` query param. */
export function appendApiKeyQueryForSse(pathOrUrl: string): string {
  const secret = getOptionalApiKey();
  if (secret == null) {
    return pathOrUrl;
  }
  const sep = pathOrUrl.includes("?") ? "&" : "?";
  return `${pathOrUrl}${sep}api_key=${encodeURIComponent(secret)}`;
}

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function errorDetailFromBody(body: unknown): string | undefined {
  if (
    body != null &&
    typeof body === "object" &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string"
  ) {
    return (body as { detail: string }).detail;
  }
  return undefined;
}

const HTML_WHEN_JSON_HINT =
  "The API returned HTML instead of JSON — usually the FastAPI backend is not reachable. " +
  "Start it (e.g. `python -m uvicorn backend.main:app` on port 8000), use `npm run dev` so Vite proxies `/api`, " +
  "or set `VITE_API_URL` to your API origin. If you use `vite preview`, ensure `preview.proxy` is set like in dev.";

async function parseSuccessJson<T>(res: Response): Promise<T> {
  const contentType = res.headers.get("content-type") ?? "";
  const raw = await res.text();
  const start = raw.trimStart();
  if (
    start.startsWith("<!") ||
    start.startsWith("<html") ||
    contentType.includes("text/html")
  ) {
    throw new ApiRequestError(res.status, HTML_WHEN_JSON_HINT);
  }
  if (raw.trim() === "") {
    throw new ApiRequestError(res.status, "Empty response body from API.");
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new ApiRequestError(
      res.status,
      `Response is not valid JSON. First characters: ${raw.slice(0, 120).trim()}`,
    );
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", ...apiAuthHeaders() },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body: unknown = await res.json();
      detail = errorDetailFromBody(body) ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiRequestError(
      res.status,
      `Request failed (${res.status}): ${detail}`,
    );
  }
  return parseSuccessJson<T>(res);
}

export async function apiPostJson<T>(
  path: string,
  body: unknown,
): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...apiAuthHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const raw: unknown = await res.json();
      detail = errorDetailFromBody(raw) ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiRequestError(
      res.status,
      `Request failed (${res.status}): ${detail}`,
    );
  }
  return parseSuccessJson<T>(res);
}
