import type { ReactNode } from "react";

const VARIANT_STYLES: Record<string, { bg: string; color: string }> = {
  requested: { bg: "#fef3c7", color: "#d97706" },
  in_progress: { bg: "#dbeafe", color: "#2563eb" },
  pr_created: { bg: "#e0e7ff", color: "#4338ca" },
  merged: { bg: "#d1fae5", color: "#059669" },
  enabled: { bg: "#ede9fe", color: "#7c3aed" },
  strict: { bg: "#fee2e2", color: "#dc2626" },
  operational: { bg: "#dbeafe", color: "#1e40af" },
  builder: { bg: "#ede9fe", color: "#6d28d9" },
};

interface BadgeProps {
  variant: keyof typeof VARIANT_STYLES | string;
  children: ReactNode;
}

export function Badge({ variant, children }: BadgeProps) {
  const s = VARIANT_STYLES[variant] ?? VARIANT_STYLES.requested;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        borderRadius: 999,
        padding: "3px 10px",
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}
