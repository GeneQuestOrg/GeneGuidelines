import { useMemo, useEffect, useState, useCallback } from "react";
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  Position,
  type Node,
  type Edge,
  type Connection,
  Background,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FlowNode, FlowsMap } from "../types";
import { NODE_STYLES } from "../data/nodeStyles";
import { StageNode, type StageNodeType } from "./StageNode";
import { CustomEdge } from "./CustomEdge";
import { createFlowNode, createFlowEdge, deleteFlowEdge, updateNodePrompt } from "../api/client";

const edgeTypes = { "custom-edge": CustomEdge };

const NODE_WIDTH = 420;
const NODE_HEIGHT = 90;
const GAP = 40;

function flowToReactFlow(
  flowsMap: FlowsMap,
  flowKey: string,
  selectedId: string | null
): { nodes: Node<StageNodeType["data"], StageNodeType["type"]>[]; edges: Edge[] } {
  const data = flowsMap[flowKey];
  if (!data) return { nodes: [], edges: [] };

  const nodes: Node<StageNodeType["data"], StageNodeType["type"]>[] =
    data.nodes.map((flowNode, i) => ({
      id: flowNode.id,
      type: "stage",
      position:
        flowNode.position != null
          ? { x: flowNode.position.x, y: flowNode.position.y }
          : { x: -NODE_WIDTH / 2, y: i * (NODE_HEIGHT + GAP) },
      data: { flowNode },
      selected: flowNode.id === selectedId,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    }));

  const edges: Edge[] = data.edges.map((flowEdge) => {
    const source = Array.isArray(flowEdge) ? flowEdge[0] : flowEdge.source;
    const target = Array.isArray(flowEdge) ? flowEdge[1] : flowEdge.target;
    const label = Array.isArray(flowEdge) ? undefined : flowEdge.label;
    return {
      id: `${source}-${target}`,
      source,
      target,
      type: "custom-edge",
      ...(label ? { label } : {}),
    };
  });

  return { nodes, edges };
}

const NODE_TYPES_OPTIONS = [
  { value: "action", label: "Action" },
  { value: "code", label: "Code / Function" },
  { value: "http_request", label: "HTTP Request" },
  { value: "prompt", label: "Prompt" },
  { value: "agentic_prompt", label: "Agentic Prompt" },
  { value: "decision", label: "Decision" },
  { value: "trigger", label: "Trigger" },
  { value: "end", label: "End" },
  { value: "output", label: "Output" },
  { value: "merge", label: "Merge" },
  { value: "approval", label: "Approval (HITL)" },
  { value: "guidelines_rag", label: "Guidelines RAG" },
  { value: "pmid_verify", label: "PMID Verify" },
  { value: "pmid_scrub", label: "PMID Scrubber" },
  { value: "evaluation_check", label: "Consistency evaluation" },
];


interface FlowCanvasProps {
  flowsMap: FlowsMap;
  flow: string;
  selectedId: string | null;
  onSelect: (node: FlowNode) => void;
  /** Refresh flow from API after a node or edge is added. */
  onRefresh?: () => void | Promise<void>;
  /** When provided, the "+ Add node" button lives in the App header; the modal stays here. */
  showAddModal?: boolean;
  setShowAddModal?: (show: boolean) => void;
  /** When provided, edge selection and the "Delete connection" button live in the App header. */
  selectedEdge?: { id: string; source: string; target: string } | null;
  onSelectEdge?: (edge: { id: string; source: string; target: string } | null) => void;
  /** Click on empty canvas area (e.g. to collapse the App edit panel). */
  onPaneDeselect?: () => void;
}

export function FlowCanvas({
  flowsMap,
  flow,
  selectedId,
  onSelect,
  onRefresh,
  showAddModal: showAddModalProp,
  setShowAddModal: setShowAddModalProp,
  selectedEdge: selectedEdgeProp,
  onSelectEdge: onSelectEdgeProp,
  onPaneDeselect,
}: FlowCanvasProps) {
  const [internalShowAdd, setInternalShowAdd] = useState(false);
  const showAddModal = setShowAddModalProp != null ? (showAddModalProp ?? false) : internalShowAdd;
  const setShowAddModal = setShowAddModalProp ?? setInternalShowAdd;
  const addButtonOnHeader = setShowAddModalProp != null;
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [connectBusy, setConnectBusy] = useState(false);
  const emptyAddForm = () => ({
    node_type: "action",
    label: "New node",
    description: "",
    prompt: "",
    python_source: "",
    http_url: "",
    http_method: "GET",
    http_headers: "",
    http_body: "",
    rag_operation: "similar",
    rag_body_json: "",
    merge_strategy: "append",
    merge_fields: '["items"]',
    merge_key_field: "id",
    integration_operation: "",
    integration_params_json: "{}",
    integration_credentials_json: "",
  });
  const [addForm, setAddForm] = useState(emptyAddForm);
  const isIntegrationType = false;

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => flowToReactFlow(flowsMap, flow, selectedId),
    [flowsMap, flow, selectedId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [internalSelectedEdge, setInternalSelectedEdge] = useState<{ id: string; source: string; target: string } | null>(null);
  const selectedEdge = onSelectEdgeProp != null ? (selectedEdgeProp ?? null) : internalSelectedEdge;
  const setSelectedEdge = onSelectEdgeProp ?? setInternalSelectedEdge;
  const edgeButtonOnHeader = onSelectEdgeProp != null;

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
    if (onSelectEdgeProp == null) setInternalSelectedEdge(null);
  }, [initialNodes, initialEdges, setNodes, setEdges, onSelectEdgeProp]);

  const handleConnect = useCallback(
    (connection: Connection | null) => {
      if (!connection?.source || !connection?.target || connectBusy || !onRefresh) return;
      const sourceNode = flowsMap[flow]?.nodes.find((n) => n.id === connection.source);
      let edgeLabel: string | undefined;
      if (sourceNode?.type === "decision") {
        const raw = window.prompt("Decision edge label (true/false):", "true");
        if (raw == null) return;
        const normalized = raw.trim().toLowerCase();
        if (!normalized || (normalized !== "true" && normalized !== "false")) {
          window.alert("Allowed labels: true or false.");
          return;
        }
        edgeLabel = normalized;
      }
      setConnectBusy(true);
      createFlowEdge(flow, connection.source, connection.target, edgeLabel)
        .then(() => onRefresh?.())
        .catch(() => {})
        .finally(() => setConnectBusy(false));
    },
    [flow, connectBusy, onRefresh, flowsMap]
  );

  const handleNodeDragStop = useCallback(
    (_e: unknown, node: Node) => {
      if (!onRefresh) return;
      updateNodePrompt(flow, node.id, {
        position_x: node.position.x,
        position_y: node.position.y,
      })
        .then(() => onRefresh?.())
        .catch(() => {});
    },
    [flow, onRefresh]
  );

  const handleAddNode = async () => {
    setAddError(null);
    setAddBusy(true);
    try {
      await createFlowNode(flow, {
        node_type: addForm.node_type,
        label: addForm.label,
        description: addForm.description,
        prompt: addForm.prompt,
        python_source: addForm.python_source,
        http_url: addForm.http_url,
        http_method: addForm.http_method,
        http_headers: addForm.http_headers,
        http_body: addForm.http_body,
        rag_operation: addForm.rag_operation,
        rag_body_json: addForm.rag_body_json,
        ...(addForm.node_type === "merge"
          ? {
              merge_strategy: addForm.merge_strategy,
              merge_fields: addForm.merge_fields,
              merge_key_field: addForm.merge_key_field,
            }
          : {}),
        ...(["slack", "jira", "entra", "email"].includes(addForm.node_type)
          ? {
              integration_operation: addForm.integration_operation,
              integration_params_json: addForm.integration_params_json,
              integration_credentials_json: addForm.integration_credentials_json,
            }
          : {}),
      });
      if (onRefresh) await onRefresh();
      setShowAddModal(false);
      setAddForm(emptyAddForm());
    } catch (e) {
      setAddError(e instanceof Error ? e.message : String(e));
    } finally {
      setAddBusy(false);
    }
  };

  const nodesWithSelection = useMemo(() => {
    return nodes.map((n) => ({
      ...n,
      selected: n.id === selectedId,
    }));
  }, [nodes, selectedId]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        flex: 1,
        minHeight: 0,
        minWidth: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          zIndex: 5,
          display: "flex",
          gap: 8,
          pointerEvents: "none",
        }}
      >
        {!addButtonOnHeader && (
          <button
            type="button"
            onClick={() => {
              setAddError(null);
              setShowAddModal(true);
            }}
            style={{
              pointerEvents: "auto",
              background: "#4f46e5",
              color: "white",
              border: "none",
              borderRadius: 8,
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            }}
          >
            + Add node
          </button>
        )}
        {connectBusy && (
          <span style={{ fontSize: 12, color: "#64748b", alignSelf: "center", pointerEvents: "auto" }}>
            Saving connection…
          </span>
        )}
        {!edgeButtonOnHeader && selectedEdge && onRefresh && (
          <button
            type="button"
            onClick={async () => {
              if (!selectedEdge) return;
              const { source, target } = selectedEdge;
              try {
                await deleteFlowEdge(flow, source, target);
              } catch {
                // ignore
              }
              setSelectedEdge(null);
              await onRefresh();
            }}
            style={{
              pointerEvents: "auto",
              background: "#fee2e2",
              color: "#b91c1c",
              border: "1px solid #fecaca",
              borderRadius: 8,
              padding: "6px 12px",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Delete connection
          </button>
        )}
      </div>

      <ReactFlow
        colorMode="light"
        nodes={nodesWithSelection}
        edges={edges.map((e) => ({
          ...e,
          selected: e.id === selectedEdge?.id,
        }))}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodeDragStop={handleNodeDragStop}
        onNodeClick={(_e, node) => {
          const flowNode = (node.data as StageNodeType["data"]).flowNode;
          onSelect(flowNode);
          setSelectedEdge(null);
        }}
        onEdgeClick={(_e, edge) => {
          setSelectedEdge({ id: edge.id, source: edge.source, target: edge.target });
        }}
        onPaneClick={() => {
          setSelectedEdge(null);
          onPaneDeselect?.();
        }}
        panOnDrag={[1, 2]}
        nodeTypes={{ stage: StageNode }}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable
        nodesConnectable={true}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        style={{ background: "#f1f5f9" }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#cbd5e1"
        />
      </ReactFlow>

      {showAddModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            background: "rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
          }}
          onClick={() => !addBusy && setShowAddModal(false)}
        >
          <div
            style={{
              background: "white",
              borderRadius: 12,
              padding: 24,
              maxWidth: 440,
              width: "100%",
              boxShadow: "0 20px 40px rgba(0,0,0,0.15)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 16px", fontSize: 18 }}>Add node</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Type</label>
                <select
                  value={addForm.node_type}
                  onChange={(e) => setAddForm((f) => ({ ...f, node_type: e.target.value }))}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                >
                  {NODE_TYPES_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Name (label)</label>
                <input
                  value={addForm.label}
                  onChange={(e) => setAddForm((f) => ({ ...f, label: e.target.value }))}
                  placeholder="e.g. Check logs"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Description</label>
                <textarea
                  value={addForm.description}
                  onChange={(e) => setAddForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Short step description"
                  rows={2}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical" }}
                />
              </div>
              <div>
                {!isIntegrationType && (
                  <>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Prompt (AI context)</label>
                    <textarea
                      value={addForm.prompt}
                      onChange={(e) => setAddForm((f) => ({ ...f, prompt: e.target.value }))}
                      placeholder="Instruction for the agent at this step"
                      rows={4}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical" }}
                    />
                  </>
                )}
              </div>
              {addForm.node_type === "code" && (
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Python Source</label>
                  <textarea
                    value={addForm.python_source}
                    onChange={(e) => setAddForm((f) => ({ ...f, python_source: e.target.value }))}
                    placeholder={"def run(context):\n    return {\"ok\": True}"}
                    rows={6}
                    style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                  />
                </div>
              )}
              {addForm.node_type === "http_request" && (
                <>
                  {NODE_STYLES.http_request?.description ? (
                    <p style={{ margin: 0, fontSize: 12, color: "#64748b", lineHeight: 1.45 }}>
                      {NODE_STYLES.http_request.description}
                    </p>
                  ) : null}
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>URL</label>
                    <input
                      value={addForm.http_url}
                      onChange={(e) => setAddForm((f) => ({ ...f, http_url: e.target.value }))}
                      placeholder="https://api.example.com/… (placeholders {{ context.* }})"
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Method</label>
                    <select
                      value={addForm.http_method}
                      onChange={(e) => setAddForm((f) => ({ ...f, http_method: e.target.value }))}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                    >
                      {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Headers (JSON)</label>
                    <textarea
                      value={addForm.http_headers}
                      onChange={(e) => setAddForm((f) => ({ ...f, http_headers: e.target.value }))}
                      placeholder='{"Content-Type": "application/json"}'
                      rows={3}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Body (optional)</label>
                    <textarea
                      value={addForm.http_body}
                      onChange={(e) => setAddForm((f) => ({ ...f, http_body: e.target.value }))}
                      placeholder='{"foo": "{{ context.initial.id }}"}'
                      rows={4}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                </>
              )}
              {addForm.node_type === "rag" && (
                <>
                  {NODE_STYLES.rag?.description ? (
                    <p style={{ margin: 0, fontSize: 12, color: "#64748b", lineHeight: 1.45 }}>
                      {NODE_STYLES.rag.description}
                    </p>
                  ) : null}
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Assist operation</label>
                    <select
                      value={addForm.rag_operation}
                      onChange={(e) => setAddForm((f) => ({ ...f, rag_operation: e.target.value }))}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                    >
                      <option value="similar">similar — similar tickets</option>
                      <option value="summary">summary — summarization</option>
                      <option value="suggest_steps">suggest-steps — suggested steps</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Body (JSON, optional)</label>
                    <textarea
                      value={addForm.rag_body_json}
                      onChange={(e) => setAddForm((f) => ({ ...f, rag_body_json: e.target.value }))}
                      placeholder='{"text": "{{ context.initial.description }}"}' 
                      rows={5}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                </>
              )}
              {addForm.node_type === "merge" && (
                <>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>
                      Merge strategy
                    </label>
                    <select
                      value={addForm.merge_strategy}
                      onChange={(e) => setAddForm((f) => ({ ...f, merge_strategy: e.target.value }))}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                    >
                      <option value="append">append</option>
                      <option value="zip">zip</option>
                      <option value="combine_by_key">combine_by_key</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>
                      Merge fields (JSON list)
                    </label>
                    <textarea
                      value={addForm.merge_fields}
                      onChange={(e) => setAddForm((f) => ({ ...f, merge_fields: e.target.value }))}
                      placeholder='["items","rows"]'
                      rows={5}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>
                      Merge key field (for combine_by_key)
                    </label>
                    <input
                      value={addForm.merge_key_field}
                      onChange={(e) => setAddForm((f) => ({ ...f, merge_key_field: e.target.value }))}
                      placeholder="id"
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                      disabled={addForm.merge_strategy !== "combine_by_key"}
                    />
                  </div>
                </>
              )}
              {["slack", "jira", "entra", "email"].includes(addForm.node_type) && (
                <>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Operation</label>
                    <select
                      value={addForm.integration_operation}
                      onChange={(e) => setAddForm((f) => ({ ...f, integration_operation: e.target.value }))}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0" }}
                    >
                      <option value="" disabled>
                        select…
                      </option>
                      {addForm.node_type === "slack" && (
                        <>
                          <option value="message">message</option>
                          <option value="invite">invite</option>
                        </>
                      )}
                      {addForm.node_type === "jira" && (
                        <>
                          <option value="create">create</option>
                          <option value="update">update</option>
                        </>
                      )}
                      {addForm.node_type === "entra" && (
                        <>
                          <option value="create">create</option>
                          <option value="update">update</option>
                          <option value="delete">delete</option>
                        </>
                      )}
                      {addForm.node_type === "email" && (
                        <>
                          <option value="send">send</option>
                        </>
                      )}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Params (JSON)</label>
                    <textarea
                      value={addForm.integration_params_json}
                      onChange={(e) => setAddForm((f) => ({ ...f, integration_params_json: e.target.value }))}
                      placeholder='{"channel_id":"...","text":"..."}'
                      rows={5}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 4 }}>Credentials (JSON)</label>
                    <textarea
                      value={addForm.integration_credentials_json}
                      onChange={(e) => setAddForm((f) => ({ ...f, integration_credentials_json: e.target.value }))}
                      placeholder='{"token":"..."}'
                      rows={5}
                      style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", fontFamily: "'SF Mono', Consolas, monospace" }}
                    />
                  </div>
                </>
              )}
            </div>
            {addError && (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 12px",
                  background: "#fef2f2",
                  color: "#b91c1c",
                  borderRadius: 8,
                  fontSize: 13,
                }}
              >
                {addError}
              </div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 20, justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => !addBusy && setShowAddModal(false)}
                style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #e2e8f0", background: "white", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAddNode}
                disabled={addBusy || !addForm.label.trim()}
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: addBusy ? "#94a3b8" : "#4f46e5",
                  color: "white",
                  cursor: addBusy ? "wait" : "pointer",
                  fontWeight: 600,
                }}
              >
                {addBusy ? "Saving…" : "Add"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
