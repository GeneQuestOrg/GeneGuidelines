import { fetchSubscriptionStatus } from "../api/subscriptions";
import {
  readStoredSubscriptionEmail,
  type SubscriptionUiStatus,
} from "./diseaseSubscriptionStorage";

export async function loadSubscriptionUiStatus(slug: string): Promise<SubscriptionUiStatus> {
  const email = readStoredSubscriptionEmail(slug);
  if (email == null) return "none";
  try {
    const { status } = await fetchSubscriptionStatus(slug, email);
    if (status === "confirmed") return "confirmed";
    if (status === "pending") return "pending";
    return "none";
  } catch {
    return "none";
  }
}
