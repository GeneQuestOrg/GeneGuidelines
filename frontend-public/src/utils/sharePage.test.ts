import { describe, expect, it } from "vitest";
import { buildEmailShareUrl, buildWhatsAppShareUrl } from "./sharePage";

describe("sharePage", () => {
  it("builds a WhatsApp share URL with encoded text", () => {
    expect(buildWhatsAppShareUrl("Hello world")).toBe(
      "https://wa.me/?text=Hello%20world",
    );
  });

  it("builds a mailto URL with encoded subject and body", () => {
    expect(buildEmailShareUrl("Subject line", "Body text")).toBe(
      "mailto:?subject=Subject%20line&body=Body%20text",
    );
  });
});
