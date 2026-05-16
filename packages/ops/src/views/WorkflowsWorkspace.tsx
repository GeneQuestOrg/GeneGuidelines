import { useState, useEffect, useCallback, useMemo } from "react";
import { FlowCanvas } from "../components/FlowCanvas";
import { NodeEditor } from "../components/NodeEditor";
import { FLOWS } from "../data/flowData";
import {
  API_BASE,
  fetchFlow,
  fetchFlowsMap,
  updateNodePrompt,
  deleteFlowNode,
  deleteFlowEdge,
  apiFlowToFlowDefinition,
} from "../api/client";
import type { FlowDefinition, FlowNode, FlowsMap } from "../types";
import "./workflows-workspace.css";

const FLOW_INSPECTOR_MIN_W = 280;
const FLOW_INSPECTOR_MAX_W = 560;
const FLOW_INSPECTOR_DEFAULT_W = 320;

const FLOW_TAB_ORDER = ["operational", "builder", "pubmed", "doctor_finder"] as const;

export function WorkflowsWorkspace() {
  const [flow, setFlow] = useState<string>("operational");
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);
  const [flowsMap, setFlowsMap] = useState<FlowsMap>(FLOWS);
  const [flowsLoadError, setFlowsLoadError] = useState<string | null>(null);
  const [nodeVersions, setNodeVersions] = useState<Record<string, number>>({});
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [showAddNodeModal, setShowAddNodeModal] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<{
    id: string;
    source: string;
    target: string;
  } | null>(null);
  const [inspectorWidth, setInspectorWidth] = useState(FLOW_INSPECTOR_DEFAULT_W);
  const [nodeInspectorOpen, setNodeInspectorOpen] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/health`, { method: "GET" })
      .then((r) => r.ok)
      .then(setApiReachable)
      .catch(() => setApiReachable(false));
  }, []);

  const mergedFlows = useMemo(() => ({ ...FLOWS, ...flowsMap }), [flowsMap]);

  const flowTabKeys = useMemo(() => {
    const keys = new Set(Object.keys(mergedFlows));
    const ordered = FLOW_TAB_ORDER.filter((k) => keys.has(k));
    const rest = [...keys]
      .filter((k) => !(FLOW_TAB_ORDER as readonly string[]).includes(k))
      .sort();
    return [...ordered, ...rest];
  }, [mergedFlows]);

  const resolvedFlowKey =
    flowTabKeys.length === 0
      ? "operational"
      : flowTabKeys.includes(flow)
        ? flow
        : flowTabKeys[0]!;

  useEffect(() => {
    fetchFlowsMap(FLOWS)
      .then((map) => {
        setFlowsMap(map);
        setFlowsLoadError(null);
      })
      .catch((e) => {
        setFlowsLoadError(
          e instanceof Error ? e.message : "Failed to load flows",
        );
      });
  }, []);

  const refreshFlow = useCallback(
    async (flowKey: string): Promise<FlowDefinition | null> => {
      try {
        const def = await fetchFlow(flowKey);
        const fallback = FLOWS[flowKey];
        const flowDef = apiFlowToFlowDefinition(def, {
          label: fallback?.label ?? flowKey,
          desc: fallback?.desc ?? "",
        });
        setFlowsMap((prev) => ({ ...prev, [flowKey]: flowDef }));
        return flowDef;
      } catch {
        return null;
      }
    },
    [],
  );

  const handleFlowSwitch = (f: string) => {
    setFlow(f);
    setSelectedNode(null);
    setNodeInspectorOpen(true);
  };

  const handleSelectNode = useCallback(
    (flowNode: FlowNode) => {
      setNodeInspectorOpen(true);
      setSelectedNode(flowNode);
      refreshFlow(resolvedFlowKey).then((updated) => {
        if (updated) {
          const fresh = updated.nodes.find((n) => n.id === flowNode.id);
          if (fresh) setSelectedNode(fresh);
        }
      });
    },
    [resolvedFlowKey, refreshFlow],
  );

  const beginInspectorResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = inspectorWidth;
    const onMove = (ev: MouseEvent) => {
      setInspectorWidth(
        Math.min(
          FLOW_INSPECTOR_MAX_W,
          Math.max(FLOW_INSPECTOR_MIN_W, startW + (startX - ev.clientX)),
        ),
      );
    };
    const onUp = () => {
      document.body.style.removeProperty("cursor");
      document.body.style.removeProperty("user-select");
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div className="ops-workflows">
      {apiReachable === false ? (
        <div className="ops-workflows__banner ops-workflows__banner--error">
          Backend unreachable. Start:{" "}
          <code>python -m uvicorn backend.main:app --reload</code> (port 8000).
          In dev, leave <code>VITE_API_URL</code> unset so Vite proxies{" "}
          <code>/api</code>.
        </div>
      ) : null}
      <header className="ops-workflows__toolbar">
        <div className="ops-workflows__flow-tabs">
          {flowTabKeys.map((id) => {
            const active = resolvedFlowKey === id;
            const def = mergedFlows[id];
            return (
              <button
                key={id}
                type="button"
                onClick={() => handleFlowSwitch(id)}
                style={{
                  border: "none",
                  background: active ? "white" : "none",
                  padding: "6px 16px",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  color: active ? "#1e293b" : "#64748b",
                  cursor: "pointer",
                  boxShadow: active ? "0 1px 3px rgba(0, 0, 0, 0.08)" : "none",
                }}
              >
                {def?.label ?? id}
              </button>
            );
          })}
        </div>
        <div className="ops-workflows__toolbar-actions">
          <button
            type="button"
            className="ops-workflows__btn ops-workflows__btn--primary"
            onClick={() => setShowAddNodeModal(true)}
          >
            + Add node
          </button>
          {selectedNode != null && nodeInspectorOpen ? (
            <button
              type="button"
              className="ops-workflows__btn ops-workflows__btn--secondary"
              onClick={() => setNodeInspectorOpen(false)}
            >
              Collapse panel
            </button>
          ) : null}
          {selectedNode != null && !nodeInspectorOpen ? (
            <button
              type="button"
              className="ops-workflows__btn ops-workflows__btn--secondary"
              onClick={() => setNodeInspectorOpen(true)}
            >
              Node panel
            </button>
          ) : null}
          {selectedEdge ? (
            <button
              type="button"
              className="ops-workflows__btn ops-workflows__btn--danger"
              onClick={async () => {
                if (!selectedEdge) return;
                try {
                  await deleteFlowEdge(
                    resolvedFlowKey,
                    selectedEdge.source,
                    selectedEdge.target,
                  );
                } catch {
                  // ignore
                }
                setSelectedEdge(null);
                await refreshFlow(resolvedFlowKey);
              }}
            >
              Delete connection
            </button>
          ) : null}
        </div>
      </header>
      <div className="ops-workflows__body">
        <div className="ops-workflows__canvas-wrap">
          {flowsLoadError ? (
            <div className="ops-workflows__banner ops-workflows__banner--warn">
              {flowsLoadError} (using in-memory fallback data)
            </div>
          ) : null}
          <FlowCanvas
            flowsMap={mergedFlows}
            flow={resolvedFlowKey}
            selectedId={selectedNode?.id ?? null}
            onSelect={handleSelectNode}
            onRefresh={async () => {
              await refreshFlow(resolvedFlowKey);
            }}
            showAddModal={showAddNodeModal}
            setShowAddModal={setShowAddNodeModal}
            selectedEdge={selectedEdge}
            onSelectEdge={setSelectedEdge}
            onPaneDeselect={() => {
              setSelectedNode(null);
              setNodeInspectorOpen(true);
            }}
          />
        </div>
        {selectedNode != null && nodeInspectorOpen ? (
          <>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize node editor panel"
              className="ops-workflows__resizer"
              onMouseDown={beginInspectorResize}
            />
            <div
              className="ops-workflows__inspector"
              style={{
                width: inspectorWidth,
                maxWidth: "min(560px, 40vw)",
              }}
            >
              <NodeEditor
                key={`${resolvedFlowKey}-${selectedNode.id}-v${nodeVersions[`${resolvedFlowKey}-${selectedNode.id}`] ?? 1}`}
                flowKey={resolvedFlowKey}
                node={selectedNode}
                version={
                  nodeVersions[`${resolvedFlowKey}-${selectedNode.id}`] ?? 1
                }
                onSave={async (payload) => {
                  if (!selectedNode) return;
                  const nodeId = selectedNode.id;
                  const versionKey = `${resolvedFlowKey}-${nodeId}`;
                  try {
                    const updatedApi = await updateNodePrompt(
                      resolvedFlowKey,
                      nodeId,
                      {
                        prompt: payload.prompt,
                        loop_policy: payload.loop_policy,
                        execution_policy: payload.execution_policy,
                        max_retry: payload.max_retry,
                        ...(payload.label != null && { label: payload.label }),
                        ...(payload.description != null && {
                          description: payload.description,
                        }),
                        ...(payload.python_source != null && {
                          python_source: payload.python_source,
                        }),
                        ...(payload.http_url != null && {
                          http_url: payload.http_url,
                        }),
                        ...(payload.http_method != null && {
                          http_method: payload.http_method,
                        }),
                        ...(payload.http_headers != null && {
                          http_headers: payload.http_headers,
                        }),
                        ...(payload.http_body != null && {
                          http_body: payload.http_body,
                        }),
                        ...(payload.rag_operation != null && {
                          rag_operation: payload.rag_operation,
                        }),
                        ...(payload.rag_body_json != null && {
                          rag_body_json: payload.rag_body_json,
                        }),
                        ...(payload.merge_strategy != null && {
                          merge_strategy: payload.merge_strategy,
                        }),
                        ...(payload.merge_fields != null && {
                          merge_fields: payload.merge_fields,
                        }),
                        ...(payload.merge_key_field != null && {
                          merge_key_field: payload.merge_key_field,
                        }),
                        ...(payload.integration_operation != null && {
                          integration_operation: payload.integration_operation,
                        }),
                        ...(payload.integration_params_json != null && {
                          integration_params_json:
                            payload.integration_params_json,
                        }),
                        ...(payload.integration_credentials_json != null && {
                          integration_credentials_json:
                            payload.integration_credentials_json,
                        }),
                      },
                    );
                    setNodeVersions((prev) => ({
                      ...prev,
                      [versionKey]: (prev[versionKey] ?? 1) + 1,
                    }));
                    const newNode: FlowNode = {
                      id: updatedApi.node_id,
                      type: updatedApi.node_type as FlowNode["type"],
                      label: updatedApi.label,
                      desc: updatedApi.description ?? "",
                      prompt: updatedApi.prompt ?? "",
                      python_source: updatedApi.python_source ?? "",
                      http_url: updatedApi.http_url ?? "",
                      http_method: updatedApi.http_method ?? "GET",
                      http_headers: updatedApi.http_headers ?? "",
                      http_body: updatedApi.http_body ?? "",
                      rag_operation: updatedApi.rag_operation ?? "similar",
                      rag_body_json: updatedApi.rag_body_json ?? "",
                      merge_strategy: updatedApi.merge_strategy ?? "append",
                      merge_fields: updatedApi.merge_fields ?? '["items"]',
                      merge_key_field: updatedApi.merge_key_field ?? "id",
                      integration_operation:
                        updatedApi.integration_operation ?? "",
                      integration_params_json:
                        updatedApi.integration_params_json ?? "{}",
                      integration_credentials_json:
                        updatedApi.integration_credentials_json ?? "",
                      loop_policy: updatedApi.loop_policy ?? "",
                      execution_policy: updatedApi.execution_policy ?? "",
                      max_retry: updatedApi.max_retry ?? 3,
                    };
                    const refreshed = await refreshFlow(resolvedFlowKey);
                    if (refreshed) {
                      const fromServer = refreshed.nodes.find(
                        (n) => n.id === nodeId,
                      );
                      if (fromServer) {
                        setSelectedNode(fromServer);
                      } else {
                        setSelectedNode(newNode);
                        setFlowsMap((prev) => {
                          const flowDef = prev[resolvedFlowKey];
                          if (!flowDef) return prev;
                          return {
                            ...prev,
                            [resolvedFlowKey]: {
                              ...flowDef,
                              nodes: flowDef.nodes.map((n) =>
                                n.id === nodeId ? newNode : n,
                              ),
                            },
                          };
                        });
                      }
                    } else {
                      setSelectedNode(newNode);
                      setFlowsMap((prev) => {
                        const flowDef = prev[resolvedFlowKey];
                        if (!flowDef) return prev;
                        return {
                          ...prev,
                          [resolvedFlowKey]: {
                            ...flowDef,
                            nodes: flowDef.nodes.map((n) =>
                              n.id === nodeId ? newNode : n,
                            ),
                          },
                        };
                      });
                    }
                  } catch {
                    // save error
                  }
                }}
                onDelete={async () => {
                  if (!selectedNode) return;
                  try {
                    await deleteFlowNode(resolvedFlowKey, selectedNode.id);
                  } catch {
                    // ignore
                  }
                  await refreshFlow(resolvedFlowKey);
                  setSelectedNode(null);
                  setNodeInspectorOpen(true);
                }}
              />
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
