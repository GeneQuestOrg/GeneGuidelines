// Medical-safety: the backend now serves every therapy row as "unverified"
// (the surface has no provenance, so no evidence tier can be shown honestly).
// The evidence-tier values are kept in the union for reversibility / older
// payloads, but the live API only ever sends "unverified".
export type TherapyStatus =
  | "unverified"
  | "consensus"
  | "verified"
  | "pending"
  | "preclinical";

export interface Therapy {
  readonly name: string;
  readonly status: TherapyStatus;
  readonly note: string;
}
