import type { ReactNode } from "react";
import "./chip.css";

export type BadgeVariant = "default" | "ok";

export interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = "default", className = "" }: BadgeProps) {
  const cls = [
    "chip",
    variant === "ok" ? "chip--ok" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <span className={cls}>{children}</span>;
}
