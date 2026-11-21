/**
 * Print one part of a page instead of the whole page.
 *
 * Puts `className` on `<html>` for the length of the print dialog; the print stylesheet keyed on that class hides everything else. The class comes off on `afterprint`, or at the visitor's next click or tap if a browser never sends that event, so a later Ctrl+P prints the full page again. No timer: a browser whose `print()` returns before it lays out the page would print the full page if the class came off too early.
 */
export function printOnly(className: string): void {
  const root = document.documentElement;
  root.classList.add(className);
  const done = () => {
    root.classList.remove(className);
    window.removeEventListener("afterprint", done);
    document.removeEventListener("pointerdown", done);
  };
  window.addEventListener("afterprint", done);
  // Registered after the click that started the print has finished, so that click does not count.
  window.setTimeout(() => {
    if (root.classList.contains(className)) {
      document.addEventListener("pointerdown", done);
    }
  }, 0);
  window.print();
}
