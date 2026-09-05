"""Direct OpenAI Chat Completions call with a strict JSON-schema response.

Why this bypasses pydantic-ai. The synthesis is the one artefact a parent actually
reads, so it is where a stronger model earns its cost. gpt-6-astra answers fine over
the raw API but comes back empty through pydantic-ai 1.97.0, which sends
``max_tokens`` — a parameter that model rejects in favour of
``max_completion_tokens``. Upgrading pydantic-ai is its own project: it is pinned
because ``mcp`` 2.0 broke the version above it. This module is the small, explicit
path that lets a frontier model be used now, without touching the pinned agent
stack every other flow depends on.

Deliberately narrow: one call, one schema, no tools, no retries beyond a transient
one. Anything needing agent behaviour still goes through the normal runner.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Type

import httpx
from pydantic import BaseModel

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_TIMEOUT = 600.0


def _strictify(schema: dict) -> dict:
    """Make a Pydantic JSON schema acceptable to OpenAI structured outputs.

    The API requires every object to set ``additionalProperties: false`` and to list
    every property in ``required``. Pydantic marks only non-defaulted fields
    required, so optional fields have to be listed too — nullability is expressed in
    the type, not by omission.
    """
    if not isinstance(schema, dict):
        return schema

    for key in ("$defs", "definitions", "properties"):
        for sub in (schema.get(key) or {}).values():
            _strictify(sub)
    for key in ("items", "additionalItems"):
        if key in schema:
            _strictify(schema[key])
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key) or []:
            _strictify(sub)

    # A $ref may carry no sibling keywords. Pydantic emits `{"$ref": ..., "description":
    # ...}` for a nested model field, which OpenAI rejects outright.
    if "$ref" in schema:
        for extra in [k for k in schema if k != "$ref"]:
            schema.pop(extra)
        return schema

    if schema.get("type") == "object" or "properties" in schema:
        schema["additionalProperties"] = False
        props = list((schema.get("properties") or {}).keys())
        if props:
            schema["required"] = props
    return schema


def call_structured(
    *,
    model: str,
    prompt: str,
    result_type: Type[BaseModel],
    api_key: str,
    max_completion_tokens: int = 32_000,
    system_prompt: str = "",
) -> dict[str, Any]:
    """One structured call. Returns the parsed object, or {} when the model returned
    nothing usable (which for a reasoning model usually means the token budget was
    spent on reasoning — raise ``max_completion_tokens`` rather than retrying)."""
    schema = _strictify(result_type.model_json_schema())
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": model,
        "messages": messages,
        # gpt-6-astra and the other reasoning models reject `max_tokens`; this is the
        # parameter that made the pydantic-ai path come back empty.
        "max_completion_tokens": max_completion_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": result_type.__name__,
                "strict": True,
                "schema": schema,
            },
        },
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            _ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"openai {resp.status_code}: {resp.text[:400]}")

    payload = resp.json()
    choice = (payload.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    usage = payload.get("usage") or {}
    if not content.strip():
        log.warning(
            "openai_direct: %s returned no content (finish_reason=%s, usage=%s)",
            model,
            choice.get("finish_reason"),
            usage,
        )
        return {}
    out = json.loads(content)
    out["_usage"] = usage
    return out


__all__ = ["call_structured"]
