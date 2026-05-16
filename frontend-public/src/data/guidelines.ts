import type { GuidelineMeta } from "../types";

export const GUIDELINE_META: Readonly<Record<string, GuidelineMeta>> = {
  fd: {
    diseaseSlug: "fd",
    version: "3.2",
    locale: "en",
    sectionCount: 12,
    lastReviewed: "2026-04-18",
  },
  mas: {
    diseaseSlug: "mas",
    version: "2.1",
    locale: "en",
    sectionCount: 8,
    lastReviewed: "2026-03-02",
  },
  noonan: {
    diseaseSlug: "noonan",
    version: "0.9-draft",
    locale: "en",
    sectionCount: 6,
    lastReviewed: null,
  },
};
