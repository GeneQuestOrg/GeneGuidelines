import { fetchSubscriptionStatus } from "../api/subscriptions";
import {
  readStoredSubscriptionRef,
  subscriptionUiFromApiStatus,
  type SubscriptionUiStatus,
} from "./diseaseSubscriptionStorage";

export async function loadSubscriptionUiStatus(slug: string): Promise<SubscriptionUiStatus> {
  const ref = readStoredSubscriptionRef(slug);
  if (ref == null) return "none";
  try {
    const { status } = await fetchSubscriptionStatus(slug, ref);
    return subscriptionUiFromApiStatus(status);
  } catch {
    return "none";
  }
}
