import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchTickets,
  fetchTicket,
  fetchFlows,
  agentRun,
  agentTraceUrl,
  fetchAgentRunResult,
  getApprovalPending,
  postApproval,
} from "../api/client";
import type { ApprovalPending, MissingToolRequest, ModelProfile } from "../api/client";
import type { AgentTraceEvent } from "../api/agentContract";
import { normalizeAgentRunResult, parseAgentTraceEvent } from "../api/agentContract";
import { sanitizeGeneratedHtml } from "../utils/pubmedOutput";
import {
  loadRunSnapshot,
  markRunFinished,
  registerRunStart,
  saveRunSnapshot,
} from "../runHistory";
import { useDefaultModelProfile } from "../hooks/useDefaultModelProfile";

interface TicketRow {
  id: number;
  title: string;
  description: string;
  status: string;
  resolution_summary?: string | null;
  diagnostic_steps?: string | null;
  category?: string;
}

const LAST_RUN_STORAGE_PREFIX = "agent_last_run_ticket_";

const STATUS_ICON: Record<string, string> = {
  not_started: "🔴",
  in_progress: "🟡",
  diagnosed: "🟢",
};

function statusIcon(status: string): string {
  return STATUS_ICON[status] ?? "⚪";
}

const FLOW_LABELS: Record<string, string> = {
  pubmed: "PubMed Search",
  doctor_finder: "Doctor Finder",
  parent_pathway: "Parent Pathway",
};

const ALLOWED_FLOW_KEYS = ["pubmed", "doctor_finder", "parent_pathway"] as const;

const DEFAULT_FLOWS = [
  { key: "pubmed", label: "PubMed Search" },
  { key: "doctor_finder", label: "Doctor Finder" },
  { key: "parent_pathway", label: "Parent Pathway" },
];

type PubmedOutput = {
  disease_name?: string;
  guideline_html?: string;
  recommendation_matrix_html?: string;
  red_flags_html?: string;
  contraindications_html?: string;
  follow_up_schedule_html?: string;
  evidence_gaps_html?: string;
  disclaimer_html?: string;
  key_updates?: string;
  confidence_level?: string;
  evidence_score?: number;
  confidence_index?: number;
  reliability_assessment_html?: string;
  source_links_html?: string;
  references?: string;
  article_count?: number;
};

const PUBMED_OUTPUT_FIELDS: ReadonlyArray<keyof PubmedOutput> = [
  "disease_name",
  "guideline_html",
  "article_count",
  "confidence_level",
  "evidence_score",
  "confidence_index",
  "key_updates",
  "recommendation_matrix_html",
  "source_links_html",
];

function parsePubmedOutput(output: string | null | undefined): PubmedOutput | null {
  if (!output) return null;
  try {
    const parsed = JSON.parse(output) as PubmedOutput;
    if (!parsed || typeof parsed !== "object") return null;
    if (PUBMED_OUTPUT_FIELDS.every((k) => parsed[k] == null)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

interface OutputPreviewProps {
  pubmedGuideline: PubmedOutput | null;
  rawOutput: string | null;
  runInProgress: boolean;
}

type OutputPreviewTab = "overview" | "treatment" | "followup" | "references";

function OutputPreview({ pubmedGuideline, rawOutput, runInProgress }: OutputPreviewProps) {
  const [activeTab, setActiveTab] = useState<OutputPreviewTab>("overview");

  if (runInProgress && pubmedGuideline == null && rawOutput == null) return null;
  if (!pubmedGuideline && !rawOutput) return null;

  if (pubmedGuideline) {
    const TABS = [
      { key: "overview", label: "Overview" },
      { key: "treatment", label: "Treatment" },
      { key: "followup", label: "Follow-up" },
      { key: "references", label: "References" },
    ] as const;

    const tabButtonStyle = (key: OutputPreviewTab): React.CSSProperties => ({
      fontSize: 12,
      fontWeight: 600,
      padding: "5px 14px",
      borderRadius: 999,
      border: "none",
      cursor: "pointer",
      background: activeTab === key ? "#4f46e5" : "#f1f5f9",
      color: activeTab === key ? "white" : "#475569",
    });

    const renderTabContent = () => {
      if (activeTab === "overview") {
        return (
          <div style={{ fontSize: 13, color: "#1e293b", lineHeight: 1.6 }}>
            {pubmedGuideline.disease_name && (
              <p style={{ margin: "0 0 6px", fontWeight: 700 }}>{pubmedGuideline.disease_name}</p>
            )}
            {pubmedGuideline.key_updates ? (
              <p style={{ margin: 0, whiteSpace: "pre-wrap", color: "#334155" }}>
                {pubmedGuideline.key_updates}
              </p>
            ) : (
              <p style={{ margin: 0, color: "#94a3b8", fontStyle: "italic" }}>No overview available.</p>
            )}
            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {typeof pubmedGuideline.evidence_score === "number" && (
                <span style={{ background: "#dcfce7", borderRadius: 999, padding: "3px 10px", fontSize: 11, color: "#14532d" }}>
                  Evidence: {pubmedGuideline.evidence_score}/100
                </span>
              )}
              {pubmedGuideline.confidence_level && (
                <span style={{ background: "#e0e7ff", borderRadius: 999, padding: "3px 10px", fontSize: 11, color: "#3730a3" }}>
                  {pubmedGuideline.confidence_level}
                </span>
              )}
            </div>
          </div>
        );
      }

      if (activeTab === "treatment") {
        const raw = pubmedGuideline.guideline_html ? stripHtml(pubmedGuideline.guideline_html) : "";
        const preview = raw.length > 400 ? raw.slice(0, 400) + "…" : raw;
        return preview ? (
          <p style={{ margin: 0, fontSize: 13, color: "#334155", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{preview}</p>
        ) : (
          <p style={{ margin: 0, color: "#94a3b8", fontStyle: "italic", fontSize: 13 }}>No treatment information available.</p>
        );
      }

      if (activeTab === "followup") {
        const raw = pubmedGuideline.follow_up_schedule_html ? stripHtml(pubmedGuideline.follow_up_schedule_html) : "";
        const preview = raw.length > 400 ? raw.slice(0, 400) + "…" : raw;
        return preview ? (
          <p style={{ margin: 0, fontSize: 13, color: "#334155", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{preview}</p>
        ) : (
          <p style={{ margin: 0, color: "#94a3b8", fontStyle: "italic", fontSize: 13 }}>No follow-up information available.</p>
        );
      }

      if (activeTab === "references") {
        if (!pubmedGuideline.article_count && !pubmedGuideline.source_links_html) {
          return (
            <p style={{ margin: 0, color: "#94a3b8", fontStyle: "italic", fontSize: 13 }}>No references available.</p>
          );
        }
        return (
          <div>
            {typeof pubmedGuideline.article_count === "number" && (
              <p style={{ margin: "0 0 8px", fontSize: 13, color: "#334155" }}>
                Based on {pubmedGuideline.article_count} articles
              </p>
            )}
            {pubmedGuideline.source_links_html && (
              <div
                style={{ fontSize: 12, maxHeight: 160, overflow: "auto" }}
                dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(pubmedGuideline.source_links_html) }}
              />
            )}
          </div>
        );
      }

      return null;
    };

    return (
      <div style={{ marginTop: 16, borderTop: "1px solid #e2e8f0", paddingTop: 14 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {TABS.map((tab) => (
            <button key={tab.key} style={tabButtonStyle(tab.key)} onClick={() => setActiveTab(tab.key as OutputPreviewTab)}>
              {tab.label}
            </button>
          ))}
        </div>
        <div style={{ maxHeight: 180, overflow: "auto", padding: "12px 0 0" }}>
          {renderTabContent()}
        </div>
      </div>
    );
  }

  // Raw fallback
  const rawOutputSafe = rawOutput ?? "";
  let previewText: string;
  try {
    previewText = JSON.stringify(JSON.parse(rawOutputSafe), null, 2);
  } catch {
    previewText = rawOutputSafe;
  }
  if (previewText.length > 600) previewText = previewText.slice(0, 600) + "…";

  return (
    <div style={{ marginTop: 16, borderTop: "1px solid #e2e8f0", paddingTop: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
        Output Preview
      </div>
      <div
        style={{
          background: "#0f172a",
          color: "#e2e8f0",
          padding: "10px 14px",
          borderRadius: 8,
          fontSize: 12,
          fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
          whiteSpace: "pre-wrap",
          maxHeight: 120,
          overflow: "auto",
        }}
      >
        {previewText}
      </div>
    </div>
  );
}

export interface AgentViewProps {
  /** Hide ticket sidebar — RunsView provides run list. */
  detailOnly?: boolean;
  activeExecutionId?: string | null;
  initialJobId?: number | null;
  initialFlowKey?: string;
  jobTitleHint?: string;
  onExecutionStarted?: (meta: {
    execution_id: string;
    ticket_id: number;
    flow_key: string;
    profile: string;
    started_at: string | null;
    job_title?: string;
  }) => void;
}

export function AgentView({
  detailOnly = false,
  activeExecutionId = null,
  initialJobId = null,
  initialFlowKey,
  jobTitleHint,
  onExecutionStarted,
}: AgentViewProps = {}) {
  const [tickets, setTickets] = useState<TicketRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [flowKey, setFlowKey] = useState("pubmed");
  const defaultModelProfile = useDefaultModelProfile();
  const [modelProfile, setModelProfile] = useState<ModelProfile>(defaultModelProfile);
  const profileSynced = useRef(false);
  const [availableFlows, setAvailableFlows] = useState(DEFAULT_FLOWS);

  useEffect(() => {
    if (profileSynced.current) return;
    setModelProfile(defaultModelProfile);
    profileSynced.current = true;
  }, [defaultModelProfile]);
  const [selectedTicket, setSelectedTicket] = useState<TicketRow | null>(null);
  const [runStatus, setRunStatus] = useState<string>("");
  const [trace, setTrace] = useState<AgentTraceEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  /** Whether an agent run is in progress (before receiving done). */
  const [runInProgress, setRunInProgress] = useState(false);
  /** Pending action awaiting approval (e.g. server restart). */
  const [approvalPending, setApprovalPending] = useState<ApprovalPending | null>(null);
  const [approvalExecutionId, setApprovalExecutionId] = useState<string | null>(null);
  /** Last agent run result — streamed live via SSE, persists across ticket changes. */
  const [lastRunResult, setLastRunResult] = useState<{
    ticketId: number | null;
    ai_summary: { issue: string; work_log_summary: string } | null;
    diagnostics_entries: { tool: string; result: string; detail?: string }[];
    missing_tool_requests: MissingToolRequest[];
    output: string | null;
    pubmed_guideline: PubmedOutput | null;
    diagnosis_summary: string | null;
    technician_steps: string[];
    steps_completed_by_ai: number[];
  }>({
    ticketId: null,
    ai_summary: null,
    diagnostics_entries: [],
    missing_tool_requests: [],
    output: null,
    pubmed_guideline: null,
    diagnosis_summary: null,
    technician_steps: [],
    steps_completed_by_ai: [],
  });
  /** Step checkboxes for the technician (user-toggled only; AI-completed steps come from lastRunResult.steps_completed_by_ai). */
  const [stepChecked, setStepChecked] = useState<Record<number, boolean>>({});
  const [showAgentThoughts, setShowAgentThoughts] = useState(true);

  // On ticket switch, load the last saved agent result from localStorage (if any).
  useEffect(() => {
    if (selectedId == null) return;
    // Don't overwrite an in-flight run.
    if (runInProgress && lastRunResult.ticketId === selectedId) return;
    try {
      const raw = window.localStorage.getItem(`${LAST_RUN_STORAGE_PREFIX}${selectedId}`);
      if (!raw) {
        // No saved result for this ticket — show nothing until Run Agent is clicked.
        setLastRunResult({
          ticketId: null,
          ai_summary: null,
          diagnostics_entries: [],
          missing_tool_requests: [],
          output: null,
          pubmed_guideline: null,
          diagnosis_summary: null,
          technician_steps: [],
          steps_completed_by_ai: [],
        });
        return;
      }
      const parsed = JSON.parse(raw) as Partial<{
        ai_summary: { issue: string; work_log_summary: string } | null;
        diagnostics_entries: { tool: string; result: string; detail?: string }[];
        missing_tool_requests: MissingToolRequest[];
        output: string | null;
        pubmed_guideline: PubmedOutput | null;
        diagnosis_summary: string | null;
        technician_steps: string[];
        steps_completed_by_ai: number[];
      }>;
      setLastRunResult({
        ticketId: selectedId,
        ai_summary: parsed.ai_summary ?? null,
        diagnostics_entries: parsed.diagnostics_entries ?? [],
        missing_tool_requests: parsed.missing_tool_requests ?? [],
        output: parsed.output ?? null,
        pubmed_guideline: parsed.pubmed_guideline ?? parsePubmedOutput(parsed.output ?? null),
        diagnosis_summary: parsed.diagnosis_summary ?? null,
        technician_steps: parsed.technician_steps ?? [],
        steps_completed_by_ai: parsed.steps_completed_by_ai ?? [],
      });
    } catch {
      // ignore JSON / storage errors
    }
  }, [selectedId, runInProgress, lastRunResult.ticketId]);

  // Persist every updated agent result for the current ticket into localStorage.
  useEffect(() => {
    if (lastRunResult.ticketId == null) return;
    try {
      const hasContent =
        !!(
          lastRunResult.ai_summary &&
          (lastRunResult.ai_summary.issue || lastRunResult.ai_summary.work_log_summary)
        ) ||
        lastRunResult.diagnostics_entries.length > 0 ||
        lastRunResult.missing_tool_requests.length > 0 ||
        !!lastRunResult.diagnosis_summary ||
        lastRunResult.technician_steps.length > 0 ||
        !!lastRunResult.output;

      const storageKey = `${LAST_RUN_STORAGE_PREFIX}${lastRunResult.ticketId}`;
      if (!hasContent) {
        window.localStorage.removeItem(storageKey);
        return;
      }

      const payload = {
        ai_summary: lastRunResult.ai_summary,
        diagnostics_entries: lastRunResult.diagnostics_entries,
        missing_tool_requests: lastRunResult.missing_tool_requests,
        output: lastRunResult.output,
        pubmed_guideline: lastRunResult.pubmed_guideline,
        diagnosis_summary: lastRunResult.diagnosis_summary,
        technician_steps: lastRunResult.technician_steps,
        steps_completed_by_ai: lastRunResult.steps_completed_by_ai,
      };
      window.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      // ignore storage quota / JSON errors
    }
  }, [lastRunResult]);

  const clearAgentResultForSelected = () => {
    if (selectedId == null) return;
    const storageKey = `${LAST_RUN_STORAGE_PREFIX}${selectedId}`;
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // ignore
    }
    setLastRunResult({
      ticketId: null,
      ai_summary: null,
      diagnostics_entries: [],
      missing_tool_requests: [],
      output: null,
      pubmed_guideline: null,
      diagnosis_summary: null,
      technician_steps: [],
      steps_completed_by_ai: [],
    });
  };

  const loadTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTickets();
      setTickets((data as TicketRow[]) || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  useEffect(() => {
    if (initialJobId != null) {
      setSelectedId(initialJobId);
    }
  }, [initialJobId]);

  useEffect(() => {
    if (initialFlowKey) {
      setFlowKey(initialFlowKey);
    }
  }, [initialFlowKey]);

  useEffect(() => {
    if (!activeExecutionId) return;
    if (initialJobId != null) {
      setSelectedId(initialJobId);
    }
    const snap = loadRunSnapshot<typeof lastRunResult>(activeExecutionId);
    if (snap && snap.ticketId != null) {
      setLastRunResult(snap);
    }
    fetchAgentRunResult(activeExecutionId)
      .then((raw) => {
        const r = normalizeAgentRunResult(raw);
        const parsedOutput = r.output ? parsePubmedOutput(r.output) : null;
        const tid = r.ticket_id || initialJobId || null;
        setLastRunResult({
          ticketId: tid,
          ai_summary: r.ai_summary ?? null,
          diagnostics_entries: r.diagnostics_entries ?? [],
          missing_tool_requests: r.missing_tool_requests ?? [],
          output: r.output ?? null,
          pubmed_guideline: parsedOutput,
          diagnosis_summary: parsedOutput?.key_updates ?? null,
          technician_steps: [],
          steps_completed_by_ai: r.steps_completed_by_ai ?? [],
        });
        if (r.done) {
          markRunFinished(activeExecutionId, { done: true, error: r.error });
        }
      })
      .catch(() => {
        // run evicted from server memory — local snapshot only
      });
  }, [activeExecutionId, initialJobId]);

  useEffect(() => {
    fetchFlows()
      .then((list) => {
        if (list.length > 0) {
          const fromApi = list
            .map((f) => f.flow_key)
            .filter((key): key is typeof ALLOWED_FLOW_KEYS[number] =>
              (ALLOWED_FLOW_KEYS as readonly string[]).includes(key)
            )
            .map((key) => ({ key, label: FLOW_LABELS[key] ?? key }));

          const merged = [...DEFAULT_FLOWS].filter((f) =>
            (ALLOWED_FLOW_KEYS as readonly string[]).includes(f.key)
          );
          for (const af of fromApi) {
            if (!merged.some((m) => m.key === af.key)) merged.push(af);
          }
          setAvailableFlows(merged);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedId == null) {
      setSelectedTicket(null);
      return;
    }
    const t = tickets.find((x) => x.id === selectedId);
    if (t) {
      setSelectedTicket(t);
      return;
    }
    fetchTicket(selectedId)
      .then((data) => setSelectedTicket(data as TicketRow))
      .catch(() => setSelectedTicket(null));
  }, [selectedId, tickets]);

  const refreshSelectedTicket = useCallback(() => {
    if (selectedId == null) return;
    fetchTicket(selectedId)
      .then((data) => setSelectedTicket(data as TicketRow))
      .catch(() => {});
  }, [selectedId]);

  // If the ticket was reset on the backend (status not_started, no summary or steps),
  // also clear the cached agent result and localStorage for this ticket.
  useEffect(() => {
    if (!selectedTicket) return;
    // Keep in-memory result for currently selected ticket; backend ticket fields
    // can still be "not_started" during/after async flow finalization.
    if (lastRunResult.ticketId === selectedTicket.id) {
      return;
    }
    const hasResultForSelectedTicket =
      lastRunResult.ticketId === selectedTicket.id &&
      (!!lastRunResult.output ||
        !!lastRunResult.pubmed_guideline ||
        !!lastRunResult.diagnosis_summary ||
        lastRunResult.technician_steps.length > 0 ||
        (lastRunResult.ai_summary != null &&
          (!!lastRunResult.ai_summary.issue ||
            !!lastRunResult.ai_summary.work_log_summary)));
    if (hasResultForSelectedTicket) {
      return;
    }
    if (
      selectedTicket.status === "not_started" &&
      (!selectedTicket.resolution_summary || selectedTicket.resolution_summary === "") &&
      (!selectedTicket.diagnostic_steps || selectedTicket.diagnostic_steps === "")
    ) {
      const storageKey = `${LAST_RUN_STORAGE_PREFIX}${selectedTicket.id}`;
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // ignore
      }
      setLastRunResult({
        ticketId: null,
        ai_summary: null,
        diagnostics_entries: [],
        missing_tool_requests: [],
        output: null,
        pubmed_guideline: null,
        diagnosis_summary: null,
        technician_steps: [],
        steps_completed_by_ai: [],
      });
    }
  }, [selectedTicket, lastRunResult]);

  // Gdy agent czeka na zatwierdzenie (np. restart) – poll co 2 s
  useEffect(() => {
    if (!runInProgress) return;
    const t = setInterval(() => {
      getApprovalPending()
        .then((r) => {
          if (r.pending) {
            setApprovalPending(r.pending);
            setApprovalExecutionId(r.execution_id ?? null);
          } else {
            setApprovalPending(null);
            setApprovalExecutionId(null);
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [runInProgress]);

  const handleRunAgent = async () => {
    if (selectedId == null) return;
    setError(null);
    setRunInProgress(true);
    setApprovalPending(null);
    setApprovalExecutionId(null);
    setRunStatus("Connecting…");
    setTrace([]);
    setLastRunResult({
      ticketId: selectedId,
      ai_summary: null,
      diagnostics_entries: [],
      missing_tool_requests: [],
      output: null,
      pubmed_guideline: null,
      diagnosis_summary: null,
      technician_steps: [],
      steps_completed_by_ai: [],
    });
    setStepChecked({});
    try {
      const { execution_id } = await agentRun(selectedId, flowKey, modelProfile);
      const startedAt = new Date().toISOString();
      registerRunStart({
        execution_id,
        pipeline: flowKey === "pubmed" ? "guideline" : "legacy",
        label: selectedTicket?.title ?? jobTitleHint ?? `Job #${selectedId}`,
        ticket_id: selectedId,
        flow_key: flowKey,
        profile: modelProfile,
        started_at: startedAt,
        done: false,
      });
      onExecutionStarted?.({
        execution_id,
        ticket_id: selectedId,
        flow_key: flowKey,
        profile: modelProfile,
        started_at: startedAt,
        job_title: selectedTicket?.title ?? jobTitleHint,
      });
      setRunStatus(`Started (${execution_id.slice(0, 8)}…)`);
      const eventSource = new EventSource(agentTraceUrl(execution_id));
      eventSource.onmessage = (event) => {
        try {
          const parsed = parseAgentTraceEvent(JSON.parse(event.data));
          if (!parsed) {
            return;
          }
          const traceEntry = parsed;
          const kind = traceEntry.kind;
          setTrace((prev) => [...prev, traceEntry]);
          if (kind === "ai_summary") {
            setLastRunResult((prev) => ({
              ...prev,
              ai_summary: {
                issue: traceEntry.issue ?? "",
                work_log_summary: traceEntry.work_log_summary ?? "",
              },
            }));
          } else if (kind === "diagnostic") {
            setLastRunResult((prev) => ({
              ...prev,
              diagnostics_entries: [
                ...prev.diagnostics_entries,
                {
                  tool: traceEntry.tool ?? "",
                  result: traceEntry.result ?? "",
                },
              ],
            }));
          } else if (kind === "ticket_status") {
            const ticket_id = traceEntry.ticket_id;
            const status = traceEntry.status ?? "";
            if (ticket_id != null && status) {
              setTickets((prev) =>
                prev.map((t) => (t.id === ticket_id ? { ...t, status } : t))
              );
              setSelectedTicket((prev) =>
                prev && prev.id === ticket_id ? { ...prev, status } : prev
              );
            }
          } else if (kind === "missing_tool_request") {
            setLastRunResult((prev) => ({
              ...prev,
              missing_tool_requests: [
                ...prev.missing_tool_requests,
                {
                  tool_name: traceEntry.tool_name ?? "",
                  reason: traceEntry.reason ?? "",
                  ticket_id: traceEntry.ticket_id,
                },
              ],
            }));
          } else if (kind === "output") {
            const outputText = traceEntry.output ?? null;
            const pubmed = parsePubmedOutput(outputText);
            setLastRunResult((prev) => ({
              ...prev,
              output: outputText,
              pubmed_guideline: pubmed ?? prev.pubmed_guideline,
              diagnosis_summary: pubmed?.key_updates?.trim()
                ? pubmed.key_updates
                : prev.diagnosis_summary,
              ai_summary:
                pubmed?.disease_name
                  ? {
                      issue: `Guideline for ${pubmed.disease_name}`,
                      work_log_summary:
                        pubmed.key_updates || "Generated from the latest PubMed evidence.",
                    }
                  : prev.ai_summary,
            }));
          } else if (kind === "technician_steps") {
            const steps = Array.isArray(traceEntry.steps)
              ? traceEntry.steps.filter(Boolean)
              : [];
            const completedByAi = Array.isArray(traceEntry.steps_completed_by_ai)
              ? traceEntry.steps_completed_by_ai
              : [];
            setLastRunResult((prev) => ({
              ...prev,
              diagnosis_summary: traceEntry.summary ?? prev.diagnosis_summary,
              technician_steps: steps,
              steps_completed_by_ai: completedByAi,
            }));
          }
          if (traceEntry.done) {
            eventSource.close();
            setRunInProgress(false);
            setApprovalPending(null);
            setApprovalExecutionId(null);
            if (traceEntry.error && typeof traceEntry.error === "string") {
              setError(traceEntry.error);
            }
            fetchAgentRunResult(execution_id)
              .then((raw) => {
                const r = normalizeAgentRunResult(raw);
                const parsedOutput = r.output ? parsePubmedOutput(r.output) : null;
                setLastRunResult((prev) => {
                  const next = {
                    ...prev,
                    ticketId: selectedId ?? prev.ticketId,
                    ai_summary: r.ai_summary ?? prev.ai_summary,
                    diagnostics_entries:
                      (r.diagnostics_entries?.length ?? 0) > 0
                        ? r.diagnostics_entries
                        : prev.diagnostics_entries,
                    missing_tool_requests:
                      (r.missing_tool_requests?.length ?? 0) > 0
                        ? r.missing_tool_requests ?? prev.missing_tool_requests
                        : prev.missing_tool_requests,
                    output: r.output ?? prev.output,
                    pubmed_guideline: parsedOutput ?? prev.pubmed_guideline,
                    diagnosis_summary:
                      parsedOutput?.key_updates
                        ? parsedOutput.key_updates
                        : prev.diagnosis_summary,
                    steps_completed_by_ai:
                      r.steps_completed_by_ai ?? prev.steps_completed_by_ai,
                  };
                  saveRunSnapshot(execution_id, next);
                  return next;
                });
                markRunFinished(execution_id, { done: true, error: r.error });
              })
              .catch(() => {});
            refreshSelectedTicket();
          }
        } catch {
          // ignore
        }
      };
      eventSource.onerror = () => {
        eventSource.close();
        setRunInProgress(false);
        setApprovalPending(null);
        setApprovalExecutionId(null);
      };
    } catch (e) {
      setError(String(e));
      setRunStatus("");
      setRunInProgress(false);
    }
  };

  const displayTicket: TicketRow | null =
    selectedTicket ??
    (selectedId != null
      ? {
          id: selectedId,
          title: jobTitleHint ?? `Job #${selectedId}`,
          description: "",
          status: "not_started",
        }
      : null);

  const handleApproval = (action: "approve" | "reject") => {
    if (!approvalPending) return;
    postApproval(action, approvalExecutionId ?? undefined)
      .then(() => {
        setApprovalPending(null);
        setApprovalExecutionId(null);
      })
      .catch(() => {
        setApprovalPending(null);
        setApprovalExecutionId(null);
      });
  };

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        height: "100%",
        width: "100%",
        display: "flex",
        flexDirection: "row",
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Modal: autoryzacja restartu (gdy agent pyta o zatwierdzenie) */}
      {approvalPending && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
          }}
        >
          <div
            style={{
              background: "white",
              borderRadius: 12,
              padding: 24,
              maxWidth: 420,
              boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
            }}
          >
            <h3 style={{ margin: "0 0 12px", fontSize: 18 }}>
              ⚠️ Approval required
            </h3>
            <p style={{ margin: "0 0 20px", fontSize: 14, color: "#475569", lineHeight: 1.5 }}>
              {approvalPending.reason}
            </p>
            {approvalPending.tool_name === "restart_service" && (
              <p style={{ margin: "0 0 20px", fontSize: 13, color: "#64748b" }}>
                Service: <strong>{approvalPending.service_name}</strong><br />
                Server: <strong>{approvalPending.server_ip}</strong>
              </p>
            )}
            <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => handleApproval("reject")}
                style={{
                  padding: "10px 20px",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  background: "white",
                  cursor: "pointer",
                  fontSize: 14,
                  fontWeight: 600,
                }}
              >
                Reject
              </button>
              <button
                type="button"
                onClick={() => handleApproval("approve")}
                style={{
                  padding: "10px 20px",
                  borderRadius: 8,
                  border: "none",
                  background: "#16a34a",
                  color: "white",
                  cursor: "pointer",
                  fontSize: 14,
                  fontWeight: 600,
                }}
              >
                Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {!detailOnly ? (
      <div
        style={{
          width: 280,
          flexShrink: 0,
          minHeight: 0,
          height: "100%",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          background: "white",
          borderRight: "1px solid #e2e8f0",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Tickets</h2>
          <button
            type="button"
            onClick={loadTickets}
            style={{
              background: "white",
              border: "1px solid #e2e8f0",
              padding: "6px 10px",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
        </div>
        {error && (
          <div
            style={{
              margin: 10,
              padding: 10,
              background: "#fef2f2",
              color: "#b91c1c",
              borderRadius: 6,
              fontSize: 12,
            }}
          >
            {error}
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          {loading ? (
            <p style={{ padding: 16, color: "#64748b", fontSize: 13 }}>
              Loading…
            </p>
          ) : tickets.length === 0 ? (
            <p style={{ padding: 16, color: "#64748b", fontSize: 13 }}>
              No tickets.
            </p>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: "8px 0" }}>
              {tickets.map((t) => {
                const active = selectedId === t.id;
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(t.id)}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "10px 16px",
                        border: "none",
                        background: active ? "#eef2ff" : "transparent",
                        cursor: "pointer",
                        fontSize: 13,
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        borderLeft: active ? "3px solid #4f46e5" : "3px solid transparent",
                      }}
                    >
                      <span style={{ fontSize: 14 }}>{statusIcon(t.status)}</span>
                      <span
                        style={{
                          flex: 1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          fontWeight: active ? 600 : 500,
                          color: "#1e293b",
                        }}
                      >
                        #{t.id} {t.title}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
      ) : null}

      {/* Center panel: details + Run Agent + AI Summary + Diagnostics + Next Steps */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          height: "100%",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          background: "#f8fafc",
        }}
      >
        {selectedId == null ? (
          <div
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 16,
              color: "#94a3b8",
              fontSize: 16,
              padding: 24,
            }}
          >
            {detailOnly ? (
              <>
                <p style={{ margin: 0, textAlign: "center" }}>
                  Start a new pipeline run — choose a research job.
                </p>
                <select
                  value=""
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    if (id > 0) setSelectedId(id);
                  }}
                  style={{
                    padding: "10px 14px",
                    borderRadius: 8,
                    border: "1px solid #cbd5e1",
                    fontSize: 14,
                    minWidth: 280,
                  }}
                >
                  <option value="">Research job…</option>
                  {tickets.map((t) => (
                    <option key={t.id} value={t.id}>
                      #{t.id} {t.title}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              "Select a ticket from the list on the left."
            )}
          </div>
        ) : (
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflow: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 0,
              scrollbarGutter: "stable",
            }}
          >
            {/* Ticket details + Run Agent */}
            <div
              style={{
                background: "white",
                padding: 24,
                borderBottom: "1px solid #e2e8f0",
              }}
            >
              {/* Controls row — full width, sits above ticket info */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  marginBottom: 16,
                  flexWrap: "wrap",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    flexWrap: "wrap",
                  }}
                >
                  <select
                    value={flowKey}
                    onChange={(e) => setFlowKey(e.target.value)}
                    disabled={runInProgress}
                    style={{
                      padding: "9px 12px",
                      borderRadius: 6,
                      border: "1px solid #e2e8f0",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#334155",
                      background: "white",
                      cursor: runInProgress ? "default" : "pointer",
                    }}
                  >
                    {availableFlows.map((f) => (
                      <option key={f.key} value={f.key}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={modelProfile}
                    onChange={(e) =>
                      setModelProfile(e.target.value as ModelProfile)
                    }
                    disabled={runInProgress}
                    title="Model profile: vllm (self-hosted), production (OpenAI), test (DeepSeek), openrouter (OpenRouter)"
                    style={{
                      padding: "9px 12px",
                      borderRadius: 6,
                      border: "1px solid #e2e8f0",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#334155",
                      background: "white",
                      cursor: runInProgress ? "default" : "pointer",
                    }}
                  >
                    <option value="vllm">vLLM (Gemma)</option>
                    <option value="production">Production (OpenAI)</option>
                    <option value="test">Test (DeepSeek)</option>
                    <option value="openrouter">OpenRouter (Gemma 4 31B free)</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleRunAgent}
                    disabled={runInProgress}
                    style={{
                      background: runInProgress ? "#e5e7eb" : "#4f46e5",
                      color: runInProgress ? "#6b7280" : "white",
                      border: "none",
                      padding: "10px 20px",
                      borderRadius: 6,
                      fontWeight: 600,
                      fontSize: 13,
                      cursor: runInProgress ? "default" : "pointer",
                    }}
                  >
                    {runInProgress ? "Agent running…" : "Run Agent"}
                  </button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <button
                    type="button"
                    onClick={clearAgentResultForSelected}
                    disabled={runInProgress || lastRunResult.ticketId !== selectedId}
                    style={{
                      background: "transparent",
                      color:
                        !runInProgress && lastRunResult.ticketId === selectedId
                          ? "#6b7280"
                          : "#cbd5e1",
                      border: "none",
                      padding: "2px 4px",
                      borderRadius: 4,
                      fontSize: 11,
                      cursor:
                        !runInProgress && lastRunResult.ticketId === selectedId
                          ? "pointer"
                          : "default",
                      textDecoration:
                        !runInProgress && lastRunResult.ticketId === selectedId
                          ? "underline"
                          : "none",
                    }}
                  >
                    Clear result
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowAgentThoughts((prev) => !prev)}
                    style={{
                      background: "transparent",
                      color: "#6b7280",
                      border: "none",
                      padding: "2px 4px",
                      borderRadius: 4,
                      fontSize: 11,
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    {showAgentThoughts ? "Hide Agent thoughts" : "Show Agent thoughts"}
                  </button>
                </div>
              </div>
              {/* Ticket info — full width below controls */}
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontSize: 18 }}>
                    {statusIcon(displayTicket?.status ?? "not_started")}
                  </span>
                  <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>
                    #{displayTicket?.id} {displayTicket?.title}
                  </h3>
                </div>
                {displayTicket?.description ? (
                  <p
                    style={{
                      margin: "0 0 12px",
                      fontSize: 13,
                      color: "#475569",
                      lineHeight: 1.5,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      overflowWrap: "break-word",
                    }}
                  >
                    {displayTicket.description}
                  </p>
                ) : null}
                {displayTicket?.resolution_summary ? (
                  <div
                    style={{
                      marginTop: 12,
                      padding: 12,
                      background: "#f1f5f9",
                      borderRadius: 8,
                      fontSize: 13,
                      color: "#334155",
                      wordBreak: "break-word",
                      overflowWrap: "break-word",
                    }}
                  >
                    <strong>Summary:</strong>{" "}
                    {displayTicket.resolution_summary}
                  </div>
                ) : null}
              </div>
              {runStatus && (
                <p style={{ margin: "12px 0 0", fontSize: 12, color: "#64748b" }}>
                  {runStatus}
                </p>
              )}
              {selectedId != null && lastRunResult.ticketId === selectedId && (
                <OutputPreview
                  pubmedGuideline={lastRunResult.pubmed_guideline}
                  rawOutput={lastRunResult.output}
                  runInProgress={runInProgress}
                />
              )}
            </div>

            {/* Agent result: always visible after Run Agent (AI Summary, Diagnostics, Diagnosis, Steps, Output). */}
            {selectedId != null && lastRunResult.ticketId === selectedId && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  padding: 24,
                  gap: 20,
                }}
              >
                {/* AI Summary – zawsze widoczny */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#4338ca",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>💡</span> AI Summary
                  </h4>
                  <div
                    style={{
                      background: "#eef2ff",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #4f46e5",
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: "#312e81",
                    }}
                  >
                    {lastRunResult.ai_summary &&
                    (lastRunResult.ai_summary.issue ||
                      lastRunResult.ai_summary.work_log_summary) ? (
                      <>
                        {lastRunResult.ai_summary.issue && (
                          <p style={{ margin: "0 0 8px" }}>
                            <strong>Issue:</strong>{" "}
                            {lastRunResult.ai_summary.issue}
                          </p>
                        )}
                        {lastRunResult.ai_summary.work_log_summary && (
                          <p style={{ margin: 0 }}>
                            <strong>Work log:</strong>{" "}
                            {lastRunResult.ai_summary.work_log_summary}
                          </p>
                        )}
                      </>
                    ) : (
                      <p style={{ margin: 0, color: "#6366f1", fontStyle: "italic" }}>
                        None yet — the agent will set it after calling set_ai_summary.
                      </p>
                    )}
                  </div>
                </section>

                {/* Diagnostics — always visible, more than just "tool: OK". */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#047857",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>🔧</span> Diagnostics
                  </h4>
                  <div
                    style={{
                      background: "#ecfdf5",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #10b981",
                      fontSize: 13,
                      color: "#065f46",
                    }}
                  >
                    {lastRunResult.diagnostics_entries.length > 0 ? (
                      <ul
                        style={{
                          margin: 0,
                          paddingLeft: 20,
                          lineHeight: 1.6,
                          listStyle: "none",
                        }}
                      >
                        {lastRunResult.diagnostics_entries.map((d, i) => (
                          <li key={i} style={{ marginBottom: 12 }}>
                            <strong>{d.tool}</strong>: {d.result}
                            {d.detail && (
                              <div
                                style={{
                                  marginTop: 4,
                                  paddingLeft: 8,
                                  whiteSpace: "pre-wrap",
                                  wordBreak: "break-word",
                                  color: "#047857",
                                }}
                              >
                                {d.detail}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ margin: 0, color: "#059669", fontStyle: "italic" }}>
                        No entries yet — they will appear after calls such as set_ai_summary, ping_ip, and get_server_logs.
                      </p>
                    )}
                  </div>
                </section>

                {/* Missing tools requested – jak AI Summary / Diagnoza */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#92400e",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>🛠️</span> Missing tools requested
                  </h4>
                  <div
                    style={{
                      background: "#fffbeb",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #d97706",
                      fontSize: 13,
                      color: "#92400e",
                    }}
                  >
                    {lastRunResult.missing_tool_requests.length > 0 ? (
                      <ul
                        style={{
                          margin: 0,
                          paddingLeft: 20,
                          lineHeight: 1.6,
                          listStyle: "none",
                        }}
                      >
                        {lastRunResult.missing_tool_requests.map((m, i) => (
                          <li key={i} style={{ marginBottom: 12 }}>
                            <strong>{m.tool_name}</strong>
                            {m.reason && (
                              <span>: {m.reason}</span>
                            )}
                            {m.ticket_id != null && (
                              <span style={{ opacity: 0.8 }}> (ticket #{m.ticket_id})</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ margin: 0, color: "#b45309", fontStyle: "italic" }}>
                        None — the agent did not request any missing tools.
                      </p>
                    )}
                  </div>
                </section>

                {lastRunResult.pubmed_guideline && (
                  <section>
                    <h4
                      style={{
                        margin: "0 0 10px",
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#166534",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span aria-hidden>🩺</span> Guideline
                      {lastRunResult.pubmed_guideline.disease_name && (
                        <span style={{ color: "#065f46", fontWeight: 600 }}>
                          — {lastRunResult.pubmed_guideline.disease_name}
                        </span>
                      )}
                    </h4>
                    {lastRunResult.pubmed_guideline.guideline_html ? (
                      <div
                        style={{
                          background: "#f0fdf4",
                          padding: 16,
                          borderRadius: 8,
                          borderLeft: "4px solid #16a34a",
                          fontSize: 13,
                          lineHeight: 1.6,
                          color: "#14532d",
                        }}
                        dangerouslySetInnerHTML={{
                          __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.guideline_html),
                        }}
                      />
                    ) : (
                      <div
                        style={{
                          background: "#fffbeb",
                          padding: 16,
                          borderRadius: 8,
                          borderLeft: "4px solid #d97706",
                          fontSize: 13,
                          lineHeight: 1.6,
                          color: "#78350f",
                        }}
                      >
                        Guideline HTML is empty in the agent output. Check Raw Agent Output below and rerun if needed.
                      </div>
                    )}
                    <div
                      style={{
                        marginTop: 10,
                        display: "flex",
                        gap: 10,
                        flexWrap: "wrap",
                        fontSize: 12,
                        color: "#14532d",
                      }}
                    >
                      {typeof lastRunResult.pubmed_guideline.evidence_score === "number" && (
                        <span style={{ background: "#dcfce7", borderRadius: 999, padding: "4px 10px" }}>
                          Evidence score: {lastRunResult.pubmed_guideline.evidence_score}/100
                        </span>
                      )}
                      {typeof lastRunResult.pubmed_guideline.confidence_index === "number" && (
                        <span style={{ background: "#dcfce7", borderRadius: 999, padding: "4px 10px" }}>
                          Confidence index: {lastRunResult.pubmed_guideline.confidence_index}/100
                        </span>
                      )}
                      {lastRunResult.pubmed_guideline.confidence_level && (
                        <span style={{ background: "#dcfce7", borderRadius: 999, padding: "4px 10px" }}>
                          Level: {lastRunResult.pubmed_guideline.confidence_level}
                        </span>
                      )}
                    </div>
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.reliability_assessment_html && (
                  <section>
                    <h4
                      style={{
                        margin: "0 0 10px",
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#7c2d12",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span aria-hidden>📊</span> Reliability Assessment
                    </h4>
                    <div
                      style={{
                        background: "#fff7ed",
                        padding: 16,
                        borderRadius: 8,
                        borderLeft: "4px solid #ea580c",
                        fontSize: 13,
                        lineHeight: 1.6,
                        color: "#7c2d12",
                      }}
                      dangerouslySetInnerHTML={{
                        __html: sanitizeGeneratedHtml(
                          lastRunResult.pubmed_guideline.reliability_assessment_html,
                        ),
                      }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.recommendation_matrix_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>🧭</span> Recommendation Matrix
                    </h4>
                    <div
                      style={{ background: "#f8fafc", padding: 16, borderRadius: 8, borderLeft: "4px solid #64748b", fontSize: 13, lineHeight: 1.6, color: "#334155", overflowX: "auto" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.recommendation_matrix_html) }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.red_flags_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#b91c1c", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>🚨</span> Red Flags
                    </h4>
                    <div
                      style={{ background: "#fef2f2", padding: 16, borderRadius: 8, borderLeft: "4px solid #dc2626", fontSize: 13, lineHeight: 1.6, color: "#7f1d1d" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.red_flags_html) }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.contraindications_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#92400e", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>⛔</span> Contraindications
                    </h4>
                    <div
                      style={{ background: "#fff7ed", padding: 16, borderRadius: 8, borderLeft: "4px solid #ea580c", fontSize: 13, lineHeight: 1.6, color: "#7c2d12" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.contraindications_html) }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.follow_up_schedule_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#0f766e", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>📅</span> Follow-up Schedule
                    </h4>
                    <div
                      style={{ background: "#ecfeff", padding: 16, borderRadius: 8, borderLeft: "4px solid #06b6d4", fontSize: 13, lineHeight: 1.6, color: "#164e63" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.follow_up_schedule_html) }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.evidence_gaps_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#7c3aed", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>🧪</span> Evidence Gaps
                    </h4>
                    <div
                      style={{ background: "#f5f3ff", padding: 16, borderRadius: 8, borderLeft: "4px solid #8b5cf6", fontSize: 13, lineHeight: 1.6, color: "#4c1d95" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.evidence_gaps_html) }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.source_links_html && (
                  <section>
                    <h4
                      style={{
                        margin: "0 0 10px",
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#1d4ed8",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span aria-hidden>🔗</span> Source Links
                    </h4>
                    <div
                      style={{
                        background: "#eff6ff",
                        padding: 16,
                        borderRadius: 8,
                        borderLeft: "4px solid #2563eb",
                        fontSize: 13,
                        lineHeight: 1.6,
                        color: "#1e3a8a",
                      }}
                      dangerouslySetInnerHTML={{
                        __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.source_links_html),
                      }}
                    />
                  </section>
                )}

                {lastRunResult.pubmed_guideline?.disclaimer_html && (
                  <section>
                    <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 6 }}>
                      <span aria-hidden>ℹ️</span> Clinical Disclaimer
                    </h4>
                    <div
                      style={{ background: "#f8fafc", padding: 16, borderRadius: 8, borderLeft: "4px solid #94a3b8", fontSize: 13, lineHeight: 1.6, color: "#334155" }}
                      dangerouslySetInnerHTML={{ __html: sanitizeGeneratedHtml(lastRunResult.pubmed_guideline.disclaimer_html) }}
                    />
                  </section>
                )}

                {/* Diagnoza (summary z update_ticket_status) – zawsze widoczna */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#0e7490",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>📋</span> Diagnosis
                  </h4>
                  <div
                    style={{
                      background: "#ecfeff",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #06b6d4",
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: "#164e63",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {lastRunResult.diagnosis_summary || (
                      <span style={{ fontStyle: "italic" }}>None yet — the agent will set it in update_ticket_status(summary).</span>
                    )}
                  </div>
                </section>

                {/* Kroki dla technika – z SSE, z ticketu lub komunikat */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#b45309",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>📌</span> Technician steps
                  </h4>
                  <div
                    style={{
                      background: "#fffbeb",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #f59e0b",
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: "#78350f",
                    }}
                  >
                    {(() => {
                      const steps =
                        lastRunResult.technician_steps.length > 0
                          ? lastRunResult.technician_steps
                          : (() => {
                              const t = tickets.find((x) => x.id === lastRunResult.ticketId);
                              const stepsText = t?.diagnostic_steps?.trim();
                              return stepsText
                                ? stepsText.split(/\r?\n/).filter((s) => s.trim())
                                : [];
                            })();
                      const completedByAi = new Set(lastRunResult.steps_completed_by_ai ?? []);
                      if (steps.length === 0) {
                        return (
                          <p style={{ margin: 0, color: "#92400e", fontStyle: "italic" }}>
                            No steps were returned by the agent. The backend now requires at least 2-3 steps in `update_ticket_status(steps_taken)`, so the next Run Agent should include them. Refresh the ticket list after the run completes.
                          </p>
                        );
                      }
                      return (
                        <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
                          {steps.map((step, i) => {
                            const label = (String(step).replace(/^\d+\.\s*/, "").trim() || step) as string;
                            const doneByAi = completedByAi.has(i);
                            const doneHeuristic =
                              /^(removed|added|updated|completed)\b/i.test(label);
                            const doneByAiEffective = doneByAi || doneHeuristic;
                            const checked = doneByAiEffective || stepChecked[i] === true;
                            return (
                              <li key={i} style={{ marginBottom: 8, display: "flex", alignItems: "flex-start", gap: 8 }}>
                                <input
                                  type="checkbox"
                                  id={`step-${i}`}
                                  checked={checked}
                                  disabled={doneByAiEffective}
                                  onChange={() => {
                                    if (doneByAiEffective) return;
                                    setStepChecked((prev) => ({ ...prev, [i]: !prev[i] }));
                                  }}
                                  style={{ marginTop: 3, flexShrink: 0, cursor: doneByAiEffective ? "default" : "pointer" }}
                                  title={doneByAiEffective ? "Completed by the agent (cannot be unchecked)" : undefined}
                                />
                                <label
                                  htmlFor={`step-${i}`}
                                  style={{
                                    margin: 0,
                                    cursor: doneByAiEffective ? "default" : "pointer",
                                    textDecoration: checked ? "line-through" : "none",
                                    opacity: doneByAiEffective ? 0.85 : 1,
                                  }}
                                >
                                  {label}
                                </label>
                              </li>
                            );
                          })}
                        </ul>
                      );
                    })()}
                  </div>
                </section>

                {/* Processed Output */}
                <section>
                  <h4
                    style={{
                      margin: "0 0 10px",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#64748b",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span aria-hidden>💬</span> Processed Output
                  </h4>
                  <div
                    style={{
                      background: "#f8fafc",
                      color: "#334155",
                      padding: 16,
                      borderRadius: 8,
                      borderLeft: "4px solid #64748b",
                      fontSize: 13,
                      lineHeight: 1.6,
                      whiteSpace: "pre-wrap",
                      overflow: "auto",
                      maxHeight: 320,
                    }}
                  >
                    {(() => {
                      const g = lastRunResult.pubmed_guideline;
                      if (g) {
                        const items: string[] = [];
                        if (g.disease_name) items.push(`Disease: ${g.disease_name}`);
                        if (typeof g.article_count === "number") items.push(`Articles used: ${g.article_count}`);
                        if (g.confidence_level) items.push(`Confidence level: ${g.confidence_level}`);
                        if (typeof g.evidence_score === "number") items.push(`Evidence score: ${g.evidence_score}/100`);
                        if (typeof g.confidence_index === "number") items.push(`Confidence index: ${g.confidence_index}/100`);
                        if (g.key_updates) items.push(`Key updates:\n${g.key_updates}`);
                        if (g.references) items.push(`References:\n${g.references}`);
                        if (items.length === 0) {
                          return (
                            <span style={{ fontStyle: "italic", color: "#64748b" }}>
                              Guideline object is present, but contains no displayable fields yet.
                            </span>
                          );
                        }
                        return items.join("\n\n");
                      }
                      if (!lastRunResult.output) {
                        return (
                          <span style={{ fontStyle: "italic", color: "#64748b" }}>
                            None yet — it will appear after the agent finishes.
                          </span>
                        );
                      }
                      const plain = lastRunResult.output.length > 1200
                        ? `${lastRunResult.output.slice(0, 1200)}…`
                        : lastRunResult.output;
                      return plain;
                    })()}
                  </div>
                </section>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right panel: Agent thoughts — full height. */}
      {showAgentThoughts && (
        <div
          style={{
            width: 400,
            flexShrink: 0,
            minHeight: 0,
            height: "100%",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            background: "#0f172a",
            borderLeft: "1px solid #334155",
          }}
        >
        <div
          style={{
            padding: "12px 16px",
            borderBottom: "1px solid #334155",
            fontSize: 11,
            fontWeight: 700,
            color: "#94a3b8",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Agent thoughts
        </div>
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            padding: 16,
            fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          {trace.length === 0 ? (
            <div style={{ color: "#64748b" }}>
              Select a ticket and click Run Agent to view the live stream of the
              agent's thoughts.
            </div>
          ) : (
            trace.map((e, i) => {
              const ev = e as {
                text?: string;
                error?: string;
                kind?: string;
                tool?: string;
              };
              const kind = ev.kind ?? "";
              const isError = Boolean(ev.error);
              const isHeartbeat = kind === "heartbeat";
              if (isHeartbeat) {
                return (
                  <div
                    key={i}
                    style={{ marginBottom: 4, color: "#1e293b", opacity: 0.3 }}
                  >
                    ·
                  </div>
                );
              }
              let bg = "#020617";
              let border = "#1e293b";
              let color = "#e2e8f0";
              if (isError) {
                bg = "#450a0a";
                border = "#b91c1c";
                color = "#fecaca";
              } else if (kind === "ai_summary") {
                bg = "#1e293b";
                border = "#6366f1";
              } else if (kind === "diagnostic") {
                bg = "#022c22";
                border = "#22c55e";
              } else if (kind === "ticket_status") {
                bg = "#111827";
                border = "#facc15";
              } else if (kind === "output") {
                bg = "#020617";
                border = "#64748b";
              }
              const line =
                typeof ev.text === "string"
                  ? ev.text
                  : ev.error
                    ? `Error: ${ev.error}`
                    : JSON.stringify(e);
              return (
                <div
                  key={i}
                  style={{
                    marginBottom: 8,
                    padding: 8,
                    borderRadius: 6,
                    border: `1px solid ${border}`,
                    background: bg,
                    color,
                  }}
                >
                  {kind && (
                    <span
                      style={{
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                        fontWeight: 700,
                        opacity: 0.8,
                      }}
                    >
                      {kind}
                      {ev.tool ? ` · ${ev.tool}` : ""}
                    </span>
                  )}
                  <div>{line}</div>
                </div>
              );
            })
          )}
        </div>

        <div
          style={{
            borderTop: "1px solid #1f2937",
            padding: 12,
            fontSize: 11,
            color: "#9ca3af",
          }}
        >
          <div
            style={{
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              marginBottom: 6,
            }}
          >
            MCP tools (backend)
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, lineHeight: 1.5 }}>
            <li>
              <strong>list_available_tools</strong> – lists MCP tools.
            </li>
            <li>
              <strong>set_ai_summary</strong> – stores issue summary and work
              log at the start of a run.
            </li>
            <li>
              <strong>pubmed_search_articles</strong> – PubMed E-utilities
              search across query variants.
            </li>
            <li>
              <strong>pubmed_fetch_article_details</strong> – fetches abstracts
              and metadata for a list of PMIDs.
            </li>
            <li>
              <strong>pubmed_browser_search</strong> – browser-based PubMed
              fallback when the API path returns no results.
            </li>
            <li>
              <strong>update_ticket_status</strong> – stores the run status,
              summary, and steps taken.
            </li>
            <li>
              <strong>request_missing_tool</strong> – queues a request for a
              missing tool so the catalog can grow on demand.
            </li>
          </ul>
        </div>
        </div>
      )}
    </div>
  );
}
