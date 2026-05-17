export type PrivateContextStatus = "pending" | "ready" | "failed";

export interface ClinicalFinding {
  readonly text: string;
  readonly category: string;
}

export interface RedactedFacts {
  readonly clinical_findings: readonly ClinicalFinding[];
  readonly interventions: readonly string[];
  readonly mutations: readonly string[];
  readonly outcomes: readonly string[];
  readonly evidence_quality: string;
  readonly pii_tokens_removed: number;
}

export interface PrivateContext {
  readonly id: number;
  readonly diseaseSlug: string;
  readonly originalFilename: string;
  readonly originalChars: number;
  readonly uploadedAt: string;
  readonly redacted: RedactedFacts;
  readonly piiTokensRemoved: number;
  readonly clinicalFactsExtracted: number;
  readonly modelUsed: string;
  readonly status: PrivateContextStatus;
  readonly error: string | null;
}
