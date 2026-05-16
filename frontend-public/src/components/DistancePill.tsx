import { formatDistanceKm } from "../utils/geo";

export interface DistancePillProps {
  readonly km: number;
}

export function DistancePill({ km }: DistancePillProps) {
  return (
    <span
      className="pill pill--dist"
      title="Distance from your selected reference location (city in settings)"
    >
      {formatDistanceKm(km)}
    </span>
  );
}
