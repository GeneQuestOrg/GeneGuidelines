import { describe, it, expect } from "vitest";
import { safeBrandHref } from "./safeBrandHref";

/** Keep in sync with backend/tests/test_safe_brand_href.py */
describe("safeBrandHref", () => {
  const fallback = "#/";

  it("allows hash and same-origin relative paths", () => {
    expect(safeBrandHref("#/choroby/fd", fallback)).toBe("#/choroby/fd");
    expect(safeBrandHref("/admin", "/")).toBe("/admin");
  });

  it("rejects unsafe protocols and external URLs", () => {
    expect(safeBrandHref("javascript:alert(1)", fallback)).toBe(fallback);
    expect(safeBrandHref("data:text/html,<script>", fallback)).toBe(fallback);
    expect(safeBrandHref("vbscript:msgbox(1)", fallback)).toBe(fallback);
    expect(safeBrandHref("https://evil.example", fallback)).toBe(fallback);
    expect(safeBrandHref("//evil.example/path", fallback)).toBe(fallback);
  });

  it("uses fallback for empty or missing href", () => {
    expect(safeBrandHref(undefined, fallback)).toBe(fallback);
    expect(safeBrandHref("", fallback)).toBe(fallback);
    expect(safeBrandHref("   ", fallback)).toBe(fallback);
  });
});
