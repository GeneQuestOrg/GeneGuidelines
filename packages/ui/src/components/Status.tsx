import "./status.css";

export type StatusValue =
  | "pending"
  | "under-review"
  | "verified"
  | "consensus"
  | "superseded"
  | "rejected"
  | "live";

interface StatusMeta {
  label: string;
  dot: string;
  text: string;
  pulse?: boolean;
}

const STATUS_META: Record<StatusValue, StatusMeta> = {
  pending: { label: "Source-backed", dot: "var(--st-slate)", text: "AI-drafted from cited peer-reviewed sources — read with a clinician; not an official guideline." },
  "under-review": { label: "Under review", dot: "var(--st-amber)", text: "Submitted for review, awaiting decision" },
  verified: { label: "Verified", dot: "var(--st-green)", text: "Approved by a specialist" },
  consensus: { label: "Consensus", dot: "var(--st-blue)", text: "Approved by ≥2 specialists" },
  superseded: { label: "Superseded", dot: "var(--st-orange)", text: "A newer version exists" },
  rejected: { label: "Rejected", dot: "var(--st-slate)", text: "Rejected by reviewer" },
  live: { label: "Live", dot: "var(--st-green)", text: "Running", pulse: true },
};

export interface StatusProps {
  status: StatusValue;
  /** Optional revision date shown after the label (draft12: label + optional date — no names channel). */
  date?: string;
  compact?: boolean;
}

export function Status({ status, date, compact = false }: StatusProps) {
  const m = STATUS_META[status] ?? STATUS_META.pending;
  return (
    <span
      className={`status status--${status}${compact ? " status--compact" : ""}`}
      title={m.text}
    >
      <span className="status__dot" style={{ background: m.dot }} aria-hidden />
      <span className="status__label">{m.label}</span>
      {date != null && !compact ? <span className="status__date">{" · " + date}</span> : null}
    </span>
  );
}
