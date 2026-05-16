import { useState, useEffect, useRef } from "react";
import {
  doctorFinderRun,
  doctorFinderTraceUrl,
  doctorFinderGetResult,
  doctorFinderSuggestAliases,
} from "../api/client";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useLiveRunTrace } from "../hooks/useLiveRunTrace";
import { registerRunStart, markRunFinished } from "../runHistory";
import type { DoctorFinderInput, DoctorReport, DoctorEntry } from "../types";
import { RunTracePanel } from "./RunTracePanel";
import "../styles/ops-forms.css";

function formatUnknownError(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const parts = value.map((v) => formatUnknownError(v)).filter((s) => s.length > 0);
    return parts.length > 0 ? parts.join("; ") : JSON.stringify(value);
  }
  if (typeof value === "object") {
    const o = value as Record<string, unknown>;
    if (typeof o.detail === "string") return o.detail;
    if (Array.isArray(o.detail)) return formatUnknownError(o.detail);
    if (typeof o.message === "string") return o.message;
    try {
      return JSON.stringify(value);
    } catch {
      return "Unknown error";
    }
  }
  return String(value);
}

const CONTINENTS = ["Africa", "Asia", "Europe", "North America", "Oceania", "South America"];

const MODEL_PROFILE_OPTIONS = ["production", "test", "openrouter"] as const;

const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  guideline_author: { label: "Guideline Author", color: "#22c55e" },
  senior_investigator: { label: "Senior Investigator", color: "#3b82f6" },
  active_contributor: { label: "Active Contributor", color: "#a78bfa" },
  case_reporter: { label: "Case Reporter", color: "#f59e0b" },
  peripheral: { label: "Peripheral", color: "#64748b" },
};

interface FormState {
  disease_name: string;
  disease_aliases_raw: string;
  continent: string;
  max_results: number;
  top_n_authors: number;
  ai_justification: boolean;
  model_profile: (typeof MODEL_PROFILE_OPTIONS)[number];
  llm_model_override: string;
  ai_generate_aliases: boolean;
}

interface TraceMessage {
  text: string;
  kind: string;
}

export interface DoctorFinderPanelProps {
  onRunStarted?: () => void;
  viewExecutionId?: string | null;
  runLive?: boolean;
}

export function DoctorFinderPanel({
  onRunStarted,
  viewExecutionId = null,
  runLive = false,
}: DoctorFinderPanelProps = {}) {
  const { diseases, loading: catalogLoading } = useDiseaseCatalog();
  const [catalogSlug, setCatalogSlug] = useState("");
  const [form, setForm] = useState<FormState>({
    disease_name: "",
    disease_aliases_raw: "",
    continent: "",
    max_results: 200,
    top_n_authors: 20,
    ai_justification: false,
    model_profile: "production",
    llm_model_override: "",
    ai_generate_aliases: false,
  });
  const [loading, setLoading] = useState(false);
  const [aliasSuggestLoading, setAliasSuggestLoading] = useState(false);
  const [traceMessages, setTraceMessages] = useState<TraceMessage[]>([]);
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<DoctorEntry | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const liveTraceUrl =
    runLive && viewExecutionId ? doctorFinderTraceUrl(viewExecutionId) : null;
  const liveTrace = useLiveRunTrace(liveTraceUrl, Boolean(liveTraceUrl), { runKind: "doctor_finder" });

  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (!viewExecutionId || runLive) return;
    void doctorFinderGetResult(viewExecutionId, { timeoutMs: 120_000 })
      .then((result) => {
        if (result.error) {
          setError(formatUnknownError(result.error));
        } else if (result.doctor_report) {
          setReport(result.doctor_report);
        }
      })
      .catch((err) => {
        setError(formatUnknownError(err));
      });
  }, [viewExecutionId, runLive]);

  useEffect(() => {
    if (liveTrace.finished && viewExecutionId) {
      void doctorFinderGetResult(viewExecutionId, { timeoutMs: 120_000 }).then(
        (result) => {
          if (result.doctor_report) setReport(result.doctor_report);
          if (result.error) setError(formatUnknownError(result.error));
        },
      );
    }
  }, [liveTrace.finished, viewExecutionId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const disease = form.disease_name.trim();
    if (!disease) {
      setError("Enter a disease name (required).");
      return;
    }

    setLoading(true);
    setReport(null);
    setError(null);
    setTraceMessages([]);
    setSelectedEntry(null);
    esRef.current?.close();

    const aliases = form.disease_aliases_raw
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);

    const input: DoctorFinderInput = {
      disease_name: disease,
      disease_aliases: aliases,
      continent: form.continent || null,
      max_results: form.max_results,
      top_n_authors: form.top_n_authors,
      ai_justification: form.ai_justification,
      model_profile: form.model_profile,
      llm_model_override: form.llm_model_override.trim() || null,
      ai_generate_aliases: form.ai_generate_aliases,
    };

    try {
      const { execution_id } = await doctorFinderRun(input);
      registerRunStart({
        execution_id,
        pipeline: "doctor_finder",
        label: disease,
        started_at: new Date().toISOString(),
        done: false,
      });
      onRunStarted?.();
      const url = doctorFinderTraceUrl(execution_id);
      const es = new EventSource(url);
      esRef.current = es;

      es.onmessage = async (evt) => {
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(evt.data) as Record<string, unknown>;
        } catch {
          return;
        }
        try {
          if (data.kind === "sys" && typeof data.text === "string") {
            setTraceMessages((prev) => [...prev, { text: data.text as string, kind: "sys" }]);
          }
          if (data.kind === "doctor_finder_progress") {
            const stage = String(data.stage ?? "");
            const count = data.count != null ? ` (${data.count})` : "";
            const done = data.done != null && data.total != null ? ` ${data.done}/${data.total}` : "";
            setTraceMessages((prev) => [...prev, { text: `${stage}${count}${done}`, kind: "progress" }]);
          }
          // Progress uses numeric `done` (e.g. ClinicalTrials checks); only boolean true ends the run.
          if (data.done === true) {
            es.close();
            setLoading(false);
            const result = await doctorFinderGetResult(execution_id, { timeoutMs: 120_000 });
            if (result.error) {
              setError(formatUnknownError(result.error));
              markRunFinished(execution_id, { done: true, error: String(result.error) });
            } else if (result.doctor_report) {
              setReport(result.doctor_report);
              markRunFinished(execution_id, { done: true, error: null });
            } else {
              setError(
                "Search finished but no report was returned. If you chose a continent, try clearing it or broadening aliases; otherwise check backend logs.",
              );
            }
          }
        } catch (err) {
          setLoading(false);
          setError(formatUnknownError(err instanceof Error ? err.message : err));
        }
      };

      es.onerror = () => {
        es.close();
        setLoading(false);
        setError(
          "SSE trace connection failed. Restart the admin dev server (Vite proxy must not time out long streams). If GENEGUIDELINES_API_KEY is set on the backend, set VITE_GENEGUIDELINES_API_KEY to the same value — EventSource cannot send Authorization. Confirm uvicorn runs on :8000.",
        );
      };
    } catch (err) {
      setLoading(false);
      setError(formatUnknownError(err instanceof Error ? err.message : err));
    }
  };

  const handleSuggestAliases = async () => {
    const disease = form.disease_name.trim();
    if (!disease) {
      setError("Enter a disease name to generate aliases.");
      return;
    }
    setAliasSuggestLoading(true);
    setError(null);
    try {
      const { aliases } = await doctorFinderSuggestAliases({
        disease_name: disease,
        model_profile: form.model_profile,
        llm_model_override: form.llm_model_override.trim() || null,
      });
      const existing = form.disease_aliases_raw
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const seen = new Set(existing.map((s) => s.toLowerCase()));
      const merged = [...existing];
      for (const a of aliases) {
        const t = a.trim();
        if (!t) continue;
        const key = t.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push(t);
      }
      setForm((f) => ({ ...f, disease_aliases_raw: merged.join(", ") }));
    } catch (err) {
      setError(formatUnknownError(err instanceof Error ? err.message : err));
    } finally {
      setAliasSuggestLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    background: "#0f172a",
    border: "1px solid #334155",
    borderRadius: 6,
    color: "#f1f5f9",
    padding: "8px 12px",
    fontSize: 14,
    width: "100%",
    boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: 4,
    display: "block",
  };

  return (
    <div className="ops-panel ops-panel--doctor-finder">
      <h2 className="ops-panel__title">Find disease specialists</h2>
      <p className="ops-panel__lead">
        Rank experts by PubMed publication profile, role, and activity.
      </p>

      {!viewExecutionId ? (
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 32 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={labelStyle}>Disease (catalog)</label>
            <select
              style={inputStyle}
              value={catalogSlug}
              disabled={catalogLoading}
              onChange={(e) => {
                const slug = e.target.value;
                setCatalogSlug(slug);
                const row = diseases.find((d) => d.slug === slug);
                if (row) {
                  setForm((f) => ({ ...f, disease_name: row.name }));
                }
              }}
            >
              <option value="">
                {catalogLoading ? "Loading…" : "Pick from catalog (optional)"}
              </option>
              {diseases.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.name}
                  {d.gene ? ` · ${d.gene}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Disease Name *</label>
            <input
              style={inputStyle}
              value={form.disease_name}
              onChange={(e) => setForm((f) => ({ ...f, disease_name: e.target.value }))}
              placeholder="e.g. fibrous dysplasia"
              required
            />
          </div>
          <div>
            <label style={labelStyle}>Aliases (comma or newline separated)</label>
            <textarea
              style={{ ...inputStyle, height: 60, resize: "vertical" }}
              value={form.disease_aliases_raw}
              onChange={(e) => setForm((f) => ({ ...f, disease_aliases_raw: e.target.value }))}
              placeholder="FD/MAS, McCune-Albright"
            />
            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                onClick={() => void handleSuggestAliases()}
                disabled={aliasSuggestLoading || loading}
                title="Calls the LLM — requires a configured API key on the backend"
                style={{
                  background: "#334155",
                  border: "1px solid #475569",
                  borderRadius: 6,
                  color: "#e2e8f0",
                  cursor: aliasSuggestLoading || loading ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                  padding: "6px 12px",
                  opacity: aliasSuggestLoading || loading ? 0.6 : 1,
                }}
              >
                {aliasSuggestLoading ? "Generating…" : "Generate aliases (AI)"}
              </button>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Continent (optional)</label>
            <select
              style={inputStyle}
              value={form.continent}
              onChange={(e) => setForm((f) => ({ ...f, continent: e.target.value }))}
            >
              <option value="">Any</option>
              {CONTINENTS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Max Results</label>
              <input
                type="number" min={1} max={500} style={inputStyle}
                value={form.max_results}
                onChange={(e) => setForm((f) => ({ ...f, max_results: Number(e.target.value) }))}
              />
            </div>
            <div>
              <label style={labelStyle}>Top N Authors</label>
              <input
                type="number" min={1} max={100} style={inputStyle}
                value={form.top_n_authors}
                onChange={(e) => setForm((f) => ({ ...f, top_n_authors: Number(e.target.value) }))}
              />
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={labelStyle}>Model profile (LLM)</label>
            <select
              style={inputStyle}
              value={form.model_profile}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  model_profile: e.target.value as FormState["model_profile"],
                }))
              }
            >
              {MODEL_PROFILE_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <p style={{ margin: "6px 0 0", fontSize: 11, color: "#64748b" }}>
              Same profile used for agent runs — applies to aliases and AI justifications.
            </p>
          </div>
          <div>
            <label style={labelStyle}>Model override (optional)</label>
            <input
              style={inputStyle}
              value={form.llm_model_override}
              onChange={(e) => setForm((f) => ({ ...f, llm_model_override: e.target.value }))}
              placeholder="e.g. openai:gpt-4o-mini or gpt-4o-mini"
            />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox" id="ai_aliases"
              checked={form.ai_generate_aliases}
              onChange={(e) => setForm((f) => ({ ...f, ai_generate_aliases: e.target.checked }))}
            />
            <label htmlFor="ai_aliases" style={{ ...labelStyle, margin: 0, textTransform: "none" }}>
              Before PubMed: merge AI-suggested aliases (combined with the fields above, deduplicated)
            </label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox" id="ai_just"
              checked={form.ai_justification}
              onChange={(e) => setForm((f) => ({ ...f, ai_justification: e.target.checked }))}
            />
            <label htmlFor="ai_just" style={{ ...labelStyle, margin: 0, textTransform: "none" }}>
              Generate AI justifications (requires OPENAI_API_KEY)
            </label>
          </div>
        </div>

        <div>
          <button
            type="submit"
            disabled={loading}
            title={
              loading
                ? "Search in progress"
                : !form.disease_name.trim()
                  ? "Enter a disease name first"
                  : "Run PubMed search and build the specialist list"
            }
            style={{
              background: loading ? "#3730a3" : "#4f46e5",
              border: "none",
              borderRadius: 8,
              color: "white",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 14,
              fontWeight: 600,
              padding: "10px 24px",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Searching…" : "Find Specialists"}
          </button>
          {!form.disease_name.trim() && !loading && (
            <p style={{ margin: "10px 0 0", fontSize: 12, color: "#fbbf24" }}>
              Enter a disease name — this field is required. You will see a message after clicking "Find Specialists" if it is empty.
            </p>
          )}
        </div>
      </form>
      ) : null}

      <RunTracePanel
        title="Specialist search trace"
        lines={runLive ? liveTrace.lines : traceMessages.map((m, i) => ({
          id: String(i),
          kind: m.kind,
          text: m.text,
        }))}
        connected={runLive ? liveTrace.connected : loading}
        finished={runLive ? liveTrace.finished : !loading && traceMessages.length > 0}
        streamError={runLive ? liveTrace.streamError : null}
        active={runLive || loading}
      />

      {loading && !runLive && (
        <div style={{ background: "#1e293b", borderRadius: 8, padding: 16, marginBottom: 24, maxHeight: 150, overflowY: "auto" }}>
          {traceMessages.length === 0 ? (
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Starting search… (first trace lines may take a few seconds)</div>
          ) : (
            traceMessages.slice(-8).map((m, i) => (
              <div key={i} style={{ fontSize: 12, color: m.kind === "progress" ? "#a78bfa" : "#64748b", marginBottom: 2 }}>
                {m.text}
              </div>
            ))
          )}
        </div>
      )}

      {error && (
        <div style={{ background: "#450a0a", border: "1px solid #dc2626", borderRadius: 8, padding: 16, marginBottom: 24, color: "#fca5a5" }}>
          {error}
        </div>
      )}

      {report && (
        <div>
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: "#94a3b8", fontSize: 13 }}>
              {report.total_papers_scanned} papers scanned · {report.total_authors_found} authors found
            </span>
          </div>
          {report.top_authors.length === 0 && (
            <div
              style={{
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: 8,
                padding: 14,
                marginBottom: 16,
                fontSize: 13,
                color: "#94a3b8",
              }}
            >
              No rows in the ranking — either aggregation returned no authors, or the continent filter
              excluded everyone (e.g. none of the scored authors match the chosen region). Clear the
              continent field or change the search criteria. If the backend attached a note to the
              Markdown report, check it in the API response or logs.
            </div>
          )}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #334155" }}>
                {["#", "Name", "Country", "Role", "Score", "Papers", ""].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 12px", color: "#94a3b8", fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.top_authors.map((entry) => {
                const badge = ROLE_BADGE[entry.role] ?? { label: entry.role, color: "#64748b" };
                return (
                  <tr key={entry.author_key} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={{ padding: "10px 12px", color: "#64748b" }}>{entry.rank}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 600 }}>
                      {entry.display_name}
                      {entry.affiliation && <div style={{ fontSize: 11, color: "#64748b", fontWeight: 400 }}>{entry.affiliation}</div>}
                    </td>
                    <td style={{ padding: "10px 12px" }}>{entry.country ?? "—"}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ background: `${badge.color}22`, color: badge.color, borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>
                        {badge.label}
                      </span>
                    </td>
                    <td style={{ padding: "10px 12px", width: 120 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ flex: 1, height: 6, background: "#334155", borderRadius: 3 }}>
                          <div style={{ width: `${entry.score}%`, height: "100%", background: "#4f46e5", borderRadius: 3 }} />
                        </div>
                        <span style={{ color: "#94a3b8", fontSize: 11, width: 32, textAlign: "right" }}>{entry.score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td style={{ padding: "10px 12px", color: "#94a3b8" }}>{entry.key_papers.length}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <button
                        onClick={() => setSelectedEntry(entry)}
                        style={{ background: "none", border: "1px solid #334155", borderRadius: 4, color: "#94a3b8", cursor: "pointer", fontSize: 11, padding: "3px 8px" }}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedEntry && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedEntry(null); }}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "flex-end", zIndex: 1000 }}
        >
          <div style={{ background: "#1e293b", width: 480, height: "100%", overflowY: "auto", padding: 24, boxShadow: "-4px 0 24px rgba(0,0,0,0.4)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 16 }}>{selectedEntry.display_name}</h3>
              <button onClick={() => setSelectedEntry(null)} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 20 }}>×</button>
            </div>

            <div style={{ marginBottom: 16, fontSize: 13, color: "#94a3b8" }}>
              <div>Role: <span style={{ color: ROLE_BADGE[selectedEntry.role]?.color ?? "#f1f5f9" }}>{selectedEntry.role}</span></div>
              <div>Score: {selectedEntry.score.toFixed(1)} / 100</div>
              {selectedEntry.country && <div>Country: {selectedEntry.country}</div>}
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", marginBottom: 8 }}>Evidence Summary</div>
              {Object.entries(selectedEntry.evidence_summary).map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                  <span style={{ color: "#94a3b8" }}>{k.replace(/_/g, " ")}</span>
                  <span>{v}</span>
                </div>
              ))}
            </div>

            {selectedEntry.key_papers.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", marginBottom: 8 }}>Key Papers</div>
                {selectedEntry.key_papers.map((p) => (
                  <div key={p.pmid} style={{ marginBottom: 8, padding: 8, background: "#0f172a", borderRadius: 6 }}>
                    <a href={p.pubmed_url} target="_blank" rel="noopener noreferrer" style={{ color: "#818cf8", fontSize: 13, textDecoration: "none" }}>
                      {p.title || `PMID ${p.pmid}`}
                    </a>
                    {p.year && <span style={{ color: "#64748b", fontSize: 11, marginLeft: 8 }}>({p.year})</span>}
                  </div>
                ))}
              </div>
            )}

            {selectedEntry.ai_justification && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", marginBottom: 8 }}>AI Justification</div>
                <p style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.6 }}>{selectedEntry.ai_justification}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
