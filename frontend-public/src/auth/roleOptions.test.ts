import { describe, expect, it } from "vitest";
import {
  ROLE_OPTIONS,
  isPendingVerification,
  shouldShowRolePicker,
} from "./roleOptions";

describe("ROLE_OPTIONS", () => {
  it("offers exactly the three self-selectable roles, excluding superadmin", () => {
    expect(ROLE_OPTIONS.map((o) => o.value)).toEqual([
      "parent",
      "doctor",
      "researcher",
    ]);
  });
});

describe("shouldShowRolePicker", () => {
  it("shows when authenticated with no role", () => {
    expect(shouldShowRolePicker(true, null)).toBe(true);
  });

  it("hides when not authenticated", () => {
    expect(shouldShowRolePicker(false, null)).toBe(false);
  });

  it("hides once a role is set", () => {
    expect(shouldShowRolePicker(true, "parent")).toBe(false);
    expect(shouldShowRolePicker(true, "superadmin")).toBe(false);
  });
});

describe("isPendingVerification", () => {
  it("is true only for unverified doctors", () => {
    expect(isPendingVerification("doctor", false)).toBe(true);
  });

  it("is false for verified doctors", () => {
    expect(isPendingVerification("doctor", true)).toBe(false);
  });

  it("is false for non-doctor roles regardless of verified flag", () => {
    expect(isPendingVerification("parent", false)).toBe(false);
    expect(isPendingVerification("researcher", false)).toBe(false);
    expect(isPendingVerification(null, false)).toBe(false);
  });
});
