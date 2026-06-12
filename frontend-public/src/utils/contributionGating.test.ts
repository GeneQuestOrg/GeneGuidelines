import { describe, it, expect } from "vitest";
import {
  addDoctorCtaMode,
  recFormMode,
  submitReducer,
  type SubmitState,
} from "./contributionGating";

describe("addDoctorCtaMode — env gate", () => {
  it("hidden when Auth0 unset (today's behaviour, byte-for-byte)", () => {
    expect(
      addDoctorCtaMode({ signInAvailable: false, isAuthenticated: false, role: null }),
    ).toBe("hidden");
    // Even an authenticated parent is hidden when the gate is off.
    expect(
      addDoctorCtaMode({ signInAvailable: false, isAuthenticated: true, role: "parent" }),
    ).toBe("hidden");
  });

  it("sign-in when Auth0 on and signed-out", () => {
    expect(
      addDoctorCtaMode({ signInAvailable: true, isAuthenticated: false, role: null }),
    ).toBe("sign-in");
  });

  it("open-modal for a signed-in parent or superadmin", () => {
    expect(
      addDoctorCtaMode({ signInAvailable: true, isAuthenticated: true, role: "parent" }),
    ).toBe("open-modal");
    expect(
      addDoctorCtaMode({ signInAvailable: true, isAuthenticated: true, role: "superadmin" }),
    ).toBe("open-modal");
  });

  it("hidden for a signed-in non-contributor (researcher/doctor)", () => {
    expect(
      addDoctorCtaMode({ signInAvailable: true, isAuthenticated: true, role: "researcher" }),
    ).toBe("hidden");
  });
});

describe("recFormMode — env gate", () => {
  it("local (localStorage echo) when Auth0 unset", () => {
    expect(
      recFormMode({ signInAvailable: false, isAuthenticated: false, role: null }),
    ).toBe("local");
  });

  it("post for a signed-in parent when Auth0 on", () => {
    expect(
      recFormMode({ signInAvailable: true, isAuthenticated: true, role: "parent" }),
    ).toBe("post");
  });

  it("sign-in when Auth0 on and signed-out", () => {
    expect(
      recFormMode({ signInAvailable: true, isAuthenticated: false, role: null }),
    ).toBe("sign-in");
  });

  it("not-allowed for a signed-in non-contributor", () => {
    expect(
      recFormMode({ signInAvailable: true, isAuthenticated: true, role: "doctor" }),
    ).toBe("not-allowed");
  });
});

describe("submitReducer — AddDoctorModal state machine", () => {
  const editing: SubmitState = { status: "editing" };

  it("editing → submitting on submit", () => {
    expect(submitReducer(editing, { type: "submit" })).toEqual({ status: "submitting" });
  });

  it("submitting → submitted on success (carrying possibleDuplicate)", () => {
    const submitting = submitReducer(editing, { type: "submit" });
    expect(submitReducer(submitting, { type: "success", possibleDuplicate: true })).toEqual({
      status: "submitted",
      possibleDuplicate: true,
    });
  });

  it("submitting → error on failure", () => {
    const submitting = submitReducer(editing, { type: "submit" });
    expect(submitReducer(submitting, { type: "failure", message: "boom" })).toEqual({
      status: "error",
      message: "boom",
    });
  });

  it("error → submitting on a fresh submit (retry)", () => {
    const errored: SubmitState = { status: "error", message: "boom" };
    expect(submitReducer(errored, { type: "submit" })).toEqual({ status: "submitting" });
  });

  it("ignores a duplicate submit while already in flight", () => {
    const submitting: SubmitState = { status: "submitting" };
    expect(submitReducer(submitting, { type: "submit" })).toBe(submitting);
  });

  it("ignores submit after a successful submission", () => {
    const submitted: SubmitState = { status: "submitted", possibleDuplicate: false };
    expect(submitReducer(submitted, { type: "submit" })).toBe(submitted);
  });

  it("ignores a late success/failure that is not in flight", () => {
    expect(submitReducer(editing, { type: "success", possibleDuplicate: false })).toBe(editing);
    expect(submitReducer(editing, { type: "failure", message: "x" })).toBe(editing);
  });
});
