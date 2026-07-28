import { describe, it, expect } from "vitest";
import { safeAnchorHref } from "./safeAnchorHref";

const fallback = "#";

describe("safeAnchorHref", () => {
  it("keeps in-app hash + relative targets", () => {
    expect(safeAnchorHref("#/choroby/fd", fallback)).toBe("#/choroby/fd");
    expect(safeAnchorHref("/admin", "/")).toBe("/admin");
    expect(safeAnchorHref("docs/page", fallback)).toBe("docs/page");
  });

  it("allows navigable share schemes (the share-with-doctor links)", () => {
    const mailto = "mailto:?subject=Noonan&body=https://x.test/d/noonan";
    const whatsapp = "https://wa.me/?text=Noonan%20https://x.test";
    expect(safeAnchorHref(mailto, fallback)).toBe(mailto);
    expect(safeAnchorHref(whatsapp, fallback)).toBe(whatsapp);
    expect(safeAnchorHref("tel:+48123", fallback)).toBe("tel:+48123");
    expect(safeAnchorHref("http://example.test", fallback)).toBe("http://example.test");
  });

  it("rejects script-injection + protocol-relative URLs", () => {
    expect(safeAnchorHref("javascript:alert(1)", fallback)).toBe(fallback);
    expect(safeAnchorHref("data:text/html,<script>", fallback)).toBe(fallback);
    expect(safeAnchorHref("vbscript:msgbox(1)", fallback)).toBe(fallback);
    expect(safeAnchorHref("//evil.example/path", fallback)).toBe(fallback);
    expect(safeAnchorHref("ftp://host/file", fallback)).toBe(fallback);
  });

  it("falls back for empty / missing", () => {
    expect(safeAnchorHref(undefined, fallback)).toBe(fallback);
    expect(safeAnchorHref("", fallback)).toBe(fallback);
    expect(safeAnchorHref("   ", fallback)).toBe(fallback);
  });
});
