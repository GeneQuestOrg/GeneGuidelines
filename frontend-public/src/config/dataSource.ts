export type DataSource = "fixture" | "api";

const VALID_SOURCES: readonly DataSource[] = ["fixture", "api"] as const;

export function getDataSource(): DataSource {
  const raw = import.meta.env.VITE_DATA_SOURCE;
  if (raw === "api") {
    return "api";
  }
  if (raw != null && raw !== "fixture" && raw !== "") {
    return "fixture";
  }
  return "fixture";
}

export function assertValidDataSource(value: string): DataSource {
  if (value === "api" || value === "fixture") {
    return value;
  }
  throw new Error(
    `Invalid VITE_DATA_SOURCE "${value}". Use "fixture" or "api".`,
  );
}

export { VALID_SOURCES };
