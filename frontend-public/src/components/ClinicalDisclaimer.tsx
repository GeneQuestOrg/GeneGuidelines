import type { AudienceView } from "../router/types";

const COPY: Record<AudienceView, { title: string; body: string }> = {
  doctor: {
    title: "Clinical decision support only",
    body: "This document is evidence-based software output for discussion with your care team. It does not replace independent clinical judgment, institutional protocols, or direct examination of the patient.",
  },
  parent: {
    title: "Informational — not medical advice",
    body: "What you read here is curated from published sources and may be incomplete or outdated. Always confirm diagnosis, treatment, and follow-up with your own clinicians.",
  },
};

export interface ClinicalDisclaimerProps {
  view: AudienceView;
}

export function ClinicalDisclaimer({ view }: ClinicalDisclaimerProps) {
  const c = COPY[view];
  return (
    <aside className="gl__disclaimer" role="note" aria-label={c.title}>
      <strong>{c.title}</strong>
      <p>{c.body}</p>
    </aside>
  );
}
