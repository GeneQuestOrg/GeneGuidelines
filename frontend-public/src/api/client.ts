/** Public JSON client: read APIs + Clerk Bearer (or legacy dev API key). */

import {
  appendClerkTokenQueryForSse,
  resolveAuthHeaders,
} from "../auth/registerAuthFetch";

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

/** Bearer headers for mutating API calls (Clerk session or legacy dev key). */
export async function apiAuthHeaders(): Promise<Readonly<Record<string, string>>> {
  return resolveAuthHeaders();
}

/** EventSource cannot send Authorization; append clerk_token or legacy api_key query. */
export async function appendApiKeyQueryForSse(pathOrUrl: string): Promise<string> {
  return appendClerkTokenQueryForSse(pathOrUrl);
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

const DEFAULT_GET_TIMEOUT_MS = 30_000;

export async function apiGet<T>(
  path: string,
  options?: { timeoutMs?: number },
): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_GET_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { Accept: "application/json", ...(await apiAuthHeaders()) },
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new ApiRequestError(
        0,
        `Request timed out after ${timeoutMs / 1000} s — the API may still be busy (e.g. a long agent run). Try again in a moment.`,
      );
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
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

export async function apiPostFormData<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", ...(await apiAuthHeaders()) },
    body: formData,
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
      `Upload failed (${res.status}): ${detail}`,
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
      ...(await apiAuthHeaders()),
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

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(await apiAuthHeaders()),
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

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(await apiAuthHeaders()),
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

export async function apiDelete(path: string): Promise<void> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...(await apiAuthHeaders()),
    },
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
}
