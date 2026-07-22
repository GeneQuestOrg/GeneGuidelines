import { useMemo } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("common");
  const sorted = useMemo(
    () => [...diseases].sort((a, b) => a.name.localeCompare(b.name)),
    [diseases],
  );

  return (
    <div className="filters__field">
      <label htmlFor={id}>{t("diseaseSelect.label")}</label>
      <select
        id={id}
        className="filters__select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={sorted.length === 0}
      >
        {sorted.length === 0 ? (
          <option value="">{t("diseaseSelect.loading")}</option>
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
