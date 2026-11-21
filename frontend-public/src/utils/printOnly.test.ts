// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { printOnly } from "./printOnly";

describe("printOnly", () => {
  afterEach(() => {
    document.documentElement.className = "";
    vi.restoreAllMocks();
  });

  it("marks the page for the length of the print dialog and clears it on afterprint", () => {
    let classDuringPrint = false;
    vi.spyOn(window, "print").mockImplementation(() => {
      classDuringPrint = document.documentElement.classList.contains("print-fd-tests");
      window.dispatchEvent(new Event("afterprint"));
    });

    printOnly("print-fd-tests");

    expect(classDuringPrint).toBe(true);
    expect(document.documentElement.classList.contains("print-fd-tests")).toBe(false);
  });

  it("clears the mark at the next click when a browser never sends afterprint", async () => {
    vi.spyOn(window, "print").mockImplementation(() => {});

    printOnly("print-fd-tests");
    expect(document.documentElement.classList.contains("print-fd-tests")).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 0));
    document.dispatchEvent(new Event("pointerdown"));
    expect(document.documentElement.classList.contains("print-fd-tests")).toBe(false);
  });
});
