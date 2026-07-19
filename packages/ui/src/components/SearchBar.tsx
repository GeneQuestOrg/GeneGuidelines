import type { ChangeEvent } from "react";
import type { ReactNode } from "react";
import "./search-bar.css";

export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  icon?: ReactNode;
  "aria-label"?: string;
}

export function SearchBar({
  value,
  onChange,
  placeholder = "Search…",
  icon,
  "aria-label": ariaLabel = "Search",
}: SearchBarProps) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value);
  const handleClear = () => onChange("");

  return (
    <div className="search">
      {icon != null && <span className="search__icon" aria-hidden>{icon}</span>}
      <input
        type="text"
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      {value.length > 0 && (
        <button
          type="button"
          className="search__clear"
          onClick={handleClear}
          aria-label="Clear search"
        >
          ×
        </button>
      )}
    </div>
  );
}
