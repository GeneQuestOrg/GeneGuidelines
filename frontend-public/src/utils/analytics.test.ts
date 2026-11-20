import { afterEach, describe, expect, it, vi } from "vitest";
import { trackEvent } from "./analytics";

describe("trackEvent", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is a no-op without the tracker", () => {
    vi.stubGlobal("window", {});
    expect(() => trackEvent("print-fd-tests")).not.toThrow();
  });

  it("sends the named event to Umami", () => {
    const track = vi.fn();
    vi.stubGlobal("window", { umami: { track } });
    trackEvent("share-disease-link", { method: "copy" });
    expect(track).toHaveBeenCalledWith("share-disease-link", { method: "copy" });
  });

  it("never lets a tracker error break the action", () => {
    vi.stubGlobal("window", {
      umami: {
        track: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(() => trackEvent("print-fd-tests")).not.toThrow();
  });
});
