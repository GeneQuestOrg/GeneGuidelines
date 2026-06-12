import { describe, expect, it } from "vitest";
import { cssVar, ROLE_COLOR_TOKENS, USER_MARKER_TOKENS } from "./cssTokens";

describe("cssVar", () => {
  it("returns the literal fallback when the token is undefined", () => {
    // In the node test env there is no document, or the property is unset, so
    // getPropertyValue yields "" — the fallback must be used either way.
    expect(cssVar("--definitely-not-a-real-token", "#abcdef")).toBe("#abcdef");
  });

  it("returns the fallback for every role marker token (none set in test env)", () => {
    for (const { token, fallback } of Object.values(ROLE_COLOR_TOKENS)) {
      expect(cssVar(token, fallback)).toBe(fallback);
    }
  });

  it("returns the fallback for the user marker tokens", () => {
    expect(cssVar(USER_MARKER_TOKENS.stroke.token, USER_MARKER_TOKENS.stroke.fallback)).toBe(
      USER_MARKER_TOKENS.stroke.fallback,
    );
    expect(cssVar(USER_MARKER_TOKENS.fill.token, USER_MARKER_TOKENS.fill.fallback)).toBe(
      USER_MARKER_TOKENS.fill.fallback,
    );
  });
});
