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
  radius_km: number | null;
  /** Random reference this browser keeps; only its hash is stored, and only it can read the status. */
  client_ref: string;
  /** Separate, optional consent to be contacted about testing GeneGuidelines / the community. */
  community: boolean;
};

export type SubscribeResponse = {
  status: string;
  message: string;
  dev_confirm_url?: string | null;
};

export type SubscriptionStatusResponse = {
  status: "pending" | "confirmed" | null;
};

/** The one alert we send: the guideline summary changed. Nothing else is promised, so nothing else is asked for. */
export const SUMMARY_CHANGE_PREFS: AlertPrefsPayload = {
  guidelines: true,
  trials: false,
  therapies: false,
  doctors: false,
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
  ref: string,
): Promise<SubscriptionStatusResponse> {
  const params = new URLSearchParams({ ref });
  return apiGet<SubscriptionStatusResponse>(
    `/api/diseases/${encodeURIComponent(slug)}/subscriptions/status?${params}`,
  );
}
