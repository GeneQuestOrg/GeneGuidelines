export interface FilterChipItem {
  readonly value: string;
  readonly label: string;
}

export interface FilterChipsProps {
  readonly items: readonly FilterChipItem[];
  readonly active: string;
  readonly onPick: (value: string) => void;
  readonly ariaLabel: string;
}

export function FilterChips({ items, active, onPick, ariaLabel }: FilterChipsProps) {
  return (
    <div className="chip-row" role="group" aria-label={ariaLabel}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          className={`chip chip--btn${active === item.value ? " is-active" : ""}`}
          aria-pressed={active === item.value}
          onClick={() => onPick(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
