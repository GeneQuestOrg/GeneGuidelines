// Medical-safety: the backend derives the served status from PMID-presence, not
// from the stored evidence tier. A row with >=1 source PMID serves "sourced"
// ("AI draft — source-backed") plus its `pmids`; a row with none serves
// "unverified". The evidence-tier values are kept in the union for reversibility
// / older payloads, but the live API only ever sends "unverified" or "sourced".
export type TherapyStatus =
  | "unverified"
  | "sourced"
  | "consensus"
  | "verified"
  | "pending"
  | "preclinical";

export interface Therapy {
  readonly name: string;
  readonly status: TherapyStatus;
  readonly note: string;
  // PubMed IDs backing this therapy line (provenance). Empty when the row has no
  // source on file yet — then `status` is "unverified".
  readonly pmids: readonly string[];
}
