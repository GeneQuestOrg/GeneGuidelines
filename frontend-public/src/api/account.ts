import { apiDelete, apiGet, apiPatch, apiPostJson, apiPut } from "./client";

export interface RunQuota {
  unlimited: boolean;
  used: number;
  limit: number | null;
  remaining: number | null;
  window_hours: number;
}

export interface MeResponse {
  clerk_id: string;
  email: string | null;
  role: "user" | "admin";
  run_quota: RunQuota;
  audience_view: "parent" | "doctor" | null;
  notify_run_email: boolean;
  unread_notifications_count: number;
}

export async function fetchMe(): Promise<MeResponse> {
  return apiGet<MeResponse>("/api/me");
}

export interface WatchedDisease {
  disease_slug: string;
  name_short: string | null;
  disease_status: string | null;
  active_run_id: string | null;
  last_run_id: string | null;
  last_run_at: string | null;
  watched_at: string;
}

export async function fetchWatches(): Promise<readonly WatchedDisease[]> {
  return apiGet<readonly WatchedDisease[]>("/api/account/watches");
}

export async function watchDisease(slug: string): Promise<WatchedDisease> {
  return apiPut<WatchedDisease>(
    "/api/account/watches/" + encodeURIComponent(slug),
    {},
  );
}

export async function unwatchDisease(slug: string): Promise<void> {
  return apiDelete("/api/account/watches/" + encodeURIComponent(slug));
}

export interface NotificationItem {
  id: number;
  execution_id: string;
  disease_slug: string | null;
  flow_key: string | null;
  label: string | null;
  status: "completed" | "failed";
  created_at: string;
  read_at: string | null;
}

export async function fetchNotifications(opts?: {
  unreadOnly?: boolean;
  limit?: number;
}): Promise<readonly NotificationItem[]> {
  const params = new URLSearchParams();
  if (opts?.unreadOnly === true) {
    params.set("unread_only", "true");
  }
  if (opts?.limit != null) {
    params.set("limit", String(opts.limit));
  }
  const qs = params.toString();
  return apiGet<readonly NotificationItem[]>(
    `/api/account/notifications${qs.length > 0 ? `?${qs}` : ""}`,
  );
}

export async function markNotificationsRead(opts: {
  ids?: readonly number[];
  all?: boolean;
}): Promise<void> {
  await apiPostJson<{ updated: number }>(
    "/api/account/notifications/mark-read",
    opts,
  );
}

export async function patchAudienceView(
  view: "parent" | "doctor" | null,
): Promise<MeResponse> {
  return apiPatch<MeResponse>("/api/me", { audience_view: view });
}
