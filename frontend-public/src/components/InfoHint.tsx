import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import "./info-hint.css";

export interface InfoHintProps {
  /** Visible trigger text, e.g. "(growing)". */
  label: ReactNode;
  /** Tooltip body. */
  children: ReactNode;
  /** Accessible name for the trigger when the label alone is not descriptive. */
  ariaLabel?: string;
}

/**
 * Small accessible info hint. Replaces the native `title` attribute, which is
 * slow (browser-imposed ~1s delay) and never opens on click/tap — so on touch
 * devices it looks broken. This opens instantly on hover (pointer devices),
 * on keyboard focus, and on click/tap (which pins it open until dismissed).
 */
export function InfoHint({ label, children, ariaLabel }: InfoHintProps) {
  const [pinned, setPinned] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipId = useId();

  // While pinned (clicked/tapped open), dismiss on outside pointer or Escape.
  useEffect(() => {
    if (!pinned) return;
    const onPointerDown = (e: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setPinned(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinned(false);
        // Drop focus too, or :focus-within keeps the bubble visible.
        btnRef.current?.blur();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [pinned]);

  return (
    <span ref={wrapRef} className={`info-hint${pinned ? " is-pinned" : ""}`}>
      <button
        ref={btnRef}
        type="button"
        className="info-hint__trigger"
        aria-label={ariaLabel}
        aria-expanded={pinned}
        aria-describedby={tipId}
        onClick={(e) => {
          const next = !pinned;
          setPinned(next);
          // Drop focus on close so :focus-within does not keep it visible.
          if (!next) e.currentTarget.blur();
        }}
      >
        {label}
      </button>
      <span role="tooltip" id={tipId} className="info-hint__bubble">
        {children}
      </span>
    </span>
  );
}
