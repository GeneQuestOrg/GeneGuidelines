import { describe, expect, it } from "vitest";
import {
  buildEmailShareUrl,
  buildWhatsAppShareUrl,
  shareMessage,
} from "./sharePage";

describe("sharePage", () => {
  it("builds a WhatsApp share URL with encoded text", () => {
    const url = buildWhatsAppShareUrl("Hello world");
    expect(url).toBe("https://wa.me/?text=Hello%20world");
  });

  it("builds a mailto URL with encoded subject and body", () => {
    const url = buildEmailShareUrl("Subject line", "Body text");
    expect(url).toBe("mailto:?subject=Subject%20line&body=Body%20text");
  });

  it("formats a share message with disease name and link", () => {
    expect(shareMessage("Rett syndrome", "https://example.com/#/diseases/rett/guidelines")).toBe(
      "I wanted to share this guideline summary for Rett syndrome with you: https://example.com/#/diseases/rett/guidelines",
    );
  });
});
