import { useEffect, useRef, useState } from "react";

export interface FilterMenuOption {
  readonly value: string;
  readonly label: string;
}

export interface FilterMenuProps {
  /** Static prefix shown before the current value (e.g. "Experience"). */
  readonly label: string;
  /** Currently selected option value; "all" renders the inactive style. */
  readonly value: string;
  readonly options: readonly FilterMenuOption[];
  readonly onPick: (value: string) => void;
}

const ALL_VALUE = "all";

/**
 * Compact "Google-Flights-style" dropdown filter: a pill button showing
 * ``label · value`` that opens a popover listbox. Closes on outside mousedown
 * and Escape; the button reads active whenever ``value`` is not "all".
 */
export function FilterMenu({ label, value, options, onPick }: FilterMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = options.find((o) => o.value === value);
  const active = value !== ALL_VALUE;

  return (
    <div className="fmenu" ref={ref}>
      <button
        type="button"
        className={`fmenu__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="fmenu__label">{label}</span>
        <span className="fmenu__value">{current?.label ?? "All"}</span>
        <span className={`fmenu__chev${open ? " is-open" : ""}`} aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <div className="fmenu__pop" role="listbox">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              className={`fmenu__opt${o.value === value ? " is-sel" : ""}`}
              onClick={() => {
                onPick(o.value);
                setOpen(false);
              }}
            >
              <span>{o.label}</span>
              {o.value === value ? (
                <span className="fmenu__check" aria-hidden="true">
                  ✓
                </span>
              ) : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
