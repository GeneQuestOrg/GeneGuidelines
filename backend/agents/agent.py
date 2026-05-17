"""
AI agent configuration (Pydantic AI) — the model wrapper used by node executors.

- The system prompt is composed from per-node prompts in the flow definition
  (see ``flow_prompt``).
- Loop policy (max iterations) comes from each node's config and is embedded in
  the prompt.
- Per-tool execution policy (auto/approval) is read from ``tool_catalog``; the
  interceptor only requests human approval for tools with ``execution_mode=approval``.

Requires ``OPENAI_API_KEY`` for the production profile, ``DEEPSEEK_API_KEY`` for
the deepseek profile, or ``OPENROUTER_API_KEY`` for openrouter (in ``.env`` or
environment variables).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Type

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL_NAME,
    MCP_SERVER_TIMEOUT_SEC,
    OLLAMA_BASE_URL,
    OPENAI_CLIENT_TIMEOUT_SEC,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)
from . import flow_prompt

_SUPPORTED_PROVIDERS = ("openai", "deepseek", "openrouter", "ollama")

# Default model id without provider prefix (e.g. "gpt-4o-mini" from "openai:gpt-4o-mini")
_MODEL_NAME = DEFAULT_MODEL_NAME.split(":", 1)[-1] if ":" in DEFAULT_MODEL_NAME else DEFAULT_MODEL_NAME
_DEFAULT_PROVIDER = (
    DEFAULT_MODEL_NAME.split(":", 1)[0].strip().lower()
    if ":" in DEFAULT_MODEL_NAME
    else "openai"
)

_openai_model: OpenAIChatModel | None = None
# Cache OpenAIChatModel instances by "<provider>:<model_id>"
_openai_model_by_id: dict[str, OpenAIChatModel] = {}


def _resolve_model_spec(model_spec: str) -> tuple[str, str]:
    """Split model_spec into (provider, model_id). Falls back to DEFAULT_LLM_MODEL."""
    s = (model_spec or "").strip()
    if not s:
        return (_DEFAULT_PROVIDER, _MODEL_NAME)
    if ":" in s:
        provider, name = s.split(":", 1)
        provider = provider.strip().lower()
        name = name.strip() or _MODEL_NAME
        if provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported model provider '{provider}' in spec '{model_spec}'. "
                f"Supported: {_SUPPORTED_PROVIDERS}"
            )
        return (provider, name)
    return (_DEFAULT_PROVIDER, s)


def get_openai_chat_model(model_spec: str | None) -> OpenAIChatModel:
    """Chat model for given spec (openai:<id>, deepseek:<id>, openrouter:<id>, or bare model id).

    DeepSeek and OpenRouter use OpenAI-compatible HTTP APIs; we reuse OpenAIChatModel with a custom
    AsyncOpenAI client (base_url + api_key from env).
    """
    provider, mid = _resolve_model_spec(model_spec or DEFAULT_MODEL_NAME)
    cache_key = f"{provider}:{mid}"
    if cache_key in _openai_model_by_id:
        return _openai_model_by_id[cache_key]
    from openai import AsyncOpenAI

    if provider == "deepseek":
        if not DEEPSEEK_API_KEY:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set; cannot use deepseek provider. "
                "Add DEEPSEEK_API_KEY=sk-... to .env or switch MODEL_PROFILE back to 'default'."
            )
        client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=OPENAI_CLIENT_TIMEOUT_SEC,
        )
    elif provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; cannot use openrouter provider. "
                "Add OPENROUTER_API_KEY to .env or choose another model profile."
            )
        client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            timeout=OPENAI_CLIENT_TIMEOUT_SEC,
        )
    elif provider == "ollama":
        # Ollama exposes an OpenAI-compatible API on /v1. Local-only by default,
        # so the api_key value is ignored by the server but required by the client.
        client = AsyncOpenAI(
            api_key="ollama",
            base_url=OLLAMA_BASE_URL,
            timeout=OPENAI_CLIENT_TIMEOUT_SEC,
        )
    else:
        client = AsyncOpenAI(timeout=OPENAI_CLIENT_TIMEOUT_SEC)

    m = OpenAIChatModel(mid, provider=OpenAIProvider(openai_client=client))
    _openai_model_by_id[cache_key] = m
    return m


def _get_openai_model() -> OpenAIChatModel:
    """
    Lazy-init OpenAI model.

    IMPORTANT: don't instantiate OpenAI client at import time, so the FastAPI app can start
    even when OPENAI_API_KEY is not set (e.g. for UI browsing / non-agent endpoints).
    """
    global _openai_model
    if _openai_model is not None:
        return _openai_model
    _openai_model = get_openai_chat_model(DEFAULT_MODEL_NAME)
    return _openai_model

# Backend directory (mcp_server.py lives here)
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Approval state – set by the runner before starting the agent; consumed by the tool interceptor.
approval_state: dict[str, Any] | None = None

# Fallback when the flow has no nodes.
SYSTEM_PROMPT_FALLBACK = """You are a clinical research assistant working through a workflow of named steps.
Discover available tools by calling list_available_tools() first, then use only those tools.
This flow provides an ordered list of steps (nodes); execute them in order based on each step's description.
The order and contents of steps may change between runs — always follow the map you are given.
At the end, call update_ticket_status with a summary and the steps taken. Do not invent facts.
Always respond in English."""


def build_system_prompt(flow: dict | None) -> str:
    """Build the system prompt from per-node prompts in the flow definition."""
    if not flow or not flow.get("flow_key"):
        return flow_prompt.BASE_SYSTEM_PROMPT or SYSTEM_PROMPT_FALLBACK
    out = flow_prompt.build_system_prompt_from_flow(flow["flow_key"])
    return out if out else (flow_prompt.BASE_SYSTEM_PROMPT or SYSTEM_PROMPT_FALLBACK)


async def _process_tool_call(ctx, call_tool, name: str, tool_args: dict[str, Any]):
    """Interceptor: tools listed in approval_state['approval_tools'] require human approval before running."""
    approval_tools = set((approval_state or {}).get("approval_tools") or [])
    if name not in approval_tools:
        return await call_tool(name, tool_args, None)

    state = approval_state
    if not state:
        return await call_tool(name, tool_args, None)

    service_name = tool_args.get("service_name", "")
    server_ip = tool_args.get("server_ip", "")
    reason = f"Invoke tool {name}."

    state["pending"] = {
        "tool_name": name,
        "service_name": service_name,
        "server_ip": server_ip,
        "reason": reason,
    }
    state["result"] = None
    state["event"].clear()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, state["event"].wait)

    approved = state.get("result") == "approve"
    state["pending"] = None
    state["result"] = None
    state["event"].clear()

    if not approved:
        return "Error: Human rejected this action."

    return await call_tool(name, tool_args, None)


def _make_mcp_server() -> MCPServerStdio:
    """
    Create MCP toolset instance.

    IMPORTANT: must be created in the same event loop that will run the agent,
    otherwise asyncio primitives inside the toolset (e.g. Lock) can become bound
    to a different loop (common on Windows when running the agent in a thread).
    """
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    server = MCPServerStdio(
        command=sys.executable,
        args=["-m", "backend.tools.mcp_server"],
        timeout=MCP_SERVER_TIMEOUT_SEC,
        cwd=str(PROJECT_DIR.parent),
        env=env,
        process_tool_call=_process_tool_call,
    )
    # pydantic_ai.mcp creates an asyncio.Lock that can become effectively shared and/or bound
    # to a different loop on Windows (especially after crashes/reloads). Force per-instance lock.
    try:
        fresh_lock = asyncio.Lock()
        # Set per-instance
        object.__setattr__(server, "_enter_lock", fresh_lock)
        # Also override class-level default lock (works around shared-lock behavior).
        try:
            setattr(server.__class__, "_enter_lock", fresh_lock)
        except Exception:
            pass
    except Exception:
        try:
            fresh_lock = asyncio.Lock()
            server._enter_lock = fresh_lock  # type: ignore[attr-defined]
            try:
                setattr(server.__class__, "_enter_lock", fresh_lock)
            except Exception:
                pass
        except Exception:
            pass
    return server


def get_agent(
    flow: dict | None,
    *,
    use_mcp: bool = True,
    system_prompt: str | None = None,
    model_spec: str | None = None,
    max_tokens: int | None = None,
):
    """Return an agent. When system_prompt is given, use it directly instead of querying the DB in the agent thread."""
    if system_prompt is None:
        system_prompt = build_system_prompt(flow)
    toolsets = [_make_mcp_server()] if use_mcp else []
    model = get_openai_chat_model(model_spec) if model_spec else _get_openai_model()
    model_settings = {"max_tokens": int(max_tokens)} if isinstance(max_tokens, int) and max_tokens > 0 else None
    return Agent(
        model,
        system_prompt=system_prompt,
        toolsets=toolsets,
        model_settings=model_settings,
    )


def get_simple_structured_agent(
    system_prompt: str,
    result_type: Type[BaseModel],
    *,
    model_spec: str,
    max_tokens: int | None = None,
) -> Agent:
    """LLM Call (Simple): no MCP, single structured output (Pydantic)."""
    model = get_openai_chat_model(model_spec)
    model_settings = {"max_tokens": int(max_tokens)} if isinstance(max_tokens, int) and max_tokens > 0 else None
    ag = Agent(
        model,
        system_prompt=system_prompt,
        toolsets=[],
        output_type=result_type,
        model_settings=model_settings,
    )
    return ag


# Backward-compatible default agent (flow=None → fallback prompt).
agent = get_agent(None, use_mcp=False)
