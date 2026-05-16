import { describe, it, expect } from "vitest";
import {
  ACCOUNT_STORAGE_KEY,
  FIELD_LIMITS,
  accountSchema,
  fieldTooLong,
  parseStoredAccount,
  trimField,
} from "./accountSchema";

const validAccount = {
  email: "user@example.org",
  name: "Alex",
  role: "parent" as const,
  specialty: null,
  institution: null,
  diseases: [] as string[],
  verified: true,
  joinedAt: "2026-05-15",
};

describe("parseStoredAccount", () => {
  it("parses valid stored account", () => {
    const raw = JSON.stringify(validAccount);
    const account = parseStoredAccount(raw);
    expect(account).toEqual(accountSchema.parse(JSON.parse(raw)));
  });

  it("returns null for invalid JSON", () => {
    expect(parseStoredAccount("not-json")).toBeNull();
  });

  it("rejects tampered role", () => {
    const raw = JSON.stringify({ ...validAccount, role: "admin" });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("rejects oversized name", () => {
    const raw = JSON.stringify({ ...validAccount, name: "x".repeat(101) });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("rejects oversized email", () => {
    const local = `${"a".repeat(243)}@example.org`;
    expect(local.length).toBeGreaterThan(FIELD_LIMITS.email);
    const raw = JSON.stringify({ ...validAccount, email: local });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("rejects oversized specialty", () => {
    const raw = JSON.stringify({ ...validAccount, specialty: "x".repeat(101) });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("rejects oversized institution", () => {
    const raw = JSON.stringify({ ...validAccount, institution: "x".repeat(201) });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("rejects disease slug with invalid characters", () => {
    const raw = JSON.stringify({ ...validAccount, diseases: ["UPPER-CASE"] });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("accepts valid disease slugs", () => {
    const raw = JSON.stringify({ ...validAccount, diseases: ["fibrous-dysplasia", "fd2"] });
    expect(parseStoredAccount(raw)?.diseases).toEqual(["fibrous-dysplasia", "fd2"]);
  });

  it("rejects more than max diseases", () => {
    const diseases = Array.from({ length: FIELD_LIMITS.maxDiseases + 1 }, (_, i) => `d-${i}`);
    const raw = JSON.stringify({ ...validAccount, diseases });
    expect(parseStoredAccount(raw)).toBeNull();
  });

  it("accepts joinedAt format regex but not calendar validation", () => {
    const raw = JSON.stringify({ ...validAccount, joinedAt: "2026-13-45" });
    expect(parseStoredAccount(raw)?.joinedAt).toBe("2026-13-45");
  });
});

describe("trimField", () => {
  it("trims whitespace and caps length", () => {
    expect(trimField("  hello world  ", 5)).toBe("hello");
  });

  it("returns empty string for whitespace-only input", () => {
    expect(trimField("   ", 10)).toBe("");
  });
});

describe("fieldTooLong", () => {
  it("is false when trimmed length equals max", () => {
    expect(fieldTooLong("a".repeat(10), 10)).toBe(false);
  });

  it("is true when trimmed length exceeds max", () => {
    expect(fieldTooLong("a".repeat(11), 10)).toBe(true);
  });

  it("ignores surrounding whitespace when measuring length", () => {
    expect(fieldTooLong(`  ${"a".repeat(11)}  `, 10)).toBe(true);
    expect(fieldTooLong(`  ${"a".repeat(10)}  `, 10)).toBe(false);
  });
});

describe("ACCOUNT_STORAGE_KEY", () => {
  it("matches AuthModal storage key", () => {
    expect(ACCOUNT_STORAGE_KEY).toBe("gg-account");
  });
});
