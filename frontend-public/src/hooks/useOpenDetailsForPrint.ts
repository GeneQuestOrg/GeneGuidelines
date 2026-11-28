import { useEffect, type RefObject } from "react";

/**
 * Print every collapsed `<details>` inside `ref` open, then put the page back.
 *
 * A browser prints a closed `<details>` closed: its summary and nothing else. The questions for the doctor are collapsed rows on screen, but a parent prints them to take to the appointment, so on `beforeprint` every closed row under `ref` is opened, and on `afterprint` exactly those rows are closed again; a row the reader had opened stays open. The events fire for Ctrl+P and the browser's menu as well as for `window.print()`. (disease-map.css also shows the rows' content in print where the browser supports `::details-content`, for a print that fires no event.)
 */
export function useOpenDetailsForPrint(ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    let opened: HTMLDetailsElement[] = [];
    const open = () => {
      const root = ref.current;
      if (root == null) {
        return;
      }
      opened = Array.from(root.querySelectorAll("details")).filter((row) => !row.open);
      for (const row of opened) {
        row.open = true;
      }
    };
    const restore = () => {
      for (const row of opened) {
        row.open = false;
      }
      opened = [];
    };
    window.addEventListener("beforeprint", open);
    window.addEventListener("afterprint", restore);
    return () => {
      window.removeEventListener("beforeprint", open);
      window.removeEventListener("afterprint", restore);
    };
  }, [ref]);
}
