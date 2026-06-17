import { describe, expect, it } from "vitest";
import type { MeAccount } from "../types/account";
import {
  audienceForRole,
  canRate,
  isClinicianView,
  isParentSide,
  isPreviewRole,
  resolveRole,
} from "./resolveRole";

function acct(role: MeAccount["role"], verified = false): MeAccount {
  return {
    id: "u1",
    email: "u@example.org",
    displayName: null,
    role,
    verified,
    orcid: null,
    institution: null,
  };
}

describe("resolveRole", () => {
  it("anonymous when not authenticated", () => {
    expect(resolveRole(null, "auto", false)).toBe("anon");
    expect(resolveRole(acct("parent"), "auto", false)).toBe("anon");
  });

  it("maps the authenticated account role", () => {
    expect(resolveRole(acct("parent"), "auto", true)).toBe("parent");
    expect(resolveRole(acct(null), "auto", true)).toBe("parent");
    expect(resolveRole(acct("doctor", true), "auto", true)).toBe("doctor");
    expect(resolveRole(acct("doctor", false), "auto", true)).toBe("doctor-unverified");
    expect(resolveRole(acct("researcher"), "auto", true)).toBe("researcher");
    expect(resolveRole(acct("superadmin"), "auto", true)).toBe("researcher");
  });

  it("lets superadmin view-as override in production", () => {
    expect(resolveRole(acct("superadmin"), "auto", true, "parent")).toBe("parent");
    expect(resolveRole(acct("superadmin"), "auto", true, "doctor")).toBe("doctor");
    expect(resolveRole(acct("superadmin"), "auto", true, "anon")).toBe("anon");
  });

  it("honors a dev previewRole override (ignored in production builds)", () => {
    const expected = import.meta.env.DEV ? "doctor" : "anon";
    expect(resolveRole(null, "doctor", false)).toBe(expected);
    const expectedResearcher = import.meta.env.DEV ? "researcher" : "parent";
    expect(resolveRole(acct("parent"), "researcher", true)).toBe(expectedResearcher);
  });
});

describe("role helpers", () => {
  it("isClinicianView / isParentSide partition the roles", () => {
    expect(isClinicianView("doctor")).toBe(true);
    expect(isClinicianView("doctor-unverified")).toBe(true);
    expect(isClinicianView("researcher")).toBe(true);
    expect(isClinicianView("parent")).toBe(false);
    expect(isClinicianView("anon")).toBe(false);
    expect(isParentSide("anon")).toBe(true);
    expect(isParentSide("parent")).toBe(true);
    expect(isParentSide("doctor")).toBe(false);
  });

  it("canRate only for verified clinicians", () => {
    expect(canRate("doctor")).toBe(true);
    expect(canRate("researcher")).toBe(true);
    expect(canRate("doctor-unverified")).toBe(false);
    expect(canRate("parent")).toBe(false);
    expect(canRate("anon")).toBe(false);
  });

  it("audienceForRole collapses to the two-value copy audience", () => {
    expect(audienceForRole("anon")).toBe("parent");
    expect(audienceForRole("parent")).toBe("parent");
    expect(audienceForRole("doctor")).toBe("doctor");
    expect(audienceForRole("doctor-unverified")).toBe("doctor");
    expect(audienceForRole("researcher")).toBe("doctor");
  });

  it("isPreviewRole validates persisted tweak values", () => {
    expect(isPreviewRole("auto")).toBe(true);
    expect(isPreviewRole("doctor-unverified")).toBe(true);
    expect(isPreviewRole("nonsense")).toBe(false);
    expect(isPreviewRole(undefined)).toBe(false);
  });
});
