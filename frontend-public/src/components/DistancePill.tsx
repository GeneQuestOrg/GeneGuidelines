import { useTranslation } from "react-i18next";
import { formatDistanceKm } from "../utils/geo";

export interface DistancePillProps {
  readonly km: number;
}

export function DistancePill({ km }: DistancePillProps) {
  const { t } = useTranslation("common");
  return (
    <span className="pill pill--dist" title={t("distancePill.title")}>
      {formatDistanceKm(km)}
    </span>
  );
}
