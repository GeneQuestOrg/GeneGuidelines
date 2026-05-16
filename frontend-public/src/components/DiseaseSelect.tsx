import { useMemo } from "react";
import type { Disease } from "../types";

export interface DiseaseSelectProps {
  readonly diseases: readonly Disease[];
  readonly value: string;
  readonly onChange: (slug: string) => void;
  readonly id?: string;
}

export function DiseaseSelect({
  diseases,
  value,
  onChange,
  id = "doctors-disease",
}: DiseaseSelectProps) {
  const sorted = useMemo(
    () => [...diseases].sort((a, b) => a.name.localeCompare(b.name)),
    [diseases],
  );

  return (
    <div className="filters__field">
      <label htmlFor={id}>Select disease</label>
      <select
        id={id}
        className="filters__select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={sorted.length === 0}
      >
        {sorted.length === 0 ? (
          <option value="">Loading diseases…</option>
        ) : (
          sorted.map((disease) => (
            <option key={disease.slug} value={disease.slug}>
              {disease.name} ({disease.nameShort})
            </option>
          ))
        )}
      </select>
    </div>
  );
}
