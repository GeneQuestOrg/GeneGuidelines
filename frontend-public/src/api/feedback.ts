import { apiPostJson } from "./client";

export type FeedbackPayload = {
  message: string;
  email?: string;
  context?: string;
};

export type FeedbackResponse = {
  status: string;
  message: string;
};

export async function submitFeedback(payload: FeedbackPayload): Promise<FeedbackResponse> {
  return apiPostJson<FeedbackResponse>("/api/feedback", payload);
}
