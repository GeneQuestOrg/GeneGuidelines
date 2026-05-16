import { useCallback, useEffect, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  fetchDiseaseGuidelinePromptProfile,
  updateDiseaseGuidelinePromptProfile,
  type GuidelinePromptProfile,
} from "../api/client";
import { invalidateContentDiseasesCache } from "../api/diseaseCatalogCache";

const EMPTY_PROFILE: GuidelinePromptProfile = {
  clinicalFraming: "",
  pubmedRetrieval: "",
  synthesisEmphasis: "",
  homonymsToAvoid: [],
  preferredTerms: [],
};

function linesToList(raw: string): string[] {
  return raw
    .split(/\n|,/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function listToLines(items: string[]): string {
  return items.join("\n");
}

export interface GuidelinePromptEditorProps {
  diseaseSlug: string;
}

export function GuidelinePromptEditor({ diseaseSlug }: GuidelinePromptEditorProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<GuidelinePromptProfile>(EMPTY_PROFILE);
  const [homonymsRaw, setHomonymsRaw] = useState("");
  const [termsRaw, setTermsRaw] = useState("");

  const load = useCallback(async () => {
    if (!diseaseSlug) return;
    setLoading(true);
    setError(null);
    try {
      const p = await fetchDiseaseGuidelinePromptProfile(diseaseSlug);
      setProfile(p);
      setHomonymsRaw(listToLines(p.homonymsToAvoid));
      setTermsRaw(listToLines(p.preferredTerms));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [diseaseSlug]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [load, open]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload: GuidelinePromptProfile = {
        ...profile,
        homonymsToAvoid: linesToList(homonymsRaw),
        preferredTerms: linesToList(termsRaw),
      };
      await updateDiseaseGuidelinePromptProfile(diseaseSlug, payload);
      invalidateContentDiseasesCache();
      setProfile(payload);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!diseaseSlug) return null;

  return (
    <div className="ops-prompt-editor">
      <button
        type="button"
        className="ops-prompt-editor__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Hide" : "Edit"} disease-specific prompts
      </button>
      {open ? (
        <div className="ops-prompt-editor__body">
          {loading ? <p className="ops-field__hint">Loading prompt profile…</p> : null}
          <div className="ops-field">
            <label htmlFor="gg-clinical-framing">Clinical framing</label>
            <textarea
              id="gg-clinical-framing"
              rows={4}
              value={profile.clinicalFraming}
              onChange={(ev) =>
                setProfile((p) => ({ ...p, clinicalFraming: ev.target.value }))
              }
            />
          </div>
          <div className="ops-field">
            <label htmlFor="gg-pubmed">PubMed retrieval notes</label>
            <textarea
              id="gg-pubmed"
              rows={3}
              value={profile.pubmedRetrieval}
              onChange={(ev) =>
                setProfile((p) => ({ ...p, pubmedRetrieval: ev.target.value }))
              }
            />
          </div>
          <div className="ops-field">
            <label htmlFor="gg-synthesis">Synthesis emphasis</label>
            <textarea
              id="gg-synthesis"
              rows={3}
              value={profile.synthesisEmphasis}
              onChange={(ev) =>
                setProfile((p) => ({ ...p, synthesisEmphasis: ev.target.value }))
              }
            />
          </div>
          <div className="ops-field">
            <label htmlFor="gg-homonyms">Homonyms to avoid (one per line)</label>
            <textarea
              id="gg-homonyms"
              rows={2}
              value={homonymsRaw}
              onChange={(ev) => setHomonymsRaw(ev.target.value)}
            />
          </div>
          <div className="ops-field">
            <label htmlFor="gg-terms">Preferred search terms (one per line)</label>
            <textarea
              id="gg-terms"
              rows={2}
              value={termsRaw}
              onChange={(ev) => setTermsRaw(ev.target.value)}
            />
          </div>
          {error ? <p className="ops-field__hint ops-field__hint--error">{error}</p> : null}
          <Button
            type="button"
            variant="ghost"
            disabled={saving || loading}
            onClick={() => void handleSave()}
          >
            {saving ? "Saving…" : "Save prompt profile"}
          </Button>
        </div>
      ) : profile.clinicalFraming ? (
        <p className="ops-field__hint">{profile.clinicalFraming.slice(0, 200)}…</p>
      ) : null}
    </div>
  );
}
