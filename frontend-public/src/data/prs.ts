import type { ContentPrSummary } from "../types";

export const CONTENT_PRS: readonly ContentPrSummary[] = [
  // Deliberately empty. This used to hold five AI-authored change requests presented
  // as "under review" / "pending" by a specialist network that does not exist — one
  // of them a paediatric denosumab dosing schedule. Fixtures must not invent a
  // review process. See backend/guidelines/seed.py for the same decision server-side.
] as const;
