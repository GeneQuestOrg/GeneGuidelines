/**
 * How old the data on screen is — and only when something real says so.
 *
 * Every date here comes from an event the backend recorded: the literature search that
 * produced a doctor row, the day a synthesis was written. None of them is a deploy time,
 * a request time, or a review date — nobody reviews these entries (ADR 008), so the copy
 * that renders these values must never say "reviewed" or "verified".
 *
 * A wrong date on medical data is worse than no date, so anything that is not an exact
 * `YYYY-MM-DD` the calendar agrees with returns null and the caller renders nothing.
 */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The row shape these helpers need — anything carrying an optional data date. */
export interface HasDataAsOf {
  readonly dataAsOf?: string | null;
}

/** True when `value` is an exact `YYYY-MM-DD` that denotes a real calendar day. */
export function isDataDate(value: string | null | undefined): value is string {
  if (typeof value !== "string" || !ISO_DATE.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return false;
  }
  // Rejects the dates the Date constructor silently rolls over ("2026-02-31" → 3 March).
  return parsed.toISOString().slice(0, 10) === value;
}

/**
 * The most recent data date across a set of rows, or null when none carries one.
 *
 * Newest rather than oldest because it answers "when did we last touch this": the catalog
 * is refreshed per disease, so a mixed set has no single age. Callers that show one date
 * for a mixed set must say what it covers.
 */
export function newestDataAsOf(rows: readonly HasDataAsOf[]): string | null {
  let newest: string | null = null;
  for (const row of rows) {
    const value = row.dataAsOf;
    if (isDataDate(value) && (newest === null || value > newest)) {
      newest = value;
    }
  }
  return newest;
}

/**
 * Render a data date in the reader's own convention ("12.11.2026" in Polish,
 * "11/12/2026" in English), or null when there is nothing real to show.
 *
 * Formatted in UTC: the stored date is the calendar day the event happened, and shifting
 * it into the reader's timezone would show the day before for anyone west of Greenwich.
 */
export function formatDataDate(
  value: string | null | undefined,
  locale: string,
): string | null {
  if (!isDataDate(value)) {
    return null;
  }
  try {
    return new Intl.DateTimeFormat(locale || "en", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: "UTC",
    }).format(new Date(`${value}T00:00:00Z`));
  } catch {
    // An unknown locale tag must not blank the page; the ISO form is still readable.
    return value;
  }
}
