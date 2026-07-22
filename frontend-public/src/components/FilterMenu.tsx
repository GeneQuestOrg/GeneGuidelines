import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface FilterMenuOption {
  readonly value: string;
  readonly label: string;
}

export interface FilterMenuProps {
  /** Static prefix shown before the current value (e.g. "Experience"). */
  readonly label: string;
  /** Currently selected option value; the neutral value renders the inactive style. */
  readonly value: string;
  readonly options: readonly FilterMenuOption[];
  readonly onPick: (value: string) => void;
  /** Value treated as "no filter applied" for the active style. Defaults to "all". */
  readonly neutralValue?: string;
}

const ALL_VALUE = "all";

/**
 * Compact "Google-Flights-style" dropdown filter: a pill button showing
 * ``label · value`` that opens a popover listbox. Closes on outside mousedown
 * and Escape; the button reads active whenever ``value`` is not the neutral value
 * (default "all"). A control with no neutral state (e.g. Sort) passes its default
 * as ``neutralValue`` so the pill does not look perpetually active.
 */
export function FilterMenu({
  label,
  value,
  options,
  onPick,
  neutralValue = ALL_VALUE,
}: FilterMenuProps) {
  const { t } = useTranslation("common");
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
  const active = value !== neutralValue;

  return (
    <div className="fmenu" ref={ref}>
      <button
        type="button"
        className={`fmenu__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="fmenu__label">{label}</span>
        <span className="fmenu__value">{current?.label ?? t("filterMenu.all")}</span>
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
