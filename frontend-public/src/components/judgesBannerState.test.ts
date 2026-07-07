import { describe, expect, it } from "vitest";
import {
  isBannerState,
  judgesBannerRelevant,
  resolveInitialState,
  shouldRememberKaggleSession,
} from "./judgesBannerState";

describe("isBannerState", () => {
  it("accepts the three valid states", () => {
    expect(isBannerState("ribbon")).toBe(true);
    expect(isBannerState("expanded")).toBe(true);
    expect(isBannerState("pill")).toBe(true);
  });

  it("rejects anything else, including the legacy v2 value", () => {
    expect(isBannerState("collapsed")).toBe(false);
    expect(isBannerState(null)).toBe(false);
    expect(isBannerState("")).toBe(false);
    expect(isBannerState(undefined)).toBe(false);
  });
});

describe("resolveInitialState", () => {
  it("defaults to the ribbon with no signals", () => {
    expect(
      resolveInitialState({ stored: null, fromKaggle: false, sessionFromKaggle: false }),
    ).toBe("ribbon");
  });

  it("starts expanded when ?from=kaggle is present this visit", () => {
    expect(
      resolveInitialState({ stored: null, fromKaggle: true, sessionFromKaggle: false }),
    ).toBe("expanded");
  });

  it("stays expanded for the rest of the session after a ?from=kaggle visit", () => {
    expect(
      resolveInitialState({ stored: null, fromKaggle: false, sessionFromKaggle: true }),
    ).toBe("expanded");
  });

  it("restores a persisted explicit user action", () => {
    expect(
      resolveInitialState({ stored: "pill", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe("pill");
    expect(
      resolveInitialState({ stored: "ribbon", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe("ribbon");
    expect(
      resolveInitialState({ stored: "expanded", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe("expanded");
  });

  it("lets a stored user action beat the ?from=kaggle param", () => {
    // Judge dismissed to a pill earlier; a fresh ?from=kaggle visit must not re-expand.
    expect(
      resolveInitialState({ stored: "pill", fromKaggle: true, sessionFromKaggle: true }),
    ).toBe("pill");
  });

  it("ignores a stale/invalid stored value and falls through to signals", () => {
    expect(
      resolveInitialState({ stored: "collapsed", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe("ribbon");
    expect(
      resolveInitialState({ stored: "garbage", fromKaggle: true, sessionFromKaggle: false }),
    ).toBe("expanded");
  });
});

describe("judgesBannerRelevant", () => {
  it("is false for a fresh family visitor (no Kaggle context)", () => {
    expect(
      judgesBannerRelevant({ stored: null, fromKaggle: false, sessionFromKaggle: false }),
    ).toBe(false);
  });

  it("is true on a ?from=kaggle arrival, a remembered session, or a prior interaction", () => {
    expect(
      judgesBannerRelevant({ stored: null, fromKaggle: true, sessionFromKaggle: false }),
    ).toBe(true);
    expect(
      judgesBannerRelevant({ stored: null, fromKaggle: false, sessionFromKaggle: true }),
    ).toBe(true);
    expect(
      judgesBannerRelevant({ stored: "pill", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe(true);
  });

  it("ignores an invalid stored value", () => {
    expect(
      judgesBannerRelevant({ stored: "garbage", fromKaggle: false, sessionFromKaggle: false }),
    ).toBe(false);
  });
});

describe("shouldRememberKaggleSession", () => {
  it("remembers a fresh ?from=kaggle arrival with no stored action", () => {
    expect(shouldRememberKaggleSession(null, true)).toBe(true);
  });

  it("does not remember when there is no param", () => {
    expect(shouldRememberKaggleSession(null, false)).toBe(false);
  });

  it("does not remember when an explicit user action is already stored", () => {
    expect(shouldRememberKaggleSession("pill", true)).toBe(false);
    expect(shouldRememberKaggleSession("ribbon", true)).toBe(false);
  });

  it("remembers when the stored value is invalid (treated as no action)", () => {
    expect(shouldRememberKaggleSession("collapsed", true)).toBe(true);
  });
});
