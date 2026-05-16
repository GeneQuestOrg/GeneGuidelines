"""
Per-node output schema for LLM Simple: JSON w flow_definitions.output_schema → Type[BaseModel].

Format (JSON string w bazie):
{
  "fields": [
    { "name": "issue", "type": "string", "description": "...", "required": true },
    { "name": "count", "type": "integer", "required": false }
  ]
}

Dozwolone typy: string, integer, number, boolean.
"""
from __future__ import annotations

import json
import re
from typing import Any, Type

from pydantic import BaseModel, Field, create_model

_MAX_FIELDS = 32
_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_ALLOWED_TYPES = frozenset({"string", "integer", "number", "boolean"})


def _python_type(type_str: str) -> type:
    t = (type_str or "string").strip().lower()
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    raise ValueError(f"Unsupported type: {type_str!r}")


def parse_output_schema_dict(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate top-level shape; returns list of field specs or raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError("output_schema must be a JSON object")
    fields = data.get("fields")
    if not isinstance(fields, list):
        raise ValueError('output_schema must contain a "fields" array')
    if len(fields) == 0:
        raise ValueError('"fields" must contain at least one entry')
    if len(fields) > _MAX_FIELDS:
        raise ValueError(f"At most {_MAX_FIELDS} fields allowed")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise ValueError(f"fields[{i}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"fields[{i}].name must be a non-empty string")
        name = name.strip()
        if not _NAME_RE.match(name):
            raise ValueError(
                f"Invalid field name {name!r}: use letters, digits, underscore; must start with letter or _"
            )
        if name in seen:
            raise ValueError(f"Duplicate field name: {name!r}")
        seen.add(name)
        type_str = raw.get("type", "string")
        if not isinstance(type_str, str) or type_str.strip().lower() not in _ALLOWED_TYPES:
            raise ValueError(
                f"fields[{i}].type must be one of: {', '.join(sorted(_ALLOWED_TYPES))}"
            )
        desc = raw.get("description", "")
        if desc is not None and not isinstance(desc, str):
            raise ValueError(f"fields[{i}].description must be a string")
        required = raw.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(f"fields[{i}].required must be a boolean")
        out.append(
            {
                "name": name,
                "type": type_str.strip().lower(),
                "description": (desc or "").strip(),
                "required": required,
            }
        )
    return out


def build_model_from_fields(
    fields: list[dict[str, Any]],
    *,
    model_name: str = "NodeOutput",
) -> Type[BaseModel]:
    """Build a Pydantic model from validated field specs."""
    field_defs: dict[str, Any] = {}
    for f in fields:
        name = f["name"]
        py_t = _python_type(f["type"])
        desc = f.get("description") or f"name: {name}"
        if f["required"]:
            field_defs[name] = (py_t, Field(..., description=desc))
        else:
            field_defs[name] = (py_t | None, Field(default=None, description=desc))
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", model_name)[:80] or "NodeOutput"
    return create_model(safe_name, **field_defs)  # type: ignore[call-overload]


def validate_output_schema_json(raw: str) -> str:
    """
    Parse and validate JSON string. Returns canonical JSON string for storage.
    Raises ValueError with user-facing message.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("output_schema JSON is empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    fields = parse_output_schema_dict(data)
    # Dry-run: model must be buildable
    build_model_from_fields(fields, model_name="ValidationModel")
    return json.dumps({"fields": fields}, ensure_ascii=False, separators=(",", ":"))


def build_model_from_output_schema_json(raw: str | None) -> tuple[Type[BaseModel] | None, str | None]:
    """
    Build Pydantic model from DB column value.
    Returns (model, None) or (None, error_message).
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    try:
        data = json.loads(s)
        fields = parse_output_schema_dict(data)
        model = build_model_from_fields(fields, model_name="DynamicNodeOutput")
        return model, None
    except (json.JSONDecodeError, ValueError) as e:
        return None, str(e)
