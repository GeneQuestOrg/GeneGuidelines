import { useCallback, useState } from "react";

const STORAGE_KEY = "gg-extra-recs";

export type LocalRecRelation = "parent" | "carer";

/** A family recommendation captured on this device, pending moderation (write-path = DOC-5). */
export interface LocalParentRec {
  readonly text: string;
  readonly region: string;
  readonly relation: LocalRecRelation;
  readonly date: string;
}

/** Stored shape: a map of doctor slug → recommendations left on this device. */
type LocalRecStore = Record<string, readonly LocalParentRec[]>;

function isRelation(value: unknown): value is LocalRecRelation {
  return value === "parent" || value === "carer";
}

function sanitizeRec(value: unknown): LocalParentRec | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.text !== "string" || typeof candidate.date !== "string") {
    return null;
  }
  return {
    text: candidate.text,
    region: typeof candidate.region === "string" ? candidate.region : "",
    relation: isRelation(candidate.relation) ? candidate.relation : "parent",
    date: candidate.date,
  };
}

/**
 * Parse the recommendations stored for one doctor from a raw localStorage string. Corrupted or
 * malformed JSON yields an empty list — this never throws.
 */
export function readLocalRecs(
  storageKeyContents: string | null,
  doctorSlug: string,
): readonly LocalParentRec[] {
  if (storageKeyContents == null) {
    return [];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(storageKeyContents);
  } catch {
    return [];
  }
  if (typeof parsed !== "object" || parsed === null) {
    return [];
  }
  const entry = (parsed as Record<string, unknown>)[doctorSlug];
  if (!Array.isArray(entry)) {
    return [];
  }
  return entry
    .map(sanitizeRec)
    .filter((rec): rec is LocalParentRec => rec !== null);
}

/**
 * Append a recommendation for one doctor, returning the next serialized store. Existing recs for
 * other doctors are preserved; corrupted current contents are treated as an empty store.
 */
export function appendLocalRec(
  storageKeyContents: string | null,
  doctorSlug: string,
  rec: LocalParentRec,
): string {
  let store: LocalRecStore = {};
  if (storageKeyContents != null) {
    try {
      const parsed: unknown = JSON.parse(storageKeyContents);
      if (typeof parsed === "object" && parsed !== null) {
        store = parsed as LocalRecStore;
      }
    } catch {
      store = {};
    }
  }
  const current = readLocalRecs(storageKeyContents, doctorSlug);
  return JSON.stringify({ ...store, [doctorSlug]: [...current, rec] });
}

export interface UseLocalParentRecs {
  readonly recs: readonly LocalParentRec[];
  readonly addRec: (rec: LocalParentRec) => void;
}

/**
 * localStorage-backed family recommendations for one doctor. Isolated so DOC-5 can swap the storage
 * for a POST without touching the view. Mirrors the read/write pattern of useAudienceView/useTweaks.
 */
export function useLocalParentRecs(doctorSlug: string): UseLocalParentRecs {
  const [recs, setRecs] = useState<readonly LocalParentRec[]>(() => {
    try {
      return readLocalRecs(localStorage.getItem(STORAGE_KEY), doctorSlug);
    } catch {
      return [];
    }
  });

  const addRec = useCallback(
    (rec: LocalParentRec) => {
      try {
        const next = appendLocalRec(localStorage.getItem(STORAGE_KEY), doctorSlug, rec);
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // ignore — keep optimistic in-memory state below
      }
      setRecs((prev) => [...prev, rec]);
    },
    [doctorSlug],
  );

  return { recs, addRec };
}
