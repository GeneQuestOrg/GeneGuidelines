import { useState, useEffect } from "react";
import { Badge } from "./Badge";
import { ToggleSwitch } from "./ToggleSwitch";
import {
  fetchToolCatalog,
  fetchRequestedTools,
  fetchImplementedTools,
  updateToolMode,
  reserveForBuilder as reserveForBuilderApi,
} from "../api/client";
import type { BuilderStep } from "../api/client";
import type { Tool, RequestedTool, ImplementedTool } from "../types";
import {
  INITIAL_TOOLS,
  INITIAL_REQUESTED,
  INITIAL_IMPLEMENTED,
} from "../data/governanceData";

const th: React.CSSProperties = {
  padding: "10px 10px",
  borderBottom: "2px solid #e2e8f0",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.03em",
  color: "#64748b",
  textAlign: "left",
};

const td: React.CSSProperties = {
  padding: "12px 10px",
  borderBottom: "1px solid #f1f5f9",
  verticalAlign: "middle",
  fontSize: 13,
};

const GOVERNANCE_RULES = [
  {
    title: "Canonical naming dedupe",
    desc: "If a request is semantically similar, use the existing canonical name.",
    v: "enabled" as const,
  },
  {
    title: "Fuzzy search preference",
    desc: "Prompts should prefer fuzzy tools when the user data is incomplete.",
    v: "enabled" as const,
  },
  {
    title: "Production actions → approval",
    desc: "These actions require technician approval by default.",
    v: "strict" as const,
  },
  {
    title: "Builder → production isolation",
    desc: "The builder flow must not call production actions directly.",
    v: "strict" as const,
  },
];

const TOOLS_REPO_URL =
  (import.meta.env.VITE_TOOLS_REPO_URL as string) ||
  "https://github.com/dmiskiew/GeneGuidelines";

export function GovernanceView() {
  const [tools, setTools] = useState<Tool[]>(INITIAL_TOOLS);
  const [requested, setRequested] = useState<RequestedTool[]>(INITIAL_REQUESTED);
  const [implemented, setImplemented] = useState<ImplementedTool[]>(INITIAL_IMPLEMENTED);
  /** Latest Builder steps ("thoughts") after Reserve for Builder. */
  const [builderSteps, setBuilderSteps] = useState<BuilderStep[]>([]);
  const [builderLoading, setBuilderLoading] = useState(false);
  const [builderError, setBuilderError] = useState<string | null>(null);
  const [implementedError, setImplementedError] = useState<string | null>(null);

  useEffect(() => {
    fetchToolCatalog(false)
      .then((rows) =>
        setTools(
          rows.map((r) => ({
            id: r.id,
            name: r.name,
            category: r.category,
            auto: r.execution_mode === "auto",
            scope: r.scope as Tool["scope"],
          }))
        )
      )
      .catch(() => {});
    fetchRequestedTools()
      .then((rows) =>
        setRequested(
          rows
            .filter((r) => r.name !== "check")
            .map((r) => ({
              id: r.id,
              name: r.name,
              status: r.status as RequestedTool["status"],
              sim: r.similarity_key,
              note: r.note ?? "",
            }))
        )
      )
      .catch(() => {});
    fetchImplementedTools()
      .then((rows) =>
        setImplemented(
          rows.map((r) => ({
            name: r.name,
            status: r.status as ImplementedTool["status"],
            pr: r.pr_number ?? "",
            url: r.pr_url ?? "",
          }))
        )
      )
      .catch((e) => setImplementedError(e instanceof Error ? e.message : String(e)));
  }, []);

  const refreshRequestedAndImplemented = () => {
    setImplementedError(null);
    fetchRequestedTools()
      .then((rows) =>
        setRequested(
          rows
            .filter((r) => r.name !== "check")
            .map((r) => ({
              id: r.id,
              name: r.name,
              status: r.status as RequestedTool["status"],
              sim: r.similarity_key,
              note: r.note ?? "",
            }))
        )
      )
      .catch(() => {});
    fetchImplementedTools()
      .then((rows) =>
        setImplemented(
          rows.map((r) => ({
            name: r.name,
            status: r.status as ImplementedTool["status"],
            pr: r.pr_number ?? "",
            url: r.pr_url ?? "",
          }))
        )
      )
      .catch((e) => setImplementedError(e instanceof Error ? e.message : String(e)));
  };

  const reserveForBuilder = async (req: RequestedTool) => {
    const id = req.id ?? (req as { id?: number }).id;
    if (id == null) return;
    setBuilderError(null);
    setBuilderSteps([]);
    setBuilderLoading(true);
    try {
      const result = await reserveForBuilderApi(id);
      setBuilderSteps(result.steps ?? []);
      if (!result.ok && result.reason) {
        setBuilderError(result.reason);
      }
      refreshRequestedAndImplemented();
    } catch (e) {
      setBuilderError(e instanceof Error ? e.message : String(e));
      setBuilderSteps([]);
    } finally {
      setBuilderLoading(false);
    }
  };

  const toggleTool = async (t: Tool) => {
    const newAuto = !t.auto;
    setTools((prev) =>
      prev.map((x) => (x.name === t.name ? { ...x, auto: newAuto } : x))
    );
    if (t.id != null) {
      try {
        await updateToolMode(t.id, {
          execution_mode: newAuto ? "auto" : "approval",
        });
      } catch {
        setTools((prev) =>
          prev.map((x) => (x.name === t.name ? { ...x, auto: !newAuto } : x))
        );
      }
    }
  };

  return (
    <div
      style={{
        padding: 28,
        overflow: "auto",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 20,
        alignContent: "start",
      }}
    >
      <div
        style={{
          gridColumn: "span 2",
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 24,
        }}
      >
        <h3 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 700 }}>
          MCP Tool Catalog
        </h3>
        <p style={{ margin: "0 0 16px", fontSize: 13, color: "#64748b" }}>
          Control each tool execution mode: automatic or technician approval.
        </p>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Tool</th>
              <th style={th}>Category</th>
              <th style={th}>Execution</th>
              <th style={th}>Scope</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((t) => (
              <tr key={t.name}>
                <td
                  style={{
                    ...td,
                    fontFamily: "monospace",
                    fontWeight: 600,
                    color: "#db2777",
                  }}
                >
                  {t.name}
                </td>
                <td style={{ ...td, color: "#64748b" }}>{t.category}</td>
                <td style={td}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <ToggleSwitch
                      checked={t.auto}
                      onChange={() => toggleTool(t)}
                    />
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: t.auto ? "#059669" : "#d97706",
                      }}
                    >
                      {t.auto ? "AUTO" : "APPROVAL"}
                    </span>
                  </div>
                </td>
                <td style={td}>
                  <Badge variant={t.scope}>{t.scope}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        style={{
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 24,
        }}
      >
        <h3 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 700 }}>
          Requested tools queue
        </h3>
        <p style={{ margin: "0 0 16px", fontSize: 13, color: "#64748b" }}>
          From the diagnostics loop, with canonical naming policy.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {requested.map((r, i) => (
            <div
              key={r.id ?? `${r.name}-${i}`}
              style={{
                border: "1px solid #f1f5f9",
                borderRadius: 10,
                padding: 14,
                background: "#fafbfc",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    fontFamily: "monospace",
                    fontWeight: 700,
                    fontSize: 13,
                    color: "#db2777",
                  }}
                >
                  {r.name}
                </span>
                <Badge variant={r.status}>
                  {r.status.replace("_", " ")}
                </Badge>
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "#64748b",
                  marginBottom: 6,
                }}
              >
                {r.note}
              </div>
              {r.sim != null && r.sim !== "" && (
                <div
                  style={{
                    fontSize: 11,
                    color: "#7c3aed",
                    background: "#f5f3ff",
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: 4,
                    marginBottom: 8,
                  }}
                >
                  sim-key: {r.sim}
                </div>
              )}
              {r.status === "requested" && (
                <div>
                  <button
                    type="button"
                    onClick={() => reserveForBuilder(r)}
                    disabled={builderLoading}
                    style={{
                      background: "#4f46e5",
                      color: "white",
                      border: "none",
                      borderRadius: 6,
                      padding: "6px 14px",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: builderLoading ? "wait" : "pointer",
                      marginTop: 2,
                      opacity: builderLoading ? 0.7 : 1,
                    }}
                  >
                    {builderLoading ? "Starting Builder…" : "Reserve for Builder"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {(builderSteps.length > 0 || builderError) && (
          <div
            style={{
              marginTop: 16,
              padding: 12,
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
            }}
          >
            <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700, color: "#475569" }}>
              Builder thoughts (latest run)
            </h4>
            {builderError && (
              <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}>{builderError}</div>
            )}
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
              {builderSteps.map((s, i) => (
                <li key={i}>
                  <span style={{ fontWeight: 600 }}>{s.step}</span>
                  {s.msg != null && s.msg !== "" && (
                    <> — {s.msg}</>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <div
        style={{
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 24,
        }}
      >
        <h3 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 700 }}>
          Implemented (Builder Agent)
        </h3>
        <p style={{ margin: "0 0 16px", fontSize: 13, color: "#64748b" }}>
          Generated tools and pull requests.
        </p>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            {implementedError ? (
              <span style={{ color: "#dc2626", fontWeight: 600 }}>Fetch error: {implementedError}</span>
            ) : (
              <span>Source: /api/tools/implemented (rows: {implemented.length})</span>
            )}
          </div>
          <button
            type="button"
            onClick={refreshRequestedAndImplemented}
            style={{
              background: "#0f172a",
              color: "white",
              border: "none",
              borderRadius: 6,
              padding: "6px 12px",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
        </div>
        {implemented.length === 0 && !implementedError && (
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>
            No entries yet. If the backend is returning data, inspect the Network tab in DevTools for the request <code>/api/tools/implemented</code>.
          </div>
        )}
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Tool</th>
              <th style={th}>PR</th>
              <th style={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {implemented.map((t) => (
              <tr key={t.name}>
                <td
                  style={{
                    ...td,
                    fontFamily: "monospace",
                    fontWeight: 600,
                    color: "#db2777",
                  }}
                >
                  {t.name}
                </td>
                <td style={td}>
                  {(() => {
                    // If PR URL is missing (e.g. ready_for_pr), link to the Tools repo directory.
                    const fallbackToolsDirUrl = `${TOOLS_REPO_URL}/tree/main/tools`;
                    const href = t.url || fallbackToolsDirUrl;
                    const label = t.url ? (t.pr || "PR") : "tools";
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          color: "#4f46e5",
                          fontWeight: 600,
                          textDecoration: "none",
                        }}
                      >
                        {label} ↗
                      </a>
                    );
                  })()}
                </td>
                <td style={td}>
                  <Badge variant={t.status}>
                    {t.status.replace("_", " ")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        style={{
          gridColumn: "span 2",
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 24,
        }}
      >
        <h3 style={{ margin: "0 0 16px", fontSize: 17, fontWeight: 700 }}>
          Governance Rules
        </h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 10,
          }}
        >
          {GOVERNANCE_RULES.map((r) => (
            <div
              key={r.title}
              style={{
                border: "1px solid #f1f5f9",
                borderRadius: 8,
                padding: "12px 16px",
                background: "#fafbfc",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 4,
                }}
              >
                <span style={{ fontWeight: 700, fontSize: 13.5 }}>
                  {r.title}
                </span>
                <Badge variant={r.v}>{r.v}</Badge>
              </div>
              <div style={{ fontSize: 12, color: "#64748b" }}>{r.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
