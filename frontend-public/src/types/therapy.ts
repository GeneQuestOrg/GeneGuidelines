export type TherapyStatus =
  | "consensus"
  | "verified"
  | "pending"
  | "preclinical";

export interface Therapy {
  readonly name: string;
  readonly status: TherapyStatus;
  readonly note: string;
  readonly pmids: readonly string[];
}
