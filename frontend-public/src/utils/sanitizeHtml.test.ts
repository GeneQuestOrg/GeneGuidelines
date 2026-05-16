/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { sanitizeGuidelineHtml } from "./sanitizeHtml";

describe("sanitizeGuidelineHtml", () => {
  it("returns empty for blank input", () => {
    expect(sanitizeGuidelineHtml("")).toBe("");
    expect(sanitizeGuidelineHtml(undefined)).toBe("");
  });

  it("allows safe tags and strips scripts", () => {
    const html = '<p>Hello <strong>world</strong></p><script>alert(1)</script>';
    const out = sanitizeGuidelineHtml(html);
    expect(out).toContain("<strong>world</strong>");
    expect(out).not.toContain("script");
    expect(out).not.toContain("alert");
  });
});
