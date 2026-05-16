"""
Pydantic request/response schemas for API – aligned with DB schema.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


# --- Agent run (structured output schema – JSON, not loose text) ---

class AgentRunResult(BaseModel):
    """Structured result of an agent run (one node or full flow). Used as output schema."""
    issue_summary: str = ""
    work_log_summary: str = ""
    diagnosis_summary: str = ""
    status: str = "not_started"  # not_started | in_progress | diagnosed
    steps_taken: list[str] = []
    tools_used: list[str] = []
    pending_approval: dict | None = None
    finished: bool = True
    error: str | None = None


# --- Ticket ---

class TicketCreate(BaseModel):
    title: str
    description: str = ""
    reporter_name: str = "User"
    category: str = "General"


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    resolution_summary: str | None = None
    diagnostic_steps: str | None = None
    reporter_name: str | None = None
    category: str | None = None


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    resolution_summary: str | None
    diagnostic_steps: str | None
    reporter_name: str
    created_at: str
    updated_at: str
    category: str


# --- Comment ---

class CommentCreate(BaseModel):
    author: str
    content: str


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author: str
    content: str
    created_at: str


# --- Tool catalog ---

class ToolCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    execution_mode: str
    scope: str
    enabled: int


class ToolCatalogUpdate(BaseModel):
    """Body for PUT /api/tools/catalog/{id} – update execution_mode."""
    execution_mode: str  # 'auto' | 'approval'


# --- Tool requests (backlog) ---

class ToolRequestCreate(BaseModel):
    name: str
    note: str = ""
    ticket_id: int | None = None
    status: str = "requested"


class ToolRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    similarity_key: str | None
    note: str | None
    ticket_id: int | None
    builder_agent_id: str | None
    created_at: str
    updated_at: str


# Backward compatibility (e.g. GET /tickets/{id}/missing-tools)
class MissingToolRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int | None
    suggested_tool_name: str
    reason: str


# --- Tool implementations ---

class ToolImplementationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    pr_number: str | None
    pr_url: str | None
    created_at: str


# --- Flows (from DB: nodes + edges) ---

class FlowNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flow_key: str
    node_id: str
    node_type: str
    label: str
    description: str | None
    prompt: str | None
    loop_policy: str
    execution_policy: str
    max_retry: int
    version: int
    updated_at: str
    position_x: float | None = None
    position_y: float | None = None
    prompt_mode: str = "agentic"
    model_name: str | None = None
    output_schema_key: str | None = None
    output_schema: str = ""
    agentic_step_close: bool = False
    python_source: str = ""
    http_url: str = ""
    http_method: str = "GET"
    http_headers: str = ""
    http_body: str = ""
    rag_operation: str = "similar"
    rag_body_json: str = ""
    merge_strategy: str = "append"
    merge_fields: str = "[]"
    merge_key_field: str = "id"
    integration_operation: str = ""
    integration_params_json: str = "{}"
    integration_credentials_json: str = ""


class FlowEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flow_key: str
    source_node_id: str
    target_node_id: str
    label: str | None = None


class FlowDefinitionResponse(BaseModel):
    flow_key: str
    nodes: list[FlowNodeResponse]
    edges: list[FlowEdgeResponse]


class FlowNodeUpdate(BaseModel):
    """Body for PUT /api/flows/{flow_key}/nodes/{node_id} – prompt and policies (all optional)."""
    prompt: str | None = None
    loop_policy: str | None = None
    execution_policy: str | None = None
    max_retry: int | None = None
    description: str | None = None
    label: str | None = None
    position_x: float | None = None
    position_y: float | None = None
    prompt_mode: str | None = None
    model_name: str | None = None
    output_schema_key: str | None = None
    output_schema: str | None = None
    agentic_step_close: bool | None = None
    python_source: str | None = None
    http_url: str | None = None
    http_method: str | None = None
    http_headers: str | None = None
    http_body: str | None = None
    rag_operation: str | None = None
    rag_body_json: str | None = None
    merge_strategy: str | None = None
    merge_fields: str | None = None
    merge_key_field: str | None = None
    integration_operation: str | None = None
    integration_params_json: str | None = None
    integration_credentials_json: str | None = None


class FlowNodeUpdateBody(BaseModel):
    """Body for PUT /api/flows/node – flow_key + node_id + fields to update in a single payload."""
    flow_key: str
    node_id: str
    prompt: str | None = None
    loop_policy: str | None = None
    execution_policy: str | None = None
    max_retry: int | None = None
    description: str | None = None
    label: str | None = None
    position_x: float | None = None
    position_y: float | None = None
    prompt_mode: str | None = None
    model_name: str | None = None
    output_schema_key: str | None = None
    output_schema: str | None = None
    agentic_step_close: bool | None = None
    python_source: str | None = None
    http_url: str | None = None
    http_method: str | None = None
    http_headers: str | None = None
    http_body: str | None = None
    rag_operation: str | None = None
    rag_body_json: str | None = None
    merge_strategy: str | None = None
    merge_fields: str | None = None
    merge_key_field: str | None = None
    integration_operation: str | None = None
    integration_params_json: str | None = None
    integration_credentials_json: str | None = None


class FlowNodeCreate(BaseModel):
    """Body for POST /api/flows/{flow_key}/nodes."""
    node_type: str = "action"
    label: str = "New node"
    description: str = ""
    prompt: str = ""
    loop_policy: str = "none"
    execution_policy: str = "auto"
    max_retry: int = 3
    python_source: str | None = None
    http_url: str | None = None
    http_method: str | None = None
    http_headers: str | None = None
    http_body: str | None = None
    rag_operation: str | None = None
    rag_body_json: str | None = None
    merge_strategy: str | None = None
    merge_fields: str | None = None
    merge_key_field: str | None = None
    integration_operation: str = ""
    integration_params_json: str = "{}"
    integration_credentials_json: str = ""


class FlowEdgeCreate(BaseModel):
    """Body for POST /api/flows/{flow_key}/edges."""
    source_node_id: str
    target_node_id: str
    label: str | None = None


# Legacy format (id, name) for compatibility
class ToolItem(BaseModel):
    name: str
    description: str = ""
    implemented: bool = True
