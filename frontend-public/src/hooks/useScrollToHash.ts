import { useEffect } from "react";

/** Open the element the address's fragment names (a collapsed `<details>` is opened) and scroll it into view. */
function revealHashTarget(): void {
  const raw = window.location.hash.slice(1);
  if (!raw || raw.startsWith("/")) {
    return; // no fragment, or an old hash-router address (main.tsx rewrites those)
  }
  let id = raw;
  try {
    id = decodeURIComponent(raw);
  } catch {
    // A malformed escape is looked up as written.
  }
  const target = document.getElementById(id);
  if (target == null) {
    return;
  }
  if (target instanceof HTMLDetailsElement) {
    target.open = true;
  }
  target.scrollIntoView({ block: "start" });
}

/**
 * Honour a `#fragment` on a page whose content arrives after the first render.
 *
 * The browser scrolls to a fragment once, when the document loads; on these pages the target does not exist yet at that moment (it is built from API data), and an in-app navigation does not scroll at all. So once `ready` turns true — the content that holds the targets is on screen — this does what the browser would have done, and does it again whenever the fragment changes on the same page.
 */
export function useScrollToHash(ready: boolean): void {
  useEffect(() => {
    if (!ready) {
      return;
    }
    revealHashTarget();
    window.addEventListener("hashchange", revealHashTarget);
    return () => window.removeEventListener("hashchange", revealHashTarget);
  }, [ready]);
}
