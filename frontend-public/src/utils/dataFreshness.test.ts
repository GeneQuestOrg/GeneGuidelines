import { describe, expect, it } from "vitest";
import { formatDataDate, isDataDate, newestDataAsOf } from "./dataFreshness";

describe("isDataDate", () => {
  it("accepts an exact calendar day", () => {
    expect(isDataDate("2026-11-12")).toBe(true);
  });

  it.each([
    ["", "empty"],
    ["2026-11", "a month"],
    ["2026-11-12T08:30:00Z", "a timestamp"],
    ["12.11.2026", "an already-formatted date"],
    ["2026-02-31", "a day that does not exist"],
    ["2026-13-01", "a month that does not exist"],
    ["not a date", "free text"],
  ])("rejects %s (%s)", (value) => {
    expect(isDataDate(value)).toBe(false);
  });

  it("rejects null and undefined", () => {
    expect(isDataDate(null)).toBe(false);
    expect(isDataDate(undefined)).toBe(false);
  });
});

describe("newestDataAsOf", () => {
  it("returns the most recent date in the set", () => {
    expect(
      newestDataAsOf([
        { dataAsOf: "2026-06-25" },
        { dataAsOf: "2026-09-06" },
        { dataAsOf: "2026-07-18" },
      ]),
    ).toBe("2026-09-06");
  });

  it("ignores rows with no date instead of guessing one", () => {
    expect(newestDataAsOf([{ dataAsOf: null }, { dataAsOf: "2026-09-06" }, {}])).toBe(
      "2026-09-06",
    );
  });

  it("returns null when nothing in the set is dated", () => {
    // The curated-seed case: real doctors, no event behind them to date. The page must
    // then show no date at all rather than fall back to today or to a deploy time.
    expect(newestDataAsOf([{ dataAsOf: null }, {}])).toBeNull();
    expect(newestDataAsOf([])).toBeNull();
  });

  it("ignores a malformed date rather than showing it", () => {
    expect(newestDataAsOf([{ dataAsOf: "whenever" }])).toBeNull();
  });
});

describe("formatDataDate", () => {
  it("uses the reader's own convention", () => {
    expect(formatDataDate("2026-11-12", "pl")).toBe("12.11.2026");
    expect(formatDataDate("2026-11-12", "en-US")).toBe("11/12/2026");
  });

  it("does not shift the day into the reader's timezone", () => {
    // Formatted in UTC: a reader in Los Angeles must not be told the search ran a day
    // earlier than it did.
    expect(formatDataDate("2026-01-01", "pl")).toBe("01.01.2026");
  });

  it("returns null for anything that is not a real date", () => {
    expect(formatDataDate(null, "pl")).toBeNull();
    expect(formatDataDate("", "pl")).toBeNull();
    expect(formatDataDate("2026-02-31", "pl")).toBeNull();
  });
});
