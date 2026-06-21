import { apiGet, apiPostJson } from "./client";

export type AlertPrefsPayload = {
  guidelines: boolean;
  trials: boolean;
  therapies: boolean;
  doctors: boolean;
};

export type SubscribePayload = {
  email: string;
  prefs: AlertPrefsPayload;
  radius_km: number;
};

export type SubscribeResponse = {
  status: string;
  message: string;
  dev_confirm_url?: string | null;
};

export type SubscriptionStatusResponse = {
  status: "pending" | "confirmed" | null;
};

export async function subscribeToDiseaseAlerts(
  slug: string,
  payload: SubscribePayload,
): Promise<SubscribeResponse> {
  return apiPostJson<SubscribeResponse>(
    `/api/diseases/${encodeURIComponent(slug)}/subscriptions`,
    payload,
  );
}

export async function fetchSubscriptionStatus(
  slug: string,
  email: string,
): Promise<SubscriptionStatusResponse> {
  const params = new URLSearchParams({ email });
  return apiGet<SubscriptionStatusResponse>(
    `/api/diseases/${encodeURIComponent(slug)}/subscriptions/status?${params}`,
  );
}
